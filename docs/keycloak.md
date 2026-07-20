# Red Hat Build of Keycloak (RHBK) Deployment

## Overview

Red Hat Build of Keycloak provides OIDC-based identity services for all pattern
components. It deploys a dedicated `ztvp` realm with pre-configured clients,
users, roles, and a SPIFFE Identity Provider that enables workload identity
federation — allowing applications to authenticate using SPIFFE SVIDs instead
of static client secrets.

**Chart:** `charts/rh-keycloak` (wrapper) + `rhbk` subchart from `oci://quay.io/validatedpatterns`  
**Namespace:** `keycloak-system`  
**Sync wave:** 35  
**Operator:** `rhbk-operator` (channel: `stable-v26.4`, source: `redhat-marketplace`)

## Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                      keycloak-system                         │
│                                                              │
│  ┌───────────────┐   ┌────────────────┐   ┌───────────────┐  │
│  │   Keycloak    │   │  PostgreSQL    │   │ Realm Import  │  │
│  │   Server      │◀─▶│  Database      │   │ Job           │  │
│  │  (port 8443)  │   │  (port 5432)   │   │ (one-time)    │  │
│  └──────┬────────┘   └────────────────┘   └───────────────┘  │
│         │                                                    │
│         ▼                                                    │
│  SPIFFE Identity Provider ◀──── SPIRE OIDC Discovery         │
│  (federated JWT auth)           Provider (JWKS)              │
└──────────────────────────────────────────────────────────────┘
         │
         ▼ OIDC Clients
   ┌─────────┼──────┬────────┬──────────────┐
   │         │      │        │              │
 qtodo-app  ACS   RHTAS   RHTPA-CLI  RHTPA-frontend
```

### Chart Structure

The `rh-keycloak` chart is a thin wrapper around the generic `rhbk` Helm chart
(pulled from `oci://quay.io/validatedpatterns`). The wrapper adds:

- The full `ztvp` realm definition (clients, users, roles, scopes)
- SPIFFE Identity Provider configuration
- ExternalSecret definitions for Vault-sourced credentials
- A PostSync cleanup Job that removes temporary secrets after realm import

## The ZTVP Realm

The `ztvp` realm is the central identity configuration. User self-registration
is disabled — all users are pre-provisioned via the realm import.

### OIDC Clients

| Client ID | Type | Auth Method | Purpose |
| --- | --- | --- | --- |
| `qtodo-app` | Confidential | `federated-jwt` (SPIFFE) | qtodo application — authenticates via SPIFFE SVID |
| `trusted-artifact-signer` | Public | Direct access grants (ROPC) | RHTAS — automated pipeline signing |
| `acs-central` | Confidential | Client secret | ACS Central — SSO for the security console |
| `rhtpa-cli` | Confidential | Client secret | RHTPA — machine-to-machine SBOM operations |
| `rhtpa-frontend` | Public | Standard + implicit flow | RHTPA — browser-based UI access |

#### qtodo-app (Federated JWT Authentication)

This client uses a unique authentication flow — instead of a client secret, it
authenticates using a SPIFFE JWT assertion through the SPIFFE Identity Provider:

1. The qtodo application obtains a SPIFFE SVID from the SPIRE agent
2. It presents the SVID as a JWT client assertion to Keycloak's token endpoint
3. Keycloak validates the JWT against the SPIFFE Identity Provider's JWKS endpoint
4. Keycloak issues an access token to the application

Key attributes:

- `clientAuthenticatorType: federated-jwt`
- `jwt.credential.issuer: spiffe` (links to the SPIFFE IdP alias)
- `serviceAccountsEnabled: true`
- `standardFlowEnabled: true` (also supports browser-based login)

#### trusted-artifact-signer (RHTAS)

A public client used for automated pipeline signing via Direct Access Grants. The pipeline fetches credentials from Vault and exchanges them for a token non-interactively.

- `directAccessGrantsEnabled: true` — used by the Tekton pipeline (non-interactive, credentials from Vault)
- `oauth2.device.authorization.grant.enabled: true` — available for interactive use (e.g., manual `cosign` invocation)
- Protocol mappers:
  - `audience-mapper` — adds `trusted-artifact-signer` to the `aud` claim
  - `email-mapper` — hardcodes `email_verified: true` for Fulcio identity

#### acs-central (ACS)

A confidential client with a secret sourced from Vault:

- Client secret: `${ACS_CLIENT_SECRET}` (placeholder resolved from Vault)
- Protocol mappers:
  - `groups` — maps group membership to the `groups` claim
  - `roles` — maps realm roles to the `roles` claim

#### rhtpa-cli (RHTPA Service Account)

Machine-to-machine client for the RHTPA CLI and pipeline operations:

- `serviceAccountsEnabled: true` (no user flows)
- `access.token.lifespan: 300` (5 minutes)
- Custom scopes: `create:document`, `read:document`, `update:document`, `delete:document`

#### rhtpa-frontend (RHTPA UI)

Public client for the RHTPA web console:

- `standardFlowEnabled: true` and `implicitFlowEnabled: true`
- Same document permission scopes as `rhtpa-cli`

### Custom Client Scopes

Beyond standard OIDC scopes (`openid`, `basic`, `email`, `profile`, `roles`,
`web-origins`), the realm defines four RHTPA-specific document permission scopes:

| Scope | Purpose |
| --- | --- |
| `create:document` | Permission to create SBOM documents |
| `read:document` | Permission to read SBOM documents |
| `update:document` | Permission to update SBOM documents |
| `delete:document` | Permission to delete SBOM documents |

### Realm Roles

| Role | Description | Assigned To |
| --- | --- | --- |
| `qtodo-admin` | qtodo App Administrator | qtodo-admin user |
| `viewer` | Read-only access | qtodo-user1, rhtas-user, rhtpa-user |
| `create:sbom` | RHTPA SBOM Creator | rhtpa-user |
| `create:document` | RHTPA Document Creator | rhtpa-user |
| `acs-admin` | ACS Administrator | acs-admin user |

### Pre-Provisioned Users

| Username | Email | Roles | Password Behavior |
| --- | --- | --- | --- |
| `qtodo-admin` | `qtodo-admin@example.com` | `qtodo-admin` | Temporary — must change on first login |
| `qtodo-user1` | `qtodo-user1@example.com` | `viewer` | Temporary — must change on first login |
| `rhtas-user` | `rhtas-user@example.com` | `viewer` | Permanent |
| `rhtpa-user` | `rhtpa-user@example.com` | `viewer`, `create:sbom`, `create:document` | Permanent |
| `acs-admin` | `acs-admin@example.com` | `acs-admin`, `offline_access` | Permanent |

All passwords are sourced from Vault via ExternalSecrets (see [Secrets
Integration](#secrets-integration) below).

## SPIFFE Identity Provider

The SPIFFE Identity Provider enables workload identity federation — allowing
applications with SPIFFE SVIDs to authenticate to Keycloak without static
credentials. It is configured as a hidden OIDC identity provider (not shown on
the login page) used only for programmatic federated client authentication.

### Configuration

| Setting | Value | Purpose |
| --- | --- | --- |
| `alias` | `spiffe` | Internal identifier referenced by clients |
| `providerId` | `oidc` | Standard OIDC provider type |
| `hideOnLogin` | `true` | Not visible to end users on the login page |
| `supportsClientAssertions` | `true` | Accepts JWT client assertions |
| `supportsClientAssertionReuse` | `true` | Same assertion can be reused within its lifetime |
| `validateSignature` | `true` | Validates JWT against JWKS endpoint |
| `useJwksUrl` | `true` | Fetches signing keys from the SPIRE OIDC Discovery Provider |

The `issuer`, `authorizationUrl`, `tokenUrl`, and `jwksUrl` fields are
auto-generated by the `rhbk` subchart from the cluster domain, pointing to the
SPIRE OIDC Discovery Provider route. These can be overridden in `values-hub.yaml`
if the SPIRE OIDC endpoint uses a non-standard URL.

### How Federated JWT Authentication Works

```text
  Application Pod                Keycloak                 SPIRE OIDC
  (e.g., qtodo)                  (ztvp realm)             Discovery Provider
       │                              │                         │
       │ 1. Obtain SVID from          │                         │
       │    SPIRE agent               │                         │
       │                              │                         │
       │ 2. POST /token               │                         │
       │    grant_type=               │                         │
       │    client_credentials        │                         │
       │    client_assertion=         │                         │
       │    <SPIFFE JWT>              │                         │
       │ ────────────────────────────▶│                         │
       │                              │ 3. Fetch JWKS           │
       │                              │ ───────────────────────▶│
       │                              │◀────────────────────────│
       │                              │                         │
       │                              │ 4. Validate JWT         │
       │                              │    signature            │
       │                              │                         │
       │◀─────────────────────────────│                         │
       │ 5. Keycloak access token     │                         │
```

## Secrets Integration

### Vault-to-Keycloak Secret Flow

All sensitive values in the realm definition use `${PLACEHOLDER}` syntax.
The `rhbk` subchart resolves these placeholders from Kubernetes Secrets that are
populated by ExternalSecrets from Vault.

| Placeholder | Source Secret | Source Key | Vault Path |
| --- | --- | --- | --- |
| `QTODO_ADMIN_PASSWORD` | `keycloak-users` | `qtodo-admin-password` | `secret/data/hub/infra/users/keycloak-users` |
| `QTODO_USER1_PASSWORD` | `keycloak-users` | `qtodo-user1-password` | `secret/data/hub/infra/users/keycloak-users` |
| `RHTAS_USER_PASSWORD` | `keycloak-users` | `rhtas-user-password` | `secret/data/hub/infra/users/keycloak-users` |
| `RHTPA_USER_PASSWORD` | `keycloak-users` | `rhtpa-user-password` | `secret/data/hub/infra/users/keycloak-users` |
| `ACS_ADMIN_PASSWORD` | `keycloak-users` | `acs-admin-password` | `secret/data/hub/infra/acs/acs-central` |
| `RHTPA_CLI_SECRET` | `rhtpa-oidc-cli-secret` | `client-secret` | `secret/data/hub/infra/rhtpa/rhtpa-oidc-cli` |
| `ACS_CLIENT_SECRET` | `acs-oidc-client-secret` | `client-secret` | `secret/data/hub/infra/acs/acs-central` |

### PostSync Secret Cleanup

The `keycloak-users` ExternalSecret is created as an Argo CD Sync hook and
labeled with `validatedpatterns.io/cleanup: delete`. After the realm import
completes, a PostSync Job deletes these temporary secrets to reduce the
credential exposure window — the passwords are stored in Vault and in the
Keycloak database, not persisted as Kubernetes Secrets.

## Network Policies

When enabled via the `values-keycloak-network-policy.yaml` overlay (loaded by
default), comprehensive network segmentation is applied:

| Policy | Pod | Allowed Traffic |
| --- | --- | --- |
| `keycloak` | Keycloak server | Egress to: DNS, PostgreSQL, JGroups (clustering), K8s API, SPIRE OIDC (443) |
| `postgresql` | PostgreSQL database | Ingress from: Keycloak, realm import. Egress to: DNS only |
| `realmImport` | Realm import Job | Egress to: DNS, PostgreSQL, K8s API, Keycloak API (8443) |
| `operator` | Keycloak operator | Egress to: DNS, K8s API, Keycloak management (9000), Keycloak API (8443) |

## Component Integration

| Component | Client Used | Auth Flow |
| --- | --- | --- |
| [qtodo](multi-tier.md) | `qtodo-app` | Federated JWT via SPIFFE SVID |
| [ACS Central](acs-deployment.md) | `acs-central` | OIDC SSO (standard flow + direct access) |
| [RHTAS](supply-chain.md) | `trusted-artifact-signer` | Direct Access Grants |
| [RHTPA](supply-chain.md) | `rhtpa-cli` + `rhtpa-frontend` | Service account (CLI) + standard flow (UI) |

## Azure Entra ID Alternative

The pattern supports replacing Keycloak with Azure Entra ID as the OIDC
provider for downstream components. Two feature variants are available:

- `entra-id` — replaces OIDC for all components (qtodo, RHTAS, RHTPA, supply chain)
- `entra-id-qtodo` — replaces OIDC for qtodo only

When Entra ID features are enabled, the Keycloak deployment remains active but
is no longer the OIDC provider for the affected components. See the
[Entra ID integration guide](oidc/entraid.md) for configuration details.

## Accessing Keycloak

### Admin Console

The Keycloak admin console is available at:

```text
https://keycloak.apps.<domain>/admin/
```

Admin credentials:

```bash
# Username is 'admin'. Retrieve the password from Vault:
oc extract -n imperative secret/vaultkeys --to=- --keys=vault_data_json 2>/dev/null | \
  jq -r ".root_token"
```

### ZTVP Realm Endpoints

| Endpoint | URL |
| --- | --- |
| Realm metadata | `https://keycloak.apps.<domain>/realms/ztvp/.well-known/openid-configuration` |
| Token endpoint | `https://keycloak.apps.<domain>/realms/ztvp/protocol/openid-connect/token` |
| Authorization | `https://keycloak.apps.<domain>/realms/ztvp/protocol/openid-connect/auth` |
| JWKS | `https://keycloak.apps.<domain>/realms/ztvp/protocol/openid-connect/certs` |
| ztvp realm console | `https://keycloak.apps.<domain>/realms/ztvp/account/` |
