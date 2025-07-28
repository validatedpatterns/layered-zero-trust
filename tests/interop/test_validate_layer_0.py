import logging
import os

import pytest
import requests

from . import __loggername__
from .pattern_crd import CertManager, ExternalSecret
from .utils import (
    get_route_by_app_label,
    send_get_request,
    verify_pod_by_deployment,
    verify_pod_in_project,
)

logger = logging.getLogger(__loggername__)

oc = os.environ["HOME"] + "/oc_client/oc"


@pytest.mark.test_vault_pod_state
def test_vault_pod_state(openshift_dyn_client):
    project_name = "vault"
    pod_name = "vault-0"
    app_pod_running = verify_pod_in_project(
        openshift_dyn_client=openshift_dyn_client, project=project_name, pod=pod_name
    )
    assert app_pod_running


@pytest.mark.test_vault_api_health
def test_vault_api_health(openshift_dyn_client):
    app_project_name = "vault"
    app_label = "app.kubernetes.io/name=vault"
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_route:
        app_hostname = app_route[0].host
        app_api_health_endpoint = "https://" + app_hostname + "/sys/health"
        logger.info("Application health endpoint is: " + app_api_health_endpoint)
        rsp = send_get_request(site_url=app_api_health_endpoint)
        assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


@pytest.mark.test_vault_ui_reachability
def test_vault_ui_reachability(openshift_dyn_client):
    app_project_name = "vault"
    app_label = "app.kubernetes.io/name=vault"
    app_route = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_route:
        vault_hostname = app_route[0].host
        vault_ui_url = "https://" + vault_hostname + "/ui/"
        rsp = send_get_request(site_url=vault_ui_url)
        assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


@pytest.mark.test_external_secret_custom_resource
def test_external_secret_custom_resource(openshift_dyn_client):
    try:
        external_secrets = ExternalSecret.get(dyn_client=openshift_dyn_client)
        for external_secrets in external_secrets:
            logger.debug(f'Found ExternalSecret "{external_secrets.name}"')
    except StopIteration:
        err_msg = "No ExternalSecret created or found"
        assert False, err_msg


@pytest.mark.test_cert_manager_custom_resource
def test_cert_manager_custom_resource(openshift_dyn_client):
    try:
        cert_managers = CertManager.get(dyn_client=openshift_dyn_client)
        for cert_manager in cert_managers:
            logger.debug(f'Found CertManager "{cert_manager.name}"')
    except StopIteration:
        err_msg = "No CertManager created or found"
        assert False, err_msg


@pytest.mark.test_compliance_operator_pod_state
def test_compliance_operator_pod_state(openshift_dyn_client):
    desired_deployment = {"compliance-operator": "openshift-compliance"}
    for deploment_name, project_name in desired_deployment.items():
        pod_running = verify_pod_by_deployment(
            openshift_dyn_client=openshift_dyn_client,
            project=project_name,
            deployment=deploment_name,
        )
        assert pod_running


@pytest.mark.test_openshift_compliance_pod_state
def test_openshift_compliance_pod_state(openshift_dyn_client):
    desired_deployment = {
        "ocp4-openshift-compliance-pp": "openshift-compliance",
        "rhcos4-openshift-compliance-pp": "openshift-compliance",
    }
    for deploment_name, project_name in desired_deployment.items():
        pod_running = verify_pod_by_deployment(
            openshift_dyn_client=openshift_dyn_client,
            project=project_name,
            deployment=deploment_name,
        )
        assert pod_running
