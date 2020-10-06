import argparse
import logging
import os
import requests
import subprocess
import sys
import coloredlogs
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from os.path import join, dirname

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

# consts
SINGLE_STREAM_RSS_URL = (
    "http://9.121.242.67:9080/jenkins/view/L3%20Builds/job/Single_Stream_Project/rssAll"
)
NS = {"W3": "http://www.w3.org/2005/Atom"}
API_KEY = os.environ.get("API_KEY")
DYNAMIC = "dynamic"
STATIC = "static"
ALL = "all"

# main logger
main_logger = logging.getLogger(__name__)


# ********************************* #
# *             UTILS             * #
# ********************************* #
def run_subprocess(command, timeout=None, logger=None):
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
        "-m",
        "--mode",
        choices=[ALL, DYNAMIC, STATIC],
        help=f"the type of scan to run. With mode {ALL}, it will run both {DYNAMIC} and {STATIC} preps.",
        default=ALL,
    )

    args = parser.parse_args()
    setup_main_logging(args.verbose)
    return args


# ********************************* #
# *        STATIC SCAN PREP       * #
# ********************************* #
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
def fetch_available_build_urls(url):
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


def get_latest_stable_image_tag():
    latest_stable_build_url = fetch_available_build_urls(SINGLE_STREAM_RSS_URL)[0]
    res = requests.get(latest_stable_build_url)
    soup = BeautifulSoup(res.text, "html.parser")
    title_soup = soup.find("title")
    title = title_soup.text
    return title.split(" ")[1]


def dynamic_scan():
    image_tag = get_latest_stable_image_tag()
    print(image_tag)
    # TODOS:
    # * - DONE - need to figure out which image tag to use (this can be done by fetching the latest successful build from jenkins)
    # ! - need to spin up the containers (rt and db2) to create the env (including setting building the ear and apps deployment)
    # ! - for each app (smcfs, sbc, sma, store, call center), need to create the new scan by calling the ASoC APIs (similar to the below - remember to delete or save the old scan)
    # ! - get the results

    # headers = {
    #     "Content-Type": "application/json",
    #     "Accept": "application/json",
    #     "Authorization": f"Bearer {API_KEY}",
    # }

    # data = {
    #     "StartingUrl": "http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp",
    #     "LoginUser": "admin",
    #     "LoginPassword": "password",
    #     "ScanType": "Production",
    #     "PresenceId": "000000000000000000000000 (CHANGE)",
    #     "IncludeVerifiedDomains": "true",
    #     "HttpAuthUserName": "string",
    #     "HttpAuthPassword": "string",
    #     "HttpAuthDomain": "string",
    #     "OnlyFullResults": "true",
    #     "TestOptimizationLevel": "NoOptimization",
    #     "ScanName": "SMCFS Scan",
    #     "EnableMailNotification": "false",
    #     "Locale": "en-US",
    #     "AppId": "000000000000000000000000 (CHANGE)",
    #     "Execute": "true",
    #     "Personal": "false",
    # }

    # res = requests.post(
    #     "https://cloud.appscan.com/api/v2/Scans/DynamicAnalyzer", json=data, headers=headers
    # )

    # print(res.text)
    pass


def main():
    args = parse_arguments()
    if args.mode == ALL:
        static_scan()
        dynamic_scan()
    elif args.mode == STATIC:
        static_scan()
    else:
        dynamic_scan()

    run_subprocess("ls -al", logger=main_logger)


if __name__ == "__main__":
    main()
