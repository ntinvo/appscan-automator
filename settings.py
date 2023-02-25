""" Settings """
import os
from os.path import dirname, join

from dotenv import load_dotenv

# get env variables
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

JFROG_APIKEY = os.environ.get("JFROG_APIKEY")
JENKINS_TAAS_TOKEN = os.environ.get("JENKINS_TAAS_TOKEN")
APPSCAN_HOME = os.environ.get("APPSCAN_HOME")
