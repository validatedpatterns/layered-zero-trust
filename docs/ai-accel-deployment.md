## Overview
These instructions will allow for the deployment of the LZTVP to be compatible with the ai-accelerator project by installing the `layered-zero-trust-hub` ArgoCD application into the default GitOps instance, `Cluster Argo CD`.

### Considerations
Efforts were made to limit modifications to this repository and instead make modifications to the ai-accelerator. This was motivated by the desire to limit changes in both repositories to achieve compatibility. See the ai-accelerator's documentation on how to disable the ArgoCD application that configures the GitOps operator, so the LZTVP can retain ownership.

### Setup
The ai-accelerator deploys to the default GitOps ArgoCD instance, `openshift-gitops` within the `openshift-gitops` namespace. This is incompatible with the Validated Pattern, which disables this instance. The following instructions instructions allow for the creation of this default instance which replaces the "Argo CD VP" GitOps instance and will be where the `layered-zero-trust-hub` application is deployed.

1. Install the OpenShift GitOps Operator from the cluster's Operator Hub. Utilize the default settings for the installation. Wait until the Operator has fully deployed.
2. Uninstall the OpenShift GitOps Operator but **keep all of the operands**; the only thing that should be uninstalled is the operator, itself.
3. Remove the **OperatorGroup** from the `openshift-gitops-operator` namespace.
    - To see the `OperatorgGroup` that needs to be deleted, you can use this command: `oc get operatorgroups.operators.coreos.com -n openshift-gitops-operator`
    - The `OperatorGroup` can then be deleted with this command: `oc delete operatorgroups.operators.coreos.com openshift-gitops-operator-XXXXX -n openshift-gitops-operator`
4. Follow the instructions to install the LZTVP as specified [here](../README.md). This should create two ArgoCD instances:
    - **Cluster Argo CD**: This is the default ArgoCD instance and will be where the `layered-zero-trust-hub` application (app-of-apps) is installed. At this point in the installation, that is the only app that will be present, but eventually all of the ai-accelerator applications will be installed into this instance.
    - **Hub ArgoCD**: This instance is created by the LZTVP and is where all of the LZTVP applications are installed. NO ai-accelerator applications are installed into this isolated instance.
5. Make modifications to your fork of the ai-accelerator to not deploy the `openshift-gitops-operator` Argo application.
