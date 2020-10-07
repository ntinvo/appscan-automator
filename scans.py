import argparse
import functools
import json
import logging
import os
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from os.path import dirname, join

import coloredlogs
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from constants import (
    ALL,
    APP_URL_DICT,
    ASOC_DYNAMIC_ENDPOINT,
    ASOC_LOGIN_ENDPOINT,
    DB2_SCAN,
    DYNAMIC,
    JFROG_REGISTRY,
    JFROG_USER,
    NETWORK_SCAN,
    NS,
    PRESENCE_ID,
    REPORTS,
    RT_SCAN,
    SCAN,
    SINGLE_DYNAMIC,
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
        level=verbose,
        logger=main_logger,
        fmt="%(asctime)s %(hostname)s %(name)s[%(process)d] %(levelname)s %(message)s",
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
        choices=[SCAN, REPORTS],
        help=f"the type of scan to run. With mode {ALL}, it will run both {DYNAMIC} and {STATIC} preps.",
        default=ALL,
    )

    args = parser.parse_args()
    setup_main_logging(args.verbose)
    return args


@timer
@logger
def get_bearer_token():
    res = requests.post(
        ASOC_LOGIN_ENDPOINT,
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
    res = requests.get(f"https://cloud.appscan.com/api/v2/Apps/{app_id}/Scans", headers=headers)
    if res.status_code == 200:
        return res.json()


# ********************************* #
# *        STATIC SCAN PREP       * #
# ********************************* #
@timer
@logger
def static_scan():
    # TODOS:
    # ! - fetch the source code
    # ! - run subprocess to generate file needed to upload the ASoC (using its API)
    # ! - use API to execute the scans
    # ! - get the results
    pass


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
        rt_image_repo = f"{JFROG_REGISTRY}/oms-single-db2-rt:{image_tag}-liberty"
        logger.info(f"#### STARTING DB2 CONTAINER: {RT_SCAN} - {rt_image_repo} ####")
        run_subprocess(
            f" \
            docker run -di --name {RT_SCAN} --privileged \
            --network={NETWORK_SCAN} \
            -e DB_HOST={DB2_SCAN} \
            -e DB_PORT=50000 \
            -e DB_VENDOR=db2 \
            -e DB_NAME=OMDB \
            -p 9080:9080 \
            -p 9443:9443 \
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
    - start liberty server 
    - wait for the server to be ready
    - logout of the registry

    Args:
        image_tag: the tag of the image
    Returns:
        None

    NOTE: as of now, this only supports single images; this can be enhanced to prep other versions    
    """
    docker_login()

    # # Starting db2 and rt containers
    # main_logger.info("Starting db2 and rt containers...")
    # start_db2_container(image_tag)
    # start_rt_container(image_tag)

    # # Build the ear
    # main_logger.info("Building ear file...")
    # run_subprocess(f'docker exec {RT_SCAN} bash -lc "buildear -warfiles=smcfs,sbc,sma,isccs,wsc"')

    # # Start liberty server
    # main_logger.info("Starting liberty server...")
    # run_subprocess(f'docker exec {RT_SCAN} bash -lc "__lbstart"')

    # Wait for the server to finish initializing
    main_logger.info("Waiting for the server to finish initializing...")
    while True:
        # TODO: need to change the below URL
        res = requests.get("http://localhost:9080/smcfs/console/login.jsp")
        if res.status_code == 200:
            break
        time.sleep(60)

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
    # # get the image tag
    # image_tag = get_latest_stable_image_tag()
    # print(image_tag)

    # spin up the containers (rt and db2)
    # prep_containers(image_tag)

    # read the old scan ids
    # TODO: fetch the scans of the app from the API
    dynamic_old_scans = {}
    try:
        with open("dynamic_old_scans.json") as f:
            dynamic_old_scans = json.load(f)
    except Exception as e:
        main_logger.warning(e)

    for app, url in APP_URL_DICT.items():
        user = "admin" if app != "WSC" else "csmith"
        passwd = "password" if app != "WSC" else "csmith"

        # remove the scan before creating a new one
        main_logger.info(f"Removing the scan: {app} - {dynamic_old_scans[app]}... ")
        try:
            res = requests.delete(
                f"https://cloud.appscan.com/api/v2/Scans/{dynamic_old_scans[app]}?deleteIssues=true",
                headers=headers,
            )
        except Exception as e:
            main_logger.warning(e)

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
        res = requests.post(ASOC_DYNAMIC_ENDPOINT, json=create_scan_data, headers=headers)
        dynamic_old_scans[app] = res.json()["Id"]

    # save old scans
    with open("dynamic_old_scans.json", "w") as f:
        json.dump(dynamic_old_scans, f)


@timer
@logger
def run_scan(args):
    if args.type == ALL:
        static_scan()
        dynamic_scan()
    elif args.type == STATIC:
        static_scan()
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
    # for scan in scans:
    #     # only generate report for ready scan
    #     if scan["LatestExecution"]["Status"] == "Ready":
    #         config_data = {
    #             "Configuration": {
    #                 "Summary": "true",
    #                 "Details": "true",
    #                 "Discussion": "true",
    #                 "Overview": "true",
    #                 "TableOfContent": "true",
    #                 "Advisories": "true",
    #                 "FixRecommendation": "true",
    #                 "History": "true",
    #                 "Coverage": "true",
    #                 "IsTrialReport": "true",
    #                 "MinimizeDetails": "true",
    #                 "ReportFileType": "Html",
    #                 "Title": scan["Name"].replace(" ", "_").lower(),
    #                 "Locale": "en-US",
    #             },
    #         }
    #         res = requests.post(
    #             f"https://cloud.appscan.com/api/v2/Reports/Security/Scan/{scan['Id']}",
    #             json=config_data,
    #             headers=headers,
    #         )
    #         if res.status_code == 200:
    #             generated_reports.append(res.json())
    rp = {
        "Id": "b3f1484b-668e-4fd8-9e3b-db45e03a218a",
        "Name": "smcfs_scan",
        "Status": "Pending",
        "Progress": 0,
        "ValidUntil": "2020-10-08T18:38:21.2043596Z",
        "HtmlInsteadOfPdf": "false",
    }
    generated_reports.append(rp)

    for report in generated_reports:
        # wait for the report to be ready
        while True:
            res = requests.get(
                f"https://cloud.appscan.com/api/v2/Reports/{report['Id']}", headers=headers
            )
            if res.status_code != 200:
                break

            if res.status_code == 200 and res.json()["Status"] == "Ready":
                break

            main_logger.info(f"Report for {report['Name']} is not ready. Waiting...")
            time.sleep(300)

        # download the report
        res = requests.get(
            f"https://cloud.appscan.com/api/v2/Reports/Download/{report['Id']}", headers=headers
        )
        if res.status_code == 200:
            with open(f"{report['Name']}.html", "wb") as f:
                f.write(res.content)


@timer
@logger
def static_reports():
    pass


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
    # read the old scan ids
    # dynamic_old_scans = {}
    # try:
    #     with open("dynamic_old_scans.json") as f:
    #         dynamic_old_scans = json.load(f)
    # except Exception as e:
    #     main_logger.warning(e)


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
