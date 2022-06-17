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
from distutils.dir_util import copy_tree
from multiprocessing import Pool

import pandas as pd
import requests

from asoc_utils import (
    download_report,
    get_bearer_token,
    get_download_config,
    get_scans,
    headers,
    remove_old_scans,
    wait_for_report,
)
from constants import (
    ALL,
    APP_URL_DICT,
    APPSCAN_CONFIG,
    ASOC_API_ENDPOINT,
    DEPCHECK,
    DEPCHECK_REPO,
    DEPCHECK_SCAN,
    DYNAMIC,
    HEADER_FIELDS,
    IAC_JAR,
    IAC_JAR_URL,
    MAX_TRIES,
    NETWORK_SCAN,
    PADDING,
    PENDING_STATUSES,
    PRESENCE_ID,
    REPORTS,
    SBA_JAR,
    SBA_JAR_URL,
    SCAN,
    SINGLE_DYNAMIC,
    SINGLE_STATIC,
    STATIC,
    VOL_SCAN,
)
from docker_utils import prep_containers, start_rt_container
from main_logger import main_logger

# from settings import APPSCAN_HOME
from utils import (
    cleanup,
    create_dir,
    download,
    f_logger,
    get_date_str,
    get_latest_stable_image_tags,
    parse_arguments,
    run_subprocess,
    timer,
)

# from distutils.dir_util import copy_tree


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
    # main_logger.info("Setting up environment...")
    # run_subprocess(f"cd {args.source}/Build && ./gradlew -b fullbuild.gradle setupEnvironment --stacktrace")

    # main_logger.info("Setting 3rd party libs...")
    # run_subprocess(f"cd {args.source}/Build && ./gradlew -b fullbuild.gradle unpack3p")

    # main_logger.info("Cleaning projects...")
    # run_subprocess(f"cd {args.source} && Build/gradlew clean")

    main_logger.info("Removing irx files...")
    run_subprocess(f'cd {args.source} && find . -name "*.irx" -type f -delete')

    # main_logger.info("Building projects...")
    # run_subprocess(f"cd {args.source}/Build && ./gradlew -b fullbuild.gradle fullbuild --stacktrace")


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


def call_asoc_apis_to_create_scan(file_req_header, project, project_file_name, tmpdir):
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
                        "Locale": "en-US",
                        "Execute": "true",
                        "Personal": "false",
                    }
                    res = requests.post(
                        f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer", json=data, headers=headers,
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


def create_static_scan_sba(tmpdir, file_req_header):
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

    call_asoc_apis_to_create_scan(file_req_header, "sba", project_file_name, f"{tmpdir}/SBA")


def create_static_scan_iac(tmpdir, file_req_header):
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

    call_asoc_apis_to_create_scan(file_req_header, "iac", project_file_name, f"{tmpdir}/IAC")


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

    call_asoc_apis_to_create_scan(file_req_header, project, project_file_name, tmpdir)
    process_project_message = f"FINISHED PROCESSING PROJECT: {project} - {project_file_name}"
    main_logger.info("#" * (len(process_project_message) + PADDING))
    main_logger.info(" " * int((PADDING / 2)) + process_project_message + " " * int((PADDING / 2)),)
    main_logger.info("#" * (len(process_project_message) + PADDING))
    # # call ASoC API to create the static scan
    # try:
    #     main_logger.info("Calling ASoC API to create the static scan...")

    #     with open(f"{tmpdir}/{project_file_name}.irx", "rb") as irx_file:
    #         file_data = {"fileToUpload": irx_file}
    #         finished = False
    #         try_count = 0
    #         while not finished:
    #             if try_count >= MAX_TRIES:
    #                 break
    #             try_count += 1
    #             file_upload_res = requests.post(
    #                 f"{ASOC_API_ENDPOINT}/FileUpload", files=file_data, headers=file_req_header,
    #             )
    #             main_logger.info(f"File Upload Response: {file_upload_res}")
    #             if file_upload_res.status_code == 401:
    #                 main_logger.info(
    #                     f"Token {file_req_header} expired. Generating a new one and retry..."
    #                 )
    #                 file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
    #                 main_logger.info(f"New bearer token {file_req_header}")
    #                 continue
    #             if file_upload_res.status_code == 201:
    #                 data = {
    #                     "ARSAFileId": file_upload_res.json()["FileId"],
    #                     "ScanName": project,
    #                     "AppId": SINGLE_STATIC,
    #                     "Locale": "en-US",
    #                     "Execute": "true",
    #                     "Personal": "false",
    #                 }
    #                 res = requests.post(
    #                     f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer", json=data, headers=headers,
    #                 )
    #                 if res.status_code == 401:
    #                     main_logger.info(
    #                         f"Token {file_req_header} expired. Generating a new one and retry..."
    #                     )
    #                     file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
    #                     main_logger.info(f"New bearer token {file_req_header}")
    #                     continue
    #             finished = res.status_code == 201
    #             main_logger.info(f"Response: {res.json()}")
    #         main_logger.info(
    #             f"PROJECT: {project} - {project_file_name} WAS PROCESSED SUCCESSFULLY."
    #         )
    #         print()
    # except Exception as error:
    #     main_logger.warning(traceback.format_exc())
    #     main_logger.warning(error)


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
    old_scan_status_dict = remove_old_scans(SINGLE_STATIC)

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
        # # get the latest appscan script
        # appcan_folder_name = download_and_extract_appscan(f"{tmpdir}/")

        # # update appscan
        # main_logger.info(
        #     f"Updating appscan! From {tmpdir}/appscan/{appcan_folder_name} to {APPSCAN_HOME}..."
        # )
        # copy_tree(f"{tmpdir}/appscan/{appcan_folder_name}/", APPSCAN_HOME)
        # if os.path.exists(APPSCAN_HOME):
        #     shutil.rmtree(APPSCAN_HOME)
        # shutil.copytree(f"{tmpdir}/appscan/{appcan_folder_name}/", APPSCAN_HOME)

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
        create_static_scan_sba(tmpdir, file_req_header)

        main_logger.info("Create Static Scan for IAC")
        create_static_scan_iac(tmpdir, file_req_header)

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
        # for project in projects:
        #     project = project.strip()
        #     project_file_name = project.strip().replace("/", "_")
        #     print()
        #     main_logger.info(
        #         "#" * (len(f"PROCESSING PROJECT: {project} - {project_file_name}") + PADDING)
        #     )
        #     main_logger.info(
        #         " " * int((PADDING / 2))
        #         + f"PROCESSING PROJECT: {project} - {project_file_name}"
        #         + " " * int((PADDING / 2)),
        #     )
        #     main_logger.info(
        #         "#" * (len(f"PROCESSING PROJECT: {project} - {project_file_name}") + PADDING)
        #     )

        #     # generate config file for appscan
        #     generate_appscan_config_file(args, project)
        #     main_logger.info(f"Generating {project_file_name}.irx file...")
        #     run_subprocess(
        #         f"source ~/.bashrc && appscan.sh prepare -c {APPSCAN_CONFIG_TMP} -n {project_file_name}.irx -d {tmpdir}"
        #     )

        #     # call ASoC API to create the static scan
        #     try:
        #         main_logger.info("Calling ASoC API to create the static scan...")

        #         with open(f"{tmpdir}/{project_file_name}.irx", "rb") as irx_file:
        #             file_data = {"fileToUpload": irx_file}
        #             finished = False
        #             try_count = 0
        #             while not finished:
        #                 if try_count >= MAX_TRIES:
        #                     break
        #                 try_count += 1
        #                 file_upload_res = requests.post(
        #                     f"{ASOC_API_ENDPOINT}/FileUpload",
        #                     files=file_data,
        #                     headers=file_req_header,
        #                 )
        #                 main_logger.info(f"File Upload Response: {file_upload_res.json()}")
        #                 if file_upload_res.status_code == 401:
        #                     main_logger.info(
        #                         f"Token {file_req_header} expired. Generating a new one and retry..."
        #                     )
        #                     file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
        #                     continue
        #                 if file_upload_res.status_code == 201:
        #                     data = {
        #                         "ARSAFileId": file_upload_res.json()["FileId"],
        #                         "ScanName": project,
        #                         "AppId": SINGLE_STATIC,
        #                         "Locale": "en-US",
        #                         "Execute": "true",
        #                         "Personal": "false",
        #                     }
        #                     res = requests.post(
        #                         f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer",
        #                         json=data,
        #                         headers=headers,
        #                     )
        #                     if res.status_code == 401:
        #                         main_logger.info(
        #                             f"Token {file_req_header} expired. Generating a new one and retry..."
        #                         )
        #                         file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}
        #                         continue
        #                 finished = res.status_code == 201
        #                 main_logger.info(f"Response: {res.json()}")
        #             main_logger.info(
        #                 f"PROJECT: {project} - {project_file_name} WAS PROCESSED SUCCESSFULLY."
        #             )
        #             print()
        #     except Exception as error:
        #         main_logger.warning(traceback.format_exc())
        #         main_logger.warning(error)


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

    # get the image tag
    image_tags = get_latest_stable_image_tags()

    # remove the old scans
    old_scan_status_dict = remove_old_scans(SINGLE_DYNAMIC)

    # spin up the containers (rt and db2), if
    # there is no scan in pending statuses
    for status in old_scan_status_dict.values():
        if status in PENDING_STATUSES:
            return

    # prep containers for the scans
    prep_containers(args, image_tags)

    # create the new scans
    main_logger.info(f"Create new scan for: {APP_URL_DICT}")
    for app, url in APP_URL_DICT.items():
        user = "admin" if app != "WSC" else "csmith"
        passwd = "password" if app != "WSC" else "csmith"

        # scan data
        create_scan_data = {
            "StartingUrl": url,
            "LoginUser": user,
            "LoginPassword": passwd,
            "ScanType": "Production",
            "PresenceId": PRESENCE_ID,
            "IncludeVerifiedDomains": "true",
            "HttpAuthUserName": "string",
            "HttpAuthPassword": "string",
            "HttpAuthDomain": "string",
            "OnlyFullResults": "true",
            "TestOptimizationLevel": "NoOptimization",
            "ScanName": f"{app} Scan",
            "EnableMailNotification": "false",
            "Locale": "en-US",
            "AppId": SINGLE_DYNAMIC,
            "Execute": "true",
            "Personal": "false",
        }

        # creating a new scan
        main_logger.info(f"Creating a new scan for {app}...")
        res = requests.post(
            f"{ASOC_API_ENDPOINT}/Scans/DynamicAnalyzer", json=create_scan_data, headers=headers
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
def dynamic_reports():
    """
    Generate and download dynamic reports.

    Args:
        args ([dict]): the arguments passed to the script
    """
    scans = get_scans(SINGLE_DYNAMIC)
    generated_reports = []
    for scan in scans:
        # only generate report for ready scan
        if scan["LatestExecution"]["Status"] == "Ready":
            config_data = get_download_config(scan["Name"])
            res = requests.post(
                f"{ASOC_API_ENDPOINT}/Reports/Security/Scan/{scan['Id']}",
                json=config_data,
                headers=headers,
            )
            if res.status_code == 200:
                generated_reports.append(res.json())

    for report in generated_reports:
        # wait for the report to be ready
        wait_for_report(report)

        # download the report
        download_report(DYNAMIC, report)


@timer
@f_logger
def static_reports():
    """
    Generate and download static reports.

    Args:
        args ([dict]): the arguments passed to the script
    """
    scans = get_scans(SINGLE_STATIC)
    app_name = "static_report"
    # for static reports, we will wait until all of the
    # scan in the static application to finish running
    # before we generate and download the reports
    for scan in scans:
        app_name = scan["AppName"]
        if scan["LatestExecution"]["Status"] != "Ready":
            return

    # config data for the reports
    config_data = get_download_config(app_name)

    # generate the reports for the application
    res = requests.post(
        f"{ASOC_API_ENDPOINT}/Reports/Security/Application/{SINGLE_STATIC}",
        json=config_data,
        headers=headers,
    )

    if res.status_code == 200:
        report = res.json()

        # wait for the report to be ready
        wait_for_report(report)

        # download the report
        download_report(STATIC, report)


@timer
@f_logger
def asoc_export(app_type):
    """
    Generate/export scan results.

    Args:
        app_type ([str]): type of scan
    """
    # filters
    filters = "$filter=Status%20ne%20'Fixed'%20and%20Status%20ne%20'Noise'&$orderby=ScanName"

    # prepare the header for requests
    main_logger.info("Requesting bearer token...")
    file_req_header = {"Authorization": f"Bearer {get_bearer_token()}"}

    # request the reports
    main_logger.info("Getting the reports...")
    app_id = SINGLE_STATIC if app_type == STATIC else SINGLE_DYNAMIC
    res = requests.get(
        f"{ASOC_API_ENDPOINT}/Issues/Application/{app_id}?{filters}", headers=file_req_header
    )
    if res.status_code == 200:
        reports_dir_path = f"reports/{get_date_str()}/{app_type}"
        create_dir(reports_dir_path)
        with open(f"{reports_dir_path}/issues.json", "w") as file:
            json.dump(res.json(), file)
        with open(f"{reports_dir_path}/issues.csv", "w") as file:
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
        read_file = pd.read_csv(f"{reports_dir_path}/issues.csv")

        main_logger.info("Export to excel...")
        read_file.to_excel(f"{reports_dir_path}/issues.xlsx", index=None, header=True)

        copy_tree(f"reports/{get_date_str()}/{app_type}", f"reports/latest/{app_type}")


@timer
@f_logger
def get_reports(args):
    """Get the reports for the scans

    Args:
        args ([dict]): the arguments passed to the script
    """
    if args.type == ALL:
        static_reports()
        dynamic_reports()
        asoc_export(DYNAMIC)
        asoc_export(STATIC)
    elif args.type == STATIC:
        static_reports()
        asoc_export(STATIC)
    elif args.type == DYNAMIC:
        dynamic_reports()
        asoc_export(DYNAMIC)

    # # copy reports to output directory
    # run_subprocess(f"rsync -a -v --ignore-existing {os.getcwd()}/reports {args.output}")


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
        # get the image tag
        image_tags = get_latest_stable_image_tags()

        # start runtime container
        try:
            for image_tag in image_tags:
                print()
                main_logger.info("#" * (len(f"Trying {image_tag}") + PADDING))
                main_logger.info(
                    " " * int((PADDING / 2)) + f"Trying {image_tag}" + " " * int((PADDING / 2))
                )
                main_logger.info("#" * (len(f"Trying {image_tag}") + PADDING))
                try:
                    start_rt_container(args, image_tag, rt_name=DEPCHECK_SCAN)
                    break
                except Exception as error:
                    main_logger.warning(error)
                    main_logger.info("Skipping to the next tag...")
                    continue
        except Exception as error:
            main_logger.warning(error)

        # build the ear
        main_logger.info("Building ear file...")
        run_subprocess(
            f'docker exec {DEPCHECK_SCAN} bash -lc "buildear -warfiles=smcfs,sbc,sma,isccs"'
        )

        # creating the source dir
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:

            # copy the ear to tempdir
            main_logger.info("Copying the ear to tempdir...")
            run_subprocess(
                f"docker cp {DEPCHECK_SCAN}:/opt/ssfs/runtime/external_deployments/smcfs.ear {tmpdir}"
            )

            # extract war files from the ear
            run_subprocess(f"cd {tmpdir} && unzip smcfs.ear *.war")

            # extract jars
            apps = ["smcfs", "sma", "sbc", "isccs", "wsc"]

            create_dir(f"{tmpdir}/3rdpartyship")
            for app in apps:
                if app == "smcfs":
                    run_subprocess(
                        f"cd {tmpdir} && mkdir {app}jarsfolder && unzip -o -j smcfs.war yfscommon/* -d {app}jarsfolder/ -x  yfscommon/platform* -x yfscommon/smcfs* -x yfscommon/*.properties -x yfscommon/*ui.jar -x yfscommon/yantra* -x yfscommon/scecore* -x yfscommon/yc*"
                    )
                else:
                    run_subprocess(
                        f"cd {tmpdir} && mkdir {app}jarsfolder && unzip -o -j sma.war WEB-INF/lib/* -d {app}jarsfolder/ -x  WEB-INF/lib/platform*"
                    )
                run_subprocess(f"cp -R {tmpdir}/{app}jarsfolder/* {tmpdir}/3rdpartyship")

            # download the latest depcheck
            download_depcheck_tool(tmpdir)

            # run dependency check
            reports_dir_path = f"reports/{get_date_str()}/{args.mode}"
            create_dir(reports_dir_path)
            run_subprocess(
                f"{tmpdir}/dependency-check/bin/dependency-check.sh -s {tmpdir}/3rdpartyship -o {reports_dir_path}/dependency_report.html --suppression {os.getcwd()}/suppressions.xml"
            )
            copy_tree(f"reports/{get_date_str()}/{args.mode}", f"reports/latest/{args.mode}")

            # # copy reports to output directory
            # run_subprocess(f"rsync -a -v --ignore-existing {os.getcwd()}/reports {args.output}")

    except Exception as error:
        main_logger.warning(traceback.format_exc())
        main_logger.warning(error)
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN}")
        raise
    finally:
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN}")


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
