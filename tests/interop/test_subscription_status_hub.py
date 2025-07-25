import logging

import pytest
from validatedpatterns_tests.interop import subscription

from . import __loggername__

logger = logging.getLogger(__loggername__)


@pytest.mark.subscription_status_hub
def test_subscription_status_hub(openshift_dyn_client):
    # These are the operator subscriptions and their associated namespaces
    expected_subs = {
        "openshift-gitops-operator": [
            "openshift-operators"
        ],  # Layer 0: GitOps Operator
        "openshift-cert-manager-operator": [
            "cert-manager-operator"
        ],  # Layer 0: Cert-Manager with LetsEncrypt Support
        "rhbk-operator": ["keycloak-system"],  # Layer 0: Red Hat Build of Keycloak
        "compliance-operator": ["openshift-compliance"],  # Layer 0: Compliance Operator
        "openshift-zero-trust-workload-identity-manager": [  # Layer 1
            "zero-trust-workload-identity-manager"
        ],
    }

    err_msg = subscription.subscription_status(
        openshift_dyn_client, expected_subs, diff=True
    )
    if err_msg:
        logger.error(f"FAIL: {err_msg}")
        assert False, err_msg
    else:
        logger.info("PASS: Subscription status check passed")
