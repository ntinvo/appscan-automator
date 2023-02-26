""" Utils """
import errno
import functools
import logging
import os
import re
import subprocess
import sys
import tarfile
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from math import ceil

import coloredlogs
import requests
import yaml
from bs4 import BeautifulSoup
from clint.textui import progress
from requests.auth import HTTPBasicAuth

from args import init_argparse
from constants import (
    APPSCAN_URL,
    APPSCAN_ZIP_URL,
    CASE_INDEX_URL,
    DEPCHECK,
    DEPCHECK_SCAN,
    JFROG_USER,
    NS,
    OWASP_URL,
    RT_SCAN,
    SINGLE_STREAM_RSS_URL,
    TWISTLOCK_URL,
)
from main_logger import main_logger
from settings import JENKINS_TAAS_TOKEN, JFROG_APIKEY


def f_logger(func):
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
        except Exception as error:
            main_logger.error(traceback.format_exc())
            main_logger.error(f"ERROR - {func.__name__} : {error}")
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
    subprocess.run(["stty", "sane"])  # pylint: disable=subprocess-run-check
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
        fmt="%(levelname)s <PID %(process)d:%(processName)s> %(name)s.%(funcName)s(): %(message)s",
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
@f_logger
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
@f_logger
def get_latest_stable_image_tags():
    """
    Get latest stable image tag.

    Returns:
        [str]: the latest available stable urls
    """
    image_tags = []
    stable_build_urls = fetch_available_build_urls(SINGLE_STREAM_RSS_URL)
    for build_url in stable_build_urls:
        res = requests.get(build_url, auth=get_auth(build_url))
        soup = BeautifulSoup(res.text, "html.parser")
        title_soup = soup.find("title")
        title = title_soup.text
        image_tags.append(title.split(" ")[1].lower())
    main_logger.info(f"Latest image tags: {image_tags}")
    return image_tags


@timer
@f_logger
def create_dir(path):
    """
    Create the directory if not exist

    Args:
        path ([str]): the path to create the directory
    """
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise


@timer
@f_logger
def get_auth(url):
    """
    Get authentication tokens

    Args:
        url ([str]): request url

    Returns:
        [tuple]: user name and tokens
    """
    if "wce-sterling-team-oms-jenkins.swg-devops.com" in url:
        return (JFROG_USER, JENKINS_TAAS_TOKEN)
    if "swg-devops.com" in url:
        return (JFROG_USER, JFROG_APIKEY)
    return None


@timer
@f_logger
def get_week_of_month(dt_obj):
    """
    Get the week number of the month

    Args:
        dt_obj ([datetime]): date time object

    Returns:
        [int]: week number
    """
    first_day = dt_obj.replace(day=1)
    day_of_month = dt_obj.day
    adjusted_day_of_month = day_of_month + first_day.weekday()
    return (
        int(ceil(adjusted_day_of_month / 7.0)) - 1
        if first_day.weekday() == 6
        else int(ceil(adjusted_day_of_month / 7.0))
    )


@timer
@f_logger
def get_date_str():
    """
    Get today date string

    Returns:
        [str]: the date string to return in yyyy-mm-dd format
    """
    dt_obj = datetime.today()
    year_month = dt_obj.strftime("%Y_%m")
    week_of_month = get_week_of_month(dt_obj)
    return f"{year_month}_week_{week_of_month}"


@timer
@f_logger
def get_files_info_in_zip(zip_file):
    """
    Generator to return the file info in the zipfile

    Args:
        zip_file ([type]): zip file

    """
    paths = []
    for name in zip_file.namelist():
        paths.append(name.split("/"))
    top_level_dir = os.path.commonprefix(paths)
    top_level_dir = "/".join(top_level_dir) + "/" if top_level_dir else top_level_dir
    for zip_file_info in zip_file.infolist():
        name = zip_file_info.filename
        if len(name) > len(top_level_dir):
            zip_file_info.filename = name[len(top_level_dir) :]
            yield zip_file_info


@timer
@f_logger
def download(url, filename, context):
    """
    Download file given the url

    Args:
        url (str): file url
        filename (str): filename to save
        context (str): directory to save file to
    """
    try:
        res = requests.get(url, stream=True, auth=get_auth(url))
        main_logger.info(f"Download {filename} returned {res.status_code}")
        if res.status_code != 200:
            return False
        total_length = int(res.headers.get("content-length"))
        with open(f"{context}/{filename}", "wb") as file:
            total_length = int(res.headers.get("content-length"))
            for chunk in progress.bar(
                res.iter_content(chunk_size=1024),
                expected_size=(total_length / 1024) + 1,
                label="Downloading. Please wait >>> ",
            ):
                if chunk:
                    file.write(chunk)
                    file.flush()
        return True
    except Exception as error:
        main_logger.earning(error)
        raise


@timer
@f_logger
def cleanup():
    """
    Cleaning up
    """
    try:
        run_subprocess(f"docker rm -f {RT_SCAN} 2> /dev/null")
    except Exception as _:
        main_logger.warning(f"Error removing {RT_SCAN} 2> /dev/null")

    try:
        run_subprocess(f"docker rm -f {DEPCHECK_SCAN} 2> /dev/null ")
    except Exception as _:
        main_logger.warning(f"Error removing {DEPCHECK_SCAN} 2> /dev/null")

    try:
        run_subprocess(
            "docker network prune -f  2> /dev/null && docker volume prune -f 2> /dev/null"
        )
    except Exception as _:
        pass


@timer
@f_logger
def download_and_extract_appscan(path):
    """
    Download latest appscan
    """
    # download(APPSCAN_ZIP_URL, "appscan.zip", path)
    # appscan_zip = zipfile.ZipFile(f"{path}/appscan.zip")
    # appscan_zip.extractall(f"{path}/appscan/")
    # appcan_folder_name = os.listdir(f"{path}/appscan/")[0]
    # return appcan_folder_name
    run_subprocess(f"wget -O {path}/appscan.zip {APPSCAN_ZIP_URL}")
    run_subprocess(f"unzip -o {path}/appscan.zip -d {path}/appscan/")
    appcan_folder_name = os.listdir(f"{path}/appscan/")[0]
    return appcan_folder_name


@timer
@f_logger
def get_latest_image():
    """Get latest built image"""
    res = requests.get(
        TWISTLOCK_URL, auth=HTTPBasicAuth(os.environ["JENKINS_USER"], os.environ["JENKINS_TOKEN"])
    )
    soup = BeautifulSoup(res.text, "html.parser")
    twistlock_file_soup = soup.find("a", href=re.compile((r"^twistlock.*json$")))
    res = requests.get(
        f"{TWISTLOCK_URL}/{twistlock_file_soup.text}",
        auth=HTTPBasicAuth(os.environ["JENKINS_USER"], os.environ["JENKINS_TOKEN"]),
    )
    scan_results = res.json()
    for img in scan_results["overview"]["images"]["resultsIncluded"]["noScanErrors"]["list"]:
        if "app" in img:
            return img
    return get_latest_released_image()


@timer
@f_logger
def update_config_file(file_name):
    """Update config file"""
    with open(file_name, "r") as file:
        data = file.read()
        data = data.replace("__DB_HOST__", os.environ["DB_HOST"])
        data = data.replace("__DB_PORT__", os.environ["DB_PORT"])
        data = data.replace("__DB_NAME__", os.environ["DB_NAME"])
        data = data.replace("__DB_USER__", os.environ["DB_USER"])
        data = data.replace("__DB_PASS__", os.environ["DB_PASS"])
        data = data.replace("__DB_SCHEMA__", os.environ["DB_SCHEMA"])
    with open(f"{file_name}.updated", "w") as file:
        file.write(data)


@timer
@f_logger
def upload_reports_to_artifactory(scan_type, report_dir, timestamp):
    """Upload the reports to artifactory"""
    upload_url = f"{APPSCAN_URL}/{timestamp}/{scan_type}"
    if scan_type == DEPCHECK:
        upload_url = f"{OWASP_URL}/{timestamp}"
    run_subprocess(
        f"cd {report_dir} && for file in $(ls); do curl -u {os.environ['ARTF_USER']}:{os.environ['ARTF_TOKEN']} -T $(realpath $file) {upload_url}/$(basename $file); done"
    )


@timer
@f_logger
def get_latest_case_version():
    """Get latest case version"""
    try:
        res = requests.get(CASE_INDEX_URL, allow_redirects=True)
        return yaml.safe_load(res.text)["latestVersion"]
    except yaml.YAMLError as exc:
        raise exc


@timer
@f_logger
def get_latest_released_image():
    """Get latest case image"""
    case_version = get_latest_case_version()
    case_url = f"https://raw.githubusercontent.com/IBM/cloud-pak/master/repo/case/ibm-oms-ent-case/{case_version}/ibm-oms-ent-case-{case_version}.tgz"
    download(case_url, f"ibm-oms-ent-case-{case_version}.tgz", "./")
    tar = tarfile.open(f"ibm-oms-ent-case-{case_version}.tgz", "r")
    for item in tar:
        if "ibmOmsEntProd/resources.yaml" in item.name:
            f = tar.extractfile(item)
            content = f.read()
            json_content = yaml.safe_load(content)
            image_tag = json_content["resources"]["resourceDefs"]["containerImages"][0]["tag"]
            run_subprocess(f"rm -f ibm-oms-ent-case-{case_version}.tgz")
            return f"stg.icr.io/cp/ibm-oms-enterprise/om-app:{image_tag}"
