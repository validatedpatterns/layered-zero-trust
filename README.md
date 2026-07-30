# Layered Zero Trust

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

<!--
[Live build status](https://validatedpatterns.io/ci/?pattern=layeredzerotrust)

-->

## About the Layered Zero Trust Pattern

Showcases the Zero Trust capabilities across Red Hat's product portfolio in a reproducible manner.

### Architecture Overview

The pattern is structured in layers, each building on the one below it:

* **Validated Patterns Framework** — bootstraps the cluster using OpenShift GitOps (Argo CD) and the Validated Patterns Operator. All subsequent components are deployed and reconciled by Argo CD.
* **Layer 0 — Foundations** — establishes a secure cluster baseline: TLS certificate management, compliance scanning, advanced cluster management, and runtime security enforcement.
* **Layer 1 — Feature Sets** — provisions workload identities (SPIFFE/SPIRE), manages secrets (Vault + ESO), and provides user authentication (Keycloak). Optionally includes a private image registry (Quay + NooBaa).
* **Layer 2 — Mapping** — deploys the demo application (qtodo) and, optionally, the full secure supply chain pipeline (RHTAS, RHTPA, OpenShift Pipelines).

See `docs/diagrams/` for logical and schematic diagrams of the pattern.

### Components

Components are grouped by their origin and whether they are always deployed or opt-in.

#### Validated Patterns Framework (provided by the VP project)

These components are part of every Validated Pattern and are not specific to ZTVP. Their Helm charts live in the [validatedpatterns](https://github.com/validatedpatterns) organization.

* [OpenShift GitOps (Argo CD)](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops)
  * Deploys and continuously reconciles all pattern components via GitOps
* [Validated Patterns Operator](https://validatedpatterns.io)
  * Bootstraps the pattern, manages the Hub/Spoke lifecycle, and drives imperative jobs

#### Core ZTVP Components (always deployed)

These components are deployed by default with every ZTVP installation. Components marked with _(externalized chart)_ use Helm charts maintained in the [validatedpatterns](https://github.com/validatedpatterns) organization rather than local charts in this repository.

* OpenShift cluster hardening
  * [Compliance Operator](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/security_and_compliance/compliance-operator) _(externalized chart)_
    * Continuously scans the cluster against CIS and other security profiles
  * [cert-manager](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/security_and_compliance/cert-manager-operator-for-red-hat-openshift)
    * Manages TLS certificates for pattern components
* [Red Hat Advanced Cluster Management (ACM)](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes)
  * Provides a management control plane in multi-cluster scenarios
* [Red Hat Advanced Cluster Security (ACS)](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_security_for_kubernetes)
  * Provides runtime security policy enforcement and image vulnerability scanning
* [HashiCorp Vault](https://www.hashicorp.com/en/products/vault)
  * Secure storage of sensitive assets and dynamic secret generation
* [External Secrets Operator (ESO)](https://external-secrets.io)
  * Synchronizes secrets stored in HashiCorp Vault with OpenShift
* [Red Hat Build of Keycloak (RHBK)](https://access.redhat.com/products/red-hat-build-of-keycloak/) _(externalized chart)_
  * Provides user identities and OIDC authentication for pattern components and workloads
* [Red Hat Zero Trust Workload Identity Manager (ZTWIM)](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/security_and_compliance/zero-trust-workload-identity-manager) _(externalized chart)_
  * Automates provisioning of SPIFFE/SPIRE-based verifiable identities for workloads running within OpenShift

#### Optional ZTVP Components (opt-in)

These components are commented out in `values-hub.yaml` by default. Uncomment the relevant sections to enable them. See [Deploy the pattern](#deploy-the-pattern) for details.

* [Red Hat Quay](https://docs.redhat.com/en/documentation/red_hat_quay) _(externalized chart)_
  * Enables a private OCI image registry within the environment
* [Multicloud Object Gateway (NooBaa MCG)](https://docs.redhat.com/en/documentation/red_hat_openshift_data_foundation/latest/html/managing_hybrid_and_multicloud_resources/about-the-multicloud-object-gateway)
  * Provides S3-compatible object storage for Quay and RHTPA
* [Red Hat Trusted Artifact Signer (RHTAS)](https://docs.redhat.com/en/documentation/red_hat_trusted_artifact_signer/1.3)
  * Provides cryptographic signing and verification of software artifacts and container images
* [Red Hat Trusted Profile Analyzer (RHTPA)](https://docs.redhat.com/en/documentation/red_hat_trusted_profile_analyzer)
  * Stores and manages _Software Bill of Materials_ (SBOMs) with cross-referencing against CVEs and Security Advisories
* [Red Hat OpenShift Pipelines](https://docs.redhat.com/en/documentation/red_hat_openshift_pipelines/1.20)
  * Enables the native CI/CD pipeline for the secure supply chain use case

## Getting Started

Utilize the following steps to prepare your machine and complete any and all prerequisites needed.

### Prerequisites

1. An OpenShift Container Platform 4.20 or 4.21 cluster with:
    1. Publicly signed certificates for Ingress
    2. A default `StorageClass` which provides dynamic `PersistentVolume` storage
2. To customize the provided default configuration, a GitHub account and a token for it with repositories permissions, to read from and write to your forks, is required.
3. Access to Podman (or Docker) for execution of the container images used by pattern.sh script for provisioning.
4. [Validated Patterns Tooling](https://validatedpatterns.io/learn/quickstart)
5. Depending on the characteristics of your cluster, you may need additional hardware resources for Advanced Cluster Management (ACM) component. For a single node cluster you can start with 4 vCPUs, 16 GB of memory and 120 GB of storage. For more detailed information about ACM sizing, please refer to the [official documentation](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.14/html-single/install/index#sizing-your-cluster).

>[!WARNING]
> The default deployment of this patterns assumes that none of the components associated with the pattern have been deployed previously. Ensure that your OpenShift environment does not include any of the preceding components.

### Prepare for Deployment

1. While not required, it is recommended that you Fork the Validated Pattern repository.From the [layered-zero-trust](https://github.com/validatedpatterns/layered-zero-trust) repository on GitHub, click the [Fork button](https://github.com/validatedpatterns/layered-zero-trust/fork).

2. Clone the forked copy of this repository by running the following command.

    ```shell
    git clone git@github.com:<your-username>/layered-zero-trust.git
    ```

3. Navigate to your repository: Ensure you are in the root directory of your Git repository by using:

    ```shell
    cd /path/to/your/repository
    ```

4. Run the following command to set the upstream repository:

    ```shell
    git remote add -f upstream git@github.com:validatedpatterns/layered-zero-trust.git
    ```

5. Verify the setup of your remote repositories by running the following command:

    ```shell
    git remote -v
    ```

    Example Output:

    ```shell
    origin  git@github.com:<your-username>/layered-zero-trust.git (fetch)
    origin  git@github.com:<your-username>/layered-zero-trust.git (push)
    upstream    https://github.com/validatedpatterns/layered-zero-trust.git (fetch)
    upstream    https://github.com/validatedpatterns/layered-zero-trust.git (push)
    ```

6. Create a local copy of the secret values file that can safely include credentials. Run the following command :

    ```shell
    cp values-secret.yaml.template ~/values-secret-layered-zero-trust.yaml
    ```

    [!NOTE]
    Putting the `values-secret.yaml` in your home directory ensures that it does not get pushed to your Git repository. It is based on the `values-secrets.yaml.template` file provided by the pattern in the top level directory. When you create your own patterns you will add your secrets to this file and save. At the moment the focus is on getting started and familiar with this pattern.

7. Create a new feature branch, for example `my-branch` from the `main` branch for your content:

    ```shell
    git checkout -b my-branch main
    ```

8. Perform any desired changes to the Helm _values_ files to customize the execution of the pattern (optional). Commit the changes

    ```shell
    git add <file(s)>
    git commit -m "Pattern customization"
    ```

9. Push the changes in the branch to your forked repository

    ```shell
    git push origin my-branch
    ```

## Deploy the pattern

The [pattern.sh](pattern.sh) script is used to deploy the Layered Zero Trust Validated pattern.

1. Login to your OpenShift cluster
    a. Obtain an API token by visiting [https://oauth-openshift.apps.<your-cluster>.<domain>/oauth/token/request](https://oauth-openshift.apps.<your-cluster>.<domain>/oauth/token/request).
    b. Log in with this retrieved token by running the following command:

    ```shell
    oc login --token=<retrieved-token> --server=https://api.<your-cluster>.<domain>:6443
    ```

2. Alternatively log in by referencing an existing _KUBECONFIG_ file:

    ```shell
    export KUBECONFIG=~/<path_to_kubeconfig>
    ```

3. Deploy the pattern

    **Default deployment (without Quay - using other registry options):**

    ```shell
    ./pattern.sh make install
    ```

    **Deployment with optional Layer 1 components (Quay Registry, RHTAS):**

    To include optional components like Quay Registry + NooBaa MCG storage or RHTAS:
    1. Edit `values-hub.yaml`
    2. Uncomment the relevant sections for the components you want
    3. Run: `./pattern.sh make install`

    > **Note**: Optional Layer 1 components are commented out by default. Quay Registry + NooBaa MCG adds ~6 CPU cores, ~12Gi memory, ~10Gi storage when enabled.

### Exploring the Deployed Pattern

Once the pattern has been successfully deployed, you can review the deployed components. Each are deployed and managed using OpenShift GitOps.

Two (2) instances of OpenShift GitOps has been deployed to your Hub Cluster. Each can be seen within the OpenShift Console by selecting the Application Selector at the top navigation bar (box with 9 smaller squares).

1. Cluster Argo CD - Deploys an Argo CD App of Apps Application called _layered-zero-trust-hub_ which deploys the components associated with the pattern. These _Applications_ are managed by the Hub Argo CD instance (see below)
2. Hub Argo CD - Manages the individual components associated with the pattern on the Hub OpenShift instance.

If all of the Argo CD applications are reporting healthy, the pattern has been deployed successfully.

### Use cases

* [Secure Multi-tier Application](./docs/multi-tier.md)
* [Secure Supply Chain](./docs/supply-chain.md)
* [ACS Deployment Details](./docs/acs-deployment.md)
* [Confidential Containers (CoCo)](./docs/CONFIDENTIAL-CONTAINERS.md)

### Importing existing clusters

>[!WARNING]
> Since ACM chart provisioning functionality uses `ClusterPools` and these technology is limited to Cloud environments, we do not recommend use those configuration settings.
> Instead, we have enabled the option to import your existing standalone clusters using the **acm-managed-clusters** chart.

The pattern supports importating pre-existing Openshift clusters into the Hub cluster, converting them into **Managed Clusters**.

1. Copy the `kubeconfig` file of the cluster you want to import to your local system.

2. In the `values-secret.yaml` file, add a new secret with the contents of the `kubeconfig` file.

    ```yaml
      - name: kubeconfig-spoke
        vaultPrefixes:
        - hub
        fields:
        - name: content
          path: ~/.kube/kubeconfig-ztvp-spoke
    ```

3. In the `values-hub.yaml` file, add a new entry in the `clusterGroup.managedClusterGroups` key.

    ```yaml
      managedClusterGroups:
        exampleRegion:
          name: group-one
          acmlabels:
            - name: clusterGroup
              value: group-one
          helmOverrides:
            - name: clusterGroup.isHubCluster
              value: false
    ```

4. Also in the `values-hub.yaml` file, add your cluster definition in the `acmManagedClusters.clusters` key.

    ```yaml
    acmManagedClusters:
      clusters:
        - name: ztvp-spoke-1
          clusterGroup: group-one
          labels:
            cloud: auto-detect
            vendor: auto-detect
          kubeconfigVaultPath: secret/data/hub/kubeconfig-spoke
    ```

5. Deploy the pattern.

## Development

Interested in developing capabilities for this pattern or performing tests against it? Head over to our [Developer Documentation](./docs/DEVELOPMENT.md).
