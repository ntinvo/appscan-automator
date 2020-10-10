import logging
import time

import requests

from constants import ASOC_API_ENDPOINT, PENDING_STATUSES, TIME_TO_SLEEP
from settings import KEY_ID, KEY_SECRET
from utils import create_dir, get_date_str, logger, timer

# logging
main_logger = logging.getLogger(__name__)


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


@timer
@logger
def download_report(args, report):
    """Download the generated report"""
    res = requests.get(f"{ASOC_API_ENDPOINT}/Reports/Download/{report['Id']}", headers=headers)
    if res.status_code == 200:
        reports_dir_path = f"reports/{args.type}/{get_date_str()}"
        create_dir(reports_dir_path)
        with open(f"{reports_dir_path}/{report['Name']}.html", "wb") as f:
            f.write(res.content)


@timer
@logger
def get_scans(app_id):
    """Get the list of scans for the application"""
    res = requests.get(f"{ASOC_API_ENDPOINT}/Apps/{app_id}/Scans", headers=headers)
    if res.status_code == 200:
        return res.json()


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
        time.sleep(TIME_TO_SLEEP)
