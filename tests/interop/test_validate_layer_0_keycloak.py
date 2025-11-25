import logging
import os

import pytest
import requests
import yaml

from . import __loggername__
from .utils import (
    get_route_by_app_label,
    git_submit_and_push,
    send_get_request,
    verify_pod_in_project,
    wait_for,
)

logger = logging.getLogger(__loggername__)


app_project_name = "keycloak-system"
app_label = "app=keycloak"

patterns_repo = f"{os.environ['HOME']}/validated_patterns/layered-zero-trust"
values_path = "charts/keycloak/values.yaml"
if os.getenv("EXTERNAL_TEST") != "true":
    values_path = f"{patterns_repo}/{values_path}"
else:
    values_path = "../../" + values_path
logger.debug(f'Values file path is: "{values_path}"')


@pytest.mark.test_keycloak_pod_state
def test_keycloak_pod_state(openshift_dyn_client):
    desired_pods = {
        "keycloak-0": "keycloak-system",
        "postgresql-db-0": "keycloak-system",
    }

    for pod_name, project_name in desired_pods.items():
        pod_running = verify_pod_in_project(
            openshift_dyn_client=openshift_dyn_client,
            project=project_name,
            pod=pod_name,
        )
        assert pod_running


@pytest.mark.test_keycloak_ui_reachability_default_hostname
def test_keycloak_ui_reachability_default_hostname(openshift_dyn_client):
    logger.info('Verify Keycloak reachability with hostname: ""')
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_route:
        app_hostname = app_route[0].host
        app_url = "https://" + app_hostname
        logger.info(f"Application url is: {app_url}")
        rsp = send_get_request(site_url=app_url)
        assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


@pytest.mark.test_keycloak_ui_reachability_customized_hostname
def test_keycloak_ui_reachability_customized_hostname(openshift_dyn_client):
    customized_hostname = "keycloak-customized"

    logger.info("Checking reachability with updated hostname")
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_route:
        app_hostname = app_route[0].host
        base_hostname = ".".join(app_hostname.split(".")[1:])
        logger.info("Update Keyloak chart with customized hostname")
        modify_keycloak_hostname(
            values_path=values_path, hostname=f"{customized_hostname}.{base_hostname}"
        )

        logger.info("Commit and push the change")
        git_submit_and_push(
            path=values_path,
            working_dir=patterns_repo,
            commit_message="Update Keycloak hostname",
        )
        app_url = f"https://{customized_hostname}.{base_hostname}"
        rsp = wait_for(app_url=app_url, acceptable_status_codes=[requests.codes.ok])
        assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


@pytest.mark.test_keycloak_ui_reachability_empty_hostname
def test_keycloak_ui_reachability_empty_hostname(openshift_dyn_client):
    logger.info('Verify Keycloak reachability with hostname: ""')
    modify_keycloak_hostname(values_path=values_path, hostname=None)
    logger.info("Commit and push the change")
    git_submit_and_push(
        path=values_path,
        working_dir=patterns_repo,
        commit_message="Update Keycloak hostname",
    )
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_route:
        app_hostname = app_route[0].host
        base_hostname = ".".join(app_hostname.split(".")[1:])
        app_url = f"https://keycloak.{base_hostname}"
        rsp = wait_for(app_url=app_url, acceptable_status_codes=[requests.codes.ok])
        assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


def modify_keycloak_hostname(values_path, hostname):
    logger.info("Modify hostname values for Keycloak")
    try:
        with open(values_path, "r") as file:
            values = yaml.safe_load(file)

            if "hostname" in values["keycloak"]["ingress"].keys():
                logger.info(
                    f"App hostname (current): \"{values['keycloak']['ingress']['hostname']}\""
                )
            else:
                logger.info("App hostname (current): None")

            if hostname:
                values["keycloak"]["ingress"]["hostname"] = hostname
                logger.info(
                    f"App hostname (new): \"{values['keycloak']['ingress']['hostname']}\""
                )
            else:
                del values["keycloak"]["ingress"]["hostname"]
                logger.info("App hostname removed")

        with open(values_path, "w") as file:
            file.write(yaml.safe_dump(values))
    except Exception:
        raise
