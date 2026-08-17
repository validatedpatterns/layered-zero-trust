# Tekton Chains Configuration

Tekton Chains adds supply chain security to OpenShift Pipelines by automatically
generating signed provenance attestations for every pipeline run. In the ZTVP,
Chains is configured for **keyless signing via SPIFFE** — the Chains controller
obtains a short-lived x509 certificate from Fulcio using its SPIFFE SVID,
signs the attestation, and logs the signature to Rekor for transparency.

**Chart:** `charts/tekton-chains`  
**Namespace:** `openshift-pipelines` (via `spec.targetNamespace` in the TektonConfig CR)  
**Sync wave:** 47  
**Feature flag:** `tekton-chains` (depends on `pipelines` + `rhtas`)  
**Status:** Disabled by default — enabled via `gen-feature-variants.py` or by uncommenting in `values-hub.yaml`

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                     OpenShift Pipelines                         │
│                                                                 │
│  Pipeline Run ──▶ Chains Controller ──▶ Signed Attestation      │
│    (builds,         │        │            (in-toto SLSA)        │
│     signs,          │        │                                  │
│     deploys)        │        ▼                                  │
│                     │   OCI Registry                            │
│                     │   (attestation + signature stored         │
│                     │    alongside the container image)         │
│                     │                                           │
│                     ▼                                           │
│               ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│               │  Fulcio  │   │  Rekor   │   │   TUF    │        │
│               │ (signing │   │ (trans-  │   │ (trust   │        │
│               │  cert)   │   │  parency │   │  root)   │        │
│               └─────┬────┘   │  log)    │   └──────────┘        │
│                     │        └──────────┘                       │
│                     ▼                                           │
│               SPIRE OIDC                                        │
│               Discovery Provider                                │
│               (SVID identity)                                   │
└─────────────────────────────────────────────────────────────────┘
```

### How Keyless Signing Works

1. The Chains controller holds a SPIFFE SVID obtained via the CSI driver (`csi.spiffe.io`)
2. When a pipeline run completes, Chains generates an in-toto provenance attestation
3. Chains presents its SVID to Fulcio, which verifies it against the SPIRE OIDC Discovery Provider
4. Fulcio issues a short-lived x509 signing certificate tied to the SPIFFE identity
5. Chains signs the attestation with this certificate
6. The signature is logged to the Rekor transparency log
7. The signed attestation is pushed to the OCI registry alongside the container image

## How It Works: TektonConfig Patching

The OpenShift Pipelines operator manages a singleton `TektonConfig` CR named
`config`. The tekton-chains chart patches this CR using **Argo CD
ServerSideApply** rather than creating a separate resource, because the operator
owns the CR lifecycle.

The Argo CD sync options on the TektonConfig resource are:

- `ServerSideApply=true` — merge the Chains fields into the operator-managed CR
- `Delete=false` — Argo CD will never delete the CR (the operator owns it)
- `SkipDryRunOnMissingResource=true` — handles the case where the CRD does not yet exist

### Chains Configuration Applied

The patch sets the following in `spec.chain`:

| Parameter | Value | Purpose |
| --- | --- | --- |
| `artifacts.taskrun.format` | `in-toto` | SLSA provenance format for task runs |
| `artifacts.taskrun.storage` | `oci` | Store attestations in the OCI registry |
| `artifacts.pipelinerun.format` | `in-toto` | SLSA provenance format for pipeline runs |
| `artifacts.pipelinerun.storage` | `oci` | Store attestations in the OCI registry |
| `artifacts.pipelinerun.enable-deep-inspection` | `true` | Inspect individual task results within the pipeline |
| `artifacts.oci.storage` | `oci` | OCI artifact storage |
| `transparency.enabled` | `true` | Log signatures to Rekor |
| `transparency.url` | `https://rekor-server-trusted-artifact-signer.<domain>` | RHTAS Rekor instance |
| `signers.x509.fulcio.enabled` | `true` | Enable Fulcio-based keyless signing |
| `signers.x509.fulcio.address` | `https://fulcio-server-trusted-artifact-signer.<domain>` | RHTAS Fulcio instance |
| `signers.x509.fulcio.issuer` | `https://spire-spiffe-oidc-discovery-provider.<domain>` | SPIRE OIDC Discovery Provider |
| `signers.x509.fulcio.provider` | `spiffe` | Use SPIFFE SVIDs (not OIDC tokens) |
| `signers.x509.tuf.mirror.url` | `https://tuf-trusted-artifact-signer.<domain>` | RHTAS TUF mirror for trust root |

### Controller Deployment Overrides

The patch also uses the TektonConfig `options.deployments` mechanism to inject
volumes into the `tekton-chains-controller` pod without directly modifying the
operator-managed deployment:

| Volume | Type | Mount Path | Purpose |
| --- | --- | --- | --- |
| `spiffe-workload-api` | CSI (`csi.spiffe.io`, readOnly) | `/spiffe-workload-api` | SPIFFE SVID socket |
| `tuf` | emptyDir | `/tuf` | TUF trust root (populated at runtime) |

Environment variables set on the controller:

| Variable | Value |
| --- | --- |
| `SPIFFE_ENDPOINT_SOCKET` | `/spiffe-workload-api/spire-agent.sock` |
| `TUF_ROOT` | `/tuf` |

## SPIRE Workload Registration

The Chains controller needs a SPIFFE identity to authenticate with Fulcio.
Unlike application workloads that use `ClusterSPIFFEID` CRDs, the Chains
controller requires `ClusterStaticEntry` resources — one per cluster node —
because the standard CRD-based registration does not cover operator-managed
deployments in system namespaces.

A **PostSync Job** (`tekton-chains-spire-entries`) handles this automatically:

1. Reads the SPIRE trust domain, cluster name, and class name from the
   `spire-controller-manager` ConfigMap in `zero-trust-workload-identity-manager`
2. Enumerates all cluster nodes
3. Creates a `ClusterStaticEntry` per node:
   - **SPIFFE ID:** `spiffe://<trustDomain>/ns/openshift-pipelines/sa/tekton-chains-controller`
   - **Parent ID:** `spiffe://<trustDomain>/spire/agent/k8s_psat/<clusterName>/<nodeUID>`
   - **Selectors:** `k8s:ns:openshift-pipelines`, `k8s:sa:tekton-chains-controller`
4. Cleans up stale entries for nodes that no longer exist

The Job runs at sync wave 48 with `argocd.argoproj.io/hook: PostSync`, ensuring
the TektonConfig CR has been applied before registration begins. The
`hook-delete-policy: BeforeHookCreation` annotation ensures old Job resources
are cleaned up on re-sync.

## Pipeline Integration

The [supply-chain pipeline](supply-chain.md) emits four well-known results that
Chains uses to construct the provenance attestation:

| Result Name | Source Task | Purpose |
| --- | --- | --- |
| `CHAINS-GIT_URL` | `qtodo-clone-repository` | Source repository URL (materials) |
| `CHAINS-GIT_COMMIT` | `qtodo-clone-repository` | Source commit SHA (materials) |
| `IMAGE_URL` | `qtodo-build-image` | Built image URL (subject) |
| `IMAGE_DIGEST` | `qtodo-build-image` | Built image digest (subject) |

The `CHAINS-` prefix is a Tekton Chains convention — Chains uses these results
to populate the `materials` section of the in-toto SLSA provenance attestation.
`IMAGE_URL` and `IMAGE_DIGEST` identify the artifact the attestation describes,
so Chains pushes the attestation and signature to the same OCI repository.

## Deployment Sequence

| Order | Component | Sync Wave | What Happens |
| --- | --- | --- | --- |
| 1 | SPIRE / ZTWIM | 30 | SPIRE server, agents, and CSI driver deployed |
| 2 | RHTAS | 46 | Fulcio, Rekor, and TUF services deployed |
| 3 | OpenShift Pipelines | (subscription) | Operator installs, creates `TektonConfig` CR |
| 4 | tekton-chains | 47 | ServerSideApply patches `TektonConfig` with Chains config |
| 5 | SPIRE static entries | 48 (PostSync) | Registers the Chains controller SPIFFE identity |
| 6 | supply-chain | 48 | Pipeline, tasks, and triggers deployed |
