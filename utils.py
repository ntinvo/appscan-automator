import argparse
import errno
import functools
import logging
import os
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime

import coloredlogs
import requests
from bs4 import BeautifulSoup

from constants import ALL, DYNAMIC, NS, REPORTS, SCAN, SINGLE_STREAM_RSS_URL, STATIC

# logging
main_logger = logging.getLogger(__name__)


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
def create_dir(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


@timer
@logger
def get_date_str():
    return datetime.today().strftime("%Y_%m_%d")
