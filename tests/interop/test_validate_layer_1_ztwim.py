import logging
import os

import pytest
import requests

from . import __loggername__, pattern_crd
from .utils import (
    get_route_by_app_label,
    send_get_request,
    verify_pod_by_deployment,
    verify_project,
)

logger = logging.getLogger(__loggername__)


app_project_name = "zero-trust-workload-identity-manager"
app_label = "argocd.argoproj.io/instance=zero-trust-workload-identity-manager"

cluster_name = os.getenv(
    "CLUSTER_NAME",
    f'{os.getenv("HUB_CLUSTER_PREFIX")}-{os.getenv("INFRA_PROVIDER")}-{os.getenv("MPTS_TEST_RUN_ID")}',
)
cluster_apps_fqdn = f'apps.{cluster_name}.{os.getenv("AWS_DOMAIN")}'


@pytest.mark.test_ztwim_project
def test_ztwim_project(openshift_dyn_client):
    project_exists = verify_project(
        openshift_dyn_client=openshift_dyn_client, project_name=app_project_name
    )
    err_msg = f'OpenShift Project "{app_project_name} not found!'
    assert project_exists, err_msg


@pytest.mark.test_ztwim_pod_status
def test_ztwim_pod_status(openshift_dyn_client):
    desired_deployment = {
        "spire-spiffe-oidc-discovery-provider": "zero-trust-workload-identity-manager-controller-manager"
    }
    for deploment_name, project_name in desired_deployment.items():
        pod_running = verify_pod_by_deployment(
            openshift_dyn_client=openshift_dyn_client,
            project=app_project_name,
            deployment=deploment_name,
        )
        assert pod_running


@pytest.mark.test_ztwim_custom_resources
def test_ztwim_custom_resources(openshift_dyn_client):
    custom_resources = [
        "SpireAgent",
        "SpireServer",
        "SpiffeCSIDriver",
        "SpireOIDCDiscoveryProvider",
    ]
    try:
        for crd_name in custom_resources:
            crd = getattr(pattern_crd, crd_name)
            instances = crd.get(dyn_client=openshift_dyn_client)
            for instance in instances:
                logger.info(
                    f'Found instance name: "{instance.name}", kind: "{crd_name}'
                )
    except StopIteration:
        assert False


@pytest.mark.test_ztwim_custom_resources_trustdomain
def test_ztwim_custom_resources_trustdomain(openshift_dyn_client):
    custom_resources = ["SpireAgent", "SpireServer", "SpireOIDCDiscoveryProvider"]
    try:
        for crd_name in custom_resources:
            crd = getattr(pattern_crd, crd_name)
            instances = crd.get(dyn_client=openshift_dyn_client)
            for instance in instances:
                assert instance.instance.spec.trustDomain == cluster_apps_fqdn
    except Exception:
        assert False


@pytest.mark.test_ztwim_spire_oidc_discovery_provider
def test_ztwim_spire_oidc_discovery_provider(openshift_dyn_client):
    desired_jwt_issuer = (
        f"https://spire-spiffe-oidc-discovery-provider.{cluster_apps_fqdn}"
    )
    try:
        crd_name = "SpireOIDCDiscoveryProvider"
        crd = getattr(pattern_crd, crd_name)
        instances = crd.get(dyn_client=openshift_dyn_client)
        for instance in instances:
            assert instance.instance.spec.managedRoute == "false"
            assert instance.instance.spec.jwtIssuer == desired_jwt_issuer
    except Exception:
        assert False


@pytest.mark.test_ztwim_routes
def test_ztwim_routes(openshift_dyn_client):
    desired_routes = {
        "spire-spiffe-oidc-discovery-provider": False,
        "spire-server": False,
    }
    app_routes = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_routes:
        logger.info("Verify routes are created")
        for desired_route in desired_routes.keys():
            for app_route in app_routes:
                app_route_name = app_route.name
                if app_route_name.startswith(desired_route):
                    desired_routes[desired_route] = True
        for desired_route_name, desired_route_existence in desired_routes.items():
            err_msg = f'Route "{desired_route_name}" does not exist'
            assert desired_route_existence, err_msg
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg


@pytest.mark.test_ztwim_routes_reachability
def test_ztwim_routes_reachability(openshift_dyn_client):
    app_routes = get_route_by_app_label(
        openshift_dyn_client=openshift_dyn_client,
        project=app_project_name,
        label=app_label,
    )
    if app_routes:
        logger.info("Verify OIDC Discovery Provider route reachability")
        for app_route in app_routes:
            app_route_name = app_route.name
            if app_route_name.startswith("spire-spiffe-oidc-discovery-provider"):
                app_hostname = app_route.host
                app_url = (
                    "https://" + app_hostname + "/.well-known/openid-configuration"
                )
                logger.info("Application URL is: " + app_url)
                rsp = send_get_request(site_url=app_url)
                assert requests.codes.ok == rsp.status_code
    else:
        err_msg = f'No route found in "{app_project_name}" with label "{app_label}"'
        assert False, err_msg
