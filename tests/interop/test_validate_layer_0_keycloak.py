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

patterns_repo = os.environ.get(
    "PATTERN_REPO",
    f"{os.environ['HOME']}/validated_patterns/layered-zero-trust",
)
# Keycloak (RHBK) chart is from https://github.com/validatedpatterns/rhbk-chart; customize via values-hub overrides
values_hub_path = os.path.join(patterns_repo, "values-hub.yaml")
logger.debug(f'Pattern repo: "{patterns_repo}", values-hub: "{values_hub_path}"')


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
def test_keycloak_ui_reachability_customized_hostname_via_override(
    openshift_dyn_client,
):
    """Customize Keycloak hostname via values-hub overrides (rhbk-chart)."""
    customized_hostname = "keycloak-customized"
    logger.info(
        "Checking reachability with customized hostname via values-hub override"
    )
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if not app_route:
        assert False, f'No route found in "{app_project_name}" with label "{app_label}"'
    app_hostname = app_route[0].host
    base_hostname = ".".join(app_hostname.split(".")[1:])
    hostname_value = f"{customized_hostname}.{base_hostname}"
    modify_keycloak_hostname_via_hub_overrides(values_hub_path, hostname_value)
    logger.info("Commit and push the change")
    git_submit_and_push(
        path=values_hub_path,
        working_dir=patterns_repo,
        commit_message="Update Keycloak hostname via values-hub override",
    )
    app_url = f"https://{hostname_value}"
    rsp = wait_for(app_url=app_url, acceptable_status_codes=[requests.codes.ok])
    assert requests.codes.ok == rsp.status_code


@pytest.mark.test_keycloak_ui_reachability_empty_hostname
def test_keycloak_ui_reachability_empty_hostname_via_override(openshift_dyn_client):
    """Use default Keycloak hostname by clearing the override in values-hub."""
    logger.info("Verify Keycloak reachability with default hostname (clear override)")
    modify_keycloak_hostname_via_hub_overrides(values_hub_path, None)
    logger.info("Commit and push the change")
    git_submit_and_push(
        path=values_hub_path,
        working_dir=patterns_repo,
        commit_message="Clear Keycloak hostname override in values-hub",
    )
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if not app_route:
        assert False, f'No route found in "{app_project_name}" with label "{app_label}"'
    app_hostname = app_route[0].host
    base_hostname = ".".join(app_hostname.split(".")[1:])
    app_url = f"https://keycloak.{base_hostname}"
    rsp = wait_for(app_url=app_url, acceptable_status_codes=[requests.codes.ok])
    assert requests.codes.ok == rsp.status_code


def modify_keycloak_hostname_via_hub_overrides(values_hub_path, hostname):
    """
    Set or clear keycloak.ingress.hostname for the rh-keycloak application in values-hub.yaml.
    Keycloak is deployed from rhbk-chart; overrides are the way to customize hostname.
    """
    logger.info(
        "Modify Keycloak hostname via clusterGroup.applications.rh-keycloak.overrides"
    )
    if not os.path.isfile(values_hub_path):
        raise FileNotFoundError(f"values-hub not found: {values_hub_path}")
    with open(values_hub_path, "r") as f:
        data = yaml.safe_load(f)
    apps = data["clusterGroup"]["applications"]
    if "rh-keycloak" not in apps:
        raise KeyError(
            "clusterGroup.applications.rh-keycloak not found in values-hub.yaml"
        )
    overrides = apps["rh-keycloak"].get("overrides") or []
    overrides = [o for o in overrides if o.get("name") != "keycloak.ingress.hostname"]
    if hostname:
        overrides.append({"name": "keycloak.ingress.hostname", "value": hostname})
    apps["rh-keycloak"]["overrides"] = overrides
    with open(values_hub_path, "w") as f:
        yaml.safe_dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
