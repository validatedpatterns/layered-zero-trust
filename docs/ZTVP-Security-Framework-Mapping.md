# ZTVP Capability-to-Framework Control Mapping

Mapping of Zero Trust Validated Pattern (ZTVP) capabilities to industry security framework controls.

---

## 1. Workload Identity (SPIFFE/SPIRE)

Cryptographic workload identity for service-to-service authentication.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenets 2, 6; §3.1.1 Enhanced Identity Governance; §3.1.2 Micro-Segmentation | Communications secured regardless of network location; dynamic authentication enforced before access |
| **NIST SP 800-207A** | §3 Identity-Based Segmentation; §3.1 SPIFFE ID | Explicitly references SPIFFE as workload identity framework; SVID as cryptographically verifiable identity document |
| **NIST SP 800-53 Rev 5** | IA-3 (Device Identification and Authentication), IA-3(1) (Cryptographic Bidirectional Authentication), IA-4 (Identifier Management), IA-4(6) (Cross-Organization Management), IA-5(2) (PKI-Based Authentication), IA-9 (Service Identification and Authentication), SC-23 (Session Authenticity) | Cryptographic device/service auth, identifier lifecycle, PKI-based workload credentials |
| **CISA ZTMM v2.0** | Identity Pillar — Authentication (Advanced/Optimal); Applications & Workloads Pillar — Application Access (Optimal) | Phishing-resistant, automated authentication for workloads; identity-aware application access |
| **EO 14028** | §3(a), §3(b) | Advance toward Zero Trust Architecture; adopt security best practices |
| **OMB M-22-09** | Action A.1 (centralized identity management); Action A.3 (device-level signals in authorization) | Enterprise-managed identities integrated into applications |
| **DoD ZT RA** | Pillar 1 (User): 1.5 Identity Federation & User Credentialing, 1.8 Continuous Authentication, 1.9 Integrated ICAM Platform | Non-person entity credentialing, continuous identity verification |

---

## 2. Secret Management (Vault + ESO)

Centralized secret storage, dynamic credentials, automatic rotation.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 5; §3.3 Trust Algorithm | Enterprise monitors and ensures assets are in the most secure state; trust algorithm requires current credential status |
| **NIST SP 800-53 Rev 5** | IA-5 (Authenticator Management), IA-5(6) (Protection of Authenticators), IA-5(7) (No Embedded Unencrypted Static Authenticators), SC-12 (Cryptographic Key Establishment and Management), SC-12(1) (Availability), SC-28 (Protection of Information at Rest), SC-28(1) (Cryptographic Protection) | Credential lifecycle management, prohibit embedded secrets, key management, encrypted storage |
| **CISA ZTMM v2.0** | Identity Pillar — Credential Management (Advanced/Optimal); Data Pillar — Data Encryption (Advanced) | Automated credential rotation, centralized secret lifecycle |
| **EO 14028** | §3(d) | Encrypt data at rest and in transit |
| **OMB M-22-09** | Action A.2 (strong MFA enterprise-wide) | Credential management underpins MFA enforcement |
| **DoD ZT RA** | Pillar 1 (User): 1.3 MFA, 1.4 Privileged Access Management (PAM) | Centralized credential management for privileged and service accounts |

---

## 3. User Identity (Keycloak OIDC)

User authentication, SSO, identity federation, MFA enforcement.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 6; §3.1.1 Enhanced Identity Governance; §6 ZTA and Existing Federal Guidance | Dynamic authentication strictly enforced; identity governance as primary ZTA approach |
| **NIST SP 800-53 Rev 5** | IA-2 (Identification and Authentication — Organizational Users), IA-2(1) (MFA for Privileged Accounts), IA-2(2) (MFA for Non-Privileged Accounts), IA-4 (Identifier Management), IA-5 (Authenticator Management), IA-8 (Identification and Authentication — Non-Organizational Users), IA-12 (Identity Proofing), AC-2 (Account Management) | User authentication, MFA, federated identity, SSO, account lifecycle |
| **CISA ZTMM v2.0** | Identity Pillar — Identity Management (Advanced/Optimal), Authentication (Advanced/Optimal), MFA (Advanced/Optimal) | Enterprise-managed identities, phishing-resistant MFA, automated lifecycle |
| **EO 14028** | §3(b) (zero trust architecture), §3(d) (MFA within 180 days) | Adopt ZTA principles; implement MFA for all users |
| **OMB M-22-09** | Action A.1 (centralized identity management), Action A.2 (phishing-resistant MFA), Action A.3 (device-level signal in authorization) | Consolidate identity providers; enforce phishing-resistant MFA at application layer |
| **DoD ZT RA** | Pillar 1 (User): 1.1 User Inventory, 1.2 Conditional User Access, 1.3 MFA, 1.5 Identity Federation & User Credentialing, 1.7 Least Privileged Access | User identity baseline, conditional access, federation, least privilege |

---

## 4. Certificate Management (cert-manager)

TLS certificate lifecycle automation, PKI certificate issuance and renewal.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 2; §3.4 Network/Environment Components | All communications secured regardless of network location |
| **NIST SP 800-53 Rev 5** | SC-12 (Cryptographic Key Establishment and Management), SC-13 (Cryptographic Protection), SC-17 (Public Key Infrastructure Certificates), IA-5(2) (PKI-Based Authentication), SC-8 (Transmission Confidentiality and Integrity), SC-8(1) (Cryptographic Protection for Transmission) | PKI certificate lifecycle, trust anchor management, TLS enforcement |
| **CISA ZTMM v2.0** | Networks Pillar — Traffic Encryption (Advanced/Optimal); Data Pillar — Data Encryption (Advanced) | Encrypt all internal traffic; automated certificate management |
| **EO 14028** | §3(d) | Adopt encryption for data in transit |
| **OMB M-22-09** | Action C (encrypt all DNS requests and HTTP traffic within their environment) | Mandatory encryption of all internal network traffic |
| **DoD ZT RA** | Pillar 5 (Network & Environment): 5.2 Software Defined Networking (SDN) | Encrypted communications infrastructure |

---

## 5. Artifact Signing (RHTAS/Sigstore)

Container image signing, code signing, transparency log (Rekor), policy enforcement.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 5 | Enterprise monitors integrity of all assets |
| **NIST SP 800-53 Rev 5** | SA-10 (Developer Configuration Management), SA-10(1) (Software and Firmware Integrity Verification), SI-7 (Software, Firmware, and Information Integrity), SI-7(1) (Integrity Checks), SI-7(6) (Cryptographic Protection), SI-7(15) (Code Authentication), SR-4 (Provenance), SR-4(3) (Validate as Genuine and Not Altered), SR-11 (Component Authenticity), AU-10 (Non-repudiation) | Code signing, integrity verification, provenance tracking, anti-counterfeit, non-repudiation via transparency log |
| **CISA ZTMM v2.0** | Applications & Workloads Pillar — Application Security (Advanced/Optimal); Governance (cross-cutting, Optimal) | Verified application integrity before deployment |
| **EO 14028** | §4(e) (software supply chain integrity verification), §4(e)(iii) (provenance of code), §4(e)(ix) (integrity and provenance of open source software) | Require integrity verification and provenance attestation in supply chain |
| **OMB M-22-09** | Action D (rigorous empirical testing of applications) | Applications must undergo integrity and security testing |
| **DoD ZT RA** | Pillar 3 (Applications & Workloads): 3.2 Secure Software Development & Integration, 3.3 Software Risk Management | Integrity verification in CI/CD, supply chain risk controls |

---

## 6. SBOM Analysis (RHTPA)

Software bill of materials generation, vulnerability analysis, dependency tracking.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 5, Tenet 7 | Monitor asset state; collect and use information about asset security posture |
| **NIST SP 800-53 Rev 5** | SR-3 (Supply Chain Controls and Processes), SR-4 (Provenance), SR-4(4) (Supply Chain Integrity — Pedigree), CM-8 (System Component Inventory), CM-8(3) (Automated Unauthorized Component Detection), RA-5 (Vulnerability Monitoring and Scanning), SA-4 (Acquisition Process — require SBOMs) | Supply chain controls, component provenance/pedigree, software inventory, vulnerability scanning |
| **CISA ZTMM v2.0** | Applications & Workloads Pillar — Application Security (Advanced/Optimal); Devices Pillar — Asset & Supply Chain Risk Management (Advanced) | Software supply chain transparency; component risk management |
| **EO 14028** | §4(e)(vii) (provide SBOM to purchaser), §4(f) (SBOM guidance), §10(j) (SBOM definition) | SBOM required for federal software procurement; NTIA minimum elements |
| **OMB M-22-09** | Action D (application security — rigorous empirical testing) | Applications tested for known vulnerabilities |
| **DoD ZT RA** | Pillar 3 (Applications & Workloads): 3.3 Software Risk Management | Bill of materials risk management, vulnerability management program |

---

## 7. Security Posture (ACS/StackRox)

Runtime monitoring, admission control, image scanning, network policy monitoring.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenets 4, 5, 7; §3.3 Trust Algorithm | Dynamic policy based on observable state; monitor and report asset security posture; collect information to improve security |
| **NIST SP 800-53 Rev 5** | CA-7 (Continuous Monitoring), SI-4 (System Monitoring), SI-4(2) (Automated Tools and Mechanisms for Real-Time Analysis), RA-5 (Vulnerability Monitoring and Scanning), RA-5(2) (Update Vulnerabilities to be Scanned), CM-2 (Baseline Configuration), CM-6 (Configuration Settings), AC-4 (Information Flow Enforcement), SC-7 (Boundary Protection) | Continuous monitoring, runtime threat detection, vulnerability scanning, configuration enforcement, admission control |
| **CISA ZTMM v2.0** | Applications & Workloads Pillar — Application Threat Protection (Advanced/Optimal); Visibility and Analytics (cross-cutting, Advanced/Optimal) | Runtime threat protection; continuous posture visibility |
| **EO 14028** | §3 (modernize cybersecurity), §7 (improving detection of vulnerabilities and incidents) | Continuous monitoring and detection capabilities |
| **OMB M-22-09** | Action D (application testing, vulnerability disclosure); Action B (EDR on all devices) | Continuous security testing; runtime threat detection |
| **DoD ZT RA** | Pillar 3 (Applications & Workloads): 3.5 Continuous Monitoring and Ongoing Authorizations; Pillar 7 (Visibility & Analytics): 7.1 Log All Traffic | Runtime monitoring, continuous authorization decisions |

---

## 8. Compliance Scanning (Compliance Operator)

CIS benchmarks, NIST profiles, OpenSCAP scanning, automated remediation.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 5 | Enterprise monitors all owned and associated assets to ensure most secure posture |
| **NIST SP 800-53 Rev 5** | CA-2 (Control Assessments), CA-2(2) (Specialized Assessments), CA-7 (Continuous Monitoring), CM-2 (Baseline Configuration), CM-3 (Configuration Change Control), CM-6 (Configuration Settings), CM-6(1) (Automated Management, Application, and Verification), RA-5 (Vulnerability Monitoring and Scanning), SI-2 (Flaw Remediation), SI-2(2) (Automated Flaw Remediation Status) | Automated control assessment, configuration baselines, continuous compliance monitoring, vulnerability remediation |
| **CISA ZTMM v2.0** | Devices Pillar — Policy Enforcement & Compliance Monitoring (Advanced/Optimal); Governance (cross-cutting, Advanced/Optimal) | Automated compliance enforcement; policy-driven governance |
| **EO 14028** | §3 (modernize cybersecurity), §3(a) (security best practices) | Adopt and maintain security baselines |
| **OMB M-22-09** | Action B (complete device inventory, EDR coverage, compliance) | Device compliance enforcement and posture management |
| **DoD ZT RA** | Pillar 2 (Device): 2.2 Device Detection and Compliance; Pillar 6 (Automation & Orchestration): 6.2 Critical Process Automation | Automated compliance scanning and remediation |

---

## 9. Network Segmentation (NetworkPolicies)

Default-deny policies, microsegmentation, namespace isolation.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §3.1.2 ZTA Using Micro-Segmentation; §3.1.3 ZTA Using Network Infrastructure and Software Defined Perimeters | Gateway-based micro-segmentation; infrastructure-level segmentation approaches |
| **NIST SP 800-53 Rev 5** | SC-7 (Boundary Protection), SC-7(5) (Deny by Default / Allow by Exception), SC-7(13) (Isolation of Security Tools), SC-7(20) (Dynamic Isolation and Segregation), SC-7(22) (Separate Subnets for Different Security Domains), AC-4 (Information Flow Enforcement), AC-4(21) (Physical/Logical Separation of Information Flows) | Default-deny network policy, dynamic micro-segmentation, flow enforcement, isolation |
| **CISA ZTMM v2.0** | Networks Pillar — Network Segmentation (Advanced/Optimal); Network Traffic Management (Advanced) | Microsegmentation of workloads; granular traffic control |
| **EO 14028** | §3(a), §3(b) (zero trust architecture) | Segment networks as part of ZTA adoption |
| **OMB M-22-09** | Action C (break down perimeters into isolated environments) | Execute plan to microsegment network |
| **DoD ZT RA** | Pillar 5 (Network & Environment): 5.1 Data Flow Mapping, 5.3 Macro Segmentation, 5.4 Micro Segmentation | Map data flows; enforce macro and micro network segmentation |

---

## 10. GitOps (Argo CD)

Infrastructure as code, declarative configuration, audit trail, drift detection.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 7; §7 Migrating to ZTA | Collect and use information about current state of assets; infrastructure monitoring during ZTA migration |
| **NIST SP 800-53 Rev 5** | CM-2 (Baseline Configuration), CM-2(2) (Automation Support for Accuracy and Currency), CM-3 (Configuration Change Control), CM-3(5) (Automated Security Response), CM-5 (Access Restrictions for Change), CM-9 (Configuration Management Plan), AU-2 (Event Logging), AU-3 (Content of Audit Records), AU-6 (Audit Record Review, Analysis, and Reporting), AU-12 (Audit Record Generation), SA-10 (Developer Configuration Management) | Declarative baselines, change control with audit trail, configuration drift detection, automated remediation |
| **CISA ZTMM v2.0** | Automation and Orchestration (cross-cutting, Advanced/Optimal); Governance (cross-cutting, Advanced/Optimal) | Automated policy enforcement and configuration management |
| **EO 14028** | §3 (modernize cybersecurity) | Infrastructure modernization via ZTA |
| **OMB M-22-09** | Action D (treat applications as internet-connected; rigorous testing) | Continuous application configuration management |
| **DoD ZT RA** | Pillar 6 (Automation & Orchestration): 6.1 Policy Decision Point (PDP), 6.2 Critical Process Automation | Automated policy enforcement and infrastructure management |

---

## 11. Multi-cluster Management (RHACM)

Policy distribution, governance, fleet-wide compliance, multi-cluster observability.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §4.2 Multi-cloud/Cloud-to-Cloud Enterprise; §3.1 Approaches to ZTA (combined approach) | ZTA for distributed multi-cloud environments |
| **NIST SP 800-53 Rev 5** | PL-8 (Security and Privacy Architectures), AC-4 (Information Flow Enforcement), CM-2 (Baseline Configuration), CM-9 (Configuration Management Plan), CA-7 (Continuous Monitoring), PM-9 (Risk Management Strategy), SI-4(16) (Correlating Monitoring Information) | Enterprise architecture governance, cross-environment policy enforcement, centralized monitoring |
| **CISA ZTMM v2.0** | Governance (cross-cutting, Advanced/Optimal); Automation and Orchestration (cross-cutting, Advanced/Optimal); Visibility and Analytics (cross-cutting, Advanced) | Enterprise-wide governance; automated policy distribution; centralized analytics |
| **EO 14028** | §3 (modernize cybersecurity across the enterprise) | Enterprise-wide ZTA adoption |
| **OMB M-22-09** | Action C (network segmentation strategy); Action A.1 (centralized identity integrated across environments) | Enterprise-wide policy consistency across environments |
| **DoD ZT RA** | Pillar 6 (Automation & Orchestration): 6.1 Policy Decision Point, 6.2 Critical Process Automation; Pillar 7 (Visibility & Analytics): 7.1 Log All Traffic, 7.2 Security Information and Event Management (SIEM) | Centralized policy decision and distribution; unified logging and analytics |

---

## 12. CI/CD Pipeline Security (Tekton + Chains)

Secure build pipelines, build attestation, provenance generation, in-toto compliance.

| Framework | Control IDs | Description |
|-----------|------------|-------------|
| **NIST SP 800-207** | §2.1 Tenet 5 | Monitor and ensure integrity of all owned infrastructure and assets |
| **NIST SP 800-53 Rev 5** | SA-10 (Developer Configuration Management), SA-10(1) (Software and Firmware Integrity Verification), SA-11 (Developer Testing and Evaluation), SA-11(1) (Static Code Analysis), SA-11(8) (Dynamic Code Analysis), SA-15 (Development Process, Standards, and Tools), SI-7 (Software, Firmware, and Information Integrity), SI-7(1) (Integrity Checks), SR-4 (Provenance), SR-4(3) (Validate as Genuine and Not Altered), SR-4(4) (Supply Chain Integrity — Pedigree), CM-14 (Signed Components) | Secure build pipelines, automated testing, build attestation, integrity verification, signed provenance records |
| **CISA ZTMM v2.0** | Applications & Workloads Pillar — Application Security (Advanced/Optimal); Automation and Orchestration (cross-cutting, Advanced) | Secure development lifecycle integrated into CI/CD; automated security gates |
| **EO 14028** | §4(e) (software supply chain security practices), §4(e)(iii) (provenance of source code), §4(e)(vi) (build integrity), §4(r) (secure software development attestation) | Supply chain integrity, build provenance, developer attestation requirements |
| **OMB M-22-09** | Action D (applications subjected to rigorous empirical testing) | Continuous security testing integrated into development lifecycle |
| **DoD ZT RA** | Pillar 3 (Applications & Workloads): 3.2 Secure Software Development & Integration, 3.3 Software Risk Management, 3.4 Resource Authorization & Integration | DevSecOps pipeline security, CI/CD authorization gates, supply chain risk management |

---

## Summary Cross-Reference Matrix

| # | ZTVP Capability | NIST 800-207 | NIST 800-53 Rev 5 (Primary Controls) | CISA ZTMM Pillar | EO 14028 | OMB M-22-09 | DoD ZT RA Capabilities |
|---|----------------|-------------|--------------------------------------|-------------------|----------|-------------|----------------------|
| 1 | Workload Identity | §2.1, §3.1.1, 207A§3 | IA-3, IA-3(1), IA-4, IA-9, SC-23 | Identity; Apps & Workloads | §3(a)(b) | A.1, A.3 | 1.5, 1.8, 1.9 |
| 2 | Secret Management | §2.1, §3.3 | IA-5, IA-5(7), SC-12, SC-28 | Identity; Data | §3(d) | A.2 | 1.3, 1.4 |
| 3 | User Identity | §2.1, §3.1.1, §6 | IA-2, IA-2(1)(2), IA-4, IA-8, AC-2 | Identity | §3(b)(d) | A.1, A.2, A.3 | 1.1, 1.2, 1.3, 1.5 |
| 4 | Certificate Mgmt | §2.1, §3.4 | SC-12, SC-13, SC-17, SC-8(1) | Networks; Data | §3(d) | C | 5.2 |
| 5 | Artifact Signing | §2.1 | SA-10(1), SI-7(1)(6)(15), SR-4(3), SR-11 | Apps & Workloads | §4(e) | D | 3.2, 3.3 |
| 6 | SBOM Analysis | §2.1 | SR-3, SR-4(4), CM-8, RA-5, SA-4 | Apps & Workloads; Devices | §4(e)(vii), §10(j) | D | 3.3 |
| 7 | Security Posture | §2.1, §3.3 | CA-7, SI-4, RA-5, CM-2, AC-4 | Apps & Workloads; V&A | §3, §7 | D, B | 3.5, 7.1 |
| 8 | Compliance Scan | §2.1 | CA-2, CA-7, CM-2, CM-6, RA-5, SI-2 | Devices; Governance | §3 | B | 2.2, 6.2 |
| 9 | Network Segmentation | §3.1.2, §3.1.3 | SC-7, SC-7(5)(20)(22), AC-4 | Networks | §3 | C | 5.1, 5.3, 5.4 |
| 10 | GitOps | §2.1, §7 | CM-2, CM-3, CM-5, AU-2, AU-12, SA-10 | A&O; Governance | §3 | D | 6.1, 6.2 |
| 11 | Multi-cluster Mgmt | §4.2, §3.1 | PL-8, AC-4, CM-2, CA-7, PM-9 | Governance; A&O; V&A | §3 | C, A.1 | 6.1, 6.2, 7.1, 7.2 |
| 12 | CI/CD Security | §2.1 | SA-10(1), SA-11, SA-15, SI-7, SR-4(3)(4) | Apps & Workloads; A&O | §4(e)(r) | D | 3.2, 3.3, 3.4 |

---

## Framework Reference Key

| Abbreviation | Full Name | Source |
|-------------|-----------|--------|
| NIST SP 800-207 | Zero Trust Architecture | [NIST](https://csrc.nist.gov/pubs/sp/800/207/final) |
| NIST SP 800-207A | ZTA for Cloud-Native Applications | [NIST](https://csrc.nist.gov/pubs/sp/800/207/a/final) |
| NIST SP 800-53 Rev 5 | Security and Privacy Controls | [NIST](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final) |
| CISA ZTMM v2.0 | Zero Trust Maturity Model Version 2.0 | [CISA](https://www.cisa.gov/zero-trust-maturity-model) |
| EO 14028 | Improving the Nation's Cybersecurity | [Federal Register](https://www.federalregister.gov/documents/2021/05/17/2021-10460/improving-the-nations-cybersecurity) |
| OMB M-22-09 | Federal Zero Trust Strategy | [OMB](https://www.whitehouse.gov/wp-content/uploads/2022/01/M-22-09.pdf) |
| DoD ZT RA v2.0 | DoD Zero Trust Reference Architecture | [DoD CIO](https://dodcio.defense.gov/Library/) |

### NIST 800-53 Rev 5 Control Family Legend

| Family | Name |
|--------|------|
| AC | Access Control |
| AU | Audit and Accountability |
| CA | Assessment, Authorization, and Monitoring |
| CM | Configuration Management |
| IA | Identification and Authentication |
| PL | Planning |
| PM | Program Management |
| RA | Risk Assessment |
| SA | System and Services Acquisition |
| SC | System and Communications Protection |
| SI | System and Information Integrity |
| SR | Supply Chain Risk Management |

### DoD Zero Trust Pillar and Capability Legend

| Pillar | Capabilities Referenced |
|--------|------------------------|
| 1 — User | 1.1 User Inventory, 1.2 Conditional User Access, 1.3 MFA, 1.4 PAM, 1.5 Identity Federation & User Credentialing, 1.7 Least Privileged Access, 1.8 Continuous Authentication, 1.9 Integrated ICAM Platform |
| 2 — Device | 2.2 Device Detection and Compliance |
| 3 — Applications & Workloads | 3.2 Secure Software Development & Integration, 3.3 Software Risk Management, 3.4 Resource Authorization & Integration, 3.5 Continuous Monitoring and Ongoing Authorizations |
| 5 — Network & Environment | 5.1 Data Flow Mapping, 5.2 Software Defined Networking, 5.3 Macro Segmentation, 5.4 Micro Segmentation |
| 6 — Automation & Orchestration | 6.1 Policy Decision Point, 6.2 Critical Process Automation |
| 7 — Visibility & Analytics | 7.1 Log All Traffic, 7.2 SIEM |

### CISA ZTMM Maturity Levels

| Level | Description |
|-------|-------------|
| Traditional | Manual processes and static policies |
| Initial | Beginning automation, some visibility |
| Advanced | Automated controls, centralized visibility, cross-pillar coordination |
| Optimal | Fully automated, dynamic policy enforcement, continuous optimization |
