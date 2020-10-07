# consts
SINGLE_STREAM_RSS_URL = (
    "http://9.121.242.67:9080/jenkins/view/L3%20Builds/job/Single_Stream_Project/rssAll"
)
DEPLOY_SERVER = "http://single1.fyre.ibm.com:7001"
SMCFS_URL = f"{DEPLOY_SERVER}/smcfs/console/login.jsp"
SBC_URL = f"{DEPLOY_SERVER}/sbc/sbc/login.do"
SMA_URL = f"{DEPLOY_SERVER}/sma/sma/container/home.do"
ISCCS_URL = f"{DEPLOY_SERVER}/isccs/isccs/login.do"
WSC_URL = f"{DEPLOY_SERVER}/wsc/wsc/login.do"
APP_URL_DICT = {
    "SMCFS": SMCFS_URL,
    "SBC": SBC_URL,
    "SMA": SMA_URL,
    "ISCCS": ISCCS_URL,
    "WSC": WSC_URL,
}
NS = {"W3": "http://www.w3.org/2005/Atom"}
DYNAMIC = "dynamic"
STATIC = "static"
ALL = "all"

# ASoC consts
OMS_APP_ID = "87af65be-ef31-4aa7-871f-8354e19d6328"
SINGLE_DYNAMIC = "fc449ae1-8742-49e9-a06b-fe37988ca2a8"
SINGLE_STATIC = "14ad3e4d-8c6e-4e1a-a092-1249ef2b5d74"
PRESENCE_ID = "418df2a0-0608-eb11-96f5-00155d55406c"
ASOC_LOGIN_ENDPOINT = "https://cloud.appscan.com/api/V2/Account/ApiKeyLogin"
ASOC_DYNAMIC_ENDPOINT = "https://cloud.appscan.com/api/v2/Scans/DynamicAnalyzer"
ASOC_FILE_UPLOAD = "https://cloud.appscan.com/api/v2/FileUpload"
