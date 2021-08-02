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


# import io
# import os
# import sys
# import zipfile
# from io import BytesIO
# from urllib.request import urlopen
# from zipfile import ZipFile

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


# # res = requests.get("https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux")
# # appscan_zip = zipfile.ZipFile(io.BytesIO(res.content))
# # # appscan_zip = ZipFile("/Users/tinnvo/Desktop/Dev/appscan_automator/SAClientUtil_8.0.1445_linux.zip")
# # appscan_zip.extractall("./tmp", get_members(appscan_zip))

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
