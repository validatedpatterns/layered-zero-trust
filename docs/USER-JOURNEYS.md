# Zero Trust Validated Pattern — User Journeys

## Executive Summary

The Layered Zero Trust Validated Pattern (ZTVP) demonstrates how to implement Zero Trust principles on Red Hat OpenShift Container Platform. This document catalogs all ZTVP capabilities, maps them to industry security frameworks, and provides persona-based User Journeys that show how the pattern addresses real-world security requirements.

The ZTVP is organized into a layered architecture where each layer builds upon the capabilities below it, enabling organizations to adopt Zero Trust incrementally based on their specific use cases and maturity level.

---

## Part A: Layered Architecture

### Architecture Overview

The ZTVP follows a three-layer architecture model with a foundational platform layer:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 2: Use Cases                            │
│  Applications and workflows that demonstrate Zero Trust in      │
│  practice — data protection, supply chain security, runtime     │
│  threat detection                                               │
├─────────────────────────────────────────────────────────────────┤
│                 Layer 1: Feature Sets (Optional)                │
│  Additional components enabled per use case — artifact signing, │
│  SBOM analysis, private registry, CI/CD pipelines               │
├─────────────────────────────────────────────────────────────────┤
│                  Layer 0: Foundation (Core)                      │
│  Always-deployed security baseline — identity, secrets,         │
│  compliance, certificate management, security posture           │
├─────────────────────────────────────────────────────────────────┤
│              Validated Pattern Framework (Platform)              │
│  OCP + OpenShift GitOps (ArgoCD) + VP Operator                  │
└─────────────────────────────────────────────────────────────────┘
```

### Validated Pattern Framework (Platform)

The base platform provides the deployment substrate and GitOps-driven lifecycle management.

| Component | Description | ZT Contribution |
|---|---|---|
| **OpenShift Container Platform (OCP)** | Kubernetes platform with enterprise security features | Platform-level enforcement points for workloads, networking, RBAC, and admission control |
| **OpenShift GitOps (ArgoCD)** | GitOps continuous delivery | Single source of truth — every change is auditable, verifiable, and traceable to a Git commit |
| **Validated Patterns Operator** | Bootstraps the pattern, manages Hub/Spoke lifecycle | Automated, repeatable deployment with imperative job orchestration |

### Layer 0: Foundation (Always Deployed)

Layer 0 establishes the core security baseline. These components are always deployed and provide the prerequisite capabilities for all use cases.

| Component | Description | ZT Contribution |
|---|---|---|
| **Red Hat Build of Keycloak (RHBK)** | Identity and access management, OIDC provider | Centralized user authentication with SSO, federation (SPIFFE, Entra ID), fine-grained role-based access control. Manages the `ztvp` realm with per-application clients and roles. |
| **Zero Trust Workload Identity Manager (ZTWIM)** | SPIFFE/SPIRE-based workload identity | Cryptographic, short-lived workload identities (SVIDs) that prove a pod's identity without shared secrets. Enables workload-to-workload mTLS and Vault authentication. |
| **HashiCorp Vault** | Centralized secret management | Stores all sensitive credentials (DB passwords, OIDC secrets, API keys). Secrets are injected dynamically via SPIFFE identity, never stored as static Kubernetes secrets. |
| **External Secrets Operator (ESO)** | Secret synchronization from Vault to Kubernetes | Bridges Vault with Kubernetes — creates short-lived ExternalSecrets that are deleted after sync, minimizing secret exposure window. |
| **Cert-manager** | Certificate lifecycle management | Automates TLS certificate issuance and rotation via Let's Encrypt (ACME) and internal CAs. Ensures all communications use valid, non-expired certificates. |
| **ZTVP Certificates** | Cluster-wide CA distribution and management | Extracts ingress CA, service CA, and custom CAs; bundles and distributes them to target namespaces; configures cluster proxy trustedCA. Daily rotation via CronJob. |
| **Red Hat Advanced Cluster Security (ACS)** | Runtime security, admission control, vulnerability management | Continuous monitoring of workload behavior, admission-time policy enforcement, network policy monitoring, image vulnerability scanning. The "security brain" of the pattern. |
| **Compliance Operator** | CIS benchmark scanning and remediation | Validates cluster hardening against security profiles (CIS, NIST). Ensures enforcement points are operational and not bypassed. |
| **Red Hat Advanced Cluster Management (ACM)** | Multi-cluster governance and policy distribution | Propagates security policies across managed clusters. Distributes CA certificates, compliance requirements, and governance policies at scale. |

### Layer 1: Feature Sets (Optional)

Layer 1 components are optional and can be enabled based on the use cases an organization wants to implement. They are activated via the ZTVP feature variant system.

| Component | Description | ZT Contribution | Required For |
|---|---|---|---|
| **Red Hat Quay** | Private OCI container registry | Secure, trusted repository for container images within the environment. Prevents reliance on external, potentially compromised registries. | Supply chain use case (registry option 1) |
| **Multicloud Object Gateway (NooBaa MCG)** | S3-compatible object storage | Provides storage backend for Quay, RHTPA, and Network Observability. | Quay, RHTPA, Network Observability |
| **Red Hat Trusted Artifact Signer (RHTAS)** | Cryptographic signing via Sigstore (Fulcio, Rekor, TUF) | Keyless signing of artifacts and images using SPIFFE workload identity. Transparency log (Rekor) provides tamper-evident record of all signing events. | Supply chain use case |
| **Red Hat Trusted Profile Analyzer (RHTPA)** | SBOM storage, analysis, and CVE cross-referencing | Stores and analyzes Software Bills of Materials. Cross-references SBOMs with known vulnerabilities (CVEs) and Red Hat security advisories. | Supply chain use case |
| **Red Hat OpenShift Pipelines (Tekton)** | Cloud-native CI/CD | Provides the automation framework for build, sign, verify, and deploy workflows with per-task identity and attestation. | Supply chain use case |
| **Network Observability** | Loki-based network flow monitoring | Provides visibility into actual network traffic patterns. Enables verification that NetworkPolicies are enforcing intended segmentation. | Network security auditing |

### Layer 2: Use Case Implementations

Layer 2 contains the applications and workflows that demonstrate Zero Trust principles in practice.

| Use Case | Components Used | Description |
|---|---|---|
| **Data Protection (UC-12)** | qtodo app, SPIFFE/SPIRE, Vault, Keycloak, NetworkPolicies | Multi-tier application (Quarkus + PostgreSQL) where database credentials are fetched just-in-time from Vault using SPIFFE workload identity. User access controlled via Keycloak OIDC. Network segmentation via default-deny policies. |
| **Secure Supply Chain (UC-01/UC-02)** | Tekton, RHTAS, RHTPA, ACS, Quay | Automated pipeline that builds, signs (RHTAS/SPIFFE keyless), verifies, generates SBOM, uploads to RHTPA, and deploys with ACS policy checks at every stage. |
| **Network Segmentation** | NetworkPolicies, ACS monitoring | Default-deny NetworkPolicies in qtodo, keycloak-system, vault, and ZTWIM namespaces. Per-pod allow rules with explicit justification. ACS monitors for policy violations. |
| **Runtime Threat Detection** | ACS policies | Custom security policies: suspicious exec detection, runtime privilege escalation prevention, network policy enforcement warnings. |
| **Confidential Computing (CoCo)** | hello-coco, Sandboxed Containers, Trustee/KBS | *Status: Configuration exists but NOT functional.* TEE-based workload protection with sealed secrets via KBS. Requires specific hardware (AMD SEV-SNP). Planned for future enablement. |

---

## Part B: User Journeys

### Journey 1: Platform Engineer — "Deploying a Zero Trust Application"

**Persona:** Platform Engineer / DevOps Engineer

**Goal:** Deploy an application on OpenShift where every interaction — user login, database access, inter-service communication — is authenticated, authorized, and encrypted, without modifying application code.

**Starting Point:** A freshly provisioned OpenShift 4.20+ cluster with cluster-admin access.

**Why This Matters:**
> *"Zero trust assumes there is no implicit trust granted to assets or user accounts based solely on their physical or network location."* — NIST SP 800-207, Section 2.1

Traditional Kubernetes deployments store database credentials as static Secrets, use shared service accounts, and allow unrestricted network communication between pods. This journey shows how ZTVP eliminates each of these trust assumptions.

#### Step 1: Deploy the Pattern

The Platform Engineer forks the ZTVP repository, configures their secrets file, and runs the bootstrap:

```bash
./pattern.sh make install
```

ArgoCD takes over and deploys all Layer 0 components in a carefully orchestrated sequence (sync waves). Within 30-45 minutes, the cluster has:

- SPIRE server issuing workload identities
- Vault storing all secrets with SPIFFE-based authentication
- Keycloak managing user identities with per-application OIDC clients
- ACS monitoring all workloads and network flows
- Compliance Operator validating cluster hardening
- Default-deny NetworkPolicies isolating critical namespaces

**Framework Alignment:**
- NIST SP 800-207, Section 3.1: "ZTA using enhanced identity governance" — SPIRE provides cryptographic workload identity
- NIST SP 800-53 IA-2: "Identification and Authentication" — Keycloak provides multi-factor, federated authentication
- CISA ZTMM, Identity Pillar: "Agency uses phishing-resistant MFA and enterprise-managed identities"

#### Step 2: Observe the Sidecar Pattern

The qtodo application pod demonstrates the sidecar pattern — security functions are injected alongside the application container without code changes:

| Container | Role | ZT Function |
|---|---|---|
| `spiffe-helper` | Identity management | Obtains and rotates SPIFFE SVID (X.509 certificate) from the SPIRE Agent |
| `spiffe-vault-client` | Secret retrieval | Uses the SPIFFE SVID to authenticate with Vault and retrieve database credentials |
| `qtodo` | Application | Receives credentials from Vault sidecar; authenticates users via Keycloak OIDC |

The application developer never sees database credentials. The Platform Engineer never hardcodes secrets. Vault releases credentials only to pods with a valid SPIFFE identity that matches the configured role.

**Framework Alignment:**
- NIST SP 800-53 AC-4: "Information Flow Enforcement" — sidecars enforce data flow policies at the pod level
- NIST SP 800-53 IA-8: "Identification and Authentication (Non-Organizational Users)" — SPIFFE provides machine identity
- EO 14028, Section 3: "Modernizing Federal Government Cybersecurity" — zero trust architecture adoption
- OMB M-22-09, Action 3: "Applications are internet-accessible, agency-authorized, and authenticated"

#### Step 3: Verify Network Segmentation

The Platform Engineer verifies that the cluster enforces network isolation:

```
qtodo namespace:
  default-deny-in-namespace-qtodo  → Blocks ALL ingress and egress
  qtodo-network-policy             → Allows: OCP router→8443, →DB:5432, →Vault:8200, →DNS:5353, →HTTPS:443
  qtodo-db-network-policy          → Allows: qtodo→5432, →DNS:5353
```

Without these explicit allow rules, no pod can communicate with any other pod — even within the same namespace. This is the "default-deny" posture that NIST SP 800-207 prescribes.

**Framework Alignment:**
- NIST SP 800-207, Section 2.1, Tenet 4: "Access to individual enterprise resources is granted on a per-session basis"
- NIST SP 800-53 SC-7: "Boundary Protection" — NetworkPolicies act as micro-boundaries
- NIST SP 800-53 AC-4: "Information Flow Enforcement" — explicit flow rules per pod
- CISA ZTMM, Network Pillar: "Agency begins microsegmenting networks around critical applications"
- DoD ZT RA, Network Pillar: "Microsegmentation" capability

#### Step 4: Verify Certificate Trust

The Platform Engineer confirms that all inter-service communication uses TLS with certificates managed by cert-manager and distributed by the ZTVP Certificates chart:

- Ingress routes use Let's Encrypt or internal CA certificates
- Service-to-service communication uses OpenShift service-serving certificates
- The `ztvp-trusted-ca` ConfigMap bundles all CA certificates and is distributed to consuming namespaces
- A daily CronJob validates and rotates the CA bundle

**Framework Alignment:**
- NIST SP 800-53 SC-8: "Transmission Confidentiality and Integrity" — all data in transit encrypted
- NIST SP 800-53 SC-12: "Cryptographic Key Establishment and Management" — automated certificate lifecycle
- CISA ZTMM, Data Pillar: "Agency encrypts all data in transit"

#### Step 5: Observe Compliance Posture

The Compliance Operator continuously scans the cluster against security profiles:

- CIS Benchmark for OpenShift
- NIST 800-53 moderate baseline

ACS aggregates these findings alongside its own runtime observations, providing a single security dashboard.

**Framework Alignment:**
- NIST SP 800-53 CA-7: "Continuous Monitoring" — automated compliance scanning
- NIST SP 800-53 CM-6: "Configuration Settings" — enforced baseline configurations
- FedRAMP: Continuous monitoring requirement (ConMon)

#### Journey 1 Summary: Before vs. After

| Aspect | Traditional Deployment | ZTVP Deployment |
|---|---|---|
| **Workload Identity** | Shared Kubernetes service accounts | Cryptographic SPIFFE SVIDs per workload |
| **Database Credentials** | Static Kubernetes Secrets | Dynamic, just-in-time from Vault via SPIFFE |
| **User Authentication** | Application-managed or none | Centralized Keycloak OIDC with SSO |
| **Network Access** | Allow-all (Kubernetes default) | Default-deny with explicit per-pod allow rules |
| **Certificate Management** | Manual or ad-hoc | Automated via cert-manager with daily rotation |
| **Compliance** | Periodic manual audits | Continuous automated scanning |
| **Secret Exposure** | Secrets persist in etcd indefinitely | Secrets are ephemeral, deleted after sync |

---

### Journey 2: Security Architect — "Securing the Software Supply Chain"

**Persona:** Security Architect / DevSecOps Lead

**Goal:** Establish a secure software supply chain where every artifact is signed, verified, and traceable — from source code to deployed container image.

**Starting Point:** ZTVP Layer 0 deployed. The Security Architect enables Layer 1 supply chain features.

**Why This Matters:**
> *"The Federal Government shall identify existing or develop new standards, tools, best practices, and other guidelines for enhancing software supply chain security."* — Executive Order 14028, Section 4(e)

Software supply chain attacks (SolarWinds, Log4Shell, xz-utils) have demonstrated that trusting artifacts without verification is a critical vulnerability. This journey shows how ZTVP implements verifiable provenance for every artifact.

#### Step 1: Enable Supply Chain Features

The Security Architect enables the supply chain feature set by uncommenting the relevant sections in `values-hub.yaml` or using the feature variant system:

- ODF/NooBaa (S3 storage backend)
- Red Hat Quay (private registry)
- RHTAS (artifact signing)
- RHTPA (SBOM analysis)
- OpenShift Pipelines (Tekton)
- Tekton Chains (attestation)
- Supply Chain pipeline

ArgoCD deploys all components. The pipeline is pre-configured to build, sign, verify, and analyze the qtodo application.

#### Step 2: Run the Secure Build Pipeline

The Tekton pipeline executes 10 tasks in sequence:

| # | Task | ZT Function |
|---|---|---|
| 1 | `git-clone` | Clone source from verified Git repository |
| 2 | `build-artifact` | Build Java application (Mandrel/Maven native image) |
| 3 | `buildah-build` | Build container image |
| 4 | `push-image` | Push to Quay (private, authenticated registry) |
| 5 | `cosign-sign-image` | **Keyless sign** image using RHTAS + SPIFFE identity |
| 6 | `cosign-verify-image` | Verify signature against Rekor transparency log |
| 7 | `generate-sbom` | Generate SBOM using Syft |
| 8 | `cosign-attest-image` | Create signed attestation binding SBOM to image |
| 9 | `upload-sbom` | Upload SBOM to RHTPA for CVE analysis |
| 10 | `verify-image` | Final verification of image signature and attestation |

Every artifact produced by this pipeline has:
- A **cryptographic signature** tied to the build pipeline's SPIFFE identity (not a static key)
- A **transparency log entry** in Rekor (tamper-evident audit trail)
- A **Software Bill of Materials** cross-referenced against known CVEs
- A **signed attestation** binding the SBOM to the specific image digest

**Framework Alignment:**
- EO 14028, Section 4(e): "Guidelines for enhancing software supply chain security" — SBOM generation, artifact signing
- OMB M-22-09, Action 7: "Agencies make use of strong encryption, code-signing"
- NIST SP 800-53 SA-10: "Developer Configuration Management" — GitOps-managed pipeline definitions
- NIST SP 800-53 SA-11: "Developer Testing and Evaluation" — automated security checks in pipeline
- NIST SP 800-53 SR-3: "Supply Chain Controls and Processes" — signing, verification, SBOM
- NIST SP 800-53 SR-4: "Provenance" — Rekor transparency log provides immutable provenance chain
- CISA ZTMM, Applications & Workloads Pillar: "Agency integrates threat protections for all workloads"

#### Step 3: Verify in RHTPA

The Security Architect opens the RHTPA web interface and reviews:

- The uploaded SBOM with all dependencies listed
- CVE cross-references showing which dependencies have known vulnerabilities
- Red Hat security advisory (RHSA) mapping showing available fixes

This provides the evidence needed for compliance audits and risk assessments.

**Framework Alignment:**
- NIST SP 800-53 RA-5: "Vulnerability Monitoring and Scanning" — continuous CVE analysis
- NIST SP 800-53 SI-2: "Flaw Remediation" — actionable fix information from RHTPA

#### Step 4: ACS Policy Enforcement

ACS enforces runtime policies that complement the supply chain controls:

| Policy | Type | Action |
|---|---|---|
| Image signature verification | Admission | Block unsigned images from deploying |
| Privileged container prevention | Admission | Block containers requesting elevated privileges |
| Suspicious exec detection | Runtime | Alert on unexpected process execution in containers |
| Network policy enforcement | Monitoring | Warn on workloads missing NetworkPolicies |

**Framework Alignment:**
- NIST SP 800-53 CM-7: "Least Functionality" — only signed, verified images deploy
- NIST SP 800-53 SI-3: "Malicious Code Protection" — runtime behavioral monitoring
- NIST SP 800-53 SI-4: "System Monitoring" — continuous workload observation
- DoD ZT RA, Applications & Workloads Pillar: "Continuous application security validation"

#### Journey 2 Summary: Supply Chain Trust Chain

```
Developer → Git commit → Pipeline (SPIFFE identity) → Build → Sign (RHTAS keyless)
    → Verify (Rekor transparency log) → SBOM (Syft) → CVE Analysis (RHTPA)
    → Attestation (Tekton Chains) → Deploy (ACS admission check) → Monitor (ACS runtime)
```

Every link in this chain is cryptographically verifiable. No single compromised component can introduce an undetected malicious artifact.

---

### Journey 3: Compliance Officer — "Auditing Zero Trust Posture"

**Persona:** CISO / Compliance & Audit Officer

**Goal:** Demonstrate to auditors and stakeholders that the organization's Kubernetes environment meets Zero Trust requirements defined by federal mandates and industry frameworks.

**Starting Point:** ZTVP fully deployed with Layer 0 and relevant Layer 1 features. The Compliance Officer needs to produce audit evidence.

**Why This Matters:**
> *"The Federal Government must adopt security best practices; advance toward Zero Trust Architecture."* — Executive Order 14028, Section 3

Organizations increasingly face mandates to demonstrate Zero Trust maturity. This journey shows how ZTVP provides continuous, automated evidence for compliance audits.

#### Step 1: Compliance Operator Scan Results

The Compliance Operator continuously scans the cluster against:
- **CIS OpenShift Benchmark** — industry-standard hardening checks
- **NIST 800-53 Moderate** — federal security control baseline

Scan results are stored as Kubernetes custom resources (`ComplianceCheckResult`) and can be exported as OSCAP reports. The Compliance Officer can show auditors:
- Which controls pass, fail, or are not applicable
- Remediation status for failing controls
- Historical trends via periodic re-scans

**Framework Alignment:**
- NIST SP 800-53 CA-2: "Control Assessments" — automated control verification
- NIST SP 800-53 CA-7: "Continuous Monitoring" — ongoing compliance scanning
- FedRAMP: Annual assessment + continuous monitoring (ConMon)
- DoD ZT RA: "Visibility and Analytics" pillar — continuous compliance posture

#### Step 2: GitOps Audit Trail

Because all ZTVP configuration is managed through Git and deployed via ArgoCD:

- Every configuration change has a Git commit with author, timestamp, and approval (PR review)
- ArgoCD sync history shows when each change was applied to the cluster
- Drift detection alerts when cluster state diverges from Git
- No ad-hoc `kubectl apply` or manual changes — everything is code-reviewed

The Compliance Officer can provide auditors with:
- Git history as the change management log
- ArgoCD sync records as deployment evidence
- PR reviews as change approval documentation

**Framework Alignment:**
- NIST SP 800-53 CM-3: "Configuration Change Control" — Git-based change management
- NIST SP 800-53 AU-2: "Event Logging" — Git commits as audit events
- NIST SP 800-53 AU-3: "Content of Audit Records" — commit metadata (who, what, when)
- NIST SP 800-53 CM-6: "Configuration Settings" — ArgoCD enforces desired state

#### Step 3: ACS Security Dashboard

ACS Central provides a unified view across all managed clusters:

- **Vulnerability Management:** CVE exposure by namespace, deployment, and image
- **Compliance Dashboard:** CIS benchmark results aggregated across clusters
- **Risk Profiling:** Per-deployment risk scores based on configuration, vulnerabilities, and runtime behavior
- **Network Graph:** Visual representation of actual network flows vs. policy-allowed flows
- **Policy Violations:** Real-time alerts for security policy breaches

**Framework Alignment:**
- NIST SP 800-53 SI-4: "System Monitoring" — continuous security monitoring
- NIST SP 800-53 RA-3: "Risk Assessment" — automated risk scoring
- CISA ZTMM, Visibility & Analytics Pillar: "Agency uses automated tools for asset discovery and threat detection"
- DoD ZT RA: "Visibility and Analytics" — centralized security operations

#### Step 4: RHACM Policy Distribution

For organizations with multiple clusters, RHACM distributes and enforces security policies at scale:

- Governance policies ensure all clusters meet baseline requirements
- Certificate policies distribute CA trust bundles to managed clusters
- Configuration policies enforce consistent settings (e.g., audit logging, RBAC)
- Compliance status is aggregated in the ACM hub console

**Framework Alignment:**
- NIST SP 800-53 PL-8: "Security and Privacy Architectures" — centralized security governance
- NIST SP 800-53 CA-7: "Continuous Monitoring" — multi-cluster compliance aggregation
- OMB M-22-09: "Government-wide zero trust goals" — consistent enforcement across the organization

#### Step 5: Network Flow Visibility (with Network Observability)

When Network Observability is enabled, the Compliance Officer gains:
- Real-time flow data showing which pods communicate with which endpoints
- Evidence that NetworkPolicies are enforced (blocked flows are visible)
- Historical flow records for forensic analysis
- Dashboard views in the OpenShift Console

**Framework Alignment:**
- NIST SP 800-53 AU-12: "Audit Record Generation" — network flow logging
- NIST SP 800-53 SI-4: "System Monitoring" — network traffic analysis
- CISA ZTMM, Network Pillar: "Agency monitors and analyzes network traffic"

#### Journey 3 Summary: Audit Evidence Map

| Audit Question | ZTVP Evidence Source | Framework |
|---|---|---|
| "Are workloads authenticated?" | SPIRE SVID issuance logs, Keycloak authentication logs | NIST 800-207 §2.1, NIST 800-53 IA-2/IA-8 |
| "Are secrets properly managed?" | Vault audit log, ESO sync records | NIST 800-53 SC-12, SC-28 |
| "Is the cluster hardened?" | Compliance Operator scan results | NIST 800-53 CM-6, CA-2 |
| "Is network access controlled?" | NetworkPolicy definitions, ACS network graph, flow logs | NIST 800-53 AC-4, SC-7 |
| "Are changes tracked?" | Git history, ArgoCD sync records | NIST 800-53 CM-3, AU-2 |
| "Are images verified?" | RHTAS signatures, Rekor log, ACS admission checks | EO 14028 §4, NIST 800-53 SR-3/SR-4 |
| "Are vulnerabilities managed?" | ACS vulnerability dashboard, RHTPA CVE analysis | NIST 800-53 RA-5, SI-2 |
| "Is there continuous monitoring?" | ACS runtime monitoring, Compliance Operator re-scans | NIST 800-53 CA-7, SI-4, FedRAMP ConMon |

---

## Part C: Framework Compliance Matrix

### NIST SP 800-207 — Seven Tenets of Zero Trust

NIST SP 800-207 (Section 2.1) defines seven tenets that a Zero Trust Architecture must adhere to. The ZTVP addresses all seven:

| # | Tenet | ZTVP Implementation |
|---|---|---|
| 1 | All data sources and computing services are considered resources | Every component (databases, queues, identity providers) is protected independently with its own NetworkPolicies and access controls |
| 2 | All communication is secured regardless of network location | cert-manager + ZTVP Certificates ensure TLS everywhere; SPIFFE mTLS for workload-to-workload; default-deny NetworkPolicies |
| 3 | Access to individual enterprise resources is granted on a per-session basis | Vault issues short-lived, per-session credentials; SPIFFE SVIDs have a 1-hour TTL; Keycloak OIDC tokens are time-bounded |
| 4 | Access to resources is determined by dynamic policy | Vault policies gate access by SPIFFE identity; Keycloak role mappings are per-client; ACS admission policies are evaluated at deploy time |
| 5 | The enterprise monitors and measures the integrity and security posture of all owned and associated assets | Compliance Operator scans cluster hardening; ACS monitors workload behavior; RHTPA tracks CVEs in deployed images |
| 6 | All resource authentication and authorization are dynamic and strictly enforced before access is allowed | SPIRE continuously re-attests workloads; Vault requires valid SVID for every secret request; Keycloak validates tokens per request |
| 7 | The enterprise collects as much information as possible about assets, network infrastructure, and communications | ACS aggregates runtime telemetry; Network Observability captures flow data; Compliance Operator stores scan history; GitOps provides full change audit trail |

### ZTVP Capability to Framework Control Mapping

| ZTVP Capability | NIST SP 800-207 | NIST SP 800-53 Rev 5 | CISA ZTMM v2.0 | EO 14028 | OMB M-22-09 | DoD ZT RA |
|---|---|---|---|---|---|---|
| **Workload Identity (SPIFFE/SPIRE)** | §2.1 Tenets 2, 6; §3.1.1 (Enhanced Identity Governance); 800-207A §3 (SPIFFE ID) | IA-3 (Device ID/Auth), IA-3(1) (Crypto Bidirectional Auth), IA-4 (Identifier Mgmt), IA-9 (Service ID/Auth), SC-23 (Session Authenticity) | Identity: Advanced/Optimal; Apps & Workloads: Optimal | §3(a)(b) — ZTA adoption | A.1 (centralized identity), A.3 (device-level signals) | Pillar 1: 1.5 Identity Federation, 1.8 Continuous Auth, 1.9 Integrated ICAM |
| **Secret Management (Vault + ESO)** | §2.1 Tenets 3, 5, 6; §3.3 (Trust Algorithm) | IA-5 (Authenticator Mgmt), IA-5(7) (No Embedded Static Auth), SC-12 (Crypto Key Mgmt), SC-28 (Info at Rest), SC-28(1) (Crypto Protection) | Identity: Advanced (Credential Mgmt); Data: Advanced (Encryption) | §3(d) — encrypt data | A.2 (MFA enterprise-wide) | Pillar 1: 1.3 MFA, 1.4 PAM |
| **User Identity (Keycloak OIDC)** | §2.1 Tenets 1, 3, 6; §3.1.1; §6 | IA-2 (User Auth), IA-2(1)(2) (MFA), IA-4 (Identifier Mgmt), IA-8 (Non-Org Users), IA-12 (Identity Proofing), AC-2 (Account Mgmt) | Identity: Advanced/Optimal (Identity Mgmt, Auth, MFA) | §3(b)(d) — ZTA + MFA | A.1 (centralized identity), A.2 (phishing-resistant MFA), A.3 (device signals) | Pillar 1: 1.1 User Inventory, 1.2 Conditional Access, 1.3 MFA, 1.5 Federation, 1.7 Least Privilege |
| **Certificate Management (cert-manager + ZTVP Certs)** | §2.1 Tenets 2, 5 | SC-8 (Transmission Confidentiality), SC-12 (Crypto Key Mgmt), SC-13 (Cryptographic Protection), SC-17 (PKI Certificates) | Network: Initial-to-Advanced — automated cert lifecycle, CA distribution | — | — | Network Pillar: "Encryption" |
| **Artifact Signing (RHTAS/Sigstore)** | §2.1 Tenet 5 (asset integrity) | SA-10(1) (SW/FW Integrity), SI-7(1)(6)(15) (Integrity/Crypto/Code Auth), SR-4(3) (Validate Genuine), SR-11 (Component Authenticity), AU-10 (Non-repudiation) | Apps & Workloads: Advanced/Optimal (App Security); Governance: Optimal | §4(e) — supply chain integrity, §4(e)(iii) provenance | D (rigorous testing) | Pillar 3: 3.2 Secure SW Dev, 3.3 SW Risk Mgmt |
| **SBOM Analysis (RHTPA)** | §2.1 Tenets 5, 7 (asset state) | SR-3 (Supply Chain Controls), SR-4(4) (Pedigree), CM-8 (Component Inventory), CM-8(3) (Automated Detection), RA-5 (Vuln Monitoring), SA-4 (Acquisition/SBOM) | Apps & Workloads: Advanced/Optimal; Devices: Advanced (Supply Chain Risk) | §4(e)(vii) SBOM to purchaser, §4(f) SBOM guidance, §10(j) SBOM definition | D (app testing) | Pillar 3: 3.3 SW Risk Mgmt |
| **Security Posture (ACS/StackRox)** | §2.1 Tenets 4, 5, 7; §3.3 (Trust Algorithm) | CA-7 (Continuous Monitoring), SI-4 (System Monitoring), SI-4(2) (Real-Time Analysis), RA-5 (Vuln Monitoring), CM-2 (Baseline Config), AC-4 (Info Flow Enforcement) | Apps & Workloads: Advanced/Optimal (Threat Protection); V&A: Advanced/Optimal | §3, §7 (detection) | D (app testing), B (EDR) | Pillar 3: 3.5 Continuous Monitoring; Pillar 7: 7.1 Log All Traffic |
| **Compliance Scanning (Compliance Operator)** | §2.1 Tenet 5 | CA-2 (Control Assessments), CA-2(2) (Specialized Assessments), CA-7 (Continuous Monitoring), CM-2 (Baseline Config), CM-6(1) (Automated Verification), RA-5 (Vuln Monitoring), SI-2(2) (Automated Remediation) | Devices: Advanced/Optimal (Compliance Monitoring); Governance: Advanced/Optimal | §3, §3(a) (best practices) | B (device compliance) | Pillar 2: 2.2 Device Detection/Compliance; Pillar 6: 6.2 Critical Process Automation |
| **Network Segmentation (NetworkPolicies)** | §3.1.2 (Micro-Segmentation); §3.1.3 (SDP) | SC-7 (Boundary Protection), SC-7(5) (Deny by Default), SC-7(20) (Dynamic Isolation), SC-7(22) (Separate Subnets), AC-4 (Info Flow Enforcement) | Networks: Advanced/Optimal (Segmentation, Traffic Mgmt) | §3(a)(b) — ZTA adoption | C (microsegment networks) | Pillar 5: 5.1 Data Flow Mapping, 5.3 Macro Segmentation, 5.4 Micro Segmentation |
| **GitOps (ArgoCD)** | §2.1 Tenet 7; §7 (ZTA Migration) | CM-2 (Baseline Config), CM-3 (Change Control), CM-5 (Change Restrictions), AU-2 (Event Logging), AU-3 (Audit Content), AU-12 (Audit Generation), SA-10 (Developer Config Mgmt) | A&O: Advanced/Optimal; Governance: Advanced/Optimal | §3 (modernize) | D (app testing/config) | Pillar 6: 6.1 Policy Decision Point, 6.2 Critical Process Automation |
| **Multi-cluster Mgmt (RHACM)** | §4.2 (Multi-cloud Enterprise); §3.1 (Combined ZTA) | PL-8 (Security Architecture), AC-4 (Info Flow Enforcement), CM-2 (Baseline Config), CA-7 (Continuous Monitoring), PM-9 (Risk Mgmt Strategy), SI-4(16) (Correlate Monitoring) | Governance: Advanced/Optimal; A&O: Advanced/Optimal; V&A: Advanced | §3 (enterprise-wide) | C (segmentation), A.1 (centralized identity) | Pillar 6: 6.1 PDP, 6.2 Automation; Pillar 7: 7.1 Log All Traffic, 7.2 SIEM |
| **CI/CD Security (Tekton + Chains)** | §2.1 Tenet 5 (asset integrity) | SA-10(1) (SW/FW Integrity), SA-11 (Developer Testing), SA-15 (Dev Process/Standards), SI-7(1) (Integrity Checks), SR-4(3)(4) (Validate/Pedigree), CM-14 (Signed Components) | Apps & Workloads: Advanced/Optimal; A&O: Advanced | §4(e) supply chain, §4(e)(vi) build integrity, §4(r) dev attestation | D (rigorous testing) | Pillar 3: 3.2 Secure SW Dev, 3.3 SW Risk Mgmt, 3.4 Resource Auth |
| **Network Observability** | §2.1 Tenet 7 | AU-12 (Audit Record Generation), SI-4 (System Monitoring), IR-4 (Incident Handling), AU-6 (Audit Review/Analysis) | Networks: Advanced (Traffic Analysis); V&A: Advanced/Optimal | — | — | Pillar 5: 5.1 Data Flow Mapping; Pillar 7: 7.1 Log All Traffic |

### Coverage Summary by Framework

| Framework | Controls Addressed | Coverage Level |
|---|---|---|
| **NIST SP 800-207** | 7 of 7 tenets; §3.1.1 (Enhanced Identity), §3.1.2 (Micro-Segmentation), §3.1.3 (SDP), §3.3 (Trust Algorithm), §4.2 (Multi-cloud); 800-207A §3 (SPIFFE) | **High** — all core ZTA tenets implemented with concrete enforcement across three deployment approaches |
| **NIST SP 800-53 Rev 5** | 45+ controls with sub-controls across 12 families (IA, AC, SC, CM, AU, CA, SI, RA, SA, SR, PL, PM) | **High** — comprehensive coverage including sub-controls (e.g., SC-7(5) deny-by-default, IA-3(1) crypto auth, SI-7(15) code auth) |
| **CISA ZTMM v2.0** | 5 of 5 pillars + 3 of 3 cross-cutting capabilities; majority at Advanced/Optimal | **Advanced-to-Optimal** across Identity, Network, Apps & Workloads; **Advanced** across Governance, A&O, V&A |
| **EO 14028** | §3(a)(b)(d) (ZTA, MFA, encryption), §4(e) (supply chain), §4(f) (SBOM), §4(r) (attestation), §7 (detection) | **High** — directly addresses ZTA adoption, supply chain, SBOM, and detection mandates |
| **OMB M-22-09** | Actions A.1 (identity), A.2 (MFA), A.3 (device signals), B (EDR/compliance), C (network segmentation), D (app security) | **Moderate-High** — 6 of 9 strategic goals addressed; primary gap is Action E (data categorization) |
| **DoD ZT RA** | Pillars 1 (User), 2 (Device), 3 (Apps), 5 (Network), 6 (Automation), 7 (Visibility); 22+ specific capabilities | **High** — covers 6 of 7 pillars with specific capability numbers; gap in Pillar 4 (Data) addressed partially by Vault |

*For the complete per-capability breakdown with detailed descriptions, see [ZTVP-Security-Framework-Mapping.md](ZTVP-Security-Framework-Mapping.md).*

### Framework Gap Analysis

| Framework Area | Current Gap | How to Address |
|---|---|---|
| **CISA ZTMM — Devices** | ZTVP does not manage device trust (laptop MDM, OS patching) | Out of scope for a Kubernetes pattern; addressed by enterprise endpoint management |
| **OMB M-22-09 — Action 2** (Devices) | No device health check before granting access | Same as above; could partially address with OCP node attestation |
| **OMB M-22-09 — Action 6** (DNS) | No encrypted DNS enforcement | Could add DNS-over-TLS configuration in future |
| **DoD ZT RA — Endpoint** | No endpoint security integration | Out of scope; addressed by enterprise EDR/XDR solutions |
| **NIST 800-53 — PE family** | Physical security controls not addressed | Out of scope for a software pattern |

---

## Part D: Use Case Catalog

### Implemented Use Cases

| ID | Use Case | Status | ZTVP Components | Layer |
|---|---|---|---|---|
| UC-12 | **Data Protection** | **Fully Implemented** | qtodo app, SPIFFE/SPIRE, Vault, Keycloak OIDC, NetworkPolicies, cert-manager | L0 + L2 |
| UC-01 | **DevSecOps (Pipeline)** | **Implemented** (optional feature set) | Tekton, Tekton Chains, RHTAS, ACS admission/runtime policies | L1 + L2 |
| UC-02 | **Supply Chain** | **Implemented** (optional feature set) | RHTAS signing, RHTPA SBOM analysis, Rekor transparency log, Quay | L1 + L2 |
| UC-06 | **ZT Control Plane (partial)** | **Partially Implemented** | Keycloak (user identity), SPIRE (workload identity), Vault (secrets), ACM (policy distribution), ACS (security posture), Compliance Operator (hardening) | L0 |

### Planned / Future Use Cases

| ID | Use Case | Status | Notes | Dependencies |
|---|---|---|---|---|
| UC-04 | **Privacy Protection** | Planned | CoCo integration exists but non-functional. Requires TEE hardware (AMD SEV-SNP) and updated configuration. | Hardware, CoCo operator maturity |
| UC-05 | **AI in Org** | Not Started | Would require RHOAI integration, data segregation controls, model provenance tracking. | RHOAI, CoCo for model protection |
| UC-03 | **Hybrid Cloud** | Not Started | Currently single-cluster. Would require SPIFFE federation across cloud providers, multi-cluster Vault. | Multi-cloud infrastructure |
| UC-07 | **Edge Control Plane** | Not Started | Would require edge-optimized SPIRE deployment, disconnected/intermittent policy enforcement. | MicroShift or SNO at edge |
| UC-08 | **Ransomware** | Not Started | Would require backup/recovery integration, immutable storage, rapid isolation capabilities. | Storage/backup vendor integration |
| UC-09 | **Edge** | Not Started | Workload authorization at edge, edge-to-core trust establishment. | Edge infrastructure |
| UC-10 | **Remote Work** | Not Started | BYOD device trust, location-independent access policies. | VPN/SASE integration |
| UC-11 | **Insider Threat** | Not Started | Privilege escalation detection, group access revocation, UBA. | Advanced ACS policies, Keycloak lifecycle |
| UC-13 | **Business Continuity** | Not Started | DR/COOP scenarios with ZT policy preservation. | Multi-site deployment |
| UC-14 | **HPC** | Not Started | Trusted compute offloading, federated data access. | CoCo, HPC infrastructure |
| UC-15 | **Telco / 5G** | Not Started | RAN security, MEC tenant isolation, VNF policy enforcement. | Telco infrastructure |
| UC-16 | **Digital Sovereignty** | Not Started | Jurisdictional boundary enforcement, sovereign key management. | Multi-region, KMS integration |
| UC-17 | **Human Resources** | Not Started | Identity lifecycle (onboarding/offboarding), least-privilege provisioning. | HR system integration |
| UC-18 | **Infrastructure** | Not Started | Hardware trust, TPM attestation, trusted computing base. | Hardware attestation support |

### Key Personas and Use Case Alignment

| Persona | Primary Use Cases | ZTVP Journey |
|---|---|---|
| **Platform Engineer** | UC-12 (Data Protection), UC-06 (Control Plane) | Journey 1: Deploy Zero Trust Application |
| **Security Architect** | UC-01 (DevSecOps), UC-02 (Supply Chain) | Journey 2: Secure Supply Chain |
| **CISO / Compliance Officer** | UC-06 (Control Plane), all use cases | Journey 3: Audit Zero Trust Posture |
| **Developer** | UC-01 (DevSecOps), UC-12 (Data Protection) | Consumes Journey 1 outcomes |
| **LOB Manager** | UC-12 (Data Protection), UC-08 (Ransomware) | Business justification via Journey 3 |

---

## Appendix A: Component Feature Variant System

The ZTVP uses a feature variant system that allows organizations to compose their deployment by enabling specific feature sets. Features are declared in `scripts/features/` and composed into the final `values-hub.yaml`.

| Feature Flag | Components Added | Dependencies |
|---|---|---|
| `storage` | ODF operator, NooBaa MCG | None |
| `quay` | Quay operator + chart | `storage` |
| `rhtas` | RHTAS operator + chart | None |
| `rhtpa` | RHTPA operator + chart | `storage` |
| `pipelines` | OpenShift Pipelines operator | None |
| `tekton-chains` | Tekton Chains configuration | `pipelines`, `rhtas` |
| `supply-chain` | Full supply chain pipeline | `tekton-chains`, `rhtpa`, `storage` |
| `protected-repos` | Private Git repository support | `supply-chain` |
| `entra-id` | Azure Entra ID integration (full) | `supply-chain` |
| `entra-id-qtodo` | Azure Entra ID for qtodo only | None |

## Appendix B: ZTVP Deployment Variants

| Variant | Description | Use Case |
|---|---|---|
| `values-hub.yaml` | Primary hub cluster | Full ZTVP deployment |
| `values-devel.yaml` | Development spoke cluster | Minimal with ESO + Pipelines |
| `values-group-one.yaml` | Generic spoke cluster | Minimal with ESO only |
| `values-standalone.yaml` | Standalone (no hub) | Vault + ESO only for development |
| `values-coco-dev.yaml` | Confidential Computing development | Adds CoCo, Trustee/KBS, hello-coco |
