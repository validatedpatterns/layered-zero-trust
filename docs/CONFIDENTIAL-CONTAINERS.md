# Confidential Containers Integration

This document describes how to deploy the Layered Zero Trust Validated
Pattern with Confidential Containers (CoCo) support. CoCo extends the
pattern with hardware-rooted workload identity: SPIRE agent runs inside
a confidential VM (peer pod) and uses x509pop attestation backed by TEE
hardware attestation to KBS.

## Architecture

In a production deployment, Trustee (the attestation server) should run
on a separate trusted cluster, since it verifies the integrity of the
infrastructure where workloads run. Running it on the same cluster
means the attestation server shares the untrusted infrastructure it is
supposed to verify. A single cluster deployment is fine for development
and testing.

The SPIRE agent runs as a sidecar container inside each CoCo peer pod.
This is different from the regular ZTVP deployment where agents run as
a DaemonSet on each node. In the CoCo model, the agent must be inside
the confidential VM so that its identity is rooted in hardware
attestation. Each CoCo workload gets its own SPIRE agent instance.

The trust chain:

1. Peer pod VM created inside a TEE (AMD SEV-SNP or Intel TDX)
2. Confidential Data Hub (CDH) inside the TEE attests to KBS
3. KBS validates the TEE evidence and returns sealed secrets
4. SPIRE agent loads x509pop certificates from the unsealed secrets
5. Agent connects to SPIRE server and performs x509pop node attestation
6. Workload receives X509-SVID via Unix attestation through spiffe-helper

## Prerequisites

- Cloud provider region with confidential VM quota for peer pod VMs
  (worker nodes themselves do not need to be confidential)
- Vault as the secret backend

### Azure Instance Types

Azure confidential VM SKU families:

- DCasv5: AMD Milan (SEV-SNP)
- DCasv6: AMD Genoa (SEV-SNP)
- DCesv6: Intel TDX

Availability varies by region. The default configuration uses
Standard_DC2as_v5. Change the VM flavor in values-coco-dev.yaml under
the sandbox-policies app overrides if your region requires a different
SKU.

## Deployment

### 1. Configure clusterGroupName

Edit values-global.yaml and set the clusterGroupName to coco-dev:

```yaml
main:
  clusterGroupName: coco-dev
```

Commit and push this change before deploying.

### 2. Generate secrets

Run the pre-deployment scripts from the pattern root:

```bash
./scripts/gen-secrets-coco.sh
./scripts/get-pcr.sh
```

gen-secrets-coco.sh creates the cryptographic keys that Trustee (the
attestation server) needs to authenticate requests. It also copies the
values-secret template if not already present. Safe to re-run (will
not overwrite existing files).

get-pcr.sh retrieves the expected hardware measurements for the
confidential VM image. Trustee compares these against the measurements
reported by the actual hardware to decide whether a VM is genuine.
Requires a Red Hat pull secret (defaults to ~/pull-secret.json, or
set the PULL_SECRET env var).

Both scripts output to ~/.config/validated-patterns/trustee/.

### 3. Edit the secrets template

Edit ~/.config/validated-patterns/values-secret-layered-zero-trust.yaml
and uncomment the CoCo secrets section. Each secret has inline comments
in the template explaining its purpose and how to populate it.

### 4. Deploy

```bash
# If deploying from a fork, set TARGET_ORIGIN to your git remote name:
# TARGET_ORIGIN=myfork ./pattern.sh make install
./pattern.sh make install
```

Wait for all ArgoCD apps to reach Healthy/Synced. CoCo apps (sandbox,
trustee, sandbox-policies) reference CRDs created by the operators. On
first deploy, ArgoCD may try to sync these apps before the operator
has finished installing and registering its CRDs. This is normal and
resolves automatically once the operator CSV succeeds and ArgoCD
retries the sync.

The imperative framework runs jobs on a 10-minute schedule for:

- Azure NAT gateway configuration
- initdata generation and compression
- SPIRE x509pop certificate generation
- SPIRE server x509pop plugin configuration

### 5. Create SPIRE workload registration entry

The regular SPIRE agents (DaemonSet) use the k8s workload attestor,
which identifies workloads through the kubelet API. In the CoCo model,
the infrastructure (including Kubernetes) is untrusted. The SPIRE agent
runs inside the confidential VM where the kubelet is not accessible by
design, ensuring workload identity is rooted in hardware attestation
rather than the cluster control plane. The agent uses the Unix workload
attestor instead, which identifies processes by UID over the Unix
socket. Because of this, ClusterSPIFFEID CRDs do not apply and
registration entries must be created manually:

```bash
oc exec -n zero-trust-workload-identity-manager spire-server-0 -- \
  spire-server entry create \
    -parentID "spiffe://<trust-domain>/spire/agent/x509pop/<cert-fingerprint>" \
    -spiffeID "spiffe://<trust-domain>/ns/zero-trust-workload-identity-manager/sa/spire-agent" \
    -selector "unix:uid:1000800000"
```

The parentID cert fingerprint comes from the x509pop certificate. The
UID is assigned by OpenShift based on the namespace UID range.

## Verification

Check the hello-coco pod is running with 3/3 containers:

```bash
oc get pod -n zero-trust-workload-identity-manager hello-coco
```

Check that SVIDs were issued:

```bash
oc exec -n zero-trust-workload-identity-manager hello-coco \
  -c test-workload -- ls -la /svids/
```

Expected files: svid.pem, svid_key.pem, svid_bundle.pem.

Verify attestation from inside the TEE:

```bash
oc exec -n zero-trust-workload-identity-manager hello-coco \
  -c test-workload -- \
  curl http://127.0.0.1:8006/cdh/resource/default/attestation-status/status
```

Should return the value configured in the attestationStatus secret.

## Known Limitations

1. The ZTWIM operator CRD does not support x509pop plugin configuration.
   An imperative job patches the SPIRE server ConfigMap and StatefulSet
   directly. CREATE_ONLY_MODE must be enabled to prevent the operator
   from reverting these patches.

2. For now, SPIRE workload registration entries for CoCo pods must be
   created manually. The ClusterSPIFFEID CRD only works with
   k8s-attested agents. We are working on alternatives to automate this.
