from ocp_resources.resource import NamespacedResource, Resource


class CertManager(Resource):
    """
    CertManager object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "CertManager"


class ExternalSecret(NamespacedResource):
    """
    ExternalSecret object
    """

    api_version = "external-secrets.io/v1beta1"
    kind = "ExternalSecret"
