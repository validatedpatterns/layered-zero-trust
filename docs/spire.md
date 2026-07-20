# SPIRE / Zero Trust Workload Identity Manager (ZTWIM)

## Overview

The Zero Trust Workload Identity Manager (ZTWIM) deploys SPIRE on OpenShift,
providing every workload with a cryptographically verifiable SPIFFE identity.
SPIRE is the foundation of the pattern's zero-trust architecture — it enables
workloads to authenticate to Vault, Keycloak, and RHTAS without static secrets.

**Chart:** `ztwim` (external, from Validated Patterns Helm repository)  
**Namespace:** `zero-trust-workload-identity-manager`  
**Sync wave:** 30  
**Operator:** `openshift-zero-trust-workload-identity-manager` (channel: `stable-v1`, source: `redhat-marketplace`)

## Architecture

```text
                    ┌──────────────────────────────────────┐
                    │     SPIRE Server                     │
                    │     (StatefulSet)                    │
                    │                                      │
                    │  ┌────────────┐  ┌────────────────┐  │
                    │  │ Workload   │  │ OIDC Discovery │  │
                    │  │ Registrar  │  │ Provider       │  │
                    │  └────────────┘  └───────┬────────┘  │
                    └──────────┬───────────────┼───────────┘
                               │               │
              Node attestation │               │ JWKS / OIDC
                               │               │ metadata
                               │               │
                    ┌──────────▼──────┐  ┌─────▼──────────┐
                    │  SPIRE Agent    │  │ OpenShift      │
                    │  (DaemonSet)    │  │ Route          │
                    │                 │  │ (reencrypt)    │
                    │  CSI Driver     │  └────────────────┘
                    │  (csi.spiffe.io)│         │
                    └────────┬────────┘         │
                             │                  │
                    ┌────────▼────────┐         │
                    │  Workload Pod   │   Consumed by:
                    │  ┌────────────┐ │   - Vault (JWT auth)
                    │  │ SVID mount │ │   - Keycloak (SPIFFE IdP)
                    │  │ via CSI    │ │   - RHTAS (issuer)
                    │  └────────────┘ │   - Tekton Chains
                    └─────────────────┘
```

### Components

| Component | Type | Purpose |
| --- | --- | --- |
| SPIRE Server | StatefulSet | Certificate authority, workload registration, SVID issuance |
| SPIRE Agent | DaemonSet | Per-node agent, node attestation, workload attestation |
| CSI Driver | DaemonSet | Mounts SPIFFE workload API socket into pods via `csi.spiffe.io` |
| OIDC Discovery Provider | Deployment | Exposes SPIRE as an OIDC-compatible identity provider |
| Controller Manager | Deployment | Processes `ClusterSPIFFEID` CRDs for automatic workload registration |

## Trust Domain

The SPIRE trust domain is set to `apps.<clusterDomain>` (e.g.,
`apps.cluster.example.com`). All SPIFFE IDs in the pattern are scoped under
this trust domain.

## Workload Registration

### ClusterSPIFFEID (Automatic)

Most workloads are registered automatically via `ClusterSPIFFEID` custom
resources. The ZTWIM controller manager watches for pods matching the CRD
selectors and creates SPIRE registration entries. SPIFFE IDs follow the
convention:

```text
spiffe://apps.<clusterDomain>/ns/<namespace>/sa/<serviceaccount>
```

### ClusterStaticEntry (Manual)

Some workloads in operator-managed namespaces cannot use `ClusterSPIFFEID` and
require `ClusterStaticEntry` resources — one per cluster node, because each
node runs its own SPIRE agent. The Tekton Chains controller uses this approach
(see [Tekton Chains](tekton-chains.md#spire-workload-registration)).

## Registered Workload Identities

| Workload | SPIFFE ID | Registration | Vault Role |
| --- | --- | --- | --- |
| qtodo | `spiffe://apps.<domain>/ns/qtodo/sa/qtodo` | ClusterSPIFFEID | `qtodo` |
| RHTPA | `spiffe://apps.<domain>/ns/trusted-profile-analyzer/sa/rhtpa` | ClusterSPIFFEID | `rhtpa` |
| Supply chain pipeline | `spiffe://apps.<domain>/ns/<pattern>-hub/sa/pipeline` | ClusterSPIFFEID | `supply-chain` |
| Tekton Chains controller | `spiffe://apps.<domain>/ns/openshift-pipelines/sa/tekton-chains-controller` | ClusterStaticEntry | (used with Fulcio) |

## OIDC Discovery Provider

The SPIRE OIDC Discovery Provider makes SPIRE act as an OIDC-compliant identity
provider. This is critical for integrating SPIFFE identities with systems that
understand OIDC but not SPIFFE natively.

### Ingress Configuration

The OIDC Discovery Provider is exposed via an OpenShift reencrypt Route
configured in `values-hub.yaml`:

```yaml
spire:
  oidcDiscoveryProvider:
    ingress:
      enabled: true
      annotations:
        route.openshift.io/termination: reencrypt
        route.openshift.io/destination-ca-certificate-secret: spire-bundle
```

The `spire-bundle` secret provides the destination CA certificate for reencrypt
TLS termination.

### Endpoints

| Endpoint | URL | Consumers |
| --- | --- | --- |
| External route | `https://spire-spiffe-oidc-discovery-provider.apps.<domain>` | RHTAS Fulcio, Tekton Chains, supply-chain tasks |
| Internal service | `https://spire-spiffe-oidc-discovery-provider.zero-trust-workload-identity-manager.svc.cluster.local` | Vault JWT auth |
| JWKS endpoint | `https://spire-spiffe-oidc-discovery-provider.apps.<domain>/keys` | Keycloak SPIFFE Identity Provider |

### Consumers

The OIDC Discovery Provider is consumed by four different systems:

1. **Vault** — uses the internal service URL as `oidc_discovery_url` to validate
   SPIFFE JWT SVIDs during JWT auth (see [Vault](vault.md#jwt-auth-spiffe))
2. **Keycloak** — the SPIFFE Identity Provider fetches JWKS from the external
   route to validate federated JWT client assertions
   (see [Keycloak](keycloak.md#spiffe-identity-provider))
3. **RHTAS Fulcio** — accepts the OIDC Discovery Provider as a trusted issuer
   for keyless signing certificates (SPIFFE type)
4. **Tekton Chains** — the Chains controller presents its SVID to Fulcio, which
   validates it against the OIDC Discovery Provider

## SPIFFE Socket and CSI Driver

### Standard Workloads

All standard workloads access SPIFFE SVIDs through the CSI driver:

```yaml
volumes:
  - name: spiffe-workload-api
    csi:
      driver: csi.spiffe.io
      readOnly: true
```

| Setting | Value |
| --- | --- |
| CSI driver | `csi.spiffe.io` |
| Mount path | `/spiffe-workload-api` |
| Socket file | `spire-agent.sock` |
| Full socket path | `/spiffe-workload-api/spire-agent.sock` |
| Environment variable | `SPIFFE_ENDPOINT_SOCKET=/spiffe-workload-api/spire-agent.sock` |

### Confidential Container Workloads (CoCo)

CoCo peer-pods cannot use the CSI driver because they run in isolated TEE VMs.
Instead, they embed a full SPIRE agent as a sidecar container:

| Setting | Value |
| --- | --- |
| Agent type | Sidecar container (not DaemonSet) |
| Socket path | `/tmp/spire-agent/public/spire-agent.sock` |
| Node attestor | `x509pop` (instead of `k8s_psat`) |
| Workload attestor | `unix` |

See [Confidential Containers](CONFIDENTIAL-CONTAINERS.md) for the CoCo-specific
SPIRE architecture.

## SVID Output Paths

The `spiffe-helper` sidecar writes SVIDs to a shared `emptyDir` volume:

| Component | Cert | Key | Bundle | JWT Token | JWT Audience |
| --- | --- | --- | --- | --- | --- |
| qtodo | `/svids/svid.pem` | `/svids/svid_key.pem` | `/svids/svid_bundle.pem` | `/svids/jwt.token` | `https://keycloak.apps.<domain>/realms/ztvp` |
| RHTPA | `/run/secrets/spiffe/svid.pem` | `/run/secrets/spiffe/svid_key.pem` | `/run/secrets/spiffe/svid_bundle.pem` | `/run/secrets/spiffe/jwt.token` | `rhtpa` |
| Supply chain token refresher | `/svids/svid.pem` | `/svids/svid_key.pem` | `/svids/svid_bundle.pem` | `/svids/jwt.token` | `supply-chain` |
| hello-coco | `/svids/svid.pem` | `/svids/svid_key.pem` | `/svids/svid_bundle.pem` | — | — |

## spiffe-helper Configuration

Each component that uses SPIFFE includes a `spiffe-helper` init container
(one-shot mode) and optionally a sidecar (daemon mode) for continuous renewal.
The configuration is stored in a ConfigMap:

```ini
agent_address = "/spiffe-workload-api/spire-agent.sock"
cert_dir = "/svids"
svid_file_name = "svid.pem"
svid_key_file_name = "svid_key.pem"
svid_bundle_file_name = "svid_bundle.pem"
jwt_svids = [{jwt_audience="<audience>", jwt_svid_file_name="jwt.token"}]
jwt_bundle_file_name = "jwt_bundle.json"
```

## Integration Points

### Vault Integration

SPIRE provides the identity layer for Vault's JWT auth method. Workloads
authenticate to Vault by presenting a SPIFFE JWT SVID. Vault validates the JWT
against the SPIRE OIDC Discovery Provider's JWKS endpoint.

See [Vault — JWT Auth](vault.md#jwt-auth-spiffe) for role and policy details.

### Keycloak Integration

The SPIFFE Identity Provider in Keycloak enables federated JWT client
assertions — workloads can authenticate to Keycloak using SPIFFE SVIDs instead
of client secrets. Keycloak validates the JWT against the SPIRE OIDC Discovery
Provider's JWKS endpoint.

See [Keycloak — SPIFFE Identity Provider](keycloak.md#spiffe-identity-provider).

### RHTAS Integration

RHTAS Fulcio accepts the SPIRE OIDC Discovery Provider as an issuer for keyless
signing. When a workload (e.g., a supply-chain pipeline task or the Tekton
Chains controller) requests a signing certificate, Fulcio verifies the SPIFFE
JWT SVID and issues a short-lived x509 certificate containing the SPIFFE ID.

The Securesign CR includes the SPIRE issuer:

```yaml
fulcio:
  oidcIssuers:
    - ClientID: "sigstore"
      Issuer: "https://spire-spiffe-oidc-discovery-provider.apps.<domain>"
      Type: "spiffe"
      SPIFFETrustDomain: "apps.<domain>"
```

### Supply Chain Integration

Five Tekton tasks mount the SPIFFE CSI volume for artifact and image signing:

- `qtodo-sign-artifact` — signs build artifacts
- `qtodo-verify-artifact` — verifies artifact signatures
- `qtodo-sign-image` — signs container images
- `qtodo-verify-image` — verifies image signatures
- `qtodo-sbom-attestation` — attests SBOMs

Additionally, the registry token refresher CronJob uses SPIFFE to authenticate
to Vault for writing refreshed OpenShift registry tokens.

## Network Policies

When enabled (default via `values-ztwim-network-policy.yaml`):

| Component | Ingress | Egress |
| --- | --- | --- |
| SPIRE Server | gRPC (8081) from agents, federation (8443) from router, webhook (9443) from K8s API, metrics (9402) | DNS (5353), K8s API (6443) |
| OIDC Discovery Provider | HTTPS (8443) from router | DNS (5353) |
| CSI Driver | — | DNS (5353) |
| Operator | Metrics (8443) | DNS (5353), K8s API (6443) |

## CoCo-Specific Configuration

For Confidential Containers, additional SPIRE configuration is required:

1. **x509pop Node Attestor** — the SPIRE server must be patched to accept
   `x509pop` attestation (via `ansible/configure-spire-server-x509pop.yaml`)
2. **Certificate Generation** — CA and agent certificates are generated for each
   CoCo workload (via `ansible/generate-certs.yaml`)
3. **CREATE_ONLY_MODE** — the ZTWIM operator is set to `CREATE_ONLY_MODE=true`
   to prevent it from reverting the manual x509pop patches

See [Confidential Containers](CONFIDENTIAL-CONTAINERS.md) for the full CoCo
deployment workflow.

## Operational Considerations

### CA Expiration on Cluster Restart

When using SPIRE's default self-signed CA (24h TTL), a cluster shutdown
exceeding the TTL causes SPIRE agent attestation to break on restart. See
[SPIRE CA Expiration Recovery](spire-ca-expiration-cluster-restart.md) for the
recovery procedure.

### OIDC Discovery Provider Route

The OIDC Discovery Provider route must be reachable from both inside the cluster
(Vault, Keycloak) and externally (for verification tooling). The reencrypt route
uses the `spire-bundle` secret as the destination CA — if this secret is missing
or the route is misconfigured, all SPIFFE-based authentication chains will fail.
