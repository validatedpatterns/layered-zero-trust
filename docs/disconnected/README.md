# Disconnected Deployment

This guide covers the steps required to deploy the Layered Zero Trust Validated Pattern
in an environment without direct internet access.

Three categories of external sources must be mirrored to internal infrastructure before
the pattern can deploy successfully:

| Source type | External location | Internal replacement |
| --- | --- | --- |
| Container images | `registry.redhat.io`, `quay.io`, `ghcr.io`, etc. | Internal OCI registry |
| Helm charts | `https://charts.validatedpatterns.io/`, `oci://quay.io/validatedpatterns` | Internal OCI registry |
| Git repository | `https://github.com/validatedpatterns/layered-zero-trust.git` | Internal Git server |

## Prerequisites

### Disk space

Mirroring all content listed in `docs/disconnected/mirror/*-imageset-config.yaml`
requires approximately **110 GB** of storage on the mirror registry host:

```text
Filesystem                                      Size  Used Avail Use% Mounted on
/dev/mapper/os--registry-registry               284G  106G  179G  38% /var/lib/registry
```

### Required tools

The following tools must be available on the machine used for mirroring:

- `oc` - OpenShift CLI with the `oc mirror` v2 plugin
- `skopeo` - for individual image copies if needed (optional)
- Access to both the internet-connected source and the internal OCI registry/Git server

### OpenShift

Deploying the ZTVP requires a installed OpenShift cluster.

If you are going to use an internal PKI, with certificates issued for the OCI
registry or the Git server, remember to import the certificates beforehand.

With the following commands we can import the digital certificates used by the
OCI registry or the Git server:

```shell
oc create configmap internal-registry-ca -n openshift-config \
    --from-file=registry.internal.example.com=/etc/pki/ca-trust/source/anchors/example-ca.pem

# This adds the internal CA as trusted for downloading images from the internal OCI registry
oc patch image.config.openshift.io/cluster --type=merge \
    -p '{"spec":{"additionalTrustedCA":{"name":"internal-registry-ca"}}}'

oc create configmap internal-ca -n openshift-config \
    --from-file=ca-bundle.crt=/etc/pki/ca-trust/source/anchors/example-ca.pem

# This configures the internal CA as trusted for HTTPS connections
# Communication with the Git server is done via HTTPS
oc patch proxy cluster --type=merge \
    -p '{"spec":{"trustedCA":{"name":"internal-ca"}}}'
```

## 1. Mirror Container Images and Helm Charts (OCI)

Validated Patterns externalized Helm charts are published as OCI artifacts on
`quay.io/validatedpatterns`. Mirror them together with workload container images
using `oc mirror` v2.

Image set configurations are split into four files under [mirror/](mirror/):

| File | Content |
| --- | --- |
| [releases-imageset-config.yaml](mirror/releases-imageset-config.yaml) | OpenShift release images |
| [operators-imageset-config.yaml](mirror/operators-imageset-config.yaml) | Operator catalogs and operator images |
| [images-imageset-config.yaml](mirror/images-imageset-config.yaml) | Workload images and Validated Patterns Helm chart OCI artifacts |
| [unsigned-imageset-config.yaml](mirror/unsigned-imageset-config.yaml) | Images without available signatures (e.g. HashiCorp Vault) |

> [!TIP]
> If we wanted to generate the configuration for a cluster with ZTVP already installed, to replicate it later, we could use the script `gen-imageset-config.py`
>
> ```shell
> python3 scripts/gen-imageset-config.py --prefix docs/disconnected/mirror/
> ```

Copy or reference these files from your working directory. The examples below assume
configs live in `~/ztvp/` and use a local workspace under `mirror/` for each stage.

Set your internal registry hostname:

```shell
REGISTRY="registry.internal.example.com"
CONFIG_DIR="${HOME}/ztvp"
```

### Mirror each stage to the internal registry

Create workspace directories and mirror each configuration separately. Use
`--remove-signatures=false` for signed content. Use `--remove-signatures=true` only
for the unsigned imageset (partner images without sigstore attachments).

```shell
mkdir -p ${CONFIG_DIR}/mirror/{releases,operators,images,unsigned}

rm -Rf mirror/releases/*
oc mirror --v2 -c "${CONFIG_DIR}/releases-imageset-config.yaml" \
  "docker://${REGISTRY}" \
  --remove-signatures=false \
  --workspace file://mirror/releases

rm -Rf mirror/operators/*
oc mirror --v2 -c "${CONFIG_DIR}/operators-imageset-config.yaml" \
  "docker://${REGISTRY}" \
  --remove-signatures=false \
  --workspace file://mirror/operators

rm -Rf mirror/images/*
oc mirror --v2 -c "${CONFIG_DIR}/images-imageset-config.yaml" \
  "docker://${REGISTRY}" \
  --remove-signatures=false \
  --workspace file://mirror/images

rm -Rf mirror/unsigned/*
oc mirror --v2 -c "${CONFIG_DIR}/unsigned-imageset-config.yaml" \
  "docker://${REGISTRY}" \
  --remove-signatures=true \
  --workspace file://mirror/unsigned
```

### Apply mirror configuration to the cluster

After mirroring, apply the generated `ImageDigestMirrorSet` and `ImageTagMirrorSet`
resources so the cluster resolves images from the internal registry:

```shell
oc apply -f mirror/releases/working-dir/cluster-resources
oc apply -f mirror/operators/working-dir/cluster-resources
oc apply -f mirror/images/working-dir/cluster-resources/

# Unsigned images need a distinct ITMS name to avoid conflicting with the signed set
sed -i 's/itms-generic-0/itms-unsigned-0/g' \
  mirror/unsigned/working-dir/cluster-resources/itms-oc-mirror.yaml
oc apply -f mirror/unsigned/working-dir/cluster-resources/
```

## 2. Mirror the Git Repository

Argo CD Applications in this pattern reference
`https://github.com/validatedpatterns/layered-zero-trust.git` at branch `main`.
Mirror the repository to an internal Git server (Gitlab, Gitea, etc.)
and keep it in sync.

### One-time mirror

```shell
git clone --mirror https://github.com/validatedpatterns/layered-zero-trust.git
cd layered-zero-trust.git
git remote set-url --push origin https://git.internal.example.com/layered-zero-trust.git
git push --mirror
```

### Point the pattern to the internal Git server

The Validated Patterns framework uses the value of the Git remote `origin` to configure
the repository URL in the `patterns-operator`. If we followed the instructions in the
previous step, this value should be correct. The Pattern CR (`gitSpec.repoURL`) controls
the Git source for the Argo CD application `layered-zero-trust-hub`.

If we need edit it after bootstrap, we can patch the deployed pattern CR:

```shell
oc patch pattern layered-zero-trust -n patterns-operator \
  --type=merge \
  -p '{"spec":{"gitSpec":{"repoURL":"https://git.internal.example.com/layered-zero-trust.git"}}}'
```

In our Git server configuration, authentication is not enabled. There are no secrets in
the repository, which simplifies the setup.

## 3. Point the Pattern to the Internal Registry

### 3.1 Configure the pattern for disconnected use

Update the file `values-global.yaml` with the pattern values files to reference
the mirrored catalog sources and the internal Helm chart registry. The values of
`patternsOperator.source` and `gitops.operatorSource` can be obtained from the
files used for mirroring.

```yaml
main:
  multiSourceConfig:
    enabled: true
    clusterGroupChartVersion: "0.9.*"
    helmRepoUrl: "oci://registry.internal.example.com/validatedpatterns"
  patternsOperator:
    source: cs-community-operator-index-v4-22
  gitops:
    operatorSource: cs-redhat-operator-index-v4-22
```

Update the `rhbk` subchart dependency in `charts/rh-keycloak/Chart.yaml`,
point its repository to the same internal OCI registry:

```yaml
dependencies:
  - name: rhbk
    version: ">=0.1.0"
    repository: "oci://registry.internal.example.com/validatedpatterns"
```

In the `values-hub.yaml` file, configure operator sources to use the internal sources:

```shell
sed -i 's/source: redhat-operators/source: cs-redhat-operator-index-v4-22/g' values-hub.yaml
```

Commit and push these changes to the disconnected Git server.

## 4. Deploy the Pattern

The following steps must be performed from a machine that has access to the
disconnected cluster and the Git repository.

Set `PATTERN_DISCONNECTED_HOME` to the OCI registry prefix that hosts the mirrored
bootstrap chart and utility container. The `pattern.sh` script uses this variable to
override both automatically:

```shell
export PATTERN_DISCONNECTED_HOME="registry.internal.example.com/validatedpatterns"
./pattern.sh make install
```

This causes the installer to use:

- `PATTERN_UTILITY_CONTAINER` -> `${PATTERN_DISCONNECTED_HOME}/utility-container`
- `PATTERN_INSTALL_CHART` -> `oci://${PATTERN_DISCONNECTED_HOME}/pattern-install`

Make sure the `utility-container` and `pattern-install` images/charts are also pushed
to the internal registry before running the install.
