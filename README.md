# Layered Zero Trust

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

<!--
[Live build status](https://validatedpatterns.io/ci/?pattern=mcgitops)

-->

## About the Layered Zero Trust Pattern

Showcases the Zero Trust capabilities across Red Hat's product portfolio in a reproducible manner.

## Getting Started

The basis of this pattern leverages the foundation provided by the [Multicloud GitOps Validated Pattern](https://validatedpatterns.io/patterns/multicloud-gitops/).

### Prerequisites

1. An OpenShift Cluster
    * Create a cluster either through the [Red Hat Hybrid Cloud Console](https://console.redhat.com) or manually using any of the available [installation methods](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/architecture/architecture-installation)
    * A default `StorageClass` which provides dynamic `PersistentVolume` storage
2. [Validated Patterns Tooling](https://validatedpatterns.io/learn/quickstart)

### Prepare for Deployment

1. From the [layered-zero-trust](https://github.com/validatedpatterns/layered-zero-trust) repository on GitHub, click the [Fork button](https://github.com/validatedpatterns/layered-zero-trust/fork).
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

### Deploy the pattern

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

    ```shell
    ./pattern.sh make install
    ```

4. Verify the deployment
    a. To verify, in the OpenShift web console, navigate to **Operators → Installed Operators** page.
    b. Check that **Red Hat OpenShift GitOps Operator** is installed in the `openshift-operators` namespace and its status is `Succeeded`.
    c. Use the Application Selector (box with 9 squares) within the OpenShift console to confirm that all _Applications_ have been synchronized successfully to both _Hub_ and _Cluster_ Argo CD instances.
