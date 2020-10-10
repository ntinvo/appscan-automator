import os
from os.path import dirname, join

from dotenv import load_dotenv

# get env variables
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)

KEY_ID = os.environ.get("KEY_ID")
KEY_SECRET = os.environ.get("KEY_SECRET")
JFROG_APIKEY = os.environ.get("JFROG_APIKEY")
JAZZ_REPO = os.environ.get("JAZZ_REPO")
JAZZ_USER = os.environ.get("JAZZ_USER")
JAZZ_PASS = os.environ.get("JAZZ_PASS")
