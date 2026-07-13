import pytest

from validatedpatterns_tests.interop import subscription, components, application


@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["VP_HUBCONFIG"],
    indirect=True,
)
def test_subscription_status_hub(openshift_dyn_client):
    expected_subs = { # subscription: [namespace]
        "advanced-cluster-management": ["open-cluster-management"],
        "openshift-gitops-operator": ["openshift-gitops-operator"],
        "openshift-external-secrets-operator": ["external-secrets-operator"],
        "openshift-cert-manager-operator": ["cert-manager-operator"],
        "rhbk-operator": ["keycloak-system"],
        "compliance-operator": ["openshift-compliance"],
        "rhacs-operator": ["openshift-operators"],
        "openshift-zero-trust-workload-identity-manager": ["zero-trust-workload-identity-manager"],
        "openshift-pipelines-operator-rh": ["openshift-operators" ],
        "odf-operator": ["openshift-storage"],
        "quay-operator": ["openshift-operators"],
        "rhtas-operator": ["openshift-operators"],
        "rhtpa-operator": ["rhtpa-operator"],
    }

    subscription.assert_subscription_status(
        openshift_dyn_client, expected_subs
    )


@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["VP_HUBCONFIG"],
    indirect=True,
)
def test_site_reachable(openshift_dyn_client):

    components.assert_site_reachable(openshift_dyn_client)


@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["VP_HUBCONFIG"],
    indirect=True,
)
def test_pod_status_hub(openshift_dyn_client):
    projects = [
        "external-secrets-operator", # application.argoproj.io/openshift-external-secrets
        "external-secrets", # application.argoproj.io/openshift-external-secrets
        "keycloak-system", # application.argoproj.io/rh-keycloak
        "openshift-compliance", # application.argoproj.io/compliance-scanning
        "openshift-operators",
        "openshift-gitops",
        "openshift-gitops-operator",
        "openshift-storage", # application.argoproj.io/noobaa-mcg
        "open-cluster-management", # application.argoproj.io/acm
        "vault", # application.argoproj.io/vault
        "zero-trust-workload-identity-manager", # application.argoproj.io/zero-trust-workload-identity-manager
        "stackrox", # application.argoproj.io/acs-central-services # application.argoproj.io/acs-policies # application.argoproj.io/acs-secured-cluster
        "cert-manager", # application.argoproj.io/rh-cert-manager
        "cert-manager-operator", # application.argoproj.io/rh-cert-manager
        "qtodo",# application.argoproj.io/qtodo
        "qtodo-db",# application.argoproj.io/qtodo-db
        "quay-enterprise", # application.argoproj.io/quay-registry
        "vp-gitops",
        "patterns-operator",
        "trusted-artifact-signer", # application.argoproj.io/trusted-artifact-signer
        "trusted-profile-analyzer", # application.argoproj.io/trusted-profile-analyzer
        "openshift-config", # application.argoproj.io/ztvp-certificates
    ]

    skip_check = [ "create-auth-provider" ]
    components.assert_pod_status(openshift_dyn_client, projects, skip_check=skip_check)


@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["VP_HUBCONFIG"],
    indirect=True,
)
def test_argocd_reachable(openshift_dyn_client):
    components.assert_argocd_reachable(openshift_dyn_client)


@pytest.mark.parametrize(
    "openshift_dyn_client",
    ["VP_HUBCONFIG"],
    indirect=True,
)
def test_argocd_applications_health(openshift_dyn_client):
    projects = ["vp-gitops", "layered-zero-trust-hub"]

    application.assert_argocd_applications(
        openshift_dyn_client, projects
    )
