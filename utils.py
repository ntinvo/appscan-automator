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

from args import init_argparse
from constants import NS, SINGLE_STREAM_RSS_URL, JFROG_USER
from main_logger import main_logger
from settings import JFROG_APIKEY, JENKINS_TAAS_TOKEN


def logger(func):
    """
    Print the function signature and return value.

    Args:
        func ([func]): the function to be wrapped

    Returns:
        [func]: the logger wrapper for the passed in function
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
        run_time ([str]): the time to convert to hours/minutes/seconds

    Returns:
        [tuple]: converted time
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
        func ([func]): the function to be wrapped

    Returns:
        [func]: return the timer wrapper for the passed in function
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
    """
    Run the subprocess.

    Args:
        command ([str]): the command to run subprocess
        timeout ([integer], optional): timeout when running subprocess. Defaults to None.
        logger ([logging], optional): logger to use. Defaults to main_logger.

    Raises:
        Exception: exception raised when running subprocess

    Returns:
        [tuple]: the return value and output of the subprocess
    """
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
    """
    Set the logging level for the script that the user passes in.

    Args:
        verbose ([str], optional): the log level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"). Defaults to logging.INFO.
    """
    coloredlogs.install(
        level=verbose,
        logger=main_logger,
        fmt="%(asctime)s %(levelname)s %(message)s",
    )


def parse_arguments():
    """
    Set up the arguments parser for the script
    Retrieves the arguments passed in by the user, parse them, and return.

    Returns:
        [dict]: the argument dict
    """
    args = init_argparse()
    setup_main_logging(args.verbose)
    return args


@timer
@logger
def fetch_available_build_urls(url):
    """
    Fetch all of the stable build urls from Jenkins server.

    Args:
        url ([str]): the build job url

    Returns:
        [list]: the list of available stable urls
    """
    res = requests.get(url, auth=get_auth(url))
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

    Returns:
        [str]: the latest available stable url
    """
    latest_stable_build_url = fetch_available_build_urls(SINGLE_STREAM_RSS_URL)[0]
    res = requests.get(latest_stable_build_url, auth=get_auth(latest_stable_build_url))
    soup = BeautifulSoup(res.text, "html.parser")
    title_soup = soup.find("title")
    title = title_soup.text
    return title.split(" ")[1]


@timer
@logger
def create_dir(path):
    """
    Create the directory if not exist

    Args:
        path ([str]): the path to create the directory
    """
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


@timer
@logger
def get_date_str():
    """
    Get today date string

    Returns:
        [str]: the date string to return in yyyy-mm-dd format
    """
    return datetime.today().strftime("%Y_%m")


@timer
@logger
def get_auth(url):
    if "wce-sterling-team-oms-jenkins.swg-devops.com" in url:
        return (JFROG_USER, JENKINS_TAAS_TOKEN)
    if "swg-devops.com" in url:
        return (JFROG_USER, JFROG_APIKEY)
    return None