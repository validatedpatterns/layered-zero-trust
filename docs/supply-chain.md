# Secure Supply Chain

This use case outlines the process of building, signing, and verifying artifacts and images within the Zero Trust Validated Pattern (ZTVP).

In this project, we used the [qtodo](https://github.com/validatedpatterns-demos/qtodo/) application as a sample to show how to build a secure supply chain in a software development factory.

> [!IMPORTANT]
> The Secure Supply Chain use case depends on **optional components** that are disabled by default. Before following this guide, uncomment the following sections in `values-hub.yaml` and redeploy the pattern with `./pattern.sh make install`:
>
> * `subscriptions.openshift-pipelines` — Red Hat OpenShift Pipelines operator
> * `namespaces` entry for `openshift-pipelines`
> * `applications.supply-chain` — the supply chain Tekton pipeline
> * `applications.trusted-artifact-signer` — RHTAS for artifact and image signing
> * `subscriptions.rhtas-operator` and its namespace entry
> * `applications.trusted-profile-analyzer` — RHTPA for SBOM management
> * `subscriptions.rhtpa-operator` and its namespace entry
> * `applications.quay-registry` — Quay image registry (or configure an external registry)
> * `applications.noobaa-mcg` — NooBaa MCG object storage (required by Quay and RHTPA)
> * `subscriptions.odf` and `subscriptions.quay-operator` and their namespace entries
>
> Additionally, uncomment the following Vault JWT roles in `overrides/values-vault-jwt.yaml` so that RHTPA and the pipeline ServiceAccount can authenticate to Vault via SPIFFE:
>
> * `rhtpa` role — allows RHTPA to read its OIDC credentials from Vault
> * `supply-chain` role — allows the Tekton pipeline ServiceAccount to read git credentials, registry credentials, and RHTPA OIDC secrets from Vault
>
> If you prefer to use an external image registry instead of Quay, skip the Quay and NooBaa sections and set the registry parameters in the `supply-chain` application overrides accordingly.

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

### Enabling this Use Case

To configure the appropriate values in the [values-hub.yaml](../values-hub.yaml) file, we can be use the [gen-feature-variants script](../scripts/gen-feature-variants.md).

For the Secure Supply Chain use case, the command would be:

```shell
python3 scripts/gen-feature-variants.py --base values-hub.yaml --features supply-chain --registry-option <id>
```

If the source repository is **private** (protected), add the `protected-repos` feature:

```shell
python3 scripts/gen-feature-variants.py --base values-hub.yaml --features supply-chain,protected-repos --registry-option <id>
```

Where `<id>` is one of the options available in _Bring Your Own (BYO) Container Registry_:

1. Embedded Quay Registry
2. External Registry
3. Embedded Internal Registry

## Bring Your Own (BYO) Container Registry

By default, ZTVP deploys a built-in Red Hat Quay registry. However, you can use your own container registry (e.g., quay.io, Docker Hub, GitHub Container Registry, or a private registry) instead.

### Configuration Steps

1. **Disable built-in Quay registry** (optional - if not using Quay): Comment out the Quay-related applications in `values-hub.yaml`: `quay-enterprise` namespace, `quay-operator` subscription, and `quay-registry` application. Remove the `applications.supply-chain.overrides.quay.enabled` and `applications.supply-chain.overrides.registry.tlsVerify` settings.

2. **Configure registry credentials in Vault** (**BYO registry only**): Per VP rule, add your registry credentials to `~/values-secrets.yaml` (or `~/values-secret.yaml` / `~/values-secret-layered-zero-trust.yaml` per VP lookup order):

   ```bash
   # Copy template to local file if not already done
   cp values-secret.yaml.template ~/values-secrets.yaml
   ```

   Uncomment the `registry-user` secret and replace the placeholder with your registry token or password:

   Store your registry token in a local file:

   ```shell
   mkdir -p ~/.config/validated-patterns
   echo -n "your-registry-token" > ~/.config/validated-patterns/registry-token
   ```

   ```yaml
   - name: registry-user
     vaultPrefixes:
       - hub/infra/registry
     fields:
       - name: registry-password
         path: ~/.config/validated-patterns/registry-token
         onMissingValue: error
   ```

   > **Note**: This secret is only required for **BYO/external registries** (Option 2). **Built-in Quay** (Option 1) uses the auto-generated `quay-users` secret. **Embedded OpenShift registry** (Option 3) does not need a manual secret when the automatic token refresher is enabled (see [Embedded OpenShift Registry](#embedded-openshift-registry)) -- the refresher creates and rotates the Vault credential automatically.
   >
   > **Note**: Never commit `~/values-secrets.yaml` (or your local values-secret file) to git. This file contains sensitive credentials and should remain local.

3. **Set the global registry configuration in values-hub.yaml**: Uncomment the matching `global.registry` block at the top of `values-hub.yaml`. All registry credentials are defined once here; both the `supply-chain` and `qtodo` charts inherit them automatically.

   ```yaml
   # Example: BYO/External Registry (Option 2)
   global:
     registry:
       enabled: true
       domain: quay.io
       repository: your-org/qtodo
       user: your-username
       vaultPath: "secret/data/hub/infra/registry/registry-user"
       passwordVaultKey: "registry-password"
   ```

   See the **Registry Options** section at the top of `values-hub.yaml` for the full set of option blocks (built-in Quay, BYO, embedded OpenShift).

4. **Enable supply-chain-specific overrides** (if needed): The `supply-chain` application may need additional overrides depending on the registry type. These are set in the `supply-chain` overrides section of `values-hub.yaml`:
   * **Built-in Quay**: Enable `quay.enabled` (Quay user provisioner CronJob) and `registry.tlsVerify: "false"` (self-signed certs).
   * **Embedded OpenShift**: Enable `registry.embeddedOpenShift.ensureImageNamespaceRBAC` (creates image namespace and push RBAC) and optionally `registry.embeddedOpenShift.tokenRefresher.enabled` (see [Embedded OpenShift Registry](#embedded-openshift-registry)).
   * **BYO/External**: No extra overrides needed.

   > **Note**: The qtodo chart automatically derives its image from `global.registry.domain` and `global.registry.repository` when `global.registry.enabled=true`. No per-app image override is needed.

### Required Configuration

These parameters are set in the `global.registry` block at the top of `values-hub.yaml`:

| Parameter                          | Description                          | Example                                        |
| ---------------------------------- | ------------------------------------ | ---------------------------------------------- |
| `global.registry.enabled`          | Enable registry auth secret creation | `true`                                         |
| `global.registry.domain`           | Registry hostname (REQUIRED)         | `quay.io`, `ghcr.io`, `registry.example.com`   |
| `global.registry.repository`       | Repository path (org/image)          | `ztvp/qtodo`, `my-org/my-app`                  |
| `global.registry.user`             | Registry username                    | `my-robot-account`                             |
| `global.registry.vaultPath`        | Vault path for registry password     | `secret/data/hub/infra/registry/registry-user` |
| `global.registry.passwordVaultKey` | Key within the Vault secret          | `registry-password`                            |

> **Note**: All registry types (built-in Quay, BYO, embedded OpenShift) use the same `global.registry` parameters. Both the `supply-chain` and `qtodo` charts fall back to these values when their local registry values are empty. See the Vault Paths table below for scenario-specific values.

### Vault Paths

Registry credentials are stored at different paths based on registry type:

| Registry Type | Vault Path                                     | Password Key         |
| ------------- | ---------------------------------------------- | -------------------- |
| Built-in Quay | `secret/data/hub/infra/quay/quay-users`        | `quay-user-password` |
| BYO Registry  | `secret/data/hub/infra/registry/registry-user` | `registry-password`  |
| Embedded OpenShift | `secret/data/hub/infra/registry/registry-user` | `registry-password`  |

Set `global.registry.vaultPath` and `global.registry.passwordVaultKey` in the `global.registry` block to match your scenario. When `global.registry.enabled` is false or unset (default), no registry auth secret is created (fresh install state).

The Vault policy `hub-supply-chain-jwt-secret` grants read access to both paths for the pipeline service account. For the embedded OpenShift registry, the policy also grants `create` and `update` capabilities on the registry path so the automatic token refresher can write fresh tokens back to Vault.

### Embedded OpenShift Registry

To use the in-cluster OpenShift image registry instead of an external registry:

1. **Uncomment the Option 3 `global.registry` block** in `values-hub.yaml` so `global.registry` points at the embedded registry (domain, repository, vault paths). Use `user: _token` when using automatic token refresh (bearer tokens; the username is not significant to the registry).

   ```yaml
   global:
     registry:
       enabled: true
       domain: default-route-openshift-image-registry.apps.{{ .Values.global.clusterDomain }}
       repository: ztvp/qtodo
       user: _token
       vaultPath: "secret/data/hub/infra/registry/registry-user"
       passwordVaultKey: "registry-password"
   ```

2. **Enable `registry.embeddedOpenShift.ensureImageNamespaceRBAC`** in the supply-chain overrides. The chart will automatically:
   * Create the image namespace from the first component of `global.registry.repository` (e.g. `ztvp` from `ztvp/qtodo`)
   * Grant the pipeline ServiceAccount `system:image-builder` in that namespace
   * Enable the default route on the image registry (via a one-time Job)

3. **Confirm the registry domain** is `default-route-openshift-image-registry.apps.<clusterDomain>` (set in `global.registry.domain` above).

4. **Enable automatic token refresh** (recommended): Set `registry.embeddedOpenShift.tokenRefresher.enabled` to `true`. This deploys:
   * A **CronJob** (`registry-token-refresher`) that runs every 6 hours. It uses a SPIFFE JWT to authenticate to Vault, creates a fresh `pipeline` ServiceAccount token via the Kubernetes TokenRequest API, and writes it to Vault.
   * A one-shot **Sync hook Job** (`registry-token-refresher-seed`) that seeds the initial token on first deploy so the pipeline is ready immediately.

   When the token refresher is enabled, you do **not** need to manually store a token in `~/values-secrets.yaml` for the embedded OpenShift registry. The refresher handles credential lifecycle automatically.

   If you prefer manual token management instead, disable the token refresher and store the output of `oc whoami -t` as the `registry-password` value in `~/values-secrets.yaml`.

Example `supply-chain` application overrides for embedded OpenShift (registry host, repository, and Vault paths are normally taken from the `global.registry` block):

```yaml
overrides:
  - name: registry.embeddedOpenShift.ensureImageNamespaceRBAC
    value: "true"
  - name: registry.embeddedOpenShift.tokenRefresher.enabled
    value: "true"
```

### Node-Level Image Pull Trust

When using a registry behind the cluster ingress (Option 1: Built-in Quay or Option 3: Embedded OpenShift Registry), kubelet cannot pull images by default because the ingress certificate is self-signed and not trusted at the node level.

The `ztvp-certificates` application handles this by patching `image.config.openshift.io/cluster` with the ingress CA certificate for the configured registry hostnames. Enable it by uncommenting the `imagePullTrust` overrides in `values-hub.yaml`:

```yaml
# ztvp-certificates overrides
- name: imagePullTrust.enabled
  value: "true"
- name: imagePullTrust.registries[0]
  value: <registry-hostname>
```

Set `<registry-hostname>` to match your registry option:

| Option                  | Registry Hostname                                             |
| ----------------------- | ------------------------------------------------------------- |
| Option 1: Built-in Quay | `quay-registry-quay-quay-enterprise.apps.<clusterDomain>`     |
| Option 3: Embedded OpenShift  | `default-route-openshift-image-registry.apps.<clusterDomain>` |

> **Note**: Option 2 (BYO/External Registry) does not require `imagePullTrust` because external registries like quay.io and ghcr.io use publicly trusted certificates.

### ArgoCD PVC Health Check

The supply-chain chart creates a `PersistentVolumeClaim` (`qtodo-workspace-source`) for the pipeline workspace. Depending on the storage class, this PVC may remain in `Pending` state until a pod is scheduled -- which is expected behavior, but ArgoCD reports it as `Progressing`, preventing the application from reaching `Healthy` status.

A custom `resourceHealthChecks` entry in `values-hub.yaml` teaches ArgoCD to treat `Pending` PVCs as `Healthy`:

```yaml
resourceHealthChecks:
  - kind: PersistentVolumeClaim
    check: |
      hs = {}
      if obj.status ~= nil and obj.status.phase ~= nil then
        if obj.status.phase == "Bound" then
          hs.status = "Healthy"
          hs.message = "PVC is bound"
        elseif obj.status.phase == "Pending" then
          hs.status = "Healthy"
          hs.message = "PVC is pending"
        else
          hs.status = "Progressing"
          hs.message = "Waiting for PVC"
        end
      else
        hs.status = "Progressing"
        hs.message = "Waiting for PVC status"
      end
      return hs
```

## Automated Secure Supply Chain Pipeline

To build and certify the application, we will use _Red Hat OpenShift Pipelines_.

ZTVP creates a `Pipeline` in our cluster called **qtodo-supply-chain** that orchestrates the various tasks necessary to build the application from its source code, generate a container image, and publish the resulting image to the defined OCI registry. Within the pipeline, an SBOM containing the build's contents will be generated, binaries and the build attestation will be signed, and the validity of those signatures will be verified.

### How to run the pipeline

Once the supply-chain application has synced in ArgoCD, start the pipeline using one of the methods below.

#### Using OpenShift Web Console

1. Launch the OpenShift Web console.
2. Select **Pipelines -> Pipelines** from the left hand navigation bar.
3. Locate the **qtodo-supply-chain** pipeline. It's within the **layered-zero-trust-hub** project.
4. In the kebab menu (three vertical dots) from the right-hand, select **Start**.

   Review the configurable parameters. Most parameters should be correct with their default values if we are in single-cluster mode. But, double-check their values just in case.

   At the bottom we have the **workspaces**. These must be configured manually.
   * For **qtodo-source**, select `PersistentVolumeClaim` and the PVC name is `qtodo-workspace-source`.
   * For **registry-auth-config**, select `Secret` and the name of the secret is `qtodo-registry-auth`.
   * For **git-auth**, the binding depends on the authentication mode (see [How it works](#how-it-works) for details):
     * **HTTPS mode**: select `Secret` and the name of the secret is `qtodo-git-credentials`. The `git-clone` ClusterTask's `basic-auth` workspace requires the secret to be provided explicitly; ServiceAccount-level credential injection alone is not sufficient for HTTPS.
     * **SSH mode**: leave **git-auth** unbound (empty). SSH credentials are injected automatically via the `pipeline` ServiceAccount. Binding the workspace directly causes the `git-clone` ClusterTask's `prepare.sh` to run a recursive `chmod` on the copied secret volume, which fails on the read-only Kubernetes projected volume symlinks.
   * For **ssl-ca-directory** (HTTPS mode with internal Git hosts only): if `git.sslCABundle.enabled` is `true`, select `ConfigMap` and the name is `ztvp-trusted-ca`. This is only needed when cloning over HTTPS from a Git server behind a corporate or self-signed CA (see [Corporate CA Trust for Internal Git Hosts](#corporate-ca-trust-for-internal-git-hosts)).

5. Press **Start** to finish and run the pipeline.

#### Using CLI

We can also start a pipeline execution using a CLI and the Kubernetes API. We start creating a new `PipelineRun` resource referencing the `qtodo-supply-chain` pipeline. Let's create a new file called `qtodo-pipeline.yaml` and copy this content.

**HTTPS mode** (bind `git-auth` to the `qtodo-git-credentials` secret):

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
    - name: git-auth
      secret:
        secretName: qtodo-git-credentials
    # Add this workspace when git.sslCABundle.enabled is true (internal Git hosts):
    # - name: ssl-ca-directory
    #   configMap:
    #     name: ztvp-trusted-ca
```

**SSH mode** (leave `git-auth` unbound):

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

> **Note**: The `git-auth` workspace binding differs between authentication modes. In **HTTPS mode**, the `qtodo-git-credentials` secret must be bound explicitly -- ServiceAccount-level credential injection alone is not sufficient for the `git-clone` ClusterTask's `basic-auth` workspace. In **SSH mode**, the workspace must be left **unbound**; SSH credentials are injected automatically through the `pipeline` ServiceAccount. Binding the `git-auth` workspace in SSH mode causes the `git-clone` ClusterTask's `prepare.sh` to run a recursive `chmod` on the copied secret volume, which fails on the read-only Kubernetes projected volume symlinks.

Using the previously created definition, start a new execution of the pipeline using `oc` CLI:

```shell
oc create -f qtodo-pipeline.yaml
```

You can review the current pipeline logs using the [Tekton CLI](https://tekton.dev/docs/cli/).

```shell
tkn pipeline logs -n layered-zero-trust-hub -L -f
```

Or use `oc` commands to monitor progress:

```shell
# List pipeline runs
oc get pipelinerun -n layered-zero-trust-hub

# Check task status for a specific run
oc get taskruns -n layered-zero-trust-hub -l tekton.dev/pipelineRun=<pipelinerun-name>

# View logs for a specific task
oc logs -n layered-zero-trust-hub -l tekton.dev/pipelineRun=<pipelinerun-name>,tekton.dev/pipelineTask=<task-name>
```

### Protected Repositories

By default the pipeline clones the qtodo source from a **public** GitHub repository. If your source code lives in a private (protected) repository, enable the Git credentials feature so the `git-clone` task can authenticate.

Two authentication modes are supported:

| Mode | URL format | Vault fields | Secret type |
| ----- | ------------------------------------ | ----------------------------------- | ---------------------- |
| HTTPS | `https://github.com/org/repo.git` | `username` + `password` (PAT) | Opaque (basic-auth) |
| SSH | `git@github.com:org/repo.git` | `ssh-privatekey` + `known_hosts` | kubernetes.io/ssh-auth |

When using the `gen-feature-variants.py` script with `--git-repo`, the auth mode is auto-detected from the URL scheme.

#### 1. Store Git credentials in Vault

Uncomment the `git-credentials` secret in your local `~/values-secret.yaml` (copied from `values-secret.yaml.template`). Choose **one** of the two options:

**Option A -- HTTPS basic auth** (username + Personal Access Token):

Store your credentials in local files to avoid plaintext in YAML:

```shell
mkdir -p ~/.config/validated-patterns
echo -n "your-git-username" > ~/.config/validated-patterns/git-username
echo -n "your-personal-access-token" > ~/.config/validated-patterns/git-token
```

```yaml
- name: git-credentials
  vaultPrefixes:
  - hub/supply-chain
  fields:
  - name: username
    path: ~/.config/validated-patterns/git-username
    onMissingValue: error
  - name: password
    path: ~/.config/validated-patterns/git-token
    onMissingValue: error
```

**Option B -- SSH key auth**:

```yaml
- name: git-credentials
  vaultPrefixes:
  - hub/supply-chain
  fields:
  - name: ssh-privatekey
    path: ~/.ssh/id_ed25519_ztvp   # or id_rsa, id_ecdsa, etc.
  - name: known_hosts
    path: ~/.ssh/known_hosts_github
```

Generate a passwordless SSH key pair (if you don't already have one):

```shell
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_ztvp -N ""
```

The key **must not** be password-protected -- Tekton cannot prompt for a passphrase at runtime.

Generate the `known_hosts` file for your Git host:

```shell
ssh-keyscan github.com > ~/.ssh/known_hosts_github
```

Then load the secret into Vault: `./pattern.sh make load-secrets`.

#### 2. Enable Git credentials in the supply-chain overrides

**Preferred: use the generator.** Add `protected-repos` to the features list and provide your private repository URL with `--git-repo`. The generator auto-detects the auth mode and sets all overrides (host, authType, repository) automatically:

```shell
# HTTPS
python3 scripts/gen-feature-variants.py \
  --features supply-chain,protected-repos \
  --registry-option <id> \
  --git-repo https://github.com/your-org/qtodo.git

# SSH
python3 scripts/gen-feature-variants.py \
  --features supply-chain,protected-repos \
  --registry-option <id> \
  --git-repo git@github.com:your-org/qtodo.git
```

**Manual configuration.** Add the following overrides to the `supply-chain` application in `values-hub.yaml`:

```yaml
- name: git.credentials.enabled
  value: "true"
- name: git.credentials.authType
  value: "https"                    # or "ssh"
- name: git.credentials.host
  value: "https://github.com"      # SSH: "github.com" (no scheme)
- name: git.credentials.vaultPath
  value: "secret/data/hub/supply-chain/git-credentials"
```

#### 3. Point the pipeline at your private repository

When using the generator with `--git-repo`, the `qtodo.repository` override is set automatically in the generated `values-hub.yaml`. If you are configuring manually, add this override to the `supply-chain` application:

```yaml
- name: qtodo.repository
  value: "https://github.com/your-org/qtodo.git"   # or SSH URL (git@github.com:your-org/qtodo.git)
```

#### How it works

When `git.credentials.enabled` is `true`:

* An `ExternalSecret` (`qtodo-git-credentials`) pulls the credentials from Vault and creates a secret annotated with `tekton.dev/git-0` pointing to the configured host.
  * **HTTPS mode**: creates an `Opaque` secret with `.git-credentials` and `.gitconfig` files.
  * **SSH mode**: creates a `kubernetes.io/ssh-auth` secret with `ssh-privatekey` and `known_hosts` entries.
* The `pipeline` ServiceAccount lists the secret (see `pipeline-sa.yaml`). Tekton's credential initialization automatically injects the credentials into task containers -- `.gitconfig` and `.git-credentials` for HTTPS, or `~/.ssh/config`, `~/.ssh/id_*`, and `~/.ssh/known_hosts` for SSH.
* The `git-auth` workspace is declared in the pipeline as `optional: true`. How it should be bound depends on the authentication mode:
  * **HTTPS mode**: the `git-auth` workspace **must** be bound to the `qtodo-git-credentials` secret. ServiceAccount-level credential injection alone is not sufficient -- without an explicit workspace binding, the `git-clone` ClusterTask cannot access the protected repository.
  * **SSH mode**: the `git-auth` workspace must be left **unbound**. SSH credentials are injected automatically via the ServiceAccount. Binding the workspace triggers the `git-clone` ClusterTask's `prepare.sh`, which runs a recursive `chmod` on the copied secret volume; this fails on the read-only Kubernetes projected volume symlinks and aborts the step.
* The Vault policy `hub-supply-chain-jwt-secret` grants read access to `secret/data/hub/supply-chain/*` for the pipeline's SPIFFE identity.

> [!NOTE]
> If your internal Git server also uses a corporate or self-signed CA, see [Corporate CA Trust for Internal Git Hosts](#corporate-ca-trust-for-internal-git-hosts) to configure TLS trust.

### Corporate CA Trust for Internal Git Hosts

This section applies whenever the pipeline clones from a Git server whose TLS certificate is signed by a corporate or self-signed CA, regardless of whether the repository is private. It is only relevant for HTTPS clones; SSH connections do not use TLS certificate verification.

> [!NOTE]
> Public Git hosts (github.com, gitlab.com) use publicly trusted certificates and do not require this. If the repository is also private, combine these settings with the [Protected Repositories](#protected-repositories) configuration above.

When a repository is hosted on an internal Git server (e.g. GitLab behind a corporate CA), the `git-clone` task will fail with `SSL certificate problem: self-signed certificate in certificate chain` because the pod does not trust the corporate CA.

The `ztvp-certificates` chart already extracts and distributes the cluster's CA bundle (ingress, service, and any custom/corporate CAs). When the `supply-chain` feature is enabled, the `ztvp-trusted-ca` ConfigMap is automatically distributed to the pipeline namespace (`layered-zero-trust-hub`) via ACM policy.

To make the `git-clone` task use this CA bundle, enable the SSL CA bundle mount in the `supply-chain` application overrides:

```yaml
- name: git.sslCABundle.enabled
  value: "true"
```

This binds the `ztvp-trusted-ca` ConfigMap as the `ssl-ca-directory` workspace on the `git-clone` task and sets the `CRT_FILENAME` parameter to `tls-ca-bundle.pem` (matching the key in the ConfigMap). The upstream `git-clone` ClusterTask uses this file to set `GIT_SSL_CAPATH`, so TLS verification succeeds against internal Git servers.

The corporate CA must be included in the `ztvp-trusted-ca` bundle. The easiest way is to use **automatic remote host extraction** -- add the Git host to `customCA.remoteHosts` in the `ztvp-certificates` overrides:

```yaml
# ztvp-certificates overrides in values-hub.yaml
- name: customCA.remoteHosts[0]
  value: "gitlab.internal.example.com"
```

The `ztvp-certificates` extraction Job will connect to the host on port 443, extract the full CA chain from the TLS handshake (no authentication needed), and merge it into the CA bundle. The CronJob keeps it fresh automatically.

Alternatively, you can provide the CA certificate manually via `customCA.secretRef` or `customCA.additionalCertificates`. See the [ztvp-certificates documentation](./ztvp-certificates.md) for details.

### Init task (pre-flight image check)

The pipeline includes an `init` task that runs before `git-clone`. It uses `skopeo inspect` to check whether the target image already exists in the registry. If the image exists (and `rebuild` is not set to `"true"`), the pipeline skips the build. This avoids unnecessary rebuilds and is modeled after the [RHTAP sample pipelines](https://github.com/konflux-ci/build-definitions).

The pipeline also emits Tekton Chains provenance results (`CHAINS-GIT_URL`, `CHAINS-GIT_COMMIT`, `IMAGE_URL`, `IMAGE_DIGEST`) so that Tekton Chains can automatically generate and sign provenance attestations.

### Pipeline tasks

The pipeline we have prepared has the following steps:

* **init**. Checks whether the target image already exists in the registry. Gates the build with a `when` condition.
* **qtodo-clone-repository**. Clones the `qtodo` repository.
* **qtodo-build-artifact**. Builds an _uber-jar_ of `qtodo` application.
* **qtodo-sign-artifact**. Signs the JAR file generated during the build process.
* **qtodo-verify-artifact**. Verifies the JAR signature generated in the previous step.
* **qtodo-build-image**. Builds a container with the `qtodo` application and upload it to an image registry.
* **qtodo-sign-image**. Signs the container image.
* **qtodo-generate-sbom**. Generates an SBOM from the image.
* **qtodo-sbom-attestation**. Creates a (signed) attestation, and attaches it to the image.
* **qtodo-upload-sbom**. Uploads the generated SBOM file to RHTPA.
* **qtodo-verify-image**. Verifies the attestation and the signature attached to the image.

**Finally task:**

* **restart-qtodo**. Runs after all tasks complete. If `qtodo-verify-image` succeeded and the `qtodo` Deployment exists, it restarts the Deployment (`oc rollout restart`) so the application picks up the newly built and signed image. If the Deployment is not yet present (e.g., the pipeline ran before the qtodo application was deployed), the task exits gracefully.

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
