import os
from os.path import dirname, join

from dotenv import load_dotenv

# get env variables
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

KEY_ID = os.environ.get("KEY_ID")
KEY_SECRET = os.environ.get("KEY_SECRET")
JFROG_APIKEY = os.environ.get("JFROG_APIKEY")
JENKINS_TAAS_TOKEN = os.environ.get("JENKINS_TAAS_TOKEN")
