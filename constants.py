""" Constants """
# consts
PADDING = 4
JFROG_REGISTRY = "wce-oms-onprem-dev-imgs-docker-local.artifactory.swg-devops.com"
JFROG_USER = "tin.vo@ibm.com"
JFROG_API_ENDPOINT = "https://na.artifactory.swg-devops.com/artifactory/api/docker/wce-oms-onprem-dev-imgs-docker-local/v2"
SINGLE_STREAM_RSS_URL = (
    "https://wce-sterling-team-oms-jenkins.swg-devops.com/job/COC_OMS_Dev.Build/rssAll"
)
DEPCHECK_REPO = "https://api.github.com/repos/jeremylong/DependencyCheck/releases/latest"
DEPLOY_SERVER = "https://9.42.105.123:9443"
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
DEPCHECK = "depcheck"
ALL = "all"
SCAN = "scan"
REPORTS = "reports"
PENDING_STATUSES = ["Running", "InQueue", "Paused", "Pausing", "Stopping"]
TIME_TO_SLEEP = 120
SINGLE = "single"
COCDEV = "cocdev"
COC = "coc"
V95 = "9.5"
V10 = "10.0"
SBA_JAR_URL = "https://wce-sterling-team-oms-jenkins.swg-devops.com/job/SBA/lastSuccessfulBuild/artifact/SBA.jar"
SBA_JAR = "SBA.jar"
IAC_JAR_URL = "https://wce-sterling-team-oms-jenkins.swg-devops.com/job/IAC/lastSuccessfulBuild/artifact/IAC.jar"
IAC_JAR = "IAC.jar"
ENTITLED_REGISTRY = "stg.icr.io"
TWISTLOCK_URL = "https://wce-sterling-team-oms-jenkins.swg-devops.com/job/OMS_CD_Development.TwistLock-Scan/lastSuccessfulBuild/artifact/tt_v1.5.0/linux_x86_64"
APPSCAN_URL = "https://na.artifactory.swg-devops.com:443/artifactory/wce-oms-onprem-dev-generic-local/Security_Scans/AppScan"
OWASP_URL = "https://na.artifactory.swg-devops.com:443/artifactory/wce-oms-onprem-dev-generic-local/Security_Scans/OWASP"
CASE_INDEX_URL = (
    "https://raw.githubusercontent.com/IBM/cloud-pak/master/repo/case/ibm-oms-ent-case/index.yaml"
)

# jazz
JAZZ_SINGLE_WS_ID = "1016"

# dynamic consts
DB2_SCAN = "db2_scan"
RT_SCAN = "rt_scan"
VOL_SCAN = "vol_scan"
NETWORK_SCAN = "network_scan"
DEPCHECK_SCAN = "depcheck_scan"

# ASoC consts
OMS_APP_ID = "87af65be-ef31-4aa7-871f-8354e19d6328"
SINGLE_DYNAMIC = "fc449ae1-8742-49e9-a06b-fe37988ca2a8"
SINGLE_STATIC = "14ad3e4d-8c6e-4e1a-a092-1249ef2b5d74"
ASOC_API_ENDPOINT = "https://cloud.appscan.com/api/v2"
APPSCAN_CONFIG = "appscan-config.xml"
APPSCAN_CONFIG_TMP = "appscan-config-tmp.xml"
APPSCAN_CONFIG_OP = "appscan-config-op.xml"
APPSCAN_ZIP_URL = "https://cloud.appscan.com/api/SCX/StaticAnalyzer/SAClientUtil?os=linux"
REPORT_FILE_TYPES = ["Html", "Pdf"]
MAX_TRIES = 5
HEADER_FIELDS = [
    "ScanName",
    "DateCreated",
    "DiscoveryMethod",
    "Scanner",
    "component",
    "intext",
    "ThreatClassId",
    "Severity",
    "asv",
    "ase",
    "asve",
    "IssueType",
    "SourceFile : Location",
    "Line",
    "dispo",
    "expl",
    "trgt",
    "compen",
    "Cve",
    "psirt",
    "Cvss",
    "Status",
    "Id",
]
