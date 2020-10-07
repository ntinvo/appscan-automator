import argparse
import functools
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
    DYNAMIC,
    NS,
    PRESENCE_ID,
    SINGLE_DYNAMIC,
    SINGLE_STREAM_RSS_URL,
    STATIC,
)

# get env variables
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

KEY_ID = os.environ.get("KEY_ID")
KEY_SECRET = os.environ.get("KEY_SECRET")

# main logger
main_logger = logging.getLogger(__name__)


# ********************************* #
# *             UTILS             * #
# ********************************* #
def logger(func):
    """Print the function signature and return value"""

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
    """Convert seconds to hours/minutes/seconds
    Args:
        run_time: the time to convert to hours/minutes/seconds
    Returns:
        hours: converted hours
        minutes: converted minutes
        seconds: converted seconds
    Raises:
        None
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
    """Print the runtime of the decorated function"""

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


@timer
@logger
def get_bearer_token():
    res = requests.post(
        ASOC_LOGIN_ENDPOINT,
        json={"KeyId": KEY_ID, "KeySecret": KEY_SECRET},
        headers={"Accept": "application/json"},
    )
    return res.json()["Token"]


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
    latest_stable_build_url = fetch_available_build_urls(SINGLE_STREAM_RSS_URL)[0]
    res = requests.get(latest_stable_build_url)
    soup = BeautifulSoup(res.text, "html.parser")
    title_soup = soup.find("title")
    title = title_soup.text
    return title.split(" ")[1]


@timer
@logger
def dynamic_scan():
    # image_tag = get_latest_stable_image_tag()
    # print(image_tag)
    # TODOS:
    # * - DONE - need to figure out which image tag to use (this can be done by fetching the latest successful build from jenkins)
    # ! - need to spin up the containers (rt and db2) to create the env (including setting building the ear and apps deployment)
    # ! - for each app (smcfs, sbc, sma, wsc, isccs), need to create the new scan by calling the ASoC APIs (similar to the below - remember to delete or save the old scan)
    # ! - get the results

    # request header for the API
    # headers = {
    #     "Content-Type": "application/json",
    #     "Accept": "application/json",
    #     "Authorization": f"Bearer {get_bearer_token()}",
    # }

    for app, url in APP_URL_DICT.items():
        user = "admin" if app != "WSC" else "csmith"
        passwd = "password" if app != "WSC" else "csmith"
        data = {
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

        print(data)

        # res = requests.post(ASOC_DYNAMIC_ENDPOINT, json=data, headers=headers)

        # print(res.text)


@timer
@logger
def main():
    args = parse_arguments()
    if args.mode == ALL:
        static_scan()
        dynamic_scan()
    elif args.mode == STATIC:
        static_scan()
    else:
        dynamic_scan()

    # run_subprocess("ls -al", logger=main_logger)


if __name__ == "__main__":
    main()
