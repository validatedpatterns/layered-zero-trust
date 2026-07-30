import json
import logging
import os
import shlex

import pytest
import requests
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.pod import Pod
from ocp_resources.project_project_openshift_io import Project
from ocp_resources.route import Route
from ocp_resources.secret import Secret

from . import __loggername__, pattern_crd
from .utils import render_yaml_template, run_cmds, wait_for

logger = logging.getLogger(__loggername__)

rhtas_namespace = "trusted-artifact-signer"
operator_namespace = "openshift-operators"


@pytest.mark.test_rhtas_integration_verify_securesign_configuration
def test_rhtas_integration_verify_securesign_configuration(
    openshift_dyn_client, cluster_apps_fqdn
):
    securesign_name = "trusted-artifact-signer"
    securesign = pattern_crd.Securesign(
        client=openshift_dyn_client, name=securesign_name, namespace=rhtas_namespace
    )

    assert securesign.exists

    for oidc_issuer in securesign.instance.spec.fulcio.config.OIDCIssuers:
        if oidc_issuer["ClientID"] == "sigstore":
            assert (
                oidc_issuer["IssuerURL"]
                == f"https://spire-spiffe-oidc-discovery-provider.{cluster_apps_fqdn}"
            )
            assert oidc_issuer["SPIFFETrustDomain"] == cluster_apps_fqdn
            assert oidc_issuer["Type"] == "spiffe"
            logger.info("PASS: Fulcio correctly configured with SPIFFE")
        if oidc_issuer["ClientID"] == "trusted-artifact-signer":
            assert oidc_issuer["Type"] == "email"
            logger.info("PASS: Fulcio correctly configured with keycloak issuer")


def extract_url_by_label(
    openshift_dyn_client, label_selector, namespace=rhtas_namespace
):
    try:
        routes = Route.get(
            dyn_client=openshift_dyn_client,
            namespace=namespace,
            label_selector=label_selector,
        )
        route = next(routes)
        return route.instance.spec.host
    except StopIteration:
        logger.error(f'No route labeled "{label_selector}" found!')
        raise


@pytest.fixture(scope="package")
def fulcio_host(openshift_dyn_client):
    return extract_url_by_label(
        openshift_dyn_client, "app.kubernetes.io/component=fulcio"
    )


@pytest.fixture(scope="package")
def rekor_host(openshift_dyn_client):
    return extract_url_by_label(
        openshift_dyn_client, "app.kubernetes.io/component=rekor-server"
    )


@pytest.fixture(scope="package")
def tuf_host(openshift_dyn_client):
    return extract_url_by_label(openshift_dyn_client, "app.kubernetes.io/component=tuf")


@pytest.fixture(scope="package")
def cli_server_host(openshift_dyn_client):
    return extract_url_by_label(
        openshift_dyn_client, "app.kubernetes.io/component=client-server"
    )


@pytest.fixture(scope="package")
def keycloak_host(openshift_dyn_client):
    return extract_url_by_label(
        openshift_dyn_client, namespace="keycloak-system", label_selector="app=keycloak"
    )


@pytest.fixture(scope="package")
def rhtas_user_pass(openshift_dyn_client):
    import base64

    secret = Secret(
        client=openshift_dyn_client, name="keycloak-users", namespace="keycloak-system"
    )
    assert secret.exists
    secrets_dict = secret.instance.to_dict()
    rhtas_user_password = base64.b64decode(secrets_dict["data"]["rhtas-user-password"])
    return rhtas_user_password.decode()


@pytest.fixture(scope="package")
def quay_url(openshift_dyn_client):
    return extract_url_by_label(
        openshift_dyn_client,
        namespace="quay-enterprise",
        label_selector="quay-component=quay-app-route",
    )


@pytest.mark.test_rhtas_integration_tests
def test_rhtas_integration_tests(
    openshift_dyn_client, fulcio_host, rekor_host, tuf_host, cli_server_host
):
    # Check cosign binaries exist inside the cli-server pod of namespace trusted-artifact-signer
    cosign_binaries_url = requests.compat.urljoin(
        f"https://{cli_server_host}", "/clients/linux/cosign-amd64.gz"
    )
    rsp = wait_for(
        app_url=cosign_binaries_url, acceptable_status_codes=[requests.codes.ok]
    )
    assert rsp.status_code == requests.codes.ok
    logger.info(
        "PASS: cosign binaries exist inside the cli-server pod of namespace trusted-artifact-signer"
    )

    # OIDC discovery endpoint
    fulcio_pods = Pod.get(
        client=openshift_dyn_client,
        namespace=rhtas_namespace,
        label_selector="app.kubernetes.io/name=fulcio-server",
    )
    fulcio_pod = next(fulcio_pods)
    oidc_route_name = "spire-spiffe-oidc-discovery-provider"
    oidc_namespace = "zero-trust-workload-identity-manager"
    oidc_internal_route_url = (
        f"https://{oidc_route_name}.{oidc_namespace}.svc.cluster.local"
    )
    oidc_discovery_internal_endpoint_url = requests.compat.urljoin(
        oidc_internal_route_url, "/.well-known/openid-configuration"
    )
    oidc_internal_route_test_cmd = [
        "curl",
        "-sk",
        oidc_discovery_internal_endpoint_url,
    ]
    oidc_internal_route_test_exec_output = fulcio_pod.execute(
        oidc_internal_route_test_cmd
    )
    oidc_internal_route_test_result = json.loads(oidc_internal_route_test_exec_output)
    logger.info(json.dumps(oidc_internal_route_test_result, indent=2))
    logger.info("PASS: OIDC discovery endpoint succeeded")

    # Test external route
    securesign_name = "trusted-artifact-signer"
    securesign = pattern_crd.Securesign(
        client=openshift_dyn_client, name=securesign_name, namespace=rhtas_namespace
    )

    assert securesign.exists
    spire_oidc_url = None
    for oidc_issuer in securesign.instance.spec.fulcio.config.OIDCIssuers:
        if oidc_issuer["Type"] == "spiffe":
            spire_oidc_url = oidc_issuer["IssuerURL"]
            break

    assert spire_oidc_url is not None

    oidc_discovery_endpoint_url = requests.compat.urljoin(
        spire_oidc_url, "/.well-known/openid-configuration"
    )
    rsp = wait_for(oidc_discovery_endpoint_url)
    assert rsp.status_code == requests.codes.ok
    logger.info("PASS: OIDC discovery endpoint is reachable via external route")
    logger.info(json.dumps(rsp.json(), indent=2))


@pytest.fixture(scope="session")
def rhtas_signing_test_project(openshift_dyn_client):
    rhtas_signing_test_namespace = "rhtas-signing-test"

    project = Project(client=openshift_dyn_client, name=rhtas_signing_test_namespace)
    if not project.exists:
        logger.info(
            f'Project "{rhtas_signing_test_namespace}" does not exist and needs to be created'
        )
        project.deploy()
        project.wait_for_status(status=Project.Status.ACTIVE, timeout=120)
    assert project.exists

    yield project

    logger.info(f'Cleaning up project "{rhtas_signing_test_namespace}"...')
    project.clean_up()


@pytest.fixture(scope="package")
def data_path(request):
    test_dir_path = os.path.dirname(request.path)
    data_dir_path = os.path.join(test_dir_path, "data/")
    logger.debug(f'Using payload data from path "{data_dir_path}')
    yield data_dir_path


@pytest.fixture(scope="package")
def rhtas_signer_pod(
    openshift_dyn_client,
    data_path,
    rhtas_signing_test_project,
    fulcio_host,
    rekor_host,
    tuf_host,
    cli_server_host,
    keycloak_host,
    rhtas_user_pass,
):
    rhtas_signer_pod_name = "rhtas-signer"
    rhtas_signer_pod = Pod(
        client=openshift_dyn_client,
        name=rhtas_signer_pod_name,
        namespace=rhtas_signing_test_project.name,
    )

    if not rhtas_signer_pod.exists:
        logger.info(f'RHTAS signing test pod "{rhtas_signer_pod_name}" is created')
        template_path = os.path.join(data_path, "rhtas-signer-pod.yaml")

        # Define your template variables
        template_vars = {
            "FULCIO_URL": fulcio_host,
            "REKOR_URL": rekor_host,
            "TUF_URL": tuf_host,
            "CLI_SERVER_URL": cli_server_host,
            "KEYCLOAK_URL": keycloak_host,
            "RHTAS_USER_PASS": rhtas_user_pass,
            "QUAY_URL": quay_url,
        }

        # Render the template
        temp_file = render_yaml_template(template_path, template_vars=template_vars)

        cmds = shlex.split(f"oc apply -f {temp_file.name}")
        run_cmds(cmds)

        # Close when done (auto-deleted if delete=True)
        temp_file.close()

        rhtas_signer_pod.wait_for_condition(
            condition=Pod.Condition.READY, status=Pod.Condition.Status.TRUE
        )
        assert rhtas_signer_pod.exists
    yield rhtas_signer_pod


@pytest.mark.test_rhtas_integration_verify_spiffe_identity
def test_rhtas_integration_verify_spiffe_identity(
    openshift_dyn_client, cluster_apps_fqdn, rhtas_signer_pod
):
    # Introduce the dependency to ensure test workload is created before tests
    assert rhtas_signer_pod.exists
    # Verify SPIRE entry
    spire_server_pod = Pod(
        client=openshift_dyn_client,
        name="spire-server-0",
        namespace="zero-trust-workload-identity-manager",
    )
    assert spire_server_pod.exists
    spire_verify_cmds = ["/spire-server", "entry", "show"]
    spire_verify_result = spire_server_pod.execute(
        spire_verify_cmds, container="spire-server"
    )
    # Expected: Shows SPIFFE ID: spiffe://apps.<domain>/ns/rhtas-signing-test/sa/signer
    spiffe_id_url = f"spiffe://{cluster_apps_fqdn}/ns/rhtas-signing-test/sa/signer"
    err_msg = f"Expected: {spiffe_id_url}\n{spire_verify_result}"
    assert spiffe_id_url in spire_verify_result, err_msg


def run_script_remotely(script_path, script_name, description, remote_pod):
    script_fp = os.path.join(script_path, "rhtas-signing-test", script_name)
    logger.debug(f"Pushing script {script_fp} to the container...")
    cmds = shlex.split(
        f"oc cp {script_fp} rhtas-signing-test/rhtas-signer:/tmp/{script_name}"
    )
    run_cmds(cmds)
    logger.debug(f'Executing the script at "/tmp/{script_name}"...')
    try:
        script_output = remote_pod.execute(shlex.split(f"bash /tmp/{script_name}"))
        logger.debug(script_output)
        logger.info(f"Pass: Succeed to {description}")
        return script_output
    except ExecOnPodError as e:
        logger.warning(f"FAIL: Failed to {description}!")
        logger.warning(e.err)
        logger.debug(e)


@pytest.mark.test_rhtas_integration_certification_issuance_with_spiffe
def test_rhtas_integration_certification_issuance_with_spiffe(
    openshift_dyn_client,
    data_path,
    fulcio_host,
    rekor_host,
    tuf_host,
    cli_server_host,
    rhtas_signer_pod,
):
    # Check SPIFFE socket exists
    cmd = shlex.split("ls -la /spiffe-workload-api/")
    cmd_result = rhtas_signer_pod.execute(cmd)
    # Expected: spire-agent.sock
    assert "spire-agent.sock" in cmd_result

    # Setup openshift ingress CA trust (Works across clusters)
    rhtas_signer_pod.execute(
        shlex.split(
            'bash -c "cp -p /run/kube-root-ca/ca.crt /etc/pki/ca-trust/source/anchors/ca.crt"'
        )
    )
    rhtas_signer_pod.execute(shlex.split("bash -c update-ca-trust"))

    # verify CA is trusted
    cmds = shlex.split(f"curl -s https://{fulcio_host}/healthz")
    try:
        rhtas_signer_pod.execute(cmds)
    except ExecOnPodError as e:
        if e.rc == 60:
            logger.debug("FAIL: CA is not trusted!")
        else:
            logger.debug(e)
            raise

    scripts = {
        "install-cosign.sh": "download and install cosign",  # Install cosign from RHTAS CLI server
        "initialize-tuf-root.sh": "initialize TUF root",  # Initiliza TUF root
        "sign-blob.sh": "sign a blob",  # Sign a Blob using a SPIFFE Identity
        "verify-signature.sh": "verify the signature",  # Verify the signature
        "verify-against-rekor.sh": "verify against rekor",  # Verify against rekor
    }

    for script_name, script_description in scripts.items():
        try:
            run_script_remotely(
                script_path=data_path,
                script_name=script_name,
                description=script_description,
                remote_pod=rhtas_signer_pod,
            )
        except Exception:
            assert False


@pytest.mark.test_keycloak_issuer
def test_keycloak_issuer(
    openshift_dyn_client, cluster_apps_fqdn, rhtas_signer_pod, data_path
):
    # Verify Fulcio configuration for email issuer
    securesign_name = "trusted-artifact-signer"
    securesign = pattern_crd.Securesign(
        client=openshift_dyn_client, name=securesign_name, namespace=rhtas_namespace
    )

    assert securesign.exists

    securesign_verified = False
    for oidc_issuer in securesign.instance.spec.fulcio.config.OIDCIssuers:
        if oidc_issuer["Type"] == "email":
            assert oidc_issuer["ClientID"] == "trusted-artifact-signer"
            assert "/realms/ztvp" in oidc_issuer["IssuerURL"]
            securesign_verified = True
            break
        else:
            continue

    assert securesign_verified
    logger.info("PASS: Fulcio correctly configured with keycloak issuer")

    scripts_dir = os.path.join(data_path, "rhtas-signing-test", "keycloak")

    # Verify token includes audience claim
    script_name = "get-keycloak-token.py"
    script_path = os.path.join(data_path, script_name)
    logger.debug(f"Pushing script {script_path} to the container...")
    cmds = shlex.split(
        f"oc cp {script_path} rhtas-signing-test/rhtas-signer:/tmp/{script_name}"
    )
    run_cmds(cmds)

    script_name = "verify-token-includes-audience-claim.sh"
    script_description = "Get token includes audience claim"
    script_output = run_script_remotely(
        script_path=scripts_dir,
        script_name=script_name,
        description=script_description,
        remote_pod=rhtas_signer_pod,
    )
    if script_output is not None:
        err_msg = "FAIL: Token does NOT include audience claim"
        assert '"aud": "trusted-artifact-signer",' in script_output, err_msg
    else:
        logger.warning("WARNING: No output from script!")

    # Sign artifact from pod
    script_name = "sign-artifact-from-pod.sh"
    script_description = "Sign artifact from pod"
    script_output = run_script_remotely(
        script_path=scripts_dir,
        script_name=script_name,
        description=script_description,
        remote_pod=rhtas_signer_pod,
    )

    # Verify the signature from rhtas-signer pod
    script_name = "verify-signature-from-pod.sh"
    script_description = "Verify the signature from rhtas-signer pod"
    script_output = run_script_remotely(
        script_path=scripts_dir,
        script_name=script_name,
        description=script_description,
        remote_pod=rhtas_signer_pod,
    )


@pytest.mark.test_sign_with_quay
def test_sign_with_quay(openshift_dyn_client, data_path, rhtas_signer_pod):
    scripts_dir = os.path.join(data_path, "rhtas-signing-text", "quay")

    scripts = {
        "build-and-push-test-image.sh": "Build and push test image",
        "sign-pushed-image.sh": "Sign the container image with SPIFFE identity",
        "verify-signature.sh": "Verify container image signed by SPIFFE",
        "sign-image-with-email-issuer.sh": "Sign the container image with email issuer (e.g., keycloak)",
        "verify-signature-with-email-issuer.sh": "Verify container image signed by email (e.g., keycloak)",
        "query-rekor-transparency-log.sh": "Query Rekor transparency log",
    }

    for script_name, script_description in scripts.items():
        try:
            run_script_remotely(
                script_path=scripts_dir,
                script_name=script_name,
                description=script_description,
                remote_pod=rhtas_signer_pod,
            )
        except Exception:
            assert False
