import os
from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

API_KEY = os.environ.get("API_KEY")

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

data = {
    "StartingUrl": "http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp",
    "LoginUser": "admin",
    "LoginPassword": "password",
    "ScanType": "Production",
    "PresenceId": "418df2a0-0608-eb11-96f5-00155d55406c",
    "IncludeVerifiedDomains": "true",
    "HttpAuthUserName": "string",
    "HttpAuthPassword": "string",
    "HttpAuthDomain": "string",
    "OnlyFullResults": "true",
    "TestOptimizationLevel": "NoOptimization",
    "ScanName": "SMCFS Scan",
    "EnableMailNotification": "false",
    "Locale": "en-US",
    "AppId": "fc449ae1-8742-49e9-a06b-fe37988ca2a8",
    "Execute": "true",
    "Personal": "false",
}

import requests

res = requests.post(
    "https://cloud.appscan.com/api/v2/Scans/DynamicAnalyzer", json=data, headers=headers
)

print(res.text)

