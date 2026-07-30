# SPIRE Self-Signed CA Expiration on Cluster Restart

## Overview

When the ZTVP pattern is deployed with SPIRE's default self-signed CA (no upstream authority configured), a cluster shutdown/restart that exceeds the CA TTL will break SPIRE agent attestation. This results in all SPIFFE-dependent workloads (e.g., qtodo) failing to start until manual intervention is performed.

> **Note:** This issue does not affect production deployments that use an external/upstream CA (e.g., customer PKI, Vault PKI backend, cert-manager). In those configurations, the trust anchor persists across restarts.

## Problem Description

### SPIRE Server Default CA Configuration

The SPIRE server is configured with a self-signed CA with the following TTLs (from the `spire-server` ConfigMap in the `zero-trust-workload-identity-manager` namespace):

| Parameter | Value | Description |
|---|---|---|
| `ca_ttl` | `24h` | Lifetime of the self-signed X509 CA certificate |
| `default_x509_svid_ttl` | `1h` | Lifetime of X509 SVIDs issued to workloads |
| `default_jwt_svid_ttl` | `5m` | Lifetime of JWT SVIDs issued to workloads |

The CA rotates approximately every 12 hours (half of `ca_ttl`), and the `k8sbundle` notifier plugin pushes the current trust bundle to the `spire-bundle` ConfigMap.

### What Happens During Cluster Shutdown

1. The cluster shuts down — all pods (including SPIRE server and agents) stop
2. The X509 CA certificate continues to age while the cluster is offline
3. If the cluster is offline for longer than `ca_ttl` (24 hours), the CA expires

### What Happens on Cluster Restart

1. **SPIRE server** starts first, detects all CA slots are expired, and generates a **new self-signed CA** with a new key pair
2. **SPIRE agents** (DaemonSet) start and attempt to re-attest against the server
3. Agents still have the **old trust bundle** cached — they do not trust the server's new CA
4. Agent attestation fails with:

   ```bash
   transport: authentication handshake failed: x509svid: could not verify leaf certificate:
   x509: certificate signed by unknown authority
   ```

5. Agents enter `CrashLoopBackOff` or `Error` state
6. **All SPIFFE-dependent workloads** (e.g., qtodo) cannot obtain SVIDs and remain stuck in init or fail health checks

### Symptoms

- SPIRE agent pods in `CrashLoopBackOff` or `Error` state across all nodes
- SPIRE server logs showing `X509CA slot unusable — slot expired` for all slots
- SPIRE server logs showing a new CA was prepared and activated
- Workload pods stuck in `Init` state (SPIFFE helper init containers cannot connect to the agent)
- SPIFFE OIDC discovery provider restarting repeatedly

## Recovery Procedure

### Step 1: Verify the Issue

Check the SPIRE server logs for expired CA slots and new CA generation:

```bash
oc logs spire-server-0 -n zero-trust-workload-identity-manager -c spire-server | grep -E "slot unusable|CA prepared|CA activated"
```

Expected output showing expired old slots and a newly activated CA:  

```bash
level=warning msg="X509CA slot unusable" error="slot expired" ...
level=info msg="X509 CA prepared" ...
level=info msg="X509 CA activated" ...
```

Check SPIRE agent logs for the trust failure:

```bash
oc logs <spire-agent-pod> -n zero-trust-workload-identity-manager | grep "unknown authority"
```

### Step 2: Restart SPIRE Agents

Restart the SPIRE agent DaemonSet so agents pick up the new trust bundle from the `spire-bundle` ConfigMap (which the server's `k8sbundle` notifier has already updated):

```bash
oc rollout restart daemonset/spire-agent -n zero-trust-workload-identity-manager
```

Wait for all agents to become ready:

```bash
oc rollout status daemonset/spire-agent -n zero-trust-workload-identity-manager
```

### Step 3: Restart Affected Workloads

Any workload pods that were stuck in init or crash-looping due to SVID acquisition failure need to be restarted:

```bash
# Example: restart qtodo
oc delete pod -l app=qtodo -n qtodo

# Check all namespaces for stuck pods with SPIFFE init containers
oc get pods --all-namespaces | grep -E 'Init|Error|CrashLoop'
```

### Step 4: Verify Recovery

Confirm SPIRE agents are healthy:

```bash
oc get pods -n zero-trust-workload-identity-manager | grep spire-agent
# All should show 1/1 Running with 0 restarts
```

Confirm workloads are running:

```bash
oc get pods -n qtodo
# qtodo pod should show 3/3 Running
```

## Production Consideration

This issue is specific to the **self-signed CA** configuration used in the default ZTVP deployment. In production environments, customers should configure SPIRE with an **UpstreamAuthority plugin** pointing to their organization's PKI infrastructure. With an upstream CA:

- The trust anchor remains stable across SPIRE server restarts
- SPIRE agents always trust the server's certificate chain because it chains back to the persistent upstream CA
- No manual intervention is required after cluster restart regardless of downtime duration

Supported upstream authority plugins include:

- **Vault PKI** (`upstream_authority "vault"`) — integrates with HashiCorp Vault's PKI secrets engine
- **cert-manager** (`upstream_authority "cert_manager"`) — uses Kubernetes cert-manager as the CA
- **AWS PCA** (`upstream_authority "aws_pca"`) — uses AWS Private Certificate Authority
- **Disk-based** (`upstream_authority "disk"`) — uses a CA certificate and key stored on disk
