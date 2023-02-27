""" Docker Utils """
import os
import time

import docker
import requests

from constants import (DB2_SCAN, DEPCHECK_SCAN, DEPLOY_SERVER,
                       ENTITLED_REGISTRY, NETWORK_SCAN, RT_SCAN, VOL_SCAN)
from main_logger import main_logger
from utils import f_logger, run_subprocess, timer

client = docker.from_env()


@timer
@f_logger
def docker_login():
    """
    Login to the registry.
    """
    main_logger.info(f"#### Login to {ENTITLED_REGISTRY} ####")
    run_subprocess(
        f"docker login -u {os.environ['ENTITLED_REGISTRY_USER']} -p {os.environ['ENTITLED_REGISTRY_TOKEN']} {ENTITLED_REGISTRY}",
        logger=main_logger,
    )


@timer
@f_logger
def docker_logout():
    """
    Logout of the registry.
    """
    main_logger.info(f"#### Logout of {ENTITLED_REGISTRY} ####")
    run_subprocess(
        f"docker logout {ENTITLED_REGISTRY}", logger=main_logger,
    )


@timer
@f_logger
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
@f_logger
def cleanup_helper(cmd):
    """
    Clean up helper to run the command passed by cleanup func

    Args:
        cmd ([str]): the command to to in subprocess
    """
    try:
        run_subprocess(cmd)
    except Exception as error:
        main_logger.warning(error)


@timer
@f_logger
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
    try:
        main_logger.info(f"Removing db2 container {DB2_SCAN}...")
        cleanup_helper(f"docker rm -f {DB2_SCAN}")
    except Exception as error:
        main_logger.info(error)

    # removing runtime container
    try:
        main_logger.info(f"Removing volume {VOL_SCAN}...")
        cleanup_helper(f"docker volume rm -f {VOL_SCAN}")
    except Exception as error:
        main_logger.info(error)

    # removing scan network
    try:
        main_logger.info(f"Removing network {NETWORK_SCAN}")
        run_subprocess(f"docker network rm {NETWORK_SCAN}")
    except Exception as error:
        main_logger.info(error)

    # removing images
    for image in remove_images:
        try:
            main_logger.info(f"Removing image {image}...")
            cleanup_helper(f"docker rmi {image}")
        except Exception as error:
            main_logger.info(error)


@timer
@f_logger
def pre_install_app(rt_name=RT_SCAN):
    """Remove runtime app container and volume"""
    try:
        run_subprocess(f"docker rm -f {rt_name}")
    except Exception as _:
        pass


@timer
@f_logger
def wait_for_deployment():
    """
    Waiting for the deployment to be ready.
    """
    while True:
        try:
            res = requests.get(f"{DEPLOY_SERVER}/smcfs/console/login.jsp", timeout=20, verify=False)
            if res.status_code == 200:
                break
        except Exception as _e:
            time.sleep(10)


@timer
@f_logger
def start_app_container(image, rt_name=RT_SCAN, logger=main_logger):
    """
    Start the rt container for deployment

    Args:
        args ([dict]): the arguments passed to the script
        image_tag ([str]): the tag of the image
        logger ([logging], optional): the logger to log the output. Defaults to main_logger.

    Raises:
        Exception: exception raised when spinning up runtime container
    """
    configs_dir = f"{os.getcwd()}/app_configs"
    try:
        docker_login()
        pre_install_app(rt_name)
        command = f"docker run -dit --name {rt_name} -v {configs_dir}/jvm.options:/config/jvm.options -v {configs_dir}/server.xml.updated:/config/server.xml -v {configs_dir}/system_overrides.properties.updated:/config/dropins/smcfs.ear/properties.jar/system_overrides.properties -p 9080:9080 -p 9443:9443 {image}"
        logger.info(f"#### STARTING RT CONTAINER: {rt_name} - {image} ####")
        logger.info(f"Command: {command}")
        run_subprocess(command, logger=logger)
        wait_for_deployment()
    except Exception as error:
        logger.warning(error)
        docker_logout()
        raise Exception  # pylint: disable=raise-missing-from
    finally:
        docker_logout()


@timer
@f_logger
def start_depcheck_container(image, rt_name=DEPCHECK_SCAN, logger=main_logger):
    """
    Start the depcheck rt container for getting the jars

    Args:
        args ([dict]): the arguments passed to the script
        image_tag ([str]): the tag of the image
        logger ([logging], optional): the logger to log the output. Defaults to main_logger.

    Raises:
        Exception: exception raised when spinning up runtime container
    """
    try:
        docker_login()
        command = f"docker run -dit -e LICENSE=accept -e LANG --privileged -v {VOL_SCAN}:/images --name {rt_name} {image}"
        logger.info(f"#### STARTING RT CONTAINER: {rt_name} - {image} ####")
        logger.info(f"Command: {command}")
        run_subprocess(command, logger=logger)
    except Exception as error:
        logger.warning(error)
        docker_logout()
        raise Exception  # pylint: disable=raise-missing-from
    finally:
        docker_logout()


@timer
@f_logger
def get_image_from_container(container, logger=main_logger):
    """Return the image from a container"""
    try:
        _, image = run_subprocess(f'docker inspect --format="{{{{.Config.Image}}}}" {container}')
        image = image.replace("\n", "")
        return image
    except Exception as _:
        logger.warn(f"Container {container} does not exist")
        return None


@timer
@f_logger
def cleanup_runtime_container(container, logger=main_logger):
    """Clean up runtime container"""
    # Remove the container
    try:
        logger.info(f"Removing container {container}")
        _, out = run_subprocess(f"docker rm -f {container}")
    except Exception as _:
        logger.warn(out)

    # Remove the image if needed
    image = get_image_from_container(container)
    if container == DEPCHECK_SCAN:
        tmp_image = get_image_from_container(RT_SCAN)
    else:
        tmp_image = get_image_from_container(DEPCHECK_SCAN)
    if image != tmp_image:
        try:
            logger.info(f"Trying to remove image {image}")
            _, out = run_subprocess(f"docker rmi {image}")
        except Exception as _:
            logger.warn(out)

    # Remove un-used volumes
    try:
        logger.info("Removing un-used volumes")
        _, out = run_subprocess("docker volume prune -f")
    except Exception as _:
        logger.warn(out)
