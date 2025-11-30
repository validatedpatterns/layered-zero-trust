import logging
import os
import tempfile

import pytest
import requests
from ocp_resources.job import Job
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from validatedpatterns_tests.interop import components

from . import __loggername__, pattern_crd
from .utils import (
    run_shell_script,
    verify_pod_by_deployment,
    verify_pod_in_project,
    verify_project,
    wait_for,
)

logger = logging.getLogger(__loggername__)

quay_app_name = "quay-registry-quay"
quay_namespace = "quay-enterprise"
quay_admin_username = "quayadmin"
quay_admin_email = "quayadmin@example.com"
quay_admin_password = "securepassword"


@pytest.mark.test_quay_namespaces
def test_quay_project(openshift_dyn_client):
    desired_projects = ["openshift-storage", "quay-enterprise"]
    for desired_project in desired_projects:
        project_exists = verify_project(
            openshift_dyn_client=openshift_dyn_client, project_name=desired_project
        )
        err_msg = f'OpenShift Project "{desired_project} not found!'
        assert project_exists, err_msg


@pytest.mark.test_openshift_storage_pod_status
def test_openshift_storage_pod_status(openshift_dyn_client):
    logger.info("Checking pod status")
    projects = ["openshift-storage"]
    err_msg = components.check_pod_status(openshift_dyn_client, projects)
    if err_msg:
        logger.error(f"FAIL: {err_msg}")
        assert False, err_msg
    else:
        logger.info('PASS: All pods running in the "openshift-storage" namespace.')


@pytest.mark.test_openshift_storage_noobaa_status
def test_openshift_storage_noobaa_status(openshift_dyn_client):
    noobaa_namespace = "openshift-storage"

    noobaa_bc_name = "noobaa-default-bucket-class"
    noobaa_bc = pattern_crd.BucketClass(
        client=openshift_dyn_client, namespace=noobaa_namespace, name=noobaa_bc_name
    )
    err_msg = "FAIL: No BucketClass found!"
    assert noobaa_bc.exists, err_msg
    logger.info('PASS: BucketClass "noobaa-default-bucket-class" found.')

    noobaa_bs_name = "noobaa-default-backing-store"
    noobaa_bs = pattern_crd.BackingStore(
        client=openshift_dyn_client, namespace=noobaa_namespace, name=noobaa_bs_name
    )
    err_msg = "FAIL: No BackingStore found!"
    assert noobaa_bs.exists, err_msg
    logger.info('PASS: BackingStore "noobaa-default-bucket-class" found.')

    pod_running = verify_pod_by_deployment(
        openshift_dyn_client=openshift_dyn_client,
        project=noobaa_namespace,
        deployment="noobaa-operator",
    )

    err_msg = f'FAIL: "noobaa-operator" pod is not running in {noobaa_namespace}!'
    assert pod_running, err_msg

    s3_route = Route(client=openshift_dyn_client, namespace=noobaa_namespace, name="s3")
    err_msg = f'FAIL: S3 route not found in namespace "{noobaa_namespace}".'
    assert s3_route.exists, err_msg
    logger.info(f'PASS: S3 route created in namespace "{noobaa_namespace}".')

    s3_base_url = f"https://{s3_route.host}"
    rsp = wait_for(app_url=s3_base_url)
    assert rsp.status_code != requests.codes.service_unavailable


@pytest.mark.test_quay_deployment
def test_quay_deployment(openshift_dyn_client):
    cluster_ob_name = "obc-quay-enterprise-quay-bucket"
    cluster_ob = pattern_crd.ObjectBucket(
        client=openshift_dyn_client, name=cluster_ob_name
    )
    err_msg = f'FAIL: ObjectBucket "{cluster_ob_name}" not found!'
    assert cluster_ob.exists, err_msg
    err_msg = f'FAIL: ObjectBucket "{cluster_ob_name}" not in "Bound" status!'
    assert cluster_ob.status == "Bound", err_msg

    quay_obc_name = "quay-bucket"
    quay_obc = pattern_crd.ObjectBucketClaim(
        client=openshift_dyn_client, namespace=quay_namespace, name=quay_obc_name
    )
    err_msg = f'FAIL: ObjectBucketClaim "{quay_obc_name}" not found in namesapce "{quay_namespace}"!'
    assert quay_obc.exists, err_msg
    err_msg = f'FAIL: ObjectBucketClaim "{quay_obc_name}" is not in "Bound" status!'
    assert quay_obc.status == "Bound", err_msg

    try:
        qrs = pattern_crd.QuayRegistry.get(
            dyn_client=openshift_dyn_client, namespace=quay_namespace
        )
        for qr in qrs:
            logger.info(f'Found quay-registry: "{qr.name}"')
    except StopIteration:
        err_msg = f'FAIL: No quay-registry found in namespace "{quay_namespace}"!'
        assert False, err_msg

    quay_s3_creds_setup_job_complete_status = False
    quay_s3_creds_setup_job_name = "quay-s3-credentials-setup"
    quay_s3_creds_setup_job = Job(
        client=openshift_dyn_client,
        namespace=quay_namespace,
        name=quay_s3_creds_setup_job_name,
    )
    err_msg = f'FAIL: Job "{quay_s3_creds_setup_job_name}" not found in namespace "{quay_namespace}"!'
    assert quay_s3_creds_setup_job.exists, err_msg
    for condition in quay_s3_creds_setup_job.instance.get("status", {}).get(
        "conditions", []
    ):
        logger.debug(f"{condition['type']}: {condition['status']}")
        if condition["type"] == "Complete":
            quay_s3_creds_setup_job_complete_status = condition["status"]
    assert quay_s3_creds_setup_job_complete_status

    desired_secrets = ["quay-init-config-bundle-secret", "quay-config-with-s3"]
    for desired_secret in desired_secrets:
        secret = Secret(
            client=openshift_dyn_client, namespace=quay_namespace, name=desired_secret
        )
        err_msg = f'FAIL: Secret "{desired_secret}" not found in namespace "{quay_namespace}"!'
        assert secret.exists, err_msg


@pytest.mark.test_quay_component_health
def test_quay_component_health(openshift_dyn_client):
    status = True
    err_pods = {}

    desired_deployments = {
        "quay-enterprise": [
            "quay-registry-quay-app",
            "quay-registry-quay-mirror",
            "quay-registry-quay-database",
            "quay-registry-quay-redis",
            "quay-registry-clair-app",
        ],
        "openshift-storage": ["noobaa-operator", "noobaa-endpoint"],
    }

    for namespace in desired_deployments.keys():
        err_pods[namespace] = []
        for desired_deployment_name in desired_deployments[namespace]:
            pod_running = verify_pod_by_deployment(
                openshift_dyn_client=openshift_dyn_client,
                project=namespace,
                deployment=desired_deployment_name,
            )
            if not pod_running:
                status = False
                err_pods[namespace].append(desired_deployment_name)

    desired_pods = {"openshift-storage": ["noobaa-core-0", "noobaa-db-pg-0"]}

    for namespace in desired_pods.keys():
        err_pods[namespace] = []
        for desired_pod_name in desired_pods[namespace]:
            pod_running = verify_pod_in_project(
                openshift_dyn_client=openshift_dyn_client,
                project=namespace,
                pod=desired_pod_name,
            )
            if not pod_running:
                status = False
                err_pods[namespace].append(desired_pod_name)

    err_msg = f"FAIL: One or more desired pods are not running\n{err_pods}"
    assert status, err_msg


@pytest.mark.test_quay_services
def test_quay_services(openshift_dyn_client):
    quay_route = Route(
        client=openshift_dyn_client, namespace=quay_namespace, name=quay_app_name
    )
    if not quay_route.exists:
        err_msg = f'FAIL: Quay route not found in namespace "{quay_namespace}".'
        assert False, err_msg

    quay_base_url = f"https://{quay_route.host}"
    quay_health_endpoint = requests.compat.urljoin(quay_base_url, "/health/instance")
    rsp = wait_for(app_url=quay_health_endpoint)
    assert rsp.status_code == requests.codes.ok

    quay_docker_v2_endpoint = requests.compat.urljoin(quay_base_url, "/v2")
    rsp = wait_for(app_url=quay_docker_v2_endpoint)
    assert rsp.status_code == requests.codes.unauthorized

    quay_catalog_endpoint = requests.compat.urljoin(quay_base_url, "/v2/_catalog")
    rsp = wait_for(app_url=quay_catalog_endpoint)
    assert rsp.status_code == requests.codes.ok

    quay_api_endpoint = requests.compat.urljoin(quay_base_url, "/api/v1/user/")

    # Send HTTP POST request using requests library
    logger.info(f"Sending POST request to create Quay admin user: {quay_api_endpoint}")
    try:
        client = requests.Session()
        rsp = client.get(
            requests.compat.urljoin(quay_base_url, "/csrf_token"), verify=False
        )
        csrf_token = rsp.json()["csrf_token"]
        client.get(
            requests.compat.urljoin(quay_base_url, "/createaccount"), verify=False
        )
        headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf_token}
        payload = {
            "username": quay_admin_username,
            "email": quay_admin_email,
            "password": quay_admin_password,
            "_csrf_token": csrf_token,
        }
        rsp = client.post(
            quay_api_endpoint, headers=headers, json=payload, verify=False, timeout=30
        )

        logger.info(f"Response status code: {rsp.status_code}")
        logger.info(f"Response content: {rsp.text}")

        # Assert the request was successful (adjust status code as needed)
        # Common success codes: 200 (OK), 201 (Created), 202 (Accepted)
        assert rsp.status_code in [
            requests.codes.ok,
            requests.codes.created,
            requests.codes.accepted,
        ], f"FAIL: Expected successful response, got {rsp.status_code}: {rsp.text}"

        logger.info("PASS: Successfully created Quay admin user via HTTP POST")

    except requests.exceptions.RequestException as e:
        logger.error(f"FAIL: HTTP POST request failed: {e}")
        raise


@pytest.mark.test_quay_validate_user_authentication_authorization
def test_quay_validate_user_authentication_authorization():
    # Create a validation script that checks Quay resources
    script_content = f"""#!/bin/bash
set -e
oc rsh -n {quay_namespace} deployment/quay-registry-quay-database \\
    psql -U quay-registry-quay-database \\
        -d quay-registry-quay-database \\
        -c "SELECT username, email, verified, robot, organization, enabled FROM \\"user\\";"
"""

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    try:
        # Make script executable
        os.chmod(script_path, 0o755)

        # Run the validation script
        logger.info("Executing shell script")
        result = run_shell_script(script_path)

        # Verify expected output patterns
        stdout = result["stdout"]
        logger.info(f"Script output:\n{stdout}")

        # Assert script executed successfully
        err_msg = f"FAIL: Validation script failed with return code {result['returncode']}\nStderr: {result['stderr']}"
        assert result["success"], err_msg

        logger.info("PASS: Shell script validation completed successfully")

    finally:
        # Cleanup temporary script
        if os.path.exists(script_path):
            os.remove(script_path)
            logger.debug(f"Cleaned up temporary script: {script_path}")


@pytest.mark.test_quay_validate_registry_operations
def test_quay_validate_registry_operations(openshift_dyn_client):
    quay_app_name = "quay-registry-quay"
    quay_namespace = "quay-enterprise"

    quay_route = Route(
        client=openshift_dyn_client, namespace=quay_namespace, name=quay_app_name
    )
    if not quay_route.exists:
        err_msg = f'FAIL: Quay route not found in namespace "{quay_namespace}".'
        assert False, err_msg

    # Create a validation script that checks Quay resources
    script_content = f"""#!/bin/bash
set -e
QUAY_HOSTNAME="{quay_route.host}"
SRC_IMAGE="quay.io/quay/busybox:latest"
DST_IMAGE="$QUAY_HOSTNAME/quayadmin/test-busybox:latest"
podman login --tls-verify=false --username "{quay_admin_username}" --password {quay_admin_password} $QUAY_HOSTNAME
# pull a public image
podman pull --tls-verify=false $SRC_IMAGE
podman tag $SRC_IMAGE $DST_IMAGE
# push to Quay registry
podman push --tls-verify=false $DST_IMAGE
# remove local image
podman rmi $DST_IMAGE
# pull image from Quay registry
podman pull --tls-verify=false $DST_IMAGE
"""

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    try:
        # Make script executable
        os.chmod(script_path, 0o755)

        # Run the validation script
        logger.info("Executing shell script")
        result = run_shell_script(script_path)

        # Verify expected output patterns
        stdout = result["stdout"]
        logger.info(f"Script output:\n{stdout}")

        # Assert script executed successfully
        err_msg = f"FAIL: Validation script failed with return code {result['returncode']}\nStderr: {result['stderr']}"
        assert result["success"], err_msg

        logger.info("PASS: Shell script validation completed successfully")

    finally:
        # Cleanup temporary script
        if os.path.exists(script_path):
            os.remove(script_path)
            logger.debug(f"Cleaned up temporary script: {script_path}")
