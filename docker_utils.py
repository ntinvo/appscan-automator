import logging
import os
import time
import traceback

import docker
import requests

from constants import DB2_SCAN, JFROG_REGISTRY, JFROG_USER, NETWORK_SCAN, RT_SCAN, VOL_SCAN
from settings import JFROG_APIKEY
from utils import logger, run_subprocess, timer

# logging
main_logger = logging.getLogger(__name__)

client = docker.from_env()


@timer
@logger
def get_remove_image_list(args):
    """Get the list of image to remove before spinning up new containers"""
    containers = client.containers.list()
    return [
        image
        for con in containers
        for image in con.image.tags
        if f"oms-{args.version}-db2" in image
    ]


@timer
@logger
def docker_login():
    """Login to the registry."""
    main_logger.info(f"#### Login to {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker login -u {JFROG_USER} -p {JFROG_APIKEY} {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def docker_logout():
    """Logout of the registry."""
    main_logger.info(f"#### Logout of {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker logout {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def start_db2_container(args, image_tag, logger=main_logger):
    """
    Start the db2 container for deployment.
    
    Args:
        image_tag: the tag of the image
        logger: the logger to log the output
    Returns:
        None
    """
    try:
        db_image_repo = f"{JFROG_REGISTRY}/oms-{args.version}-db2-db:{image_tag}-refs"
        logger.info(f"#### STARTING DB2 CONTAINER: {DB2_SCAN} - {db_image_repo} ####")
        run_subprocess(
            f" \
            docker volume create {VOL_SCAN} && \
            docker network create {NETWORK_SCAN} && \
            docker run -di --name {DB2_SCAN} --privileged \
            --network={NETWORK_SCAN} \
            -e DB2INSTANCE=db2inst1 \
            -e DB2INST1_PASSWORD=db2inst1 \
            -e DB_USER=omsuser \
            -e DB_PASSWORD=omsuser \
            -e LICENSE=accept \
            -e DBNAME=omdb \
            -e AUTOCONFIG=false \
            -v {VOL_SCAN}:/database \
            -p 50005:50000 {db_image_repo} && \
            chmod +x {os.getcwd()}/waitDB2.sh && \
            /bin/bash {os.getcwd()}/waitDB2.sh {DB2_SCAN}",
            logger=logger,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        raise Exception


@timer
@logger
def start_rt_container(args, image_tag, logger=main_logger):
    """
    Start the rt container for deployment
    
    Args:
        image_tag: the tag of the image
        logger: the logger to log the output
    Returns:
        None
    """
    try:
        rt_image_repo = f"{JFROG_REGISTRY}/oms-{args.version}-db2-rt:{image_tag}-weblogic"
        logger.info(f"#### STARTING DB2 CONTAINER: {RT_SCAN} - {rt_image_repo} ####")
        run_subprocess(
            f" \
            docker run -di --name {RT_SCAN} --privileged \
            --network={NETWORK_SCAN} \
            -e DB_HOST={DB2_SCAN} \
            -e DB_PORT=50000 \
            -e DB_VENDOR=db2 \
            -e DB_NAME=OMDB \
            -p 7001:7001 \
            {rt_image_repo}",
            logger=logger,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        raise Exception


@timer
@logger
def prep_containers(args, image_tag):
    """
    Prepare the rt and db2 container. This function will do the followings:
    - login to the registry 
    - start db2 and rt containers 
    - build the ear for deployment 
    - start weblogic server 
    - wait for the server to be ready
    - logout of the registry

    Args:
        image_tag: the tag of the image
    Returns:
        None

    NOTE: as of now, this only supports single images; this can be enhanced to prep other versions    
    """
    docker_login()

    # starting db2 and rt containers
    main_logger.info("Starting db2 and rt containers...")
    start_db2_container(args, image_tag)
    start_rt_container(args, image_tag)

    # build the ear
    main_logger.info("Building ear file...")
    run_subprocess(f'docker exec {RT_SCAN} bash -lc "buildear -warfiles=smcfs,sbc,sma,isccs,wsc"')

    # start weblogic server
    main_logger.info("Starting weblogic server...")
    run_subprocess(f'docker exec {RT_SCAN} bash -lc "__wlstart -autodeploy=true"')

    # check to make sure the apps are run and running
    main_logger.info(
        "Checking deployment @ http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp..."
    )
    while True:
        try:
            res = requests.get(
                "http://single1.fyre.ibm.com:7001/smcfs/console/login.jsp", timeout=20
            )
            if res.status_code == 200:
                break
        except Exception as _e:
            time.sleep(10)

    main_logger.info("The db2 and rt containers are up and running...")
    docker_logout()
