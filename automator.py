""" Automator """
import csv
import io
import json
import os
import pathlib
import sys
import tempfile
import time
import traceback
import zipfile
from datetime import datetime
from distutils.dir_util import copy_tree
from multiprocessing import Pool

import pandas as pd
import requests

from asoc_utils import (
    download_report,
    get_asoc_req_headers,
    get_bearer_token,
    get_download_config,
    get_scans,
    remove_old_scans,
    start_asoc_presence,
    wait_for_report,
)
from constants import (
    ALL,
    APP_URL_DICT,
    APPSCAN_CONFIG,
    APPSCAN_CONFIG_OP,
    ASOC_API_ENDPOINT,
    DEPCHECK,
    DEPCHECK_REPO,
    DEPCHECK_SCAN,
    DYNAMIC,
    HEADER_FIELDS,
    IAC_JAR,
    IAC_JAR_URL,
    MAX_TRIES,
    PADDING,
    PENDING_STATUSES,
    REPORT_FILE_TYPES,
    REPORTS,
    RT_SCAN,
    SBA_JAR,
    SBA_JAR_URL,
    SCAN,
    SINGLE_DYNAMIC,
    SINGLE_STATIC,
    STATIC,
)
from docker_utils import cleanup_runtime_container, start_app_container, start_depcheck_container
from main_logger import main_logger
from utils import (
    cleanup,
    create_dir,
    download,
    f_logger,
    get_date_str,
    get_latest_image,
    parse_arguments,
    run_subprocess,
    timer,
    update_config_file,
    upload_reports_to_artifactory,
)


# ********************************* #
# *        STATIC SCAN PREP       * #
# ********************************* #
@timer
@f_logger
def get_projects():
    """
    Get the list of projects to scan.

    Returns:
        [list]: list of the oms projects to scan
    """
    projects = []
    with open("projects.list", "r") as file:
        projects = file.readlines()
    return projects


@timer
@f_logger
def build_source_code(args):
    """
    Build the source code to prep for the scans.

    Args:
        args ([dict]): the arguments passed to the script
    """
    main_logger.info("Removing irx files...")
    run_subprocess(f'cd {args.source} && find . -name "*.irx" -type f -delete')


def generate_appscan_config_file(args, project, project_file_name):
    """
    Generate appscan config file.

    Args:
        args ([dict]): the arguments passed to the script
        project ([str]): the project name
    """
    with open(APPSCAN_CONFIG) as reader:
        text = reader.read().replace("PROJECT_PATH", f"{args.source_working}/{project.strip()}")
    if project == "afc.product/platform_afc":
        with open(f"appscan-config-{project_file_name}-afc.xml", "w") as writer:
            writer.write(text)
    else:
        with open(f"appscan-config-{project_file_name}-tmp.xml", "w") as writer:
            writer.write(text)


def call_asoc_apis_to_create_scan(
    file_req_header, project, project_file_name, tmpdir, asoc_headers
):
    """
    Call AppScan API to create the static scan

    Args:
        file_req_header: request header
        project: project name
        project_file_name: project file name for uploading
        tmpdir: temporary directory
    """
    try:
        main_logger.info(f"Calling ASoC API to create the static scan for {project}...")

        with open(f"{tmpdir}/{project_file_name}.irx", "rb") as irx_file:
            file_data = {"fileToUpload": irx_file}
            finished = False
            try_count = 0
            while not finished:
                if try_count >= MAX_TRIES:
                    break
                try_count += 1
                main_logger.info(f"TRYING #{try_count} OF {MAX_TRIES}...")
                try:
                    file_upload_res = requests.post(
                        f"{ASOC_API_ENDPOINT}/FileUpload", files=file_data, headers=file_req_header,
                    )
                    main_logger.info(f"File Upload Response: {file_upload_res}")
                    main_logger.info(file_upload_res.json())
                except Exception as error:
                    main_logger.warning(f"Error with File Upload: {error}")

                if file_upload_res.status_code == 400:
                    main_logger.info("Error when uploading IRX file")
                    main_logger.info(file_upload_res.json())
                    main_logger.info("Retrying...")
                    continue

                if file_upload_res.status_code == 401:
                    main_logger.info(
                        f"Token {file_req_header} expired. Generating a new one and retry..."
                    )
                    file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
                    main_logger.info(f"New bearer token {file_req_header}")
                    continue

                if file_upload_res.status_code == 201:
                    data = {
                        "ARSAFileId": file_upload_res.json()["FileId"],
                        "ScanName": project,
                        "AppId": SINGLE_STATIC,
                        "Locale": "en",
                        "Execute": True,
                        "Personal": False,
                    }

                    # payload
                    main_logger.info(f"Payload: \n{data}\n")

                    res = requests.post(
                        f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer",
                        json=data,
                        headers=asoc_headers,
                    )
                    if res.status_code == 401:
                        main_logger.info(
                            f"Token {file_req_header} expired. Generating a new one and retry..."
                        )
                        file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
                        main_logger.info(f"New bearer token {file_req_header}")
                        continue
                finished = res.status_code == 201
                main_logger.info(f"Response: {res.json()}")
            main_logger.info(
                f"PROJECT: {project} - {project_file_name} WAS PROCESSED SUCCESSFULLY.\n"
            )
    except Exception as error:
        main_logger.warning(traceback.format_exc())
        main_logger.warning(error)


def create_static_scan_operator(args, file_req_header):
    """
    Create static scan for operator project
    """

    main_logger.info("Generating appscan config file...")
    project_file_name = "ibm-oms-operator"
    with open(APPSCAN_CONFIG_OP) as reader:
        text = reader.read().replace("PROJECT_PATH", f"{args.source_operator}")
    with open(f"appscan-config-{project_file_name}-tmp.xml", "w") as writer:
        writer.write(text)

    main_logger.info(f"Generating {project_file_name}.irx file...")
    run_subprocess(
        f"source ~/.bashrc && appscan.sh prepare -c appscan-config-{project_file_name}-tmp.xml -n {project_file_name}.irx -d {args.source_operator}"
    )

    call_asoc_apis_to_create_scan(
        file_req_header,
        "ibm-oms-operator",
        project_file_name,
        f"{args.source_operator}",
        args.asoc_headers,
    )


def create_static_scan_sba(args, tmpdir, file_req_header):
    """
    Create static scan for sba project

    Args:
        tmpdir (str): temporary directory
    """
    main_logger.info("Create a temporary directory for the jar...")
    pathlib.Path(f"{tmpdir}/SBA").mkdir(parents=True, exist_ok=True)

    main_logger.info(f"Downloading {SBA_JAR}...")
    download(SBA_JAR_URL, SBA_JAR, f"{tmpdir}/SBA")

    main_logger.info("Generating appscan config file...")
    project_file_name = "sba"
    with open(APPSCAN_CONFIG) as reader:
        text = reader.read().replace("PROJECT_PATH", f"{tmpdir}/SBA")
    with open(f"appscan-config-{project_file_name}-tmp.xml", "w") as writer:
        writer.write(text)

    main_logger.info(f"Generating {project_file_name}.irx file...")
    run_subprocess(
        f"source ~/.bashrc && appscan.sh prepare -c appscan-config-{project_file_name}-tmp.xml -n {project_file_name}.irx -d {tmpdir}/SBA"
    )

    call_asoc_apis_to_create_scan(
        file_req_header, "sba", project_file_name, f"{tmpdir}/SBA", args.asoc_headers
    )


def create_static_scan_iac(args, tmpdir, file_req_header):
    """
    Create static scan for IAC project

    Args:
        tmpdir (str): temporary directory
    """
    main_logger.info("Create a temporary directory for the jar...")
    pathlib.Path(f"{tmpdir}/IAC").mkdir(parents=True, exist_ok=True)

    main_logger.info(f"Downloading {IAC_JAR}...")
    download(IAC_JAR_URL, IAC_JAR, f"{tmpdir}/IAC")

    main_logger.info("Generating appscan config file...")
    project_file_name = "iac"
    with open(APPSCAN_CONFIG) as reader:
        text = reader.read().replace("PROJECT_PATH", f"{tmpdir}/IAC")
    with open(f"appscan-config-{project_file_name}-tmp.xml", "w") as writer:
        writer.write(text)

    main_logger.info(f"Generating {project_file_name}.irx file...")
    run_subprocess(
        f"source ~/.bashrc && appscan.sh prepare -c appscan-config-{project_file_name}-tmp.xml -n {project_file_name}.irx -d {tmpdir}/IAC"
    )

    call_asoc_apis_to_create_scan(
        file_req_header, "iac", project_file_name, f"{tmpdir}/IAC", args.asoc_headers
    )


def create_static_scan(args, project, tmpdir, file_req_header):
    """
    Create static scan
    """
    project = project.strip()
    project_file_name = project.strip().replace("/", "_")
    print()
    process_project_message = f"PROCESSING PROJECT: {project} - {project_file_name}"
    main_logger.info("#" * (len(process_project_message) + PADDING))
    main_logger.info(" " * int((PADDING / 2)) + process_project_message + " " * int((PADDING / 2)),)
    main_logger.info("#" * (len(process_project_message) + PADDING))

    # generate config file for appscan
    generate_appscan_config_file(args, project, project_file_name)
    main_logger.info(f"Generating {project_file_name}.irx file...")
    run_subprocess(
        f"source ~/.bashrc && appscan.sh prepare -c appscan-config-{project_file_name}-tmp.xml -n {project_file_name}.irx -d {tmpdir}"
    )

    call_asoc_apis_to_create_scan(
        file_req_header, project, project_file_name, tmpdir, args.asoc_headers
    )
    process_project_message = f"FINISHED PROCESSING PROJECT: {project} - {project_file_name}"
    main_logger.info("#" * (len(process_project_message) + PADDING))
    main_logger.info(" " * int((PADDING / 2)) + process_project_message + " " * int((PADDING / 2)),)
    main_logger.info("#" * (len(process_project_message) + PADDING))


@timer
@f_logger
def static_scan(args):
    """
    Prepare and run the static scan.

    Args:
        args ([dict]): the arguments passed to the script
    """

    # prepare the header for requests
    file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}

    # remove the old scans
    old_scan_status_dict = remove_old_scans(SINGLE_STATIC, args.asoc_headers)

    # build source code
    main_logger.info("Building source code...")
    build_source_code(args)

    # read the list of projects to scan
    main_logger.info("Getting the projects...")
    projects = get_projects()

    # the below block of code would do:
    # - create tempdir to store the config files
    # - go through the list of projects
    # - generate the irx file for each project
    # - upload the generated irx file to ASoC
    # - create and execute the static scan
    with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:

        # if any of the old scan still pending, return
        for project in projects:
            project = project.strip()
            if (
                project in old_scan_status_dict
                and old_scan_status_dict[project] in PENDING_STATUSES
            ):
                main_logger.info(f"{project} is PENDING/RUNNING")
                return

        main_logger.info("Create Static Scan for SBA")
        create_static_scan_sba(args, tmpdir, file_req_header)

        main_logger.info("Create Static Scan for IAC")
        create_static_scan_iac(args, tmpdir, file_req_header)

        main_logger.info("Create Static Scan for Operator")
        create_static_scan_operator(args, file_req_header)

        main_logger.debug(f"PROJECTS TO SCAN: {projects}")
        processes = []
        pool = Pool(processes=3)
        for project in projects:
            static_scan_args = (args, project, tmpdir, file_req_header)
            results = pool.apply_async(create_static_scan, static_scan_args)
            processes.append(results)
            time.sleep(5)
        for process in processes:
            process.get()


# ********************************* #
# *       DYNAMIC SCAN PREP       * #
# ********************************* #
@timer
@f_logger
def dynamic_scan(args):
    """
    Prepare and run the dynamic scan.

    Args:
        args ([dict]): the arguments passed to the script
    """

    # update configs
    configs_dir = f"{os.getcwd()}/app_configs"
    update_config_file(f"{configs_dir}/server.xml")
    update_config_file(f"{configs_dir}/system_overrides.properties")

    # get the image tag
    latest_image = get_latest_image()

    # remove the old scans
    old_scan_status_dict = remove_old_scans(SINGLE_DYNAMIC, args.asoc_headers)

    # spin up the containers (rt and db2), if
    # there is no scan in pending statuses
    for status in old_scan_status_dict.values():
        if status in PENDING_STATUSES:
            return

    # start ASoC presense
    start_asoc_presence()

    # start the app container for the scans
    start_app_container(latest_image)

    # create the new scans
    main_logger.info(f"Create new scan for: {APP_URL_DICT}")
    for app, url in APP_URL_DICT.items():
        user = "admin" if app != "WSC" else "csmith"
        passwd = "password" if app != "WSC" else "csmith"

        # scan data
        create_scan_data = {
            "ScanType": "Staging",
            "PresenceId": os.environ.get("PRESENCE_ID"),
            "IncludeVerifiedDomains": False,
            "StartingUrl": url,
            "LoginUser": user,
            "LoginPassword": passwd,
            "ExtraField": "",
            "HttpAuthUserName": user,
            "HttpAuthPassword": passwd,
            "OnlyFullResults": True,
            "TestOptimizationLevel": "NoOptimization",
            "ThreadNum": 5,
            "ScanName": f"{app} Scan",
            "EnableMailNotification": False,
            "Locale": "en",
            "AppId": SINGLE_DYNAMIC,
            "Execute": True,
            "Personal": False,
            "UseAutomaticTimeout": True,
            "FullyAutomatic": False,
        }

        # payload
        main_logger.info(f"Payload: \n{create_scan_data}\n")

        # creating a new scan
        main_logger.info(f"Creating a new scan for {app}...")
        res = requests.post(
            f"{ASOC_API_ENDPOINT}/Scans/DynamicAnalyzer",
            json=create_scan_data,
            headers=args.asoc_headers,
        )
        main_logger.debug(res)


@timer
@f_logger
def run_scan(args):
    """
    Run the scans. This can run either static or dynamic or both

    Args:
        args ([dict]): the arguments passed to the script
    """
    if args.type == ALL:
        dynamic_scan(args)
        static_scan(args)
    elif args.type == STATIC:
        static_scan(args)
    else:
        dynamic_scan(args)


# ********************************* #
# *            REPORTS            * #
# ********************************* #
@timer
@f_logger
def dynamic_reports(args):
    """
    Generate and download dynamic reports.

    Args:
        args ([dict]): the arguments passed to the script
    """
    scans = get_scans(SINGLE_DYNAMIC, args.asoc_headers)
    generated_reports = []
    all_done = True
    for scan in scans:
        # only generate report for ready scan
        if scan["LatestExecution"]["Status"] == "Ready":
            for report_file_type in REPORT_FILE_TYPES:
                config_data = get_download_config(scan["Name"], report_file_type)
                res = requests.post(
                    f"{ASOC_API_ENDPOINT}/Reports/Security/Scan/{scan['Id']}",
                    json=config_data,
                    headers=args.asoc_headers,
                )
                if res.status_code == 200:
                    generated_reports.append(res.json())
        else:
            all_done = False

    # clean up when all of the scans complete
    if all_done:
        cleanup_runtime_container(RT_SCAN)

    for report in generated_reports:
        # wait for the report to be ready
        report_data = wait_for_report(report, args.asoc_headers)

        # download the report
        download_report(DYNAMIC, report_data)

    # upload reports to artifactory
    upload_reports_to_artifactory(DYNAMIC, f"reports/{args.date_str}/{DYNAMIC}", args.timestamp)


@timer
@f_logger
def static_reports(args):
    """
    Generate and download static reports.

    Args:
        args ([dict]): the arguments passed to the script
    """
    scans = get_scans(SINGLE_STATIC, args.asoc_headers)
    app_name = "static_report"
    # for static reports, we will wait until all of the
    # scan in the static application to finish running
    # before we generate and download the reports
    for scan in scans:
        app_name = scan["AppName"]
        if scan["LatestExecution"]["Status"] != "Ready":
            return

    for report_file_type in REPORT_FILE_TYPES:

        # config data for the reports
        config_data = get_download_config(app_name, report_file_type)

        # generate the reports for the application
        res = requests.post(
            f"{ASOC_API_ENDPOINT}/Reports/Security/Application/{SINGLE_STATIC}",
            json=config_data,
            headers=args.asoc_headers,
        )

        if res.status_code == 200:
            report = res.json()

            # wait for the report to be ready
            report_data = wait_for_report(report, args.asoc_headers)

            # download the report
            download_report(STATIC, report_data)

    # upload reports to artifactory
    upload_reports_to_artifactory(STATIC, f"reports/{args.date_str}/{STATIC}", args.timestamp)


@timer
@f_logger
def asoc_export(args, app_type, full_report=False):
    """
    Generate/export scan results.

    Args:
        app_type ([str]): type of scan
    """
    # filters
    if full_report is not True:
        filters = "$filter=Status%20ne%20'Fixed'%20and%20Status%20ne%20'Noise'&$orderby=ScanName"

    # prepare the header for requests
    main_logger.info("Requesting bearer token...")
    file_req_header = {"Authorization": f"Bearer {get_bearer_token()}", "User-Agent": "Mozilla/5.0"}

    # request the reports
    main_logger.info("Getting the reports...")
    app_id = SINGLE_STATIC if app_type == STATIC else SINGLE_DYNAMIC
    if full_report is True:
        res = requests.get(
            f"{ASOC_API_ENDPOINT}/Issues/Application/{app_id}",
            headers=file_req_header,
            timeout=5400,
        )
    else:
        res = requests.get(
            f"{ASOC_API_ENDPOINT}/Issues/Application/{app_id}?{filters}", headers=file_req_header
        )
    main_logger.info(res)
    if res.status_code == 200:
        reports_dir_path = f"reports/{args.date_str}/{app_type}"
        create_dir(reports_dir_path)

        report_file_name = "issues" if full_report is True else "issues_filtered"

        with open(f"{reports_dir_path}/{report_file_name}.json", "w") as file:
            json.dump(res.json(), file)
        with open(f"{reports_dir_path}/{report_file_name}.csv", "w") as file:
            csv_writer = csv.writer(file)
            csv_writer.writerow(HEADER_FIELDS)
            for item in res.json()["Items"]:
                csv_writer.writerow(
                    [
                        item["ScanName"],
                        item["DateCreated"],
                        item["DiscoveryMethod"],
                        item["Scanner"],
                        "component",
                        "intext",
                        item["ThreatClassId"],
                        item["Severity"],
                        "asv",
                        "ase",
                        "asve",
                        item["IssueType"],
                        f"{item['SourceFile']} : {item['Location']}",
                        item["Line"],
                        "dispo",
                        "expl",
                        "trgt",
                        "compen",
                        item["Cve"],
                        "psirt",
                        item["Cvss"],
                        item["Status"],
                        item["Id"],
                    ]
                )

        main_logger.info("Export to CSV...")
        read_file = pd.read_csv(f"{reports_dir_path}/{report_file_name}.csv")

        main_logger.info("Export to excel...")
        read_file.to_excel(f"{reports_dir_path}/{report_file_name}.xlsx", index=None, header=True)

        copy_tree(f"reports/{args.date_str}/{app_type}", f"reports/latest/{app_type}")


@timer
@f_logger
def get_reports(args):
    """Get the reports for the scans

    Args:
        args ([dict]): the arguments passed to the script
    """
    if args.type == ALL:
        static_reports(args)
        dynamic_reports(args)
        asoc_export(args, DYNAMIC)
        asoc_export(args, STATIC)
        asoc_export(args, STATIC, full_report=True)
    elif args.type == STATIC:
        static_reports(args)
        asoc_export(args, STATIC)
        asoc_export(args, STATIC, full_report=True)
    elif args.type == DYNAMIC:
        dynamic_reports(args)
        asoc_export(args, DYNAMIC)


# ********************************* #
# *           DEPCHECK            * #
# ********************************* #
@timer
@f_logger
def download_depcheck_tool(download_dir):
    """
    Download depcheck tool.

    Args:
        download_dir ([str]): the directory to download the depcheck tool to
    """
    main_logger.info("Downloading updated dependency check tool...")
    res = requests.get(DEPCHECK_REPO)
    tag_name = res.json()["tag_name"].replace("v", "")
    download_url = f"https://github.com/jeremylong/DependencyCheck/releases/download/v{tag_name}/dependency-check-{tag_name}-release.zip"
    res = requests.get(download_url, allow_redirects=True)
    zip_file = zipfile.ZipFile(io.BytesIO(res.content))
    zip_file.extractall(f"{download_dir}")
    run_subprocess(f"chmod +x {download_dir}/dependency-check/bin/dependency-check.sh")


@timer
@f_logger
def depcheck(args):
    """
    Run and export report for the dependency check.

    Args:
        args ([dict]): the arguments passed to the script
    """
    try:

        # get the latest image
        latest_image = get_latest_image()
        assert latest_image is not None

        # start runtime container
        try:
            start_depcheck_container(latest_image, rt_name=DEPCHECK_SCAN)
        except Exception as error:
            main_logger.warning(error)

        # creating the source dir
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:

            third_party_jars = "3rdpartyjars"

            # build the ear
            main_logger.info("Getting jars to scans...")
            run_subprocess(
                f'docker exec {DEPCHECK_SCAN} bash -lc \'cd /opt/ibm/wlp/usr/servers/defaultServer/dropins/smcfs.ear/ && mkdir -p mkdir ../{third_party_jars} && rm -rf ../{third_party_jars}/* && for file in $(find ./*/ -type f -name "*.jar" -not -path "*ui.jar" -not -path "*platform_*" -not -path "*xapi.jar" -not -path "*yfscommon*icons*" -not -path "*yfscommon*y*"); do cp -vf $file /opt/ibm/wlp/usr/servers/defaultServer/dropins/{third_party_jars}/; done\''
            )

            # copy the 3rd party jars to temp dir
            main_logger.info("Copying 3rd party jars to tempdir...")
            run_subprocess(
                f"docker cp {DEPCHECK_SCAN}:/opt/ibm/wlp/usr/servers/defaultServer/dropins/{third_party_jars}/ {tmpdir}/"
            )

            # download the latest depcheck
            main_logger.info("Download the latest depcheck...")
            download_depcheck_tool(tmpdir)

            # run dependency check
            main_logger.info("Running the scan...")
            reports_dir_path = f"reports/{args.date_str}/{args.mode}"
            create_dir(reports_dir_path)
            run_subprocess(
                f"{tmpdir}/dependency-check/bin/dependency-check.sh -s {tmpdir}/{third_party_jars} -o {reports_dir_path}/dependency_report.html --suppression {os.getcwd()}/suppressions.xml"
            )
            copy_tree(f"reports/{args.date_str}/{args.mode}", f"reports/latest/{args.mode}")

            # upload reports to artifactory
            upload_reports_to_artifactory(
                DEPCHECK, f"reports/{args.date_str}/{DEPCHECK}", args.timestamp
            )

            # clean up depcheck container
            cleanup_runtime_container(DEPCHECK_SCAN)

    except Exception as error:
        main_logger.warning(traceback.format_exc())
        main_logger.warning(error)
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN} 2> /dev/null")
        run_subprocess("docker volume prune -f 2> /dev/null")
        raise
    finally:
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN} 2> /dev/null")
        run_subprocess("docker volume prune -f 2> /dev/null")


# ********************************* #
# *             MAIN              * #
# ********************************* #
@timer
@f_logger
def main():
    """
    Main
    """
    try:
        args = parse_arguments()
        args.date_str = get_date_str()
        args.timestamp = datetime.today().strftime("%y%m%d_%H%m")
        args.asoc_headers = get_asoc_req_headers()
        main_logger.info(args)
        if args.mode == SCAN:
            run_scan(args)
        elif args.mode == REPORTS:
            get_reports(args)
        elif args.mode == DEPCHECK:
            depcheck(args)
    except Exception as error:
        main_logger.info(error)
        cleanup()
        raise


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as _:
        sys.exit(-1)
