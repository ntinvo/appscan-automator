import argparse
import errno
import functools
import json
import logging
import os
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from os.path import dirname, join

import coloredlogs
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from constants import (
    ALL,
    APP_URL_DICT,
    APPSCAN_CONFIG,
    APPSCAN_CONFIG_TMP,
    ASOC_API_ENDPOINT,
    DB2_SCAN,
    DYNAMIC,
    JAZZ_SINGLE_WS_ID,
    JFROG_REGISTRY,
    JFROG_USER,
    NETWORK_SCAN,
    NS,
    PRESENCE_ID,
    REPORTS,
    RT_SCAN,
    SCAN,
    SINGLE_DYNAMIC,
    SINGLE_STATIC,
    SINGLE_STREAM_RSS_URL,
    STATIC,
    VOL_SCAN,
)

# get env variables
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

KEY_ID = os.environ.get("KEY_ID")
KEY_SECRET = os.environ.get("KEY_SECRET")
JFROG_APIKEY = os.environ.get("JFROG_APIKEY")
JAZZ_REPO = os.environ.get("JAZZ_REPO")
JAZZ_USER = os.environ.get("JAZZ_USER")
JAZZ_PASS = os.environ.get("JAZZ_PASS")

# main logger
main_logger = logging.getLogger(__name__)


# ********************************* #
# *             UTILS             * #
# ********************************* #
def logger(func):
    """
    Print the function signature and return value.
    
    Args:
        func: the function to be wrapped
    Returns:
        wrapper: return the logger wrapper for the passed in function
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = ", ".join(args_repr + kwargs_repr)
            main_logger.info(f"START - {func.__name__}")
            main_logger.debug(f"{func.__name__}({signature})")
            value = func(*args, **kwargs)
            main_logger.debug(f"{func.__name__!r} returned {value!r}")
            return value
        except Exception as e:
            main_logger.error(traceback.format_exc())
            main_logger.error(f"ERROR - {func.__name__} : {e}")
            raise
        finally:
            main_logger.info(f"END - {func.__name__}")
            sys.stdout.flush()

    return wrapper


def get_run_duration(run_time):
    """
    Convert seconds to hours/minutes/seconds.
    
    Args:
        run_time: the time to convert to hours/minutes/seconds
    Returns:
        hours: converted hours
        minutes: converted minutes
        seconds: converted seconds
    """
    seconds = run_time % (24 * 3600)
    hours = run_time // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    hours = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)

    return hours, minutes, seconds


def timer(func):
    """
    Print the runtime of the decorated function.
    
    Args:
        func: the function to be wrapped
    Returns:
        wrapper: return the timer wrapper for the passed in function
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        value = func(*args, **kwargs)
        end_time = time.time()
        run_time = end_time - start_time
        hours, minutes, seconds = get_run_duration(run_time)
        main_logger.info(f"{func.__name__}() completed in: {hours}h {minutes}m {seconds}s")
        return value

    return wrapper


def run_subprocess(command, timeout=None, logger=main_logger):
    """Run the subprocess."""
    popen = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines_iterator = iter(popen.stdout.readline, b"")
    output = ""
    while popen.poll() is None:
        for line in lines_iterator:
            nline = line.rstrip()
            nline = nline.decode(
                encoding=sys.stdout.encoding,
                errors="replace" if (sys.version_info) < (3, 5) else "backslashreplace",
            )
            output += nline + "\n"
            if logger:
                logger.info(nline)
            if main_logger.level <= logging.INFO:
                if not logger:
                    print(nline, end="\r\n", flush=True)
    if logger:
        logger.info(f"PROCESS: {popen.pid} return {popen.returncode}")
        if popen.returncode != 0:
            _, err = popen.communicate()
            logger.error(f"ERROR: {err}")
            raise Exception(err)
    retval = popen.wait(timeout)
    subprocess.run(["stty", "sane"])
    return retval, output


def setup_main_logging(verbose=logging.INFO):
    """Set the logging level for the script that the user passes in. Default is WARNING
    
    Args:
        verbose: the log level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    Returns:
        None
    Raises:
        None
    """
    coloredlogs.install(
        level=verbose, logger=main_logger, fmt="%(asctime)s %(levelname)s %(message)s",
    )


def parse_arguments():
    """Set up the arguments parser for the script
    Retrieves the arguments passed in by the user, parse them, and return.
    Args:
        None
    Returns:
        The argument parser
    Raises:
        None
    """
    parser = argparse.ArgumentParser(
        description="This will run the scans preps.", epilog="Have a nice day! :)"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="the verbose level of the script",
        default=logging.WARNING,
    )
    parser.add_argument(
        "-t",
        "--type",
        choices=[ALL, DYNAMIC, STATIC],
        help=f"the type of scan to run. With mode {ALL}, it will run both {DYNAMIC} and {STATIC} preps.",
        default=ALL,
    )
    parser.add_argument(
        "-m",
        "--mode",
        required=True,
        choices=[SCAN, REPORTS],
        help=f"the mode to run the scan; {SCAN} will create the scan, and {REPORTS} will generate and download the reports for the scans.",
    )
    parser.add_argument(
        "-s",
        "--source",
        help=f"the path to source code. When running type {STATIC} and mode {SCAN}, this is required.",
    )

    args = parser.parse_args()
    setup_main_logging(args.verbose)
    validate_args(args)
    return args


@timer
@logger
def validate_args(args):
    if (args.type == STATIC and args.mode == SCAN) and not args.source:
        raise ValueError(
            f"Param: source is required when running type {STATIC} and mode {SCAN} . Args: {args.source}"
        )


@timer
@logger
def get_bearer_token():
    res = requests.post(
        f"{ASOC_API_ENDPOINT}/Account/ApiKeyLogin",
        json={"KeyId": KEY_ID, "KeySecret": KEY_SECRET},
        headers={"Accept": "application/json"},
    )
    return res.json()["Token"]


headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {get_bearer_token()}",
}


@timer
@logger
def get_scans(app_id):
    """Get the list of scans for the application"""
    res = requests.get(f"{ASOC_API_ENDPOINT}/Apps/{app_id}/Scans", headers=headers)
    if res.status_code == 200:
        return res.json()


@timer
@logger
def get_date_str():
    return datetime.today().strftime("%Y_%m_%d")


@timer
@logger
def create_dir(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


@timer
@logger
def remove_old_scans(app_id):
    # read the old scan ids
    old_scans = get_scans(app_id)
    scan_status_dict = {}
    scans_pending = False

    # if any of the scan in the app is still running or
    # in InQueue, Paused, Pausing, Stopping status,
    # do not remove the scan and return the old scans
    # with their current statuses (as a dict)
    for old_scan in old_scans:
        scan_status_dict[old_scan["Name"]] = old_scan["LatestExecution"]["Status"]
        if old_scan["LatestExecution"]["Status"] in [
            "Running",
            "InQueue",
            "Paused",
            "Pausing",
            "Stopping",
        ]:
            scans_pending = True
    if scans_pending:
        main_logger.warning("Scan(s) pending. Returning...")
        return scan_status_dict

    # remove the old scans from the app before creating new ones
    for old_scan in old_scans:
        main_logger.info(f"Removing {old_scan['Name']} - {old_scan['Id']}... ")
        try:
            _ = requests.delete(
                f"{ASOC_API_ENDPOINT}/Scans/{old_scan['Id']}?deleteIssues=true", headers=headers,
            )
        except Exception as e:
            main_logger.warning(e)

    return scan_status_dict


@timer
@logger
def wait_for_report(report):
    """Wait for the generated report to be ready"""
    while True:
        res = requests.get(f"{ASOC_API_ENDPOINT}/Reports/{report['Id']}", headers=headers)
        if res.status_code != 200:
            break

        if res.status_code == 200 and res.json()["Status"] == "Ready":
            break

        main_logger.info(f"Report for {report['Name']} is not ready. Waiting...")
        time.sleep(300)


@timer
@logger
def download_report(report):
    """Download the generated report"""
    res = requests.get(f"{ASOC_API_ENDPOINT}/Reports/Download/{report['Id']}", headers=headers)
    if res.status_code == 200:
        reports_dir_path = f"reports/dynamic/{get_date_str()}"
        create_dir(reports_dir_path)
        with open(f"{reports_dir_path}/{report['Name']}.html", "wb") as f:
            f.write(res.content)


@timer
@logger
def get_download_config(name):
    """Get the report download configurations"""
    return {
        "Configuration": {
            "Summary": "true",
            "Details": "true",
            "Discussion": "true",
            "Overview": "true",
            "TableOfContent": "true",
            "Advisories": "true",
            "FixRecommendation": "true",
            "History": "true",
            "Coverage": "true",
            "IsTrialReport": "true",
            "MinimizeDetails": "true",
            "ReportFileType": "Html",
            "Title": name.replace(" ", "_").lower(),
            "Locale": "en-US",
        },
    }


# ********************************* #
# *        STATIC SCAN PREP       * #
# ********************************* #
@timer
@logger
def get_projects():
    """Get the list of projects to scan."""
    projects = []
    with open("projects.list", "r") as f:
        projects = f.readlines()
    return projects


@timer
@logger
def accept_changes(args):
    """Accepting the changes from the stream."""
    try:
        run_subprocess(
            f"cd {args.source} && lscm accept --verbose -r {JAZZ_REPO} -u {JAZZ_USER} -P {JAZZ_PASS} -i -s {JAZZ_SINGLE_WS_ID}"
        )
    except Exception as _:
        main_logger.warning(
            "Attempt to accept the changes. The return code is not 0, this can be ignored. Continue..."
        )


@timer
@logger
def build_source_code(args):
    """Build the source code."""
    run_subprocess(f"cd {args.source} && Build/gradlew all")


def generate_appscan_config_file(args, project):
    """Generate appscan config file."""
    with open(APPSCAN_CONFIG) as r:
        text = r.read().replace("PROJECT_PATH", f"{args.source}/{project.strip()}")
    with open(APPSCAN_CONFIG_TMP, "w") as w:
        w.write(text)


@timer
@logger
def static_scan(args):
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
    # - remove the old irx files in configs dir
    # - go through the list of projects
    # - generate the irx file for each project
    # - upload the generated irx file to ASoC
    # - create and execute the static scan
    run_subprocess(f"rm -rf {os.getcwd()}/configs")
    for project in projects:
        project = project.strip()
        project_file_name = project.strip().replace("/", "_")

        # if the old scan still running, skip
        if project in old_scan_status_dict and old_scan_status_dict[project] in [
            "Running",
            "InQueue",
            "Paused",
            "Pausing",
            "Stopping",
        ]:
            continue

        # generate config file for appscan
        generate_appscan_config_file(args, project)
        main_logger.info(f"Generating {project_file_name}.irx file...")
        run_subprocess(
            f"source ~/.bashrc && appscan.sh prepare -c {APPSCAN_CONFIG_TMP} -n {project_file_name}.irx -d {os.getcwd()}/configs -v -sp"
        )

        # call ASoC API to create the static scan
        try:
            with open(f"{os.getcwd()}/configs/{project_file_name}.irx", "rb") as irx_file:
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
def fetch_available_build_urls(url):
    """
    Fetch all of the stable build urls from Jenkins server.
    
    Args:
        url: the build job url 
    Returns:
        build_urls: the available stable urls
    """
    res = requests.get(url)
    build_urls = []
    if res.ok:
        root = ET.fromstring(res.text)
        entries = root.findall("W3:entry", NS)
        for entry in entries:
            title = entry.find("W3:title", NS).text
            if "broken" in title or "aborted" in title:
                continue
            link = entry.find("W3:link", NS)
            build_urls.append(link.get("href"))
    return build_urls


@timer
@logger
def get_latest_stable_image_tag():
    """
    Get latest stable image tag.
    
    Args:
        None 
    Returns:
        The latest available stable url
    """
    latest_stable_build_url = fetch_available_build_urls(SINGLE_STREAM_RSS_URL)[0]
    res = requests.get(latest_stable_build_url)
    soup = BeautifulSoup(res.text, "html.parser")
    title_soup = soup.find("title")
    title = title_soup.text
    return title.split(" ")[1]


@timer
@logger
def docker_login():
    """Login to the registry."""
    main_logger.info(f"#### Login to {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker login -u {JFROG_USER} -p {JFROG_APIKEY} {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def docker_logout():
    """Logout of the registry."""
    main_logger.info(f"#### Logout of {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker logout {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def start_db2_container(image_tag, logger=main_logger):
    """
    Start the db2 container for deployment.
    
    Args:
        image_tag: the tag of the image
        logger: the logger to log the output
    Returns:
        None
    """
    try:
        db_image_repo = f"{JFROG_REGISTRY}/oms-single-db2-db:{image_tag}-refs"
        logger.info(f"#### STARTING DB2 CONTAINER: {DB2_SCAN} - {db_image_repo} ####")
        run_subprocess(
            f" \
            docker volume create {VOL_SCAN} && \
            docker network create {NETWORK_SCAN} && \
            docker run -di --name {DB2_SCAN} --privileged \
            --network={NETWORK_SCAN} \
            -e DB2INSTANCE=db2inst1 \
            -e DB2INST1_PASSWORD=db2inst1 \
            -e DB_USER=omsuser \
            -e DB_PASSWORD=omsuser \
            -e LICENSE=accept \
            -e DBNAME=omdb \
            -e AUTOCONFIG=false \
            -v {VOL_SCAN}:/database \
            -p 50005:50000 {db_image_repo} && \
            chmod +x {os.getcwd()}/waitDB2.sh && \
            /bin/bash {os.getcwd()}/waitDB2.sh {DB2_SCAN}",
            logger=logger,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        raise Exception


@timer
@logger
def start_rt_container(image_tag, logger=main_logger):
    """
    Start the rt container for deployment
    
    Args:
        image_tag: the tag of the image
        logger: the logger to log the output
    Returns:
        None
    """
    try:
        rt_image_repo = f"{JFROG_REGISTRY}/oms-single-db2-rt:{image_tag}-weblogic"
        logger.info(f"#### STARTING DB2 CONTAINER: {RT_SCAN} - {rt_image_repo} ####")
        run_subprocess(
            f" \
            docker run -di --name {RT_SCAN} --privileged \
            --network={NETWORK_SCAN} \
            -e DB_HOST={DB2_SCAN} \
            -e DB_PORT=50000 \
            -e DB_VENDOR=db2 \
            -e DB_NAME=OMDB \
            -p 7001:7001 \
            {rt_image_repo}",
            logger=logger,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        raise Exception


@timer
@logger
def prep_containers(image_tag):
    """
    Prepare the rt and db2 container. This function will do the followings:
    - login to the registry 
    - start db2 and rt containers 
    - build the ear for deployment 
    - start weblogic server 
    - wait for the server to be ready
    - logout of the registry

    Args:
        image_tag: the tag of the image
    Returns:
        None

    NOTE: as of now, this only supports single images; this can be enhanced to prep other versions    
    """
    docker_login()

    # Starting db2 and rt containers
    main_logger.info("Starting db2 and rt containers...")
    start_db2_container(image_tag)
    start_rt_container(image_tag)

    # Build the ear
    main_logger.info("Building ear file...")
    run_subprocess(f'docker exec {RT_SCAN} bash -lc "buildear -warfiles=smcfs,sbc,sma,isccs,wsc"')

    # Start weblogic server
    main_logger.info("Starting weblogic server...")
    run_subprocess(f'docker exec {RT_SCAN} bash -lc "__wlstart -autodeploy=true"')

    # Check to make sure the apps are run and running
    main_logger.info(
        "Checking deployment @ http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp..."
    )
    while True:
        try:
            res = requests.get(
                "http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp", timeout=20
            )
            if res.status_code == 200:
                break
        except Exception as _e:
            time.sleep(10)

    main_logger.info("The db2 and rt containers are up and running...")
    docker_logout()


@timer
@logger
def cleanup():
    """Clean up resouces."""
    main_logger.info(f"Removing volume {VOL_SCAN}...")
    run_subprocess(f"docker volume rm {VOL_SCAN}")

    main_logger.info(f"Removing network {NETWORK_SCAN}...")
    run_subprocess(f"docker network rm {NETWORK_SCAN}")


@timer
@logger
def dynamic_scan():
    # get the image tag
    image_tag = get_latest_stable_image_tag()
    print(image_tag)

    # spin up the containers (rt and db2)
    prep_containers(image_tag)

    # remove the old scans
    remove_old_scans(SINGLE_DYNAMIC)

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
            "TestOptimizationLevel": "Fast",
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
    if args.type == ALL:
        static_scan(args)
        dynamic_scan()
    elif args.type == STATIC:
        static_scan(args)
    else:
        dynamic_scan()


# ********************************* #
# *            REPORTS            * #
# ********************************* #
@timer
@logger
def dynamic_reports():
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
        download_report(report)


@timer
@logger
def static_reports():
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
        download_report(report)


@timer
@logger
def get_reports(args):
    if args.type == ALL:
        static_reports()
        dynamic_reports()
    elif args.type == STATIC:
        static_reports()
    else:
        dynamic_reports()


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


if __name__ == "__main__":
    main()
