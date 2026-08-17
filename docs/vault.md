# HashiCorp Vault

## Overview

HashiCorp Vault is the centralized secrets management engine for the entire
pattern. Every component retrieves credentials from Vault — either through the
External Secrets Operator (ESO) for Kubernetes-native secret sync, or through
direct SPIFFE JWT authentication for workloads that need dynamic credentials.

**Chart:** `hashicorp-vault` (external, from Validated Patterns Helm repository)  
**Namespace:** `vault`  
**Sync wave:** 25  
**Service endpoint:** `https://vault.vault.svc.cluster.local:8200`

## Architecture

```text
                        ┌─────────────────────────┐
                        │   Validated Patterns    │
                        │   Framework             │
                        │   - Initialize Vault    │
                        │   - Unseal              │
                        │   - Configure k8s auth  │
                        │   - Seed secrets        │
                        └───────────┬─────────────┘
                                    │
                                    ▼
                            ┌──────────────┐
                            │    Vault     │
                            │  (port 8200) │
                            └──┬───────┬───┘
                               │       │
              k8s Auth         │       │        JWT Auth
          (ServiceAccount)     │       │     (SPIFFE SVID)
                               │       │
               ┌───────────────┘       └────────────────┐
               ▼                                        ▼
    ┌─────────────────────┐               ┌──────────────────────┐
    │  External Secrets   │               │  SPIFFE Vault Client │
    │  Operator (ESO)     │               │  (sidecar pattern)   │
    │                     │               │                      │
    │  ClusterSecretStore │               │  SPIRE CSI ──▶ JWT   │
    │  "vault-backend"    │               │  ──▶ Vault login     │
    │                     │               │  ──▶ read secret     │
    │  Syncs to k8s       │               │  ──▶ write to file   │
    │  Secrets            │               │  ──▶ renew lease     │
    └────────┬────────────┘               └──────────┬───────────┘
             │                                      │
             ▼                                      ▼
    All charts via                          qtodo, RHTPA, supply-chain
    ExternalSecret CRs
```

## Authentication Methods

Vault uses two authentication methods, each serving a different purpose:

### Kubernetes Auth (ESO)

Configured automatically by the Validated Patterns framework Ansible playbooks.
Used by the External Secrets Operator's `ClusterSecretStore` named
`vault-backend`. Every `ExternalSecret` CR across all charts references this
store to sync Vault secrets into Kubernetes Secrets.

This is the default path for secrets that need to exist as Kubernetes Secrets
(operator configurations, database passwords, OIDC client secrets).

### JWT Auth (SPIFFE)

Configured via `overrides/values-vault-jwt.yaml`. This method validates SPIFFE
JWT SVIDs against the SPIRE OIDC Discovery Provider, enabling workloads to
authenticate directly to Vault using their workload identity.

The OIDC discovery URL points to the cluster-internal SPIRE endpoint:
`https://spire-spiffe-oidc-discovery-provider.zero-trust-workload-identity-manager.svc.cluster.local`

#### JWT Roles

Each workload that authenticates directly to Vault has a dedicated role that
binds a specific SPIFFE ID to a set of policies:

| Role | SPIFFE Subject | Audience | Policies |
| --- | --- | --- | --- |
| `qtodo` | `spiffe://apps.<domain>/ns/qtodo/sa/qtodo` | `https://keycloak.apps.<domain>/realms/ztvp` | `apps-qtodo-jwt-secret` |
| `rhtpa` | `spiffe://apps.<domain>/ns/trusted-profile-analyzer/sa/rhtpa` | `rhtpa` | `hub-infra-rhtpa-jwt-secret` |
| `supply-chain` | `spiffe://apps.<domain>/ns/<pattern>-hub/sa/pipeline` | `supply-chain` | `hub-supply-chain-jwt-secret` |

The `qtodo` role is active by default. The `rhtpa` and `supply-chain` roles are
activated when their respective features are enabled.

#### JWT Policies

| Policy | Vault Path | Capabilities | Used By |
| --- | --- | --- | --- |
| `apps-qtodo-jwt-secret` | `secret/data/apps/qtodo/*` | read | qtodo |
| `hub-infra-rhtpa-jwt-secret` | `secret/data/hub/infra/rhtpa/*` | read | RHTPA |
| `hub-supply-chain-jwt-secret` | `secret/data/hub/infra/quay/*` | read | supply-chain |
| | `secret/data/hub/infra/registry/*` | read, create, update | supply-chain (token refresh) |
| | `secret/data/hub/infra/rhtpa/rhtpa-oidc-cli` | read | supply-chain |
| | `secret/data/hub/supply-chain/*` | read | supply-chain |

## Secret Path Hierarchy

Secrets are organized in a least-privilege, path-based hierarchy:

```text
secret/data/
├── global/                              # Shared secrets
│   └── config-demo                      #   Demo secret
├── apps/
│   └── qtodo/                           # Application-scoped secrets
│       ├── qtodo-db                     #   DB credentials (admin-password, db-password)
│       ├── qtodo-truststore             #   Java truststore password
│       ├── qtodo-oidc-client            #   OIDC client secret (optional)
│       └── qtodo-oidc-entraid           #   Entra ID client secret (optional)
├── hub/
│   ├── infra/                           # Infrastructure secrets (components)
│   │   ├── keycloak/
│   │   │   └── keycloak                 #   Keycloak admin + DB passwords
│   │   ├── acs/
│   │   │   └── acs-central              #   ACS admin password + OIDC client secret
│   │   ├── rhtpa/
│   │   │   ├── rhtpa-db                 #   RHTPA PostgreSQL password
│   │   │   └── rhtpa-oidc-cli           #   RHTPA CLI client secret
│   │   ├── rhtas/
│   │   │   └── rhtas-oidc-client-secret #   RHTAS OIDC client secret
│   │   ├── quay/
│   │   │   └── quay-users               #   Built-in Quay user password
│   │   ├── registry/
│   │   │   └── registry-user            #   BYO/embedded registry credentials
│   │   └── users/
│   │       └── keycloak-users           #   All user passwords for realm import
│   ├── supply-chain/
│   │   └── git-credentials              #   Git HTTPS/SSH credentials
│   └── kubeconfig-spoke-*               #   Spoke cluster kubeconfigs
└── pushsecrets/
    └── <cert-name>                      #   CoCo agent certificates (via PushSecret)
```

### Path Convention

- `apps/` — application-scoped secrets, accessed by workloads directly
- `hub/infra/` — infrastructure secrets, accessed by operators and shared services
- `hub/supply-chain/` — pipeline-specific secrets
- `hub/` (top-level) — Hub cluster level secrets (kubeconfigs, attestation)

## SPIFFE Vault Client Sidecar Pattern

The pattern implements a sidecar-based authentication flow for workloads that
need dynamic secrets from Vault. This avoids storing secrets as Kubernetes
Secrets, keeping them in-memory only.

### How It Works

```text
Pod Lifecycle:

  1. init-spiffe-helper     Obtains initial SPIFFE X.509 + JWT SVIDs
         │                  from SPIRE agent via CSI driver
         ▼
  2. init-spiffe-vault      Authenticates to Vault with JWT SVID,
         │                  fetches DB password, writes credentials file
         ▼
  3. Application starts     Reads credentials from shared volume
         │
         ▼
  4. spiffe-helper sidecar  Continuously renews SVIDs
         │
         ▼
  5. vault-client sidecar   Renews Vault lease at 50% of duration,
                            re-authenticates on failure
```

### Implementation

The sidecar is a Python script (`spiffe-vault-client.py`) that:

1. Reads the SPIFFE JWT from `/svids/jwt.token`
2. Authenticates to Vault via `POST /v1/auth/jwt/login` with the JWT and role name
3. Reads the target secret from the configured Vault path
4. Writes the credentials as a properties file to `/run/secrets/db-credentials/`
5. In daemon mode, renews the Vault token at 50% of its lease duration

This pattern is used by:

- **qtodo** — reads DB password from `secret/data/apps/qtodo/qtodo-db`
- **RHTPA** — reads DB password from `secret/data/hub/infra/rhtpa/rhtpa-db`
- **Registry token refresher** — reads and **writes** registry tokens to `secret/data/hub/infra/registry/registry-user`

### Volumes

| Volume | Type | Purpose |
| --- | --- | --- |
| `spiffe-workload-api` | CSI (`csi.spiffe.io`) | SPIRE agent socket |
| `svids` | emptyDir | Shared SVID storage between spiffe-helper and vault-client |
| `db-credentials` | emptyDir | Credentials file consumed by the application |
| `spiffe-vault-client` | ConfigMap | The Python script |
| `ztvp-trusted-ca` | ConfigMap | CA bundle for TLS verification |

## ExternalSecret Pattern

Every chart that needs Vault secrets uses `ExternalSecret` resources referencing
the `vault-backend` `ClusterSecretStore`:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
spec:
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: <k8s-secret-name>
  data:
    - secretKey: <k8s-key>
      remoteRef:
        key: secret/data/<vault-path>
        property: <vault-field>
```

### ExternalSecrets by Chart

| Chart | ExternalSecret | Vault Path | Purpose |
| --- | --- | --- | --- |
| qtodo | `qtodo-db-secret` | `apps/qtodo/qtodo-db` | PostgreSQL credentials |
| qtodo | `qtodo-truststore-secret` | `apps/qtodo/qtodo-truststore` | Java truststore password |
| rh-keycloak | `keycloak-users` | `hub/infra/users/keycloak-users` + `hub/infra/acs/acs-central` | Realm user passwords |
| rh-keycloak | `acs-oidc-client-secret` | `hub/infra/acs/acs-central` | ACS OIDC client secret |
| rh-keycloak | `rhtpa-oidc-cli-secret` | `hub/infra/rhtpa/rhtpa-oidc-cli` | RHTPA CLI client secret |
| acs-central | `central-htpasswd` | `hub/infra/acs/acs-central` | ACS admin password |
| acs-central | `keycloak-acs-client` | `hub/infra/acs/acs-central` | ACS Keycloak client secret |
| rhtpa-operator | `rhtpa-db-secret` | `hub/infra/rhtpa/rhtpa-db` | RHTPA DB password |
| rhtpa-operator | `rhtpa-oidc-cli-secret` | `hub/infra/rhtpa/rhtpa-oidc-cli` | RHTPA CLI secret |
| supply-chain | `qtodo-registry-auth` | `hub/infra/quay/*` or `hub/infra/registry/*` | Registry credentials |
| supply-chain | `qtodo-rhtpa-cli-password` | `hub/infra/rhtpa/rhtpa-oidc-cli` | RHTPA CLI secret |
| supply-chain | `qtodo-git-credentials` | `hub/supply-chain/git-credentials` | Git credentials |
| acm-managed-clusters | `kubeconfig-<name>` | `hub/kubeconfig-<cluster>` | Spoke kubeconfigs |

## Initialization and Seeding

Vault initialization, unsealing, and secret seeding are handled automatically
by the Validated Patterns framework:

1. The VP operator detects Vault pods are ready
2. Ansible playbooks run as imperative Jobs to:
   - Initialize Vault (generate unseal keys and root token)
   - Store unseal keys in a Kubernetes Secret (`vaultkeys` in `imperative` namespace)
   - Unseal Vault
   - Configure Kubernetes auth method
   - Seed secrets from `~/values-secret-layered-zero-trust.yaml`
3. The JWT auth method is configured via `overrides/values-vault-jwt.yaml`

The root token and unseal keys are stored in:

```bash
oc extract -n imperative secret/vaultkeys --to=- --keys=vault_data_json 2>/dev/null | jq -r ".root_token"
```

## Network Policies

When enabled (default via `values-vault-network-policy.yaml`), Vault has
fine-grained network segmentation:

**Ingress to Vault (port 8200):**

| Source | Purpose |
| --- | --- |
| OpenShift router | Vault UI/API route |
| `qtodo` namespace | SPIFFE vault client sidecar |
| `registry-token-refresher` pods | Supply chain token refresh |
| Vault pods (port 8201) | HA replication |

**Egress from Vault:**

| Destination | Purpose |
| --- | --- |
| `openshift-dns` (port 5353) | DNS resolution |
| SPIRE OIDC Discovery Provider (ports 443/8443) | JWKS fetch for JWT auth validation |
| Vault pods (port 8201) | HA replication |
| Kubernetes API (ports 443/6443) | TokenReview for ESO service account validation |

## Accessing Vault

### CLI Access

```bash
# Get the root token
VAULT_TOKEN=$(oc extract -n imperative secret/vaultkeys \
  --to=- --keys=vault_data_json 2>/dev/null | jq -r ".root_token")

# Read a secret
oc exec -n vault vault-0 -- env VAULT_TOKEN="$VAULT_TOKEN" \
  vault kv get secret/hub/infra/users/keycloak-users

# List secrets at a path
oc exec -n vault vault-0 -- env VAULT_TOKEN="$VAULT_TOKEN" \
  vault kv list secret/hub/infra
```

### Web UI

```text
https://vault-vault.apps.<clusterDomain>
```

Login with the root token retrieved above.

### Reading ESO-Synced Secrets

For secrets already synced to Kubernetes by ESO:

```bash
oc get secret <secret-name> -n <namespace> -o jsonpath='{.data.<key>}' | base64 -d
```

## Secrets Template

The `values-secret.yaml.template` file defines all secrets that need to be
seeded into Vault. Copy it to `~/values-secret-layered-zero-trust.yaml` and
customize before deploying:

```bash
cp values-secret.yaml.template ~/values-secret-layered-zero-trust.yaml
# Edit the file to set any manual values (most are auto-generated)
```

Password generation policies:

| Policy | Length | Used For |
| --- | --- | --- |
| `basicPolicy` | 10 chars | Standard passwords |
| `advancedPolicy` | 20 chars | Admin passwords |
| `alphaNumericPolicy` | 32 chars | Passwords where the use of special characters can cause errors (e.g., RHBK) |
