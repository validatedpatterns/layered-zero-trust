import logging
import os
import subprocess
import time

import requests
from ocp_resources.pod import Pod
from ocp_resources.project_project_openshift_io import Project
from ocp_resources.replica_set import ReplicaSet
from ocp_resources.resource import Resource
from ocp_resources.route import Route
from requests import HTTPError, RequestException
from urllib3.exceptions import InsecureRequestWarning

from . import __loggername__

logger = logging.getLogger(__loggername__)


def send_get_request(site_url):
    site_response = None

    try:
        # Suppress only the single warning from urllib3 needed.
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
        site_response = requests.get(site_url, verify=False)
    except (ConnectionError, HTTPError, RequestException) as e:
        logger.exception(
            "Failed to connect %s due to refused connection or unsuccessful status code %s",
            site_url,
            e,
        )
    logger.debug(f"Site Response is: {site_response}")

    return site_response


def verify_pod_in_project(openshift_dyn_client, project, pod):
    pod_name = pod
    logger.debug(f'Verify pod "{pod}" in project "{project}"')
    try:
        pods = Pod.get(dyn_client=openshift_dyn_client, namespace=project)
        for pod in pods:
            logger.debug(f"Current pod: {pod.instance.metadata.name}")
            if pod.instance.metadata.name == pod_name:
                logger.debug("Pod name match!")
                for container in pod.instance.status.containerStatuses:
                    if container.state.terminated:
                        if (
                            container.state.terminated.reason
                            != Resource.Status.COMPLETED
                        ):
                            return False
                    elif not container.state.running:
                        return False
                return True
        return False
    except StopIteration:
        raise


def verify_pod_by_deployment(openshift_dyn_client, project, deployment):
    rs = None
    pod = None
    try:
        replicasets = ReplicaSet.get(dyn_client=openshift_dyn_client, namespace=project)
        rs = _get_resource_by_owner(deployment, replicasets)
        if rs.instance.spec.replicas == 0:
            return True
        pods = Pod.get(dyn_client=openshift_dyn_client, namespace=project)
        pod = _get_resource_by_owner(rs.name, pods)
        logger.debug(f'Found matching pod: "{pod.name}"')
        return verify_pod_in_project(
            openshift_dyn_client=openshift_dyn_client, project=project, pod=pod.name
        )
    except StopIteration:
        raise


def _get_resource_by_owner(owner, resources):
    try:
        for res in resources:
            res_owner = res.instance.metadata.ownerReferences[0].name
            logger.debug(f"Current Resource: {res.name} Owner: {res_owner}")
            if res_owner == owner:
                return res
        return None
    except StopIteration:
        raise


def get_route_by_app_label(openshift_dyn_client, project, label):
    label = label.split("=")
    matches = []
    try:
        routes = Route.get(dyn_client=openshift_dyn_client, namespace=project)
        for route in routes:
            if label[0] in route.labels.keys():
                if route.labels[label[0]] == label[-1]:
                    matches.append(route)
        if len(matches) > 0:
            return matches
        return None
    except StopIteration:
        raise


def verify_project(openshift_dyn_client, project_name):
    try:
        projects = Project.get(dyn_client=openshift_dyn_client)
        for project in projects:
            if project.name == project_name:
                if project.status == Project.Status.ACTIVE:
                    return True
    except StopIteration:
        raise
    return False


def git_submit_and_push(path, working_dir, commit_message, push=True):
    if os.getenv("EXTERNAL_TEST") != "true":
        subprocess.run(["git", "add", path], cwd=f"{working_dir}")
        subprocess.run(["git", "commit", "-m", commit_message], cwd=f"{working_dir}")
        if push:
            push = subprocess.run(
                ["git", "push"], cwd=f"{working_dir}", capture_output=True, text=True
            )
    else:
        subprocess.run(["git", "add", path])
        subprocess.run(["git", "commit", "-m", commit_message])
        if push:
            push = subprocess.run(["git", "push"], capture_output=True, text=True)
    logger.info(push.stdout)
    logger.info(push.stderr)


def wait_for(
    app_url, timeout_minutes=10, sleep_seconds=30, acceptable_status_codes=None
):
    """
    Wait for a URL to become available by polling it until it returns an acceptable status code.

    Args:
        app_url: The URL to poll
        timeout_minutes: Maximum time to wait in minutes (default: 10)
        sleep_seconds: Time to wait between attempts in seconds (default: 30)
        acceptable_status_codes: List of acceptable HTTP status codes (default: [200, 401])

    Returns:
        The response object if successful, or the last response if timeout occurs
    """
    if acceptable_status_codes is None:
        acceptable_status_codes = [requests.codes.ok, requests.codes.unauthorized]

    counter = 0
    timeout = time.time() + 60 * timeout_minutes
    logger.debug(f"Waiting for URL: {app_url} (timeout: {timeout_minutes} minutes)")

    while time.time() < timeout:
        time.sleep(sleep_seconds)
        counter += 1
        logger.info(f"Attempt #{counter}...")
        rsp = send_get_request(site_url=app_url)

        if rsp is not None and rsp.status_code in acceptable_status_codes:
            logger.debug(
                f"Successfully received status {rsp.status_code} from {app_url}"
            )
            return rsp

    logger.warning(f"Timeout reached waiting for {app_url}")
    return rsp


def run_shell_script(script_path, args=None, cwd=None, timeout=300):
    """
    Run a shell script and return its result.

    Args:
        script_path: Path to the shell script to execute
        args: Optional list of arguments to pass to the script
        cwd: Optional working directory for script execution
        timeout: Maximum time in seconds to wait for script completion (default: 300)

    Returns:
        A dictionary containing:
            - returncode: The exit code of the script
            - stdout: Standard output from the script
            - stderr: Standard error from the script
            - success: Boolean indicating if returncode was 0
    """
    logger.info(f"Running shell script: {script_path}")

    cmd = [script_path]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )

        logger.debug(f"Script exit code: {result.returncode}")
        logger.debug(f"Script stdout: {result.stdout}")
        if result.stderr:
            logger.debug(f"Script stderr: {result.stderr}")

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Script execution timed out after {timeout} seconds")
        raise
    except Exception as e:
        logger.error(f"Failed to execute script: {e}")
        raise
