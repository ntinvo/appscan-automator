import logging
import os
import tempfile
import traceback

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
    DYNAMIC,
    JAZZ_SINGLE_WS_ID,
    PENDING_STATUSES,
    PRESENCE_ID,
    REPORTS,
    SCAN,
    SINGLE_DYNAMIC,
    SINGLE_STATIC,
    STATIC,
)
from docker_utils import prep_containers
from settings import JAZZ_PASS, JAZZ_REPO, JAZZ_USER, KEY_ID, KEY_SECRET
from utils import get_latest_stable_image_tag, logger, parse_arguments, run_subprocess, timer

# main logger
main_logger = logging.getLogger(__name__)


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
def accept_changes(args):
    """
    Accepting the changes from the stream.
    
    Args:
        args ([dict]): the arguments passed to the script
    """
    try:
        run_subprocess(
            f"source ~/.bashrc && cd {args.source} && lscm accept --verbose -r {JAZZ_REPO} -u {JAZZ_USER} -P {JAZZ_PASS} -i -s {JAZZ_SINGLE_WS_ID}"
        )
    except Exception as _:
        main_logger.warning(
            "Attempt to accept the changes. The return code is not 0, this can be ignored. Continue..."
        )


@timer
@logger
def build_source_code(args):
    """
    Build the source code to prep for the scans.
    
    Args:
        args ([dict]): the arguments passed to the script
    """
    run_subprocess(f"cd {args.source} && Build/gradlew all")


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

    # accept the changes
    main_logger.info(f"Accepting changes...")
    accept_changes(args)

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
        for project in projects:
            project = project.strip()
            project_file_name = project.strip().replace("/", "_")

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
                f"source ~/.bashrc && appscan.sh prepare -c {APPSCAN_CONFIG_TMP} -n {project_file_name}.irx -d {tmpdir} -v -sp"
            )

            # call ASoC API to create the static scan
            try:
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
                        _ = requests.post(
                            f"{ASOC_API_ENDPOINT}/Scans/StaticAnalyzer", json=data, headers=headers
                        )
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
        _ = requests.post(
            f"{ASOC_API_ENDPOINT}/Scans/DynamicAnalyzer", json=create_scan_data, headers=headers
        )


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

    # cinfig data for the reports
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
# *             MAIN              * #
# ********************************* #
@timer
@logger
def main():
    args = parse_arguments()
    if args.mode == SCAN:
        run_scan(args)
    elif args.mode == REPORTS:
        get_reports(args)
    elif args.mode == DEPCHECK:
        pass


if __name__ == "__main__":
    main()
