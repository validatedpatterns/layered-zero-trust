# Layered Zero Trust Validated Pattern — Documentation

This directory contains the engineering documentation for the Layered Zero Trust Validated Pattern (ZTVP). For the user-facing documentation, visit [validatedpatterns.io](https://validatedpatterns.io/patterns/layered-zero-trust/).

## Strategy & Planning

| Document | Description |
|---|---|
| [User Journeys](USER-JOURNEYS.md) | Persona-based user journeys mapping ZTVP capabilities to real-world security requirements across Security Architects, Platform Engineers, Compliance Officers, and Application Developers |
| [Security Framework Mapping](ZTVP-Security-Framework-Mapping.md) | Mapping of ZTVP capabilities to industry security framework controls (NIST SP 800-207, NIST SP 800-53, CISA Zero Trust Maturity Model, EO 14028) |

## Operations

| Document | Description |
|---|---|
| [Development](DEVELOPMENT.md) | Supported OCP versions, development workflow, credential access, and testing practices |
| [Support Matrix](support-matrix.md) | Validated combinations of OCP and pattern component versions |
| [Sync-Wave Inventory](SYNC-WAVE-INVENTORY.md) | Argo CD sync-wave assignments for all pattern components |

## Component Guides

| Document | Description |
|---|---|
| [ACS Deployment](acs-deployment.md) | Red Hat Advanced Cluster Security deployment workflow and configuration |
| [Keycloak](keycloak.md) | Red Hat Build of Keycloak deployment, realm configuration, and OIDC clients |
| [Vault](vault.md) | HashiCorp Vault deployment, secret management, and JWT authentication |
| [SPIRE / ZTWIM](spire.md) | Zero Trust Workload Identity Manager setup and SPIFFE identity management |
| [SPIRE CA Expiration](spire-ca-expiration-cluster-restart.md) | Handling SPIRE self-signed CA expiration on cluster restart |
| [Certificates](ztvp-certificates.md) | CA certificate extraction, validation, and rotation management |

## Use Cases

| Document | Description |
|---|---|
| [Secure Multi-tier Application](multi-tier.md) | Just-in-time credential fetching for the `qtodo` demo application |
| [Secure Supply Chain](supply-chain.md) | Building, signing, and verifying container images and artifacts |
| [Tekton Chains](tekton-chains.md) | Tekton Chains configuration for supply chain security in OpenShift Pipelines |

## Advanced Topics

| Document | Description |
|---|---|
| [Private Repositories](private-repos.md) | Deploying the pattern from a private Git repository |
| [Confidential Containers](CONFIDENTIAL-CONTAINERS.md) | Confidential Containers integration for trusted execution environments |
