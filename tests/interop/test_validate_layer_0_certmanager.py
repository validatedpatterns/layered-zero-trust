import logging
import os

import pytest

from . import __loggername__
from .pattern_crd import (
    APIServer,
    Certificate,
    CertManager,
    ClusterIssuer,
    IngressController,
)

logger = logging.getLogger(__loggername__)

apiserver_certificate_name = os.getenv("CERTIFIACTE_NAME_APISERVER", "cluster-api-cert")
ingresscontroller_certificate_name = os.getenv(
    "CERTIFICATE_NAME_INGRESS_CONTROLLER", "default-ingress-wildcard-cert"
)


@pytest.mark.skipif(
    os.getenv("INFRA_PROVIDER") != "aws", reason="Requires AWS platform"
)
@pytest.mark.test_cert_manager_dns01_recursive_nameservers_option
def test_cert_manager_dns01_recursive_nameservers_option(openshift_dyn_client):
    certmanager_cluster = None
    is_set_dns_options = False
    try:
        certmanagers = CertManager.get(dyn_client=openshift_dyn_client)
        for certmanager in certmanagers:
            if certmanager.name == "cluster":
                certmanager_cluster = certmanager
        override_args = certmanager_cluster.instance.spec.controllerConfig.overrideArgs
        logger.debug(override_args)
        for arg in override_args:
            if "dns01-recursive-nameservers" in arg:
                is_set_dns_options = True
                break
    except StopIteration:
        err_msg = "No CertManager found!"
        assert False, err_msg
    except AttributeError:
        err_msg = 'No DNS options are set for CertManager "cluster"'
        assert False, err_msg

    err_msg = "Improper DNS options"
    assert is_set_dns_options, err_msg


@pytest.mark.test_cert_manager_clusterissuer_cr
def test_cert_manager_clusterissuer_cr(openshift_dyn_client):
    clusterIssuer_acme_exist = False
    try:
        clusterIssuers = ClusterIssuer.get(dyn_client=openshift_dyn_client)
        for clusterIssuer in clusterIssuers:
            logger.debug(f'Found ClusterIsser: "{clusterIssuer.name}"')
            if "acme" == clusterIssuer.name:
                clusterIssuer_acme_exist = True
                break
        assert clusterIssuer_acme_exist, 'ClusterIssuer "acme" not found!'
    except StopIteration:
        err_msg = "No ClusterIssuer found!"
        assert False, err_msg


@pytest.mark.test_certificate_status
def test_certificate_status(openshift_dyn_client):
    desired_certificates = {
        "openshift-ingress": [ingresscontroller_certificate_name],
        "openshift-config": [apiserver_certificate_name],
    }
    desired_certificates_status = {}
    for cert_ns in desired_certificates.keys():
        for name in desired_certificates[cert_ns]:
            desired_certificates_status[name] = False
        try:
            certificates = Certificate.get(
                dyn_client=openshift_dyn_client, namespace=cert_ns
            )
            for certificate in certificates:
                logger.debug(
                    f'Found Certificate: "{certificate.name}" in namespace "{certificate.namespace}"'
                )
                if certificate.name in desired_certificates[cert_ns]:
                    desired_certificates_status[certificate.name] = True
                    break
        except StopIteration:
            err_msg = "No Certificate found!"
            assert False, err_msg
    err_msg = f'One or more certificates are not in "Ready" status: {desired_certificates_status}'
    failed_certificates = list(
        filter(lambda x: x is False, desired_certificates_status.values())
    )
    assert len(failed_certificates) <= 0, err_msg


@pytest.mark.test_openshift_api_certificate
def test_openshift_api_certificate(openshift_dyn_client):
    cluster_name = f"{os.getenv("HUB_CLUSTER_PREFIX")}-{os.getenv("INFRA_PROVIDER")}-{os.getenv("MPTS_TEST_RUN_ID")}"
    apiserver_name = "cluster"
    apiserver_fqdn = f"api.{cluster_name}.{os.getenv("AWS_DOMAIN")}"
    apiserver_patch = {
        "metadata": {"name": apiserver_name},
        "spec": {
            "servingCerts": {
                "namedCertificates": [
                    {
                        "names": [apiserver_fqdn],
                        "servingCertificate": {
                            "name": f"{apiserver_certificate_name}-tls"
                        },
                    }
                ]
            }
        },
    }

    try:
        apiservers = APIServer.get(dyn_client=openshift_dyn_client)
        for apiserver in apiservers:
            if apiserver.name == apiserver_name:
                break
        logger.info("Patching APIServer...")
        apiserver.update(resource_dict=apiserver_patch)
    except StopIteration:
        err_msg = f"APIServer {apiserver_name} not found!"
        assert False, err_msg


@pytest.mark.test_openshift_default_ingress_certificate
def test_openshift_default_ingress_certificate(openshift_dyn_client):
    ingresscontroller_name = "default"
    ingresscontroller_patch = {
        "metadata": {"name": ingresscontroller_name},
        "spec": {
            "defaultCertificate": {"name": f"{ingresscontroller_certificate_name}-tls"}
        },
    }

    try:
        ingresscontrollers = IngressController.get(dyn_client=openshift_dyn_client)
        for ingresscontroller in ingresscontrollers:
            if ingresscontroller.name == ingresscontroller_name:
                ingresscontroller_patch["metadata"][
                    "namespace"
                ] = ingresscontroller.namespace
                break
        logger.info("Patching ingresscontroller...")
        ingresscontroller.update(resource_dict=ingresscontroller_patch)
    except StopIteration:
        err_msg = f"ingresscontroller {ingresscontroller_name} not found!"
        assert False, err_msg
