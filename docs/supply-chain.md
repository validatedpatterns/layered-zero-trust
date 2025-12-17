# Secure Supply Chain

This use case outlines the process of building, signing, and verifying artifacts and images within the Zero Trust Validated Pattern (ZTVP).

In this project, we used the [qtodo](https://github.com/validatedpatterns-demos/qtodo/) application as a sample to show how to build a secure supply chain in a software development factory.

## Components

### Main

* [Red Hat Trusted Artifact Signer (RHTAS)](https://docs.redhat.com/en/documentation/red_hat_trusted_artifact_signer/1) is a solution for signing and verifying software artifacts to ensure their integrity and authenticity.
* [Red Hat Trusted Profile Analyzer (RHTPA)](https://docs.redhat.com/en/documentation/red_hat_trusted_profile_analyzer/2) is a product that helps DevSecOps teams gain visibility into software supply chain risks by analyzing _Software Bill of Materials_ (SBOMs) and crossing data with _Vulnerability Exploitability eXchange_ (VEX) and _Common Vulnerabilities and Exposures_ (CVE) databases.

### Supporting Components

In our demo, we will use a number of additional ZTVP components. These components are auxiliary, and help us prepare an environment compatible with Zero Trust (ZT), but they are also cross-cutting and can be replaced by other compatible solutions.

* [Red Hat Zero Trust Workload Identity Manager](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/security_and_compliance/zero-trust-workload-identity-manager) is a solution that automates the provisioning and management of verifiable identities based on SPIRE/SPIFFE for workloads on OpenShift. It will be used to manage the signature and verification. It could be replaced by your own OIDC.
* [Red Hat Quay](https://docs.redhat.com/en/documentation/red_hat_quay/3) is container registry platform for storing and distributing container images and cloud-native artifacts. We will use it to store the image, signature, and attestations associated with our application. An alternate image registry can be used if desired.
* [Multicloud Object Gateway](https://docs.redhat.com/en/documentation/red_hat_openshift_container_storage/4.8/html/managing_hybrid_and_multicloud_resources/index) is a data service for OpenShift that provides an S3-compatible object storage. In our case, this component is necessary to provide a storage system to Quay.
* [Red Hat OpenShift Pipelines](https://docs.redhat.com/en/documentation/red_hat_openshift_pipelines/1.20) is a cloud-native CI/CD solution built on the Tekton framework. We will use this product to automate our secure supply chain process, but you could use your own CI/CD solution if one exists.

## Automatic approach

To automate the application building and certifying process, we will use _Red Hat OpenShift Pipelines_.

ZTVP will create a `Pipeline` in our cluster called **qtodo-supply-chain** that will orchestrate the various tasks necessary to build the application from its source code, generate a container image, and publish the resulting image to the defined OCI registry. Within the pipeline, an SBOM containing the build's contents will be generated, binaries and the build attestation will be signed, and the validity of those signatures will be verified.

### How to run the pipeline

#### Using OpenShift Web Console

1. Launch the OpenShift Web console.
2. Select **Pipelines -> Pipelines** from the left hand navigation bar.
3. Locate the **qtodo-supply-chain** pipeline. It's within the **layered-zero-trust-hub** project.
4. In the kebab menu (three vertical dots) from the right-hand, select **Start**.

    Review the configurable parameters. Most parameters should be correct with their default values if we are in single-cluster mode. But, double-check their values just in case.

    At the bottom we have the **workspaces**. These must be configured manually.

    * For **qtodo-source**, select `PersistentVolumeClaim` and the PVC name is `qtodo-workspace-source`.
    * For **registry-auth-config**, select `Secret` and the name of the secret is `qtodo-registry-auth`.

5. Press **Start** to finish and run the pipeline.

#### Using CLI

We can also start a pipeline execution using a CLI and the Kubernetes API. We start creating a new `PipelineRun` resource referencing the `qtodo-supply-chain` pipeline. Let's create a new file called `qtodo-pipeline.yaml` and copy this content.

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: qtodo-manual-run-
  namespace: layered-zero-trust-hub
spec:
  pipelineRef:
    name: qtodo-supply-chain
  taskRunTemplate:
    serviceAccountName: pipeline
  timeouts:
    pipeline: 1h0m0s
  workspaces:
  - name: qtodo-source
    persistentVolumeClaim:
      claimName: qtodo-workspace-source
  - name: registry-auth-config
    secret:
      secretName: qtodo-registry-auth
```

As was described previously, verify the values associated with the PVC storage and registry configuration.

Using the previously created definition, start a new execution of the pipeline using `oc` CLI:

```shell
oc create -f qtodo-pipeline.yaml
```

You can review the current pipeline logs using the [Tekton CLI](https://tekton.dev/docs/cli/).

```shell
tkn pipeline logs -n layered-zero-trust-hub -L -f
```

### Pipeline tasks

The pipeline we have prepared has the following steps:

* **qtodo-clone-repository**. Clones the `qtodo` repository.
* **qtodo-build-artifact**. Builds an _uber-jar_ of `qtodo` application.
* **qtodo-sign-artifact**. Signs the JAR file generated during the build process.
* **qtodo-verify-artifact**. Verifies the JAR signature generated in the previous step.
* **qtodo-build-image**. Builds a container with the `qtodo` application and upload it to an image registry.
* **qtodo-sign-image**. Signs the container image.
* **qtodo-generate-sbom**. Generates an SBOM from the image.
* **qtodo-sbom-attestation**. Creates a (signed) attestation, and attaches it to the image.
* **qtodo-upload-sbom**. Uploads the generated SBOM file  to RHTPA.
* **qtodo-verify-image**. Verifies the attestation and the signature attached to the image.

### Inspecting the results

#### Openshift Web UI

1. Launch the OpenShift Web console.
2. Select **Pipelines -> Pipelines** from the left hand navigation bar.
3. Locate the **qtodo-supply-chain** pipeline (**layered-zero-trust-hub** project).
4. Select the **PipelineRun** link in the column **Last run**.
5. In the **Details** tab we can see a summary of the pipeline execution and tasks.
6. By **clicking** on each individual task, or on the **Logs** tab, we can see the output of the tasks.

#### CLI

The first thing we'll check is whether our pipeline has finished successfully.

```shell
oc get pipelinerun -n layered-zero-trust-hub

NAME                        SUCCEEDED   REASON      STARTTIME   COMPLETIONTIME
qtodo-manual-run-p46f7      True        Succeeded   7m4s        2m12s
```

We can see the individual result of each step by reviewing the `TaskRuns`.

```shell
oc get taskruns -n layered-zero-trust-hub

NAME                                               SUCCEEDED   REASON             STARTTIME   COMPLETIONTIME
qtodo-manual-run-p46f7-qtodo-build-artifact        True        Succeeded          7m44s       5m17s
qtodo-manual-run-p46f7-qtodo-build-image           True        Succeeded          4m55s       4m4s
qtodo-manual-run-p46f7-qtodo-clone-repository      True        Succeeded          7m55s       7m44s
qtodo-manual-run-p46f7-qtodo-generate-sbom         True        Succeeded          4m4s        3m41s
qtodo-manual-run-p46f7-qtodo-sbom-attestation      True        Succeeded          3m41s       3m22s
qtodo-manual-run-p46f7-qtodo-sign-artifact         True        Succeeded          5m16s       5m5s
qtodo-manual-run-p46f7-qtodo-sign-image            True        Succeeded          4m4s        3m45s
qtodo-manual-run-p46f7-qtodo-upload-sbom           True        Succeeded          3m41s       3m29s
qtodo-manual-run-p46f7-qtodo-verify-artifact       True        Succeeded          5m5s        4m55s
qtodo-manual-run-p46f7-qtodo-verify-image          True        Succeeded          3m22s       3m3s
```

Tasks run as pods within OpenShift. We can find these pods in the namespace `layered-zero-trust-hub`.

```shell
oc get pods -n layered-zero-trust-hub

NAME                                                    READY   STATUS      RESTARTS   AGE
qtodo-manual-run-p46f7-qtodo-build-artifact-pod         0/1     Completed   0          10m
qtodo-manual-run-p46f7-qtodo-build-image-pod            0/1     Completed   0          7m21s
qtodo-manual-run-p46f7-qtodo-clone-repository-pod       0/1     Completed   0          10m
qtodo-manual-run-p46f7-qtodo-generate-sbom-pod          0/1     Completed   0          6m30s
qtodo-manual-run-p46f7-qtodo-sbom-attestation-pod       0/1     Completed   0          6m7s
qtodo-manual-run-p46f7-qtodo-sign-artifact-pod          0/1     Completed   0          7m42s
qtodo-manual-run-p46f7-qtodo-sign-image-pod             0/1     Completed   0          6m30s
qtodo-manual-run-p46f7-qtodo-upload-sbom-pod            0/1     Completed   0          6m7s
qtodo-manual-run-p46f7-qtodo-verify-artifact-pod        0/1     Completed   0          7m31s
qtodo-manual-run-p46f7-qtodo-verify-image-pod           0/1     Completed   0          5m48s
```

If we want to see the output of a particular step, we can view this information in the pod logs. For example, let's look at the image verification messages:

```shell
oc logs -n layered-zero-trust-hub qtodo-manual-run-p46f7-qtodo-verify-image-pod

Success: true
Result: SUCCESS
Violations: 0, Warnings: 0, Successes: 3
Component: Unnamed
ImageRef: quay-registry-quay-quay-enterprise.apps.example.com/ztvp/qtodo@sha256:df6506e93a141cfcaeb3b4686b558cddd963410a146b10c3cbd1319122f5f880

Results:
✓ [Success] builtin.attestation.signature_check
  ImageRef: quay-registry-quay-quay-enterprise.apps.example.com/ztvp/qtodo@sha256:df6506e93a141cfcaeb3b4686b558cddd963410a146b10c3cbd1319122f5f880

✓ [Success] builtin.attestation.syntax_check
  ImageRef: quay-registry-quay-quay-enterprise.apps.example.com/ztvp/qtodo@sha256:df6506e93a141cfcaeb3b4686b558cddd963410a146b10c3cbd1319122f5f880

✓ [Success] builtin.image.signature_check
  ImageRef: quay-registry-quay-quay-enterprise.apps.example.com/ztvp/qtodo@sha256:df6506e93a141cfcaeb3b4686b558cddd963410a146b10c3cbd1319122f5f880
```

#### Review the services

The results of our supply chain are also visible in the different services we have used during the build process.

##### Quay

If we used Quay as image registry, we can review the built image inside.

The credentials to access the Quay web interface can be obtained as follows:

* Quay URL

    ```shell
    echo "https://$(oc get route -n quay-enterprise \
        -l quay-component=quay-app-route \
        -o jsonpath='{.items[0].spec.host}')"
    ```

* Quay username: The same one you specified in `values-hub.yaml` or **quay-user**.
* Quay password:

    ```shell
    oc get secret -n layered-zero-trust-hub qtodo-quay-password -o json | jq '.data["password"] | @base64d'
    ```

Now that we have the credentials, we can check the content in Quay.

1. Launch the Quay Web UI.
2. Log in to the system.
3. Locate and select the **ztvp/qtodo** repository.
4. In the left menu, select **Tags**.
5. Along to the image's latest tag, we can see the indication that it is signed (the shield)
6. We can also see the image attestation (the `.att` file).

![Quay Web UI](./images/quay-web-ui.png)

##### Rekor

You can check the verification records by using the Rekor search UI in your web browser. You can search records by email address or record index. The URL for the Rekor Search UI can be obtained with this command:

```shell
echo "https://$(oc get route -n trusted-artifact-signer -l app.kubernetes.io/component=rekor-ui -o jsonpath='{.items[0].spec.host}')"
```

![Rekor's Search UI](./images/rekor-web-ui.png)

##### RHTPA

The RHTPA web UI uses OIDC for user authentication. If you are using the **Keycloak** integrated with our pattern, use the following commands to obtain the credentials:

* RHTPA URL

    ```shell
    echo "https://$(oc get route -n trusted-profile-analyzer \
        -l app.kubernetes.io/name=server \
        -o jsonpath='{.items[0].spec.host}')"
    ```

* RHTPA user: **rhtpa-user**
* RHTPA user password

    ```shell
    oc get secret keycloak-users -n keycloak-system -o json \
        | jq '.data["rhtpa-user-password"] | @base64d'
    ```

To review our SBOM within the RHTPA web UI:

1. Launch the RHTPA Web UI
2. Log in with Keycloak and the RHTPA credentials.
3. Navigate to the **SBOMs** section via the left-hand menu
4. Select the entry corresponding to the name of the container image from the list of available SBOMs.

![RHTPA Web UI](./images/rhtpa-web-ui.png)
