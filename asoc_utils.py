import logging
import time

import requests
from requests.models import Response

from constants import (ASOC_API_ENDPOINT, JFROG_USER, PENDING_STATUSES,
                       TIME_TO_SLEEP)
from main_logger import main_logger
from settings import JENKINS_TAAS_TOKEN, JFROG_APIKEY, KEY_ID, KEY_SECRET
from utils import create_dir, get_date_str, logger, timer


@timer
@logger
def get_bearer_token():
    """
    Get the bearer token for ASoC API requests.

    Returns:
        [str]: the bearer token
    """

    res = requests.post(
        f"{ASOC_API_ENDPOINT}/Account/ApiKeyLogin",
        json={"KeyId": KEY_ID, "KeySecret": KEY_SECRET},
        headers={"Accept": "application/json"},
    )
    return res.json()["Token"]


# headers for API requests
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {get_bearer_token()}",
}


@timer
@logger
def get_download_config(name):
    """
    Get the report download configurations

    Args:
        name ([str]): the name of the scan

    Returns:
        [dict]: the configurations of the scan
    """
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
        "OdataFilter": "(Severity eq 'High' or Severity eq 'Critical' or Severity eq 'Medium' or Severity eq 'Low')",
    }


@timer
@logger
def download_report(type, report):
    """
    Download the generated report.

    Args:
        args ([dict]): the arguments passed to the script
        report ([dict]): the report to download
    """
    res = requests.get(f"{ASOC_API_ENDPOINT}/Reports/Download/{report['Id']}", headers=headers)
    if res.status_code == 200:
        reports_dir_path = f"reports/{get_date_str()}/{type}"
        create_dir(reports_dir_path)
        with open(f"{reports_dir_path}/{report['Name']}.html", "wb") as f:
            f.write(res.content)


@timer
@logger
def get_scans(app_id):
    """
        Get the list of scans for the application.

    Args:
        app_id ([str]): the application id that the scans belong to

    Returns:
        [list]: the list of scans belong to the application
    """
    res = requests.get(f"{ASOC_API_ENDPOINT}/Apps/{app_id}/Scans", headers=headers)
    if res.status_code == 200:
        return res.json()


@timer
@logger
def remove_old_scans(app_id):
    """
    Remove old scan by calling the ASoC API.

    Args:
        app_id ([str]): the application id that the scans belong to

    Returns:
        [dict]: the scans with their statuses
    """
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
        if old_scan["LatestExecution"]["Status"] in PENDING_STATUSES:
            scans_pending = True
    if scans_pending:
        main_logger.warning("Scan(s) pending. Returning...")
        return scan_status_dict

    # remove the old scans from the app before creating new ones
    for old_scan in old_scans:
        main_logger.info(f"Removing {old_scan['Name']} - {old_scan['Id']}... ")
        try:
            _ = requests.delete(
                f"{ASOC_API_ENDPOINT}/Scans/{old_scan['Id']}?deleteIssues=true",
                headers=headers,
            )
        except Exception as e:
            main_logger.warning(e)

    # reset the app
    try:
        main_logger.info(f"Resetting app {app_id}")
        reset_app_config_data = {"DeleteIssues": "true"}
        _ = requests.delete(
            f"{ASOC_API_ENDPOINT}/Apps/{app_id}/Reset",
            json=reset_app_config_data,
            headers=headers,
        )
    except Exception as e:
        main_logger.warning(e)

    return scan_status_dict


@timer
@logger
def wait_for_report(report):
    """
    Wait for the generated report to be ready.

    Args:
        report ([dict]): the report to download
    """
    while True:
        res = requests.get(f"{ASOC_API_ENDPOINT}/Reports/{report['Id']}", headers=headers)
        if res.status_code != 200:
            break

        if res.status_code == 200 and res.json()["Status"] == "Ready":
            break

        main_logger.info(f"Report for {report['Name']} is not ready. Waiting...")
        time.sleep(TIME_TO_SLEEP)
