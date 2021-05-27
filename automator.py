import io
import logging
import os
import tempfile
import time
import traceback
import zipfile

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
    APPSCAN_CONFIG_TMP,
    ASOC_API_ENDPOINT,
    DEPCHECK,
    DEPCHECK_REPO,
    DEPCHECK_SCAN,
    DYNAMIC,
    PENDING_STATUSES,
    PRESENCE_ID,
    REPORTS,
    SCAN,
    SINGLE_DYNAMIC,
    SINGLE_STATIC,
    STATIC,
)
from settings import JFROG_APIKEY
from docker_utils import prep_containers, start_rt_container
from main_logger import main_logger
from utils import (
    create_dir,
    get_date_str,
    get_latest_stable_image_tag,
    logger,
    parse_arguments,
    run_subprocess,
    timer,
)


# ********************************* #
# *        STATIC SCAN PREP       * #
# ********************************* #
@timer
@logger
def get_projects():
    """
    Get the list of projects to scan.

    Returns:
        [list]: list of the oms projects to scan
    """
    projects = []
    with open("projects.list", "r") as f:
        projects = f.readlines()
    return projects


@timer
@logger
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

    main_logger.info("Cleaning projects...")
    run_subprocess(f"cd {args.source} && Build/gradlew clean")

    main_logger.info("Removing irx files...")
    run_subprocess(f'cd {args.source} && find . -name "*.irx" -type f -delete')

    # main_logger.info("Building projects...")
    # run_subprocess(f"cd {args.source}/Build && ./gradlew -b fullbuild.gradle fullbuild --stacktrace")


def generate_appscan_config_file(args, project):
    """
    Generate appscan config file.

    Args:
        args ([dict]): the arguments passed to the script
        project ([str]): the project name
    """
    with open(APPSCAN_CONFIG) as r:
        text = r.read().replace("PROJECT_PATH", f"{args.source}/{project.strip()}")
    with open(APPSCAN_CONFIG_TMP, "w") as w:
        w.write(text)


@timer
@logger
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
    main_logger.info(f"Building source code...")
    build_source_code(args)

    # read the list of projects to scan
    main_logger.info(f"Getting the projects...")
    projects = get_projects()

    # the below block of code would do:
    # - create tempdir to store the config files
    # - go through the list of projects
    # - generate the irx file for each project
    # - upload the generated irx file to ASoC
    # - create and execute the static scan
    with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
        main_logger.debug(f"PROJECTS TO SCAN: {projects}")
        for project in projects:
            project = project.strip()
            project_file_name = project.strip().replace("/", "_")
            main_logger.info("####################################################")
            main_logger.info(f"PROCESSING PROJECT: {project} - {project_file_name}")
            main_logger.info("####################################################")

            # if the old scan still pending, skip
            if (
                project in old_scan_status_dict
                and old_scan_status_dict[project] in PENDING_STATUSES
            ):
                continue

            # generate config file for appscan
            generate_appscan_config_file(args, project)
            main_logger.info(f"Generating {project_file_name}.irx file...")
            run_subprocess(
                f"source ~/.bashrc && appscan.sh prepare -c {APPSCAN_CONFIG_TMP} -n {project_file_name}.irx -d {tmpdir}"
            )

            # call ASoC API to create the static scan
            try:
                main_logger.info(f"Calling ASoC API to create the static scan...")
                with open(f"{tmpdir}/{project_file_name}.irx", "rb") as irx_file:
                    file_data = {"fileToUpload": irx_file}

                    res = requests.post(
                        f"{ASOC_API_ENDPOINT}/FileUpload", files=file_data, headers=file_req_header
                    )
                    if res.status_code == 201:
                        data = {
                            "ARSAFileId": res.json()["FileId"],
                            "ScanName": project,
                            "AppId": SINGLE_STATIC,
                            "Locale": "en-US",
                            "Execute": "true",
                            "Personal": "false",
                        }
                        res = requests.post(
                            f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer", json=data, headers=headers
                        )
                    main_logger.info(
                        f"Project: {project} - {project_file_name} was processed successfully."
                    )
                    main_logger.info(f"Response: {res.json()}")
                    main_logger.info("####################################################")
            except Exception as e:
                main_logger.warning(traceback.format_exc())
                main_logger.warning(e)


# ********************************* #
# *       DYNAMIC SCAN PREP       * #
# ********************************* #
@timer
@logger
def dynamic_scan(args):
    """
    Prepare and run the dynamic scan.

    Args:
        args ([dict]): the arguments passed to the script
    """

    # get the image tag
    image_tag = get_latest_stable_image_tag()

    # remove the old scans
    old_scan_status_dict = remove_old_scans(SINGLE_DYNAMIC)

    # spin up the containers (rt and db2), if
    # there is no scan in pending statuses
    for status in old_scan_status_dict.values():
        if status in PENDING_STATUSES:
            return

    # prep containers for the scans
    prep_containers(args, image_tag)

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
@logger
def run_scan(args):
    """
    Run the scans. This can run either static or dynamic or both

    Args:
        args ([dict]): the arguments passed to the script
    """
    if args.type == ALL:
        static_scan(args)
        dynamic_scan(args)
    elif args.type == STATIC:
        static_scan(args)
    else:
        dynamic_scan(args)


# ********************************* #
# *            REPORTS            * #
# ********************************* #
@timer
@logger
def dynamic_reports(args):
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
@logger
def static_reports(args):
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
@logger
def get_reports(args):
    """Get the reports for the scans

    Args:
        args ([dict]): the arguments passed to the script
    """
    if args.type == ALL:
        static_reports(args)
        dynamic_reports(args)
    elif args.type == STATIC:
        static_reports(args)
    elif args.type == DYNAMIC:
        dynamic_reports(args)

    # copy reports to output directory
    run_subprocess(f"rsync -a -v --ignore-existing {os.getcwd()}/reports {args.output}")


# ********************************* #
# *           DEPCHECK            * #
# ********************************* #
@timer
@logger
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
    zip = zipfile.ZipFile(io.BytesIO(res.content))
    zip.extractall(f"{download_dir}")
    run_subprocess(f"chmod +x {download_dir}/dependency-check/bin/dependency-check.sh")


@timer
@logger
def depcheck(args):
    """
    Run and export report for the dependency check.

    Args:
        args ([dict]): the arguments passed to the script
    """
    try:
        # get the image tag
        image_tag = get_latest_stable_image_tag()

        # start runtime container
        start_rt_container(args, image_tag, rt_name=DEPCHECK_SCAN)

        # build the ear
        main_logger.info("Building ear file...")
        run_subprocess(
            f'docker exec {DEPCHECK_SCAN} bash -lc "buildear -warfiles=smcfs,sbc,sma,isccs,wsc"'
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

            # copy reports to output directory
            run_subprocess(f"rsync -a -v --ignore-existing {os.getcwd()}/reports {args.output}")

    except Exception as e:
        main_logger.warning(traceback.format_exc())
        main_logger.warning(e)
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN}")
    finally:
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN}")


# ********************************* #
# *             MAIN              * #
# ********************************* #
@timer
@logger
def main():
    args = parse_arguments()
    main_logger.info(args)
    if args.mode == SCAN:
        run_scan(args)
    elif args.mode == REPORTS:
        get_reports(args)
    elif args.mode == DEPCHECK:
        depcheck(args)


if __name__ == "__main__":
    main()
