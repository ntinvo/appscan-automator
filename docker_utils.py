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
def docker_login():
    """
    Login to the registry.
    """
    main_logger.info(f"#### Login to {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker login -u {JFROG_USER} -p {JFROG_APIKEY} {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def docker_logout():
    """
    Logout of the registry.
    """
    main_logger.info(f"#### Logout of {JFROG_REGISTRY} ####")
    run_subprocess(
        f"docker logout {JFROG_REGISTRY}", logger=main_logger,
    )


@timer
@logger
def get_remove_image_list(args):
    """
    Get the list of image to remove before spinning up new containers.

    Args:
        args ([dict]): the arguments passed to the script

    Returns:
        [list]: list of images to remove
    """
    containers = client.containers.list(all=True)
    return [
        image
        for con in containers
        for image in con.image.tags
        if f"oms-{args.version}-db2" in image
    ]


@timer
@logger
def cleanup_helper(cmd):
    """
    Clean up helper to run the command passed by cleanup func

    Args:
        cmd ([str]): the command to to in subprocess
    """
    try:
        run_subprocess(cmd)
    except Exception as e:
        main_logger.warning(e)


@timer
@logger
def cleanup(args):
    """
    Cleaning up the resources before creating new containers.
    The will do the followings:
        - get the image list to remove 
        - remove rt and db2 containers 
        - remove volume and network 
        - remove images

    Args:
        args ([dict]): the arguments passed to the script
    """

    # clean up before creating new containers
    remove_images = get_remove_image_list(args)
    if len(remove_images) == 0:
        return

    # disconnect the containers and network
    main_logger.info(f"Disconnecting runtime container {RT_SCAN} from network {NETWORK_SCAN}...")
    cleanup_helper(f"docker network disconnect -f {NETWORK_SCAN} {RT_SCAN}")
    main_logger.info(f"Disconnecting db2 container {DB2_SCAN} from network {NETWORK_SCAN}...")
    cleanup_helper(f"docker network disconnect -f {NETWORK_SCAN} {DB2_SCAN}")

    # removing runtime container
    main_logger.info(f"Removing runtime container {RT_SCAN}...")
    cleanup_helper(f"docker rm -f {RT_SCAN}")

    # removing runtime container
    main_logger.info(f"Removing db2 container {DB2_SCAN}...")
    cleanup_helper(f"docker rm -f {DB2_SCAN}")

    # removing runtime container
    main_logger.info(f"Removing volume {VOL_SCAN}...")
    cleanup_helper(f"docker volume rm -f {VOL_SCAN}")

    # removing runtime container
    run_subprocess(f"docker network rm {NETWORK_SCAN}")

    # removing images
    for image in remove_images:
        main_logger.info(f"Removing image {image}...")
        cleanup_helper(f"docker rmi {image}")


@timer
@logger
def start_db2_container(args, image_tag, logger=main_logger):
    """
    Start the db2 container for deployment.

    Args:
        args ([str]): the arguments passed to the script
        image_tag ([str]): the tag of the image
        logger ([logging], optional): the logger to log the output. Defaults to main_logger.

    Raises:
        Exception: exception raised when running subprocess
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
        args ([dict]): the arguments passed to the script
        image_tag ([str]): the tag of the image
        logger ([logging], optional): the logger to log the output. Defaults to main_logger.

    Raises:
        Exception: exception raised when spinning up runtime container
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
        args ([dict]): the arguments passed to the script
        image_tag ([str]): the tag of the image
    """

    # clean up
    cleanup(args)

    # login to registry
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

    # logout of registry
    docker_logout()
