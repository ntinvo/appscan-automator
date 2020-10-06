import argparse
import logging
import os
import requests
import subprocess
import sys
import coloredlogs

from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

# consts
API_KEY = os.environ.get("API_KEY")
DYNAMIC = "dymanic"
STATIC = "static"

# main logger
main_logger = logging.getLogger(__name__)


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
    parser.add_argument("-m", "--mode", choices=[DYNAMIC, STATIC], help=f"the type of scan to run.")

    args = parser.parse_args()
    setup_main_logging(args.verbose)
    return args


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
#     "PresenceId": "418df2a0-0608-eb11-96f5-00155d55406c",
#     "IncludeVerifiedDomains": "true",
#     "HttpAuthUserName": "string",
#     "HttpAuthPassword": "string",
#     "HttpAuthDomain": "string",
#     "OnlyFullResults": "true",
#     "TestOptimizationLevel": "NoOptimization",
#     "ScanName": "SMCFS Scan",
#     "EnableMailNotification": "false",
#     "Locale": "en-US",
#     "AppId": "fc449ae1-8742-49e9-a06b-fe37988ca2a8",
#     "Execute": "true",
#     "Personal": "false",
# }


# res = requests.post(
#     "https://cloud.appscan.com/api/v2/Scans/DynamicAnalyzer", json=data, headers=headers
# )

# print(res.text)


def main():
    args = parse_arguments()
    run_subprocess("ls -al", logger=main_logger)


if __name__ == "__main__":
    main()
