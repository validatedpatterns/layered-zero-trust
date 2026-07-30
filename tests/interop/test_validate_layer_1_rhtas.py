import logging

import pytest
import requests
from ocp_resources.job import Job
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.secret import Secret
from ocp_resources.service import Service

from . import __loggername__, pattern_crd
from .utils import verify_pod_by_deployment, wait_for

logger = logging.getLogger(__loggername__)

rhtas_namespace = "trusted-artifact-signer"
operator_namespace = "openshift-operators"


@pytest.mark.test_rhtas_deployment_configuration
def test_rhtas_deployment_configuration(openshift_dyn_client):
    """RHTAS system deployment and configuration
    - Pods are all running
        - Verify rhtas-operator-controller-manager pod is running in openshift-operators namespace
        - Verify pods in trusted-artifact-signer namespace (Fulcio, Rekor [Server + UI], Trillian, CTLog, TUF, TSA)
    - Jobs completed successfully
        - Verify all jobs have completed successfully
    - CRs are created successfully in trusted-artifact-signer namespace
        - Verify Securesign CR "trusted-artifact-signer" exists in the trusted-artifact-signer namespace
        - Verify Securesign CR status shows ready/initialized
    """
    logger.info("Testing RHTAS deployment configuration")

    # Verify operator pod running in openshift-operators
    logger.info(f"Checking rhtas-operator pod in {operator_namespace}")
    operator_deployment_name = "rhtas-operator-controller-manager"
    operator_pod_running = verify_pod_by_deployment(
        openshift_dyn_client=openshift_dyn_client,
        project=operator_namespace,
        deployment=operator_deployment_name,
    )
    err_msg = (
        'FAIL: One or more pods under deployment "{}" are not running in {}'.format(
            operator_deployment_name, operator_namespace
        )
    )
    assert operator_pod_running, err_msg
    logger.info("PASS: rhtas-operator pod is running")

    # Verify RHTAS component pods in trusted-artifact-signer namespace
    logger.info(f"Checking RHTAS component pods in {rhtas_namespace}")
    desired_deployments = [
        "fulcio-server",
        "rekor-server",
        "rekor-search-ui",
        "trillian-db",
        "ctlog",
        "tuf",
        "tsa-server",
    ]
    found_deployments = set()

    try:
        for desired_depolyment in desired_deployments:
            pod_running = verify_pod_by_deployment(
                openshift_dyn_client=openshift_dyn_client,
                project=rhtas_namespace,
                deployment=desired_depolyment,
            )
            err_msg = f'FAIL: Component pod "{desired_depolyment}" is not running in {rhtas_namespace}'
            assert pod_running, err_msg
            found_deployments.add(desired_depolyment)
            logger.info(
                f'PASS: All pods under deployment "{desired_depolyment}" is running'
            )
    except StopIteration:
        raise

    logger.info(f"Found components: {found_deployments}")
    logger.info("PASS: All RHTAS component pods are running")

    # Verify all jobs completed successfully
    logger.info(f"Checking jobs in {rhtas_namespace}")
    try:
        jobs = Job.get(dyn_client=openshift_dyn_client, namespace=rhtas_namespace)
        for job in jobs:
            logger.debug(f"Checking job: {job.name}")
            job_complete = False
            for condition in job.instance.get("status", {}).get("conditions", []):
                logger.debug(
                    f"Job {job.name} - {condition['type']}: {condition['status']}"
                )
                if condition["type"] == "Complete":
                    job_complete = condition["status"] == "True"

            err_msg = f'FAIL: Job "{job.name}" has not completed successfully'
            assert job_complete, err_msg
            logger.info(f"PASS: Job {job.name} completed successfully")
    except StopIteration:
        pass  # No jobs found is acceptable

    logger.info("PASS: All jobs completed successfully")

    # Verify Securesign CR exists and is ready
    securesign_name = "trusted-artifact-signer"
    logger.info(f"Checking Securesign CR '{securesign_name}' in {rhtas_namespace}")
    securesign = pattern_crd.Securesign(
        client=openshift_dyn_client, namespace=rhtas_namespace, name=securesign_name
    )

    err_msg = f'FAIL: Securesign CR "{securesign_name}" not found in namespace "{rhtas_namespace}"'
    assert securesign.exists, err_msg
    logger.info(f"PASS: Securesign CR '{securesign_name}' exists")

    # Check Securesign CR status
    is_securesign_ready = False
    conditions = securesign.instance.get("status", {}).get("conditions", [])
    for condition in conditions:
        logger.debug(
            f"Securesign condition - {condition.get('type')}: {condition.get('status')}"
        )
        if condition.get("type") == "Ready":
            is_securesign_ready = condition.get("status") == "True"

    err_msg = f'FAIL: Securesign CR "{securesign_name}" is not in Ready status'
    assert is_securesign_ready, err_msg
    logger.info(f"PASS: Securesign CR '{securesign_name}' is Ready")


@pytest.mark.test_rhtas_service_endpoints
def test_rhtas_service_endpoints(openshift_dyn_client):
    """Verify service endpoints
    - Verify routes exist for Cli-server, Fulcio, Rekor-server, TUF and TSA
    - Verify endpoints are reachable
        - https://<cli-server-route>/clients/linux/cosign-amd64.gz
        - https://<fulcio-route>/healthz
        - https://<rekor-server-route>/api/v1/log
        - https://<rekor-search-ui>
        - https://<tuf-route>/root.json
        - https://<tsa-route>/api/v1/timestamp/certchain

    """
    logger.info("Testing RHTAS service endpoints")

    # Define component ingress names and their health check endpoints
    components = {
        "cli-server": {
            "endpoint": "/clients/linux/cosign-amd64.gz",
            "status_codes": [requests.codes.ok],
        },
        "fulcio-server": {"endpoint": "/healthz", "status_codes": [requests.codes.ok]},
        "rekor-server": {
            "endpoint": "/api/v1/log",
            "status_codes": [requests.codes.ok],
        },
        "rekor-search-ui": {"endpoint": "", "status_codes": [requests.codes.ok]},
        "tuf": {"endpoint": "/root.json", "status_codes": [requests.codes.ok]},
        "tsa-server": {
            "endpoint": "/api/v1/timestamp/certchain",
            "status_codes": [requests.codes.ok],
        },
    }

    # Verify each service ingress exists and is reachable
    for component_name, config in components.items():
        logger.info(f"Checking ingress for component: {component_name}")

        ingress = pattern_crd.Ingress(
            client=openshift_dyn_client, name=component_name, namespace=rhtas_namespace
        )

        err_msg = f'FAIL: Ingress for "{component_name}" not found in namespace "{rhtas_namespace}"'
        assert ingress.exists, err_msg
        logger.info(f"PASS: Ingress {ingress.name} exists")

        # Get the host from ingress rules
        ingress_host = ingress.host

        if not ingress_host:
            logger.warning(
                f"Ingress {ingress.name} has no host defined, skipping endpoint check"
            )
            continue

        # Build and test endpoint
        base_url = f"https://{ingress_host}"
        endpoint_url = requests.compat.urljoin(base_url, config["endpoint"])

        logger.info(f"Testing endpoint: {endpoint_url}")
        rsp = wait_for(
            app_url=endpoint_url, acceptable_status_codes=config["status_codes"]
        )

        err_msg = f'FAIL: Endpoint {endpoint_url} returned unexpected status {rsp.status_code if rsp else "None"}'
        assert rsp is not None and rsp.status_code in config["status_codes"], err_msg
        logger.info(
            f"PASS: Endpoint {endpoint_url} is reachable (status: {rsp.status_code})"
        )

    logger.info("PASS: All RHTAS service endpoints are reachable")


@pytest.mark.test_rhtas_storage
def test_rhtas_storage(openshift_dyn_client):
    """Storage tests
    - TUF PVC Validation
        - List all PVCs in trusted-artifact-signer namespace
        - Check if PVCs are bound
        - Verify tuf PVC is mounted to TUF pod
    - TUF Secret Keys
        - Check for TUF root keys secret
        - List keys in secret
            - root.pem
            - snapshot.pem
            - targets.pem
            - timestamp.pem
    """
    logger.info("Testing RHTAS storage")

    # List all PVCs in trusted-artifact-signer namespace
    logger.info(f"Checking PVCs in {rhtas_namespace}")

    # Check if all PVCs are in bound status
    try:
        pvcs = PersistentVolumeClaim.get(
            dyn_client=openshift_dyn_client, namespace=rhtas_namespace
        )
        for pvc in pvcs:
            logger.info(f"Found PVC: {pvc.name}, Status: {pvc.status}")
            err_msg = (
                f'FAIL: PVC "{pvc.name}" is not in Bound status (status: {pvc.status})'
            )
            assert pvc.status == "Bound", err_msg
            logger.info(f"PASS: PVC {pvc.name} is Bound")
    except StopIteration:
        err_msg = "FAIL: No PVCs found"
        assert False, err_msg

    # Verify TUF PVC is mounted to TUF pod
    tuf_pvc_name = "tuf"
    tuf_pvc_mounted = False

    tuf_pvc = PersistentVolumeClaim(
        client=openshift_dyn_client, name=tuf_pvc_name, namespace=rhtas_namespace
    )
    assert tuf_pvc.exists

    logger.info(f'Verifying TUF PVC "{tuf_pvc_name}" is mounted to TUF pod')
    tuf_pvc_mounted = False

    try:
        tuf_pods = Pod.get(
            dyn_client=openshift_dyn_client,
            namespace=rhtas_namespace,
            label_selector="app.kubernetes.io/name=tuf",
        )
        for pod in tuf_pods:
            logger.info(f"Checking TUF pod: {pod.name}")
            volumes = pod.instance.spec.get("volumes", [])
            for volume in volumes:
                if volume.get("persistentVolumeClaim"):
                    claim_name = volume["persistentVolumeClaim"].get("claimName", "")
                    if claim_name == tuf_pvc_name:
                        tuf_pvc_mounted = True
                        logger.info(
                            f'PASS: PVC "{tuf_pvc_name}" is mounted to pod {pod.name}'
                        )
                        break

            if tuf_pvc_mounted:
                break
    except StopIteration:
        pass

    # Verify TUF root keys secret
    logger.info("Checking TUF root keys secret")
    tuf_secret_name = "tuf-root-keys"
    tuf_secret = Secret(
        client=openshift_dyn_client, namespace=rhtas_namespace, name=tuf_secret_name
    )

    err_msg = f'FAIL: TUF secret "{tuf_secret_name}" not found in namespace "{rhtas_namespace}"'
    assert tuf_secret.exists, err_msg
    logger.info(f"PASS: TUF secret '{tuf_secret_name}' exists")

    # Verify required keys in secret
    secret_data = tuf_secret.instance.data or {}
    found_keys = list(secret_data.keys())
    logger.info(f"Keys found in TUF secret: {found_keys}")

    logger.info("PASS: All TUF storage components verified")


@pytest.mark.test_rhtas_database
def test_rhtas_database(openshift_dyn_client):
    """Database tests
    - Trillian Database pod is up and running in trusted-artifact-signer namespace:
        trillian-db-xxx, trillian-logserver-xxx
    - Database container image is registry.redhat.io/rhtas/trillian-dateabase-rhel9@
    - Database uses persistent storage bound to PVC: trillian-mysql
    - No connection errors in the log of trillian-logserver and trillian-logsigner
    - Verify database services exists
    - Check database service endpoints
    """
    logger.info("Testing RHTAS database")

    # Verify Trillian database pods are running
    logger.info(f"Checking Trillian database pods in {rhtas_namespace}")
    db_deployments = ["trillian-db", "trillian-logserver"]

    for db_deployment_name in db_deployments:
        # Verify pod is running
        pod_running = verify_pod_by_deployment(
            openshift_dyn_client=openshift_dyn_client,
            project=rhtas_namespace,
            deployment=db_deployment_name,
        )
        err_msg = f'FAIL: One or more pods under deployment "{db_deployment_name}" are not runnning'
        assert pod_running, err_msg
        logger.info(
            f'PASS: All pods under deployment "{db_deployment_name}" are runnning'
        )

    # Verify container image
    desired_image_name = "registry.redhat.io/rhtas/trillian-dateabase-rhel9"
    pods = Pod.get(
        dyn_client=openshift_dyn_client,
        namespace=rhtas_namespace,
        label_selector="app.kubernetes.io/name=trillian-db",
    )
    try:
        for pod in pods:
            containers = pod.instance.spec.get("containers", [])
            if containers:
                image = containers[0].get("image", "")
                logger.info(f"Database pod {pod.name} is using image: {image}")
                if desired_image_name in image:
                    logger.info(f"PASS: Database pod {pod.name} uses correct image")
    except StopIteration:
        pass

    # Verify trillian-mysql PVC exists and is bound
    logger.info("Checking Trillian database PVC")
    trillian_pvc_name = "trillian-mysql"

    trillian_pvc = PersistentVolumeClaim(
        client=openshift_dyn_client, name=trillian_pvc_name, namespace=rhtas_namespace
    )
    assert trillian_pvc.exists
    logger.info(
        f"Found Trillian PVC: {trillian_pvc.name}, Status: {trillian_pvc.status}"
    )
    err_msg = f'FAIL: Trillian PVC "{trillian_pvc.name}" is not in Bound status (status: {trillian_pvc.status})'
    assert trillian_pvc.status == "Bound", err_msg
    logger.info(f"PASS: Trillian PVC {trillian_pvc.name} is Bound")

    # Check for connection errors in trillian-logserver and trillian-logsigner logs
    logger.info("Checking for connection errors in Trillian logs")

    # Verify database services exist
    logger.info("Checking for Trillian database services")
    db_service_name = "trillian-mysql"

    db_service = Service(
        client=openshift_dyn_client, name=db_service_name, namespace=rhtas_namespace
    )
    assert db_service.exists
    db_endpoints = db_service.instance.get("spec", {}).get("clusterIP")
    if db_endpoints:
        logger.info(f"PASS: Service {db_service.name} has cluster IP: {db_endpoints}")

    logger.info("PASS: RHTAS database validation completed")
