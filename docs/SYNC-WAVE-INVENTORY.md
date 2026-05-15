# Argo CD Sync-Wave Inventory

All `argocd.argoproj.io/sync-wave` assignments in `layered-zero-trust`.

A +31 offset was applied to every value so that all waves are positive (>= 1), preserving the original relative ordering. This accommodates the Validated Patterns operator applying the Argo CD super-role later than before, which caused resources with negative sync waves to fail.

## Unified deployment timeline

Every sync-wave in the repository, in order. **App** = hub-level Argo CD Application creation. **chart** = resource inside a chart (resolved locally within that app's sync). **sub** = operator Subscription.

| Wave | Component | Scope | What |
| ---: | --- | --- | --- |
| 1 | compliance-scanning | **App** | Argo CD Application created on hub |
| 5 | acm | **App** | |
| 5 | rh-cert-manager | **App** | |
| 10 | acm-managed-clusters | **App** | |
| 21 | ztvp-certificates | **App** | |
| 21 | └ compliance-scanning | chart | apiserver-encryption, pvc, scan-setting, scan-setting-binding |
| 22 | └ ztvp-certificates | chart | RBAC (7 resources), configmap-script |
| 23 | └ ztvp-certificates | chart | ca-extraction-job-initial, ca-extraction-cronjob |
| 25 | vault | **App** | |
| 25 | └ ztvp-certificates | chart | managedclusterset-binding |
| 26 | └ ztvp-certificates | chart | distribution-policy (3 resources) |
| 26 | └ openshift-storage | ns | Namespace + OperatorGroup |
| 26 | └ rhtpa-operator | ns | Namespace + OperatorGroup |
| 27 | └ odf | sub | ODF operator install |
| 27 | └ rhtpa-operator | sub | RHTPA operator install |
| 28 | └ quay-operator | sub | Quay operator install |
| 29 | └ rhtas-operator | sub | RHTAS operator install |
| 30 | golang-external-secrets | **App** | |
| 30 | zero-trust-workload-identity-manager | **App** | |
| 31 | └ rhtpa-operator | chart | ingress-ca-job (SA, Role, RoleBinding, ConfigMap, Job) |
| 32 | └ rhtpa-operator | chart | operator-rolebinding (2 bindings) |
| 32 | └ noobaa-mcg | chart | default-backingstore |
| 32 | └ acs-central | chart | rbac/* (SA, Role, ClusterRole, bindings) |
| 32 | └ quay-enterprise | ns | Namespace |
| 32 | └ trusted-artifact-signer | ns | Namespace |
| 32 | └ trusted-profile-analyzer | ns | Namespace |
| 33 | └ rhtpa-operator | chart | ingress-ca-job (completion Job) |
| 33 | └ noobaa-mcg | chart | noobaa-system |
| 34 | └ rhtpa-operator | chart | oidc-cli-secret |
| 34 | └ noobaa-mcg | chart | bucket-class |
| 35 | rh-keycloak | **App** | |
| 36 | noobaa-mcg | **App** | |
| 36 | └ rhtpa-operator | chart | postgresql-serviceaccount, postgresql-external-secret, object-bucket-claim |
| 36 | └ keycloak | chart | keycloak.yaml (Keycloak CR) |
| 36 | └ quay-registry | chart | object-bucket-claim |
| 36 | └ acs-central | chart | admin-password-secret, central-htpasswd-external-secret, keycloak-client-secret-external-secret |
| 36 | └ qtodo | chart | truststore-secret-external-secret, registry-external-secret |
| 38+0 | └ qtodo | chart | registry-seed SA, ClusterRole, ClusterRoleBinding |
| 38+5 | └ qtodo | chart (hook) | registry-seed-image (Sync hook Job -- mirrors upstream image to configured registry) |
| 37 | └ quay-registry | chart | quay-s3-setup-serviceaccount (5 resources) |
| 37 | └ acs-central | chart | create-htpasswd-field (Job) |
| 38 | qtodo | **App** | |
| 38 | └ quay-registry | chart | quay-config-bundle-secret |
| 39 | └ rhtpa-operator | chart | s3-credentials-secret |
| 39 | └ quay-registry | chart | quay-s3-credentials-job |
| 41 | acs-central | **App** | |
| 41 | quay-registry | **App** | |
| 41 | trusted-profile-analyzer | **App** | |
| 41 | └ rhtpa-operator | chart | postgresql-statefulset, postgresql-service |
| 41 | └ keycloak | chart | keycloak-realm-import |
| 41 | └ quay-registry | chart | quay-registry (QuayRegistry CR) |
| 41 | └ acs-central | chart | central-cr (Central CR) |
| 41 | └ qtodo | chart | postgresql-statefulset, postgresql-service, qtodo-truststore-config |
| 43 | └ acs-central | chart | create-cluster-init-bundle (Job) |
| 44 | └ acs-central | chart | create-auth-provider (Job) |
| 46 | acs-secured-cluster | **App** | |
| 46 | trusted-artifact-signer | **App** | |
| 46 | └ acs-central | chart | console-link |
| 46 | └ acs-secured-cluster | chart | secured-cluster-cr |
| 46 | └ rhtas-operator | chart | securesign |
| 47 | tekton-chains | **App** | Tekton Chains config (RHTAS keyless signing) |
| 47 | └ tekton-chains | chart | tektonconfig-chains (TektonConfig CR) |
| 48 | supply-chain | **App** | |
| 48+0 | └ supply-chain | chart | registry-image-namespace (Namespace, RBAC), pipeline-sa, tasks (incl. restart-qtodo), secrets (quay-pass, rhtpa-pass), quay-user, rhtas/rhtpa-config, pipeline-qtodo-restarter (Role+RoleBinding in qtodo ns) |
| 48+1 | └ supply-chain | chart (hook) | enable-registry-default-route (Sync hook Job) |
| 48+10 | └ supply-chain | chart (hook) | registry-token-refresher-seed (Sync hook Job — writes SA token to Vault) |
| 48+15 | └ supply-chain | chart | qtodo-registry-auth ExternalSecret (reads token from Vault) |
| 49 | └ rhtpa-operator | chart | spiffe-helper-config |
| 51 | acs-policies | **App** | After ACS Central + Secured Cluster |
| 51 | └ rhtpa-operator | chart | trusted-profile-analyzer (supporting objects) |
| 51 | └ qtodo | chart | app-deployment, app-service |
| 51 | └ supply-chain | chart | workspaces |
| 71 | └ rhtpa-operator | chart | operator-readiness-check (SA, Role, Job) |
| 81 | └ rhtpa-operator | chart | trusted-profile-analyzer (Policy/CR) |

## Application-level waves (`values-hub.yaml`)

| Application | Old | Current | Comment |
| --- | ---: | ---: | --- |
| compliance-scanning | -30 | 1 | Earliest app |
| rh-cert-manager | — | 5 | Infrastructure, early (newly added) |
| acm | — | 5 | Infrastructure, early (newly added) |
| acm-managed-clusters | — | 10 | After ACM (newly added) |
| ztvp-certificates | -10 | 21 | Custom CA distribution |
| vault | — | 25 | Core secret store (newly added) |
| openshift-storage (OperatorGroup) | -5 | 26 | Propagated to OperatorGroup |
| rhtpa-operator (namespace) | -5 | 26 | Before operator subscription |
| odf (subscription) | -4 | 27 | After OperatorGroup (26) |
| rhtpa-operator (subscription) | -4 | 27 | After OperatorGroup (26) |
| quay-operator (subscription) | -3 | 28 | After ODF operator |
| rhtas-operator (subscription) | -2 | 29 | After Quay operator |
| golang-external-secrets | — | 30 | After Vault (newly added) |
| zero-trust-workload-identity-manager | — | 30 | After Vault/certs (newly added) |
| quay-enterprise (namespace) | 1 | 32 | Before NooBaa and Quay components |
| trusted-artifact-signer (namespace) | 1 | 32 | Auto-created by RHTAS operator |
| trusted-profile-analyzer (namespace) | 1 | 32 | Before RHTPA components |
| rh-keycloak | — | 35 | After ZTWIM for SPIFFE IdP (newly added) |
| noobaa-mcg | 5 | 36 | Deploy after core services |
| qtodo | — | 38 | After Keycloak, Vault (newly added) |
| acs-central | 10 | 41 | — |
| quay-registry | 10 | 41 | Deploy after NooBaa |
| trusted-profile-analyzer | 10 | 41 | Chart resources (OBC, DB, etc.) |
| acs-secured-cluster | 15 | 46 | — |
| trusted-artifact-signer | 15 | 46 | Deploy after dependencies |
| tekton-chains | — | 47 | After RHTAS, before supply-chain (newly added) |
| supply-chain | — | 48 | After RHTAS/ACS, before chart templates (newly added) |
| acs-policies | 20 | 51 | After ACS Central + Secured Cluster |

## Application-level waves (`values-coco-dev.yaml`)

The CoCo development configuration reuses several of the same components. Only the active `compliance-scanning` wave differs from the commented-out defaults; other entries are commented out but updated for consistency.

| Application | Old | Current | Comment |
| --- | ---: | ---: | --- |
| compliance-scanning | -30 | 1 | Earliest app |
| openshift-storage (OperatorGroup) | -5 | 26 | Commented; propagated to OperatorGroup |
| quay-enterprise (namespace) | 1 | 32 | Commented; before NooBaa and Quay components |
| trusted-artifact-signer (namespace) | 1 | 32 | Commented; auto-created by RHTAS operator |
| odf (subscription) | -4 | 27 | Commented; after OperatorGroup (26) |
| quay-operator (subscription) | -3 | 28 | Commented; after ODF operator |
| rhtas-operator (subscription) | -2 | 29 | Commented; after Quay operator |
| noobaa-mcg | 5 | 36 | Commented; deploy after core services |
| quay-registry | 10 | 41 | Commented; deploy after NooBaa |
| trusted-artifact-signer | 15 | 46 | Commented; deploy after dependencies |

## Chart-level waves (templates)

These control resource ordering within a single Application's sync. Template waves are resolved locally within each app, not globally across all apps.

Charts marked **(external)** have been externalized to standalone repositories managed under [validatedpatterns](https://github.com/validatedpatterns). Their resource-level sync-wave annotations are maintained in those repos, not here. The tables below reflect the +31 offset values that each external chart should carry.

### compliance-scanning — **(external)** `ocp-compliance-scanning-chart` v0.0.3 — App wave: 1

| Resource | Old | Current |
| --- | ---: | ---: |
| apiserver-encryption.yaml | -10 | 21 |
| pvc.yaml | -10 | 21 |
| scan-setting.yaml | -10 | 21 |
| scan-setting-binding.yaml | -10 | 21 |

### ztvp-certificates (`charts/ztvp-certificates/templates/`) — App wave: 21

| Resource | Old | Current |
| --- | ---: | ---: |
| rbac.yaml (7 resources) | -9 | 22 |
| configmap-script.yaml | -9 | 22 |
| ca-extraction-job-initial.yaml | -8 | 23 |
| ca-extraction-cronjob.yaml | -8 | 23 |
| managedclusterset-binding.yaml | -6 | 25 |
| distribution-policy.yaml (3 resources) | -5 | 26 |

### noobaa-mcg (`charts/noobaa-mcg/templates/`) — App wave: 36

| Resource | Old | Current |
| --- | ---: | ---: |
| default-backingstore.yaml | 1 | 32 |
| noobaa-system.yaml | 2 | 33 |
| bucket-class.yaml | 3 | 34 |

### keycloak — **(external)** `rhbk-chart` v0.0.4 — App wave: 35

| Resource | Old | Current |
| --- | ---: | ---: |
| keycloak.yaml | 5 | 36 |
| keycloak-realm-import.yaml | 10 | 41 |

### quay-registry — **(external)** `quay-chart` v0.1.3 — App wave: 41

| Resource | Old | Current |
| --- | ---: | ---: |
| object-bucket-claim.yaml | 5 | 36 |
| quay-s3-setup-serviceaccount.yaml (5 resources) | 6 | 37 |
| quay-config-bundle-secret.yaml | 7 | 38 |
| quay-s3-credentials-job.yaml | 8 | 39 |
| quay-registry.yaml | 10 | 41 |

### acs-central (`charts/acs-central/templates/`) — App wave: 41

| Resource | Old | Current |
| --- | ---: | ---: |
| rbac/* (SA, Role, ClusterRole, bindings) | 1 | 32 |
| admin-password-secret.yaml | 5 | 36 |
| central-htpasswd-external-secret.yaml | 5 | 36 |
| keycloak-client-secret-external-secret.yaml | 5 | 36 |
| create-htpasswd-field.yaml (Job) | 6 | 37 |
| central-cr.yaml | 10 | 41 |
| create-cluster-init-bundle.yaml (Job) | 12 | 43 |
| create-auth-provider.yaml (Job) | 13 | 44 |
| console-link.yaml | 15 | 46 |

### acs-secured-cluster (`charts/acs-secured-cluster/templates/`) — App wave: 46

| Resource | Old | Current |
| --- | ---: | ---: |
| secured-cluster-cr.yaml | 15 | 46 |

### rhtas-operator (`charts/rhtas-operator/templates/`) — App wave: 46

| Resource | Old | Current |
| --- | ---: | ---: |
| securesign.yaml | 15 | 46 |

### tekton-chains (`charts/tekton-chains/templates/`) — App wave: 47

| Resource | Old | Current |
| --- | ---: | ---: |
| tektonconfig-chains.yaml | — | 47 |

### rhtpa-operator (`charts/rhtpa-operator/templates/`) — App wave: 41

| Resource | Old | Current |
| --- | ---: | ---: |
| ingress-ca-job.yaml (SA, Role, RoleBinding, ConfigMap, Job) | 0 | 31 |
| operator-rolebinding.yaml (2 bindings) | 1 | 32 |
| ingress-ca-job.yaml (completion Job) | 2 | 33 |
| oidc-cli-secret.yaml | 3 | 34 |
| postgresql-serviceaccount.yaml | 5 | 36 |
| postgresql-external-secret.yaml | 5 | 36 |
| object-bucket-claim.yaml | 5 | 36 |
| s3-credentials-secret.yaml | 8 | 39 |
| postgresql-statefulset.yaml | 10 | 41 |
| postgresql-service.yaml | 10 | 41 |
| spiffe-helper-config.yaml | 18 | 49 |
| trusted-profile-analyzer.yaml (supporting objects) | 20 | 51 |
| operator-readiness-check.yaml (SA, Role, Job) | 40 | 71 |
| trusted-profile-analyzer.yaml (Policy/CR) | 50 | 81 |

### qtodo (`charts/qtodo/templates/`) — App wave: 38

| Resource | Old | Current |
| --- | ---: | ---: |
| registry-seed-job.yaml (SA, ClusterRole, ClusterRoleBinding) | --- | 0 |
| registry-seed-job.yaml (Sync hook Job) | --- | 5 |
| truststore-secret-external-secret.yaml | 5 | 36 |
| registry-external-secret.yaml | --- | 36 |
| postgresql-statefulset.yaml | 10 | 41 |
| postgresql-service.yaml | 10 | 41 |
| qtodo-truststore-config.yaml | 10 | 41 |
| app-deployment.yaml | 20 | 51 |
| app-service.yaml | 20 | 51 |

### supply-chain (`charts/supply-chain/templates/`) — App wave: 48

Resources without an explicit sync-wave default to wave 0. These include: pipeline-sa, pipeline-qtodo, tasks/* (incl. restart-qtodo), secrets/qtodo-quay-pass, secrets/qtodo-rhtpa-pass, rhtas-config, rhtpa-config, quay/quay-user-cm, quay/quay-user-job, pipeline-qtodo-restarter (Role+RoleBinding).

| Resource | Old | Current | Notes |
| --- | ---: | ---: | --- |
| registry-image-namespace.yaml (Namespace, RoleBinding, SA, ClusterRole, ClusterRoleBinding) | — | 0 | Foundation RBAC for embedded OpenShift registry |
| enable-registry-default-route (Sync hook Job) | — | 1 | Exposes the OpenShift image registry route |
| registry-token-refresher-seed (Sync hook Job) | — | 10 | Writes initial SA token to Vault |
| qtodo-registry-auth ExternalSecret | — | 15 | Reads registry token from Vault; must run after seed Job |
| workspaces.yaml | 20 | 51 | Pipeline PVCs |
| pipelinerun-qtodo.yaml (PostSync hook Job + RBAC) | — | — | Job wraps `oc create` of PipelineRun (PipelineRun is excluded from ArgoCD tracking) |
| pipeline-qtodo.yaml `finally` section | — | — | restart-qtodo Task runs after successful verify-image |

### docs/DEVELOPMENT.md (example snippet, not deployed)

| Resource | Old | Current |
| --- | ---: | ---: |
| noobaa-mcg example | 5 | 36 |

## Notes

- **"Old"** = value before the +31 offset. **"---"** = no sync-wave existed (defaulted to 0).
- **"Current"** = value after the +31 offset plus newly added application-level annotations.
- Template waves are resolved **locally within each app sync**, not globally. A template wave of 32 inside acs-central (app wave 41) does not conflict with a template wave of 32 inside noobaa-mcg (app wave 36); they run independently.
- Sync waves control **Application creation order**, not readiness. A later wave means the Application resource is submitted to the hub later, but the earlier app's pods may not be fully running yet. For hard readiness gates, use Argo CD health checks or resource hooks.
- **Externalized charts**: Five charts (certmanager, compliance-scanning, keycloak/RHBK, quay-registry, ZTWIM) are maintained in standalone repositories. Their resource-level sync-wave annotations are managed there and pinned via `chartVersion` in `values-hub.yaml`. Application-level sync-waves remain in this repository.
