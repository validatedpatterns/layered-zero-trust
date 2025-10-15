import logging

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
