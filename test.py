# # from datetime import datetime
# # from math import ceil

# # # dt = datetime.today().strftime("%Y_%m")

# # dt = datetime.today()


# # def get_week_of_month(dt):
# #     first_day = datetime.today().replace(day=1)
# #     day_of_month = dt.day
# #     if first_day.weekday() == 6:
# #         adjusted_dom = (1 + first_day.weekday()) / 7
# #     else:
# #         adjusted_dom = day_of_month + first_day.weekday()
# #     return int(ceil(adjusted_dom / 7.0))

import io
import os
# download_appscan("./tmp")
import shutil
import sys
import zipfile
from datetime import datetime, timedelta
# from clint.textui import progressfrom distutils.dir_util import copy_tree
from distutils.dir_util import copy_tree
from io import BytesIO
from math import ceil
from urllib.request import urlopen
from zipfile import ZipFile

import requests

from main_logger import main_logger

copy_tree(
    "/Users/tinnvo/Desktop/Dev/appscan_automator/reports/2021_08_week_3/static",
    "/Users/tinnvo/Desktop/Dev/appscan_automator/reports/latest/static",
)

# from utils import download_appscan

# # dt = datetime.today()
# # week_of_month = get_week_of_month(dt)
# # a = dt.strftime("%Y_%m")
# # print(f"{a}_week_{week_of_month}")
# import requests

# # res = requests.get("https://9.42.105.123:9443/smcfs/console/login.jsp", timeout=20, verify=False)

# # print(res)

# # r = requests.get("https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux")
# # z = zipfile.ZipFile(io.BytesIO(r.content))
# # z.extractall("./testing/")

# # url = "https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux"
# # r = requests.get(url, stream=True)
# # with open("./testing/appscan.zip", "wb") as fd:
# #     for chunk in r.iter_content(chunk_size=128):
# #         fd.write(chunk)

# # with ZipFile("./testing/appscan.zip", "r") as zip_obj:
# #     for n in zip_obj.namelist():
# #         print(n)
# #     for l in zip_obj.infolist():
# #         print(l)

# #     zip_obj.extractall(
# #         path="./testing/ttest",
# #         members=[
# #             "SAClientUtil.8.0.1445/notices/Notices.txt",
# #             "SAClientUtil.8.0.1445/vdb/factory/php/vdb_cache.oz",
# #         ],
# #     )


# def get_members(zip_obj):
#     paths = []
#     for name in zip_obj.namelist():
#         paths.append(name.split("/"))
#     top_level_dir = os.path.commonprefix(paths)
#     top_level_dir = "/".join(top_level_dir) + "/" if top_level_dir else top_level_dir
#     for zip_file_info in zip_obj.infolist():
#         name = zip_file_info.filename
#         if len(name) > len(top_level_dir):
#             zip_file_info.filename = name[len(top_level_dir) :]
#             yield zip_file_info


# def download(url, filename, context):
#     try:
#         res = requests.get(url, stream=True)
#         main_logger.info(f"Download {filename} returned {res.status_code}")
#         if res.status_code != 200:
#             return False
#         total_length = int(res.headers.get("content-length"))
#         with open(f"{context}/{filename}", "wb") as file:
#             total_length = int(res.headers.get("content-length"))
#             for chunk in progress.bar(
#                 res.iter_content(chunk_size=1024),
#                 expected_size=(total_length / 1024) + 1,
#                 label="Downloading. Please wait >>> ",
#             ):
#                 if chunk:
#                     file.write(chunk)
#                     file.flush()
#         return True
#     except Exception as error:
#         main_logger.earning(error)
#         raise


# download(
#     "https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux",
#     "appscan.zip",
#     "./tmp/",
# )
# res = requests.get("https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux")
# appscan_zip = zipfile.ZipFile(io.BytesIO(res.content))
# appscan_zip = ZipFile("./tmp/appscan.zip")
# appscan_zip.extractall("./tmp/appscan")
# print(os.listdir("./tmp/appscan/"))
# appscan_zip.extractall("./tmp")

# from main_logger import main_logger

# name = "Tin"
# main_logger.error("Name is %s" % name)

# import os
# import shutil
# from distutils.dir_util import copy_tree

# def copytree(src, dst, symlinks=False, ignore=None):
#     for item in os.listdir(src):
#         s = os.path.join(src, item)
#         d = os.path.join(dst, item)
#         if os.path.isdir(s):
#             shutil.copytree(s, d, symlinks, ignore)
#         else:
#             shutil.copy2(s, d)


# copytree(
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/tmp/",
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/appscansrc/",
# )

# copy_tree(
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/tmp/",
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/appscansrc/",
# )

# if os.path.exists(to_path):
#         shutil.rmtree(to_path)
#     shutil.copytree(from_path, to_path)

# shutil.copytree(
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/tmp/appscan/SAClientUtil.8.0.1445",
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/tmp/tt",
# )


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
    # return (dt_obj.day - dt_obj.weekday() - 2) // 7 + 2
    # month = dt_obj.month
    # week = 0
    # while dt_obj.month == month:
    #     week += 1
    #     dt_obj -= timedelta(days=7)
    # return week
    # return (dt_obj.day - 1) // 7 + 1
    # first_day = datetime.today().replace(day=1)
    # print("First day", first_day)
    # day_of_month = dt_obj.day
    # print("day of month", day_of_month)
    # print("Firstday weekday", first_day.weekday())
    # if first_day.weekday() == 6:
    #     adjusted_dom = (1 + first_day.weekday()) / 7
    #     print(adjusted_dom)
    # else:
    #     adjusted_dom = day_of_month + first_day.weekday()
    # print("adjusted_dom", adjusted_dom)
    # return int(ceil(adjusted_dom / 7.0))


# dt = datetime(2011, 2, 28)
# dt = datetime.today()
# week_of_month = get_week_of_month(dt)
# print(week_of_month)

from clint.textui import progress

from constants import SBA_JAR, SBA_JAR_URL
from utils import get_auth


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
        print(res)
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

download("https://asocstorage.blob.core.windows.net/reports/bdbd1962-505e-4a1a-af15-6c50698050dc?sv=2021-10-04&se=2023-02-26T20%3A10%3A44Z&sr=b&sp=r&sig=HcrUTNxvxiSaW5U%2F17y7f6ZgHv1Z6nD1lvvagxhkezM%3D", "test.html", "reports" )


# download(SBA_JAR_URL, SBA_JAR, "./tmp/")

# import pdfkit

# pdfkit.from_url(
#     "http://9.42.105.123/~harness/scans/reports/2021_08_week_3/static/single_stream_static.html",
#     "/Users/tinnvo/Desktop/Dev/appscan_automator/reports/2021_08_week_3/static/single_stream_static.pdf",
# )
