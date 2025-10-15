from ocp_resources.resource import NamespacedResource, Resource


class APIServer(Resource):
    """
    APIServer object
    """

    api_version = "config.openshift.io/v1"
    kind = "APIServer"


class CertManager(Resource):
    """
    CertManager object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "CertManager"


class ClusterIssuer(Resource):
    """
    ClusterIssuer object
    """

    api_version = "cert-manager.io/v1"
    kind = "ClusterIssuer"


class Certificate(NamespacedResource):
    """
    Certificate object
    """

    api_version = "cert-manager.io/v1"
    kind = "Certificate"

    @property
    def ready(self):
        """
        Get Certificate status

        Returns:
            True if Ready else False
        """
        condition = self.instance.status.conditions[0]
        if condition.type == "Ready":
            if condition.status == "True":
                return True
        return False


class ExternalSecret(NamespacedResource):
    """
    ExternalSecret object
    """

    api_version = "external-secrets.io/v1beta1"
    kind = "ExternalSecret"


class IngressController(NamespacedResource):
    """
    IngressController object
    """

    api_version = "operator.openshift.io/v1"
    kind = "IngressController"


class SpireAgent(Resource):
    """
    SpireAgent object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "SpireAgent"


class SpireServer(Resource):
    """
    SpireServer object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "SpireServer"


class SpiffeCSIDriver(Resource):
    """
    SpiffeCSIDriver object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "SpiffeCSIDriver"


class SpireOIDCDiscoveryProvider(Resource):
    """
    SpireOIDCDiscoveryProvider object
    """

    api_version = "operator.openshift.io/v1alpha1"
    kind = "SpireOIDCDiscoveryProvider"
