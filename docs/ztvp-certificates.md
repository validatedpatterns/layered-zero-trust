# ZTVP Certificates

The [`ztvp-certificates`](../charts/ztvp-certificates/) chart manages CA certificate extraction, validation,
bundling, and distribution across the Zero Trust Validated Pattern. It runs as
an application managed by Argo CD in the `openshift-config` namespace, ensuring
certificates are available before any workload that needs TLS verification.

## Architecture

```text
 IngressControllers          Service CA           Cluster trusted-ca-bundle
 (openshift-ingress)      (openshift-config)     (openshift-config-managed)
        |                       |                          |
        +-----------+-----------+--------------------------+
                    |
         extract-certificates.sh    <-- runs as Job (initial) + CronJob (daily)
                    |
          validates & combines
                    |
                    v
        ConfigMap: ztvp-trusted-ca
           (openshift-config)
                    |
        +-----------+-----------+-----------------------+
        |                       |                       |
  ACM Policy distributes     proxyCA patches      imagePullTrust
  to target namespaces       proxy/cluster        patches image.config
   (e.g. qtodo)              (all platforms)      (when enabled)
```

### Kubernetes Resources

| Resource | Purpose |
|---|---|
| **ServiceAccount / RBAC** | Grants the extraction Job read access to secrets, configmaps, ingresscontrollers, and proxy across namespaces |
| **ConfigMap (script)** | Holds the templated `extract-certificates.sh` script |
| **Job (initial)** | Runs once at first sync to populate the CA bundle |
| **CronJob** | Runs on schedule (default daily at 02:00) for automatic rotation |
| **ACM Policy + Placement** | Distributes the `ztvp-trusted-ca` ConfigMap into target namespaces via ACM governance |
| **ManagedClusterSetBinding** | Binds the `default` ManagedClusterSet in `openshift-config` so the Placement can target `local-cluster` |

## Extraction Phases

The extraction script runs through a deterministic sequence of phases. Each
phase is independently gated by values, so the script adapts to the active
configuration.

| Phase | Gate | What It Does |
|---|---|---|
| 1 -- Custom CA | `customCA.secretRef.enabled` | Reads a user-supplied secret and writes `custom-ca.crt` |
| 2 -- Ingress CA | `autoDetect` | Loops over every `IngressController`, extracts `tls.crt` from the referenced or default router secret |
| 3 -- Service CA | `autoDetect` | Reads `openshift-service-ca.crt` ConfigMap |
| 4 -- Cluster CA Bundle | `autoDetect` | Reads `trusted-ca-bundle` from `openshift-config-managed` (present when a corporate proxy injects CAs) |
| 5 -- Additional Certs | `customCA.additionalCertificates[]` | Reads each additional secret and writes a `.crt` file |
| 6 -- Validation | `validation.enabled` | Checks minimum size and `openssl x509` parse for every `.crt` |
| 7 -- Combine | always | Concatenates all `.crt` files into `tls-ca-bundle.pem`; fails if bundle < 100 bytes |
| 8 -- ConfigMap | always | `oc apply` the `ztvp-trusted-ca` ConfigMap with annotations recording extraction metadata |
| 8.1 -- Proxy CA | `proxyCA.enabled` | Creates a separate ConfigMap with ingress + service CAs only |
| 8.2 -- Proxy Patch | `proxyCA.enabled` | Patches `proxy/cluster` to set `trustedCA` (only if not already set to another value) |
| 9 -- Image Pull Trust | `imagePullTrust.enabled` | Creates a ConfigMap keyed by registry hostname and patches `image.config.openshift.io/cluster` to set the `additionalTrustedCA` attribute. |
| 10 -- Rollout | `rollout.enabled` | Restarts Deployments/StatefulSets that consume the certificate bundle |

## Scenario Handling

### Scenario 1: Cloud Cluster with Public Certificates (Default)

Applies to AWS, Azure, GCP, and any cluster whose ingress uses certificates
signed by a public CA.

**Active settings:**

* `autoDetect: true`
* `proxyCA.enabled: true` (default -- ensures ACS Central and other workloads
  that verify TLS on routes can trust the ingress CA without per-pod volume mounts)
* `imagePullTrust.enabled: false`

**What happens:**

1. The Job auto-detects the ingress CA from each `IngressController`'s router
   secret in `openshift-ingress`.
2. The service CA is read from `openshift-service-ca.crt` from within the Job Pod.
3. If a cluster-wide proxy bundle exists, it is included.
4. All certificates are combined into `ztvp-trusted-ca` ConfigMap and distributed via
   ACM Policy to target namespaces.
5. A proxy CA ConfigMap (`ztvp-proxy-ca`) is created with ingress + service
   CAs and the `proxy/cluster` is patched so the Cluster Network Operator injects
   these CAs into all workloads automatically.

No platform override file is needed. The chart's default `values.yaml` handles
this scenario out of the box.

### Scenario 2: Bare Metal / vSphere with Self-Signed Ingress

Bare metal and vSphere clusters typically use self-signed certificates for the
default ingress. Since `proxyCA` is enabled by default (see Scenario 1), the
ingress CA is automatically injected cluster-wide. Workloads that verify TLS
on routes (e.g., ACS Central connecting to Keycloak) work without extra
configuration.

**Platform overrides:**

* `overrides/values-ztvp-certificates-BareMetal.yaml`
* `overrides/values-ztvp-certificates-VSphere.yaml`

Both contain:

```yaml
proxyCA:
  enabled: true
```

> **Note:** These overrides are now redundant because the chart default is
> `proxyCA.enabled: true`. They are retained for clarity and backward
> compatibility with older chart versions.

**Behavior is identical to Scenario 1** -- Phases 8.1 and 8.2 run by default:

1. Phase 8.1 builds a proxy-specific bundle containing only the ingress and
   service CAs (the Cluster Network Operator merges these with system CAs).
2. Phase 8.2 patches `proxy/cluster` to set `spec.trustedCA.name` to
   `ztvp-proxy-ca`.
3. The CNO propagates the merged bundle to every node, making the ingress CA
   trusted system-wide for all pods without explicit volume mounts.

### Scenario 3: Enterprise Custom CA

When the organization uses a private PKI (e.g., a corporate root CA that
signed the cluster's ingress certificate), the administrator creates a
Kubernetes secret with the CA and enables `customCA.secretRef`.

**Setup:**

```bash
oc create secret generic custom-ca-bundle \
  --from-file=ca.crt=/path/to/corporate-root-ca.crt \
  -n openshift-config
```

**values-hub.yaml overrides:**

```yaml
- name: customCA.secretRef.enabled
  value: "true"
- name: customCA.secretRef.name
  value: custom-ca-bundle
- name: customCA.secretRef.namespace
  value: openshift-config
```

**What happens:**

1. Phase 1 extracts the custom CA from the referenced secret.
2. Auto-detect (phases 2-4) still runs, so ingress and service CAs are
   included alongside the custom CA.
3. The combined bundle contains both the custom CA and the auto-detected
   certificates.

### Scenario 4: Multiple Additional CAs

When several external CAs are needed (e.g., corporate root CA, a partner CA,
and an intermediate CA), use `additionalCertificates` via the
`extraValueFiles` mechanism.

**Configuration** (`overrides/values-ztvp-certificates.yaml`):

```yaml
customCA:
  additionalCertificates:
    - name: corporate-root-ca
      secretRef:
        name: corporate-root-ca
        namespace: openshift-config
        key: ca.crt
    - name: partner-ca
      secretRef:
        name: partner-ca
        namespace: openshift-config
        key: ca.crt
```

**What happens:**

1. Phase 5 iterates over each entry and extracts the certificate from its
   secret. Missing secrets produce a warning but do not fail the job.
2. All additional certificates are combined with auto-detected and custom CAs
   in Phase 7.

### Scenario 5: Image Pull Trust for Built-In Registry

When an image registry (e.g., Quay or the embedded OpenShift registry) is
exposed behind the cluster ingress with a self-signed or internal CA, kubelet
image pulls fail with `x509: certificate signed by unknown authority`. The
`imagePullTrust` feature solves this at the node level.

**values-hub.yaml overrides:**

```yaml
- name: imagePullTrust.enabled
  value: "true"
- name: imagePullTrust.registries[0]
  value: quay-registry-quay-quay-enterprise.apps.example.com
```

**What happens:**

1. Phase 9 combines all extracted ingress CAs into a single PEM.
2. A ConfigMap (`ztvp-registry-cas`) is created in `openshift-config` with
   each registry hostname as a key and the ingress CA PEM as the value.
3. `image.config.openshift.io/cluster` is patched to set
   `additionalTrustedCA.name` to that ConfigMap.
4. The Machine Config Operator rolls the trust configuration out to all nodes.

### Scenario 6: Custom Source Locations

In non-standard environments where the ingress CA or service CA are stored in
different locations, `customSource` overrides the default auto-detection
targets.

```yaml
customSource:
  ingressCA:
    secretName: my-ingress-ca
    secretNamespace: my-namespace
    secretKey: tls.crt
  serviceCA:
    configMapName: my-service-ca
    configMapNamespace: my-namespace
    configMapKey: service-ca.crt
```

Auto-detection will read from the specified locations instead of the standard
OpenShift defaults.

## Distribution

Certificate distribution uses **ACM Governance Policies** to replicate the
`ztvp-trusted-ca` ConfigMap from `openshift-config` into each target
namespace.

```text
openshift-config/ztvp-trusted-ca  ---ACM Policy--->  qtodo/ztvp-trusted-ca
                                                      rhtpa/ztvp-trusted-ca
                                                      ...
```

The policy uses [`fromConfigMap`](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.12/html-single/governance/index#fromConfigMap-function) hub templates so that the ConfigMap data is
always sourced from the hub cluster's copy. Target namespaces are configured
via `distribution.targetNamespaces`.

**Requirements:**

* ACM (Advanced Cluster Management) must be installed
* A `ManagedClusterSetBinding` for the `default` cluster set is created
  automatically by the chart
* The `Placement` targets clusters with `local-cluster: "true"`

## Automatic Rollout

When certificates are updated, consuming workloads need to pick up the new
bundle. The chart supports three rollout strategies:

| Strategy | Behavior |
|---|---|
| `labeled` (default) | Restarts Deployments/StatefulSets matching `ztvp.io/uses-certificates: "true"` in distribution target namespaces |
| `all` | Restarts all Deployments/StatefulSets in target namespaces |
| `specific` | Restarts only the named resources listed in `rollout.targets` |

To opt a workload into automatic restart, add the label:

```yaml
metadata:
  labels:
    ztvp.io/uses-certificates: "true"
```

## Sync Wave Ordering

The chart's resources are ordered within the Argo CD sync:

| Order | Resources |
|---|---|
| 1st | ServiceAccount, RBAC (Role, RoleBinding, ClusterRole, ClusterRoleBinding) |
| 2nd | Initial Job, CronJob, ConfigMap (script) |
| 3rd | ManagedClusterSetBinding |
| 4th | ACM Policy, PlacementBinding, Placement |

The application itself is deployed early in the overall sync order (via
`values-hub.yaml`), ensuring it runs before operators and workloads that depend
on the CA bundle.

## Configuration Reference

### Top-Level Values

| Value | Default | Description |
|---|---|---|
| `enabled` | `true` | Master toggle for all chart resources |
| `autoDetect` | `true` | Auto-detect ingress, service, and cluster CAs from OpenShift |
| `configMapName` | `ztvp-trusted-ca` | Name of the output ConfigMap |
| `proxyCA.enabled` | `true` | Create a proxy CA ConfigMap and patch `proxy/cluster` |
| `imagePullTrust.enabled` | `false` | Configure node-level registry trust via `image.config` |
| `rollout.enabled` | `true` | Restart consuming workloads after certificate updates |
| `rollout.strategy` | `labeled` | One of: `labeled`, `all`, `specific` |
| `distribution.enabled` | `true` | Distribute CA bundle via ACM Policy |
| `distribution.method` | `acm-policy` | Distribution mechanism |
| `cronJob.schedule` | `0 2 * * *` | Cron schedule for automatic re-extraction |
| `validation.enabled` | `true` | Validate certificate size and format |
| `debug.verbose` | `false` | Enable `set -x` in the extraction script |

### Platform Override Files

| File | When Applied | Effect |
|---|---|---|
| `overrides/values-ztvp-certificates.yaml` | Always | Additional CAs, rollout config |
| `overrides/values-ztvp-certificates-BareMetal.yaml` | `clusterPlatform == BareMetal` | Confirms `proxyCA` (redundant; default is already `true`) |
| `overrides/values-ztvp-certificates-VSphere.yaml` | `clusterPlatform == VSphere` | Confirms `proxyCA` (redundant; default is already `true`) |
