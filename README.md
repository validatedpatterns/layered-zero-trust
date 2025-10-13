# Layered Zero Trust

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

<!--
[Live build status](https://validatedpatterns.io/ci/?pattern=layeredzerotrust)

-->

## About the Layered Zero Trust Pattern

Showcases the Zero Trust capabilities across Red Hat's product portfolio in a reproducible manner.

### Components

The following components are included in the Layered Zero Trust Pattern

* OpenShift cluster hardening
  * [Compliance Operator](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/security_and_compliance/compliance-operator)
* [Red Hat Build of Keycloak](https://access.redhat.com/products/red-hat-build-of-keycloak/)
  * Identities to access pattern components
  * OIDC client to authenticate uses to a web application
* [Red Hat Zero Trust Workload Identity Manager](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/security_and_compliance/zero-trust-workload-identity-manager)
  * Provides identities to workloads running within OpenShift
* [HashiCorp Vault](https://www.hashicorp.com/en/products/vault)
  * Secure storage of sensitive assets
* [External Secrets Operator (ESO)](https://external-secrets.io)
  * Synchronizes secrets stored in HashiCorp Vault with OpenShift

## Getting Started

Utilize the following steps to prepare your machine and complete any and all prerequisites needed.

### Prerequisites

1. An OpenShift Container Platform 4.19+ cluster with:
    1. Publicly signed certificates for Ingress
    2. A default `StorageClass` which provides dynamic `PersistentVolume` storage
2. To customize the provided default configuration, a GitHub account and a token for it with repositories permissions, to read from and write to your forks, is required.
3. Access to Podman (or Docker) for execution of the container images used by pattern.sh script for provisioning.
4. [Validated Patterns Tooling](https://validatedpatterns.io/learn/quickstart)
5. Depending on the characteristics of your cluster, you may need additional hardware resources for Advanced Cluster Management (ACM) component. For a single node cluster you can start with 4 vCPUs, 16 GB of memory and 120 GB of storage. For more detailed information about ACM sizing, please refer to the [official documentation](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.14/html-single/install/index#sizing-your-cluster).

_NOTE_: The default deployment of this patterns assumes that none of the components associated with the pattern have been deployed previously. Ensure that your OpenShift environment does not include any of the preceding components.

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
    git remote add -f upstream git@github.com/validatedpatterns/layered-zero-trust.git
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

#### Secure Multi-tier Application Use Case

One of the most common application design patterns makes use of a frontend application leveraging a database for persistent storage. Instead of traditional methods for accessing the database from the frontend application using static values stored within the application, this pattern will make use "just in time" methods for obtaining these database values from a credential store. A more detailed overview is located below:

* qtodo - [Quarkus](https://quarkus.io) based frontend application. Access is protected via OIDC based authentication with users defined within an external identity store (Red Hat Build of Keycloak by default)
* PostgreSQL - Relational database for use by the qtodo application. Credentials are generated dynamically and stored within Vault.
* External Identity store - Users have been defined to enable access to the qtodo frontend. OIDC clients have also been created and configured within the todo application
* HashiCorp Vault - Several features are being leveraged within this use case the external identity store
  * Secrets store - Storage of sensitive values for components including PostgreSQL and RHBK
  * JWT based authentication - Enables access using ZTWIM based identities
* Zero Trust Workload Identity - Enables an identity to be assigned to the qtodo application to communicate with HashiCorp Vault and obtain the credentials to access the PostgreSQL database
  * [spiffe-helper](https://github.com/spiffe/spiffe-helper) - Supplemental component provided for the qtodo application to dynamically fetch JWT based identities from the SPIFFE Workload API.

#### Investigating the qtodo Application in depth

With an understanding of the goals and architecture of qtodo, launch the OpenShift Console of the Hub cluster and navigate to the `qtodo` project

1. Select **Home** -> **Projects** from the left hand navigation bar
2. Locate and select the **qtodo** project

The _qtodo_ Quarkus application and _qtodo-db_ PostgreSQL database are found within this namespace.

View the running pods associated with these components

1. Select **Workloads** -> **Pods** from the left hand navigation bar
2. Explore both the _qtodo_ and _qtodo-db_ pods.

Take note that the _qtodo_ Pod makes use of a series of init containers and sidecar containers that are used to supply the application with credentials needed to support the application.

Access the qtodo application in a browser. The URL can be located from the OpenShift Route in the `qtodo` Project

1. Select **Networking** -> **Routes** from the lefthand navigation bar
2. Click the arrow next to the the URL underneath the _Location_ column to open the qtodo application in a new browser tab

You will be presented with a login page to access the application. When using the default External Identity Provider (RHBK), two users (`qtodo-admin` and `qtodo-user`) were provisioned automatically. Their initial credentials are stored in a Secret in the `keycloak-system` namespace called `keycloak-users`. You can reveal the credentials by switching to the tab containing the OpenShift Console using the following steps:

1. Select **Home** -> **Projects** from the left hand navigation bar
2. Locate and select the **keycloak-system** project
3. Select **Workloads** -> **Secrets** from the left hand navigation bar
4. Select the **keycloak-users** Secret
5. Click the **Reveal values** link to uncover the underlying values for the users

Switch back to the qtodo application and enter the username and password on the login page for one of the users using the values discovered previously.

Once you have authenticated to RHBK, you will be instructed to change the temporary password and set a more permanent password. Once complete, you will be redirected to the qtodo application verifying the OIDC based authentication functions properly.

Feel free to add new items to the list of todos. By being able to add and remove items from the page, the integration between the Quarkus application and the backend PostgreSQL database using credentials sourced from HashiCorp Vault was successful.
