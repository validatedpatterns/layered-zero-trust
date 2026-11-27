# Layered Zero Trust Uninstall Procedure

This procedure removes the Layered Zero Trust Validated Pattern (ZTVP) from an OpenShift cluster. It uses the experimental uninstall flow in the Validated Patterns Operator and then audits resources that the flow intentionally retains.

The accompanying automation is [`scripts/ztvp_uninstall.py`](../scripts/ztvp_uninstall.py). Run it from the repository root with Python 3 and the `oc` CLI available.

> [!IMPORTANT]
> Deleting a Pattern is destructive. Back up application data and, when possible, record the cluster's pre-install state before starting. A pre-install baseline enables the strongest ownership and trust comparisons. If ZTVP is already installed and no baseline exists, use the separate current-inventory workflow below: it protects likely pre-existing and ambiguous resources tracked by the target Argo tree, but cannot prove full ownership, restore original Proxy/Image trust values, or support a strict zero-residue claim. OpenShift OLM may retain operator CRDs, API services, and custom resources after operator removal. Review the final audit in either workflow.

## Scope and expected result

The Pattern Operator removes the pattern's Argo CD applications in dependency order. The Validated Patterns Operator and the cluster-wide OpenShift GitOps installation remain installed by design. They are framework components that may be used by other patterns or platform workloads. A separate `ArgoCD` instance, such as `vp-gitops`, can remain after the Pattern is gone; remove it only after confirming it is new and dedicated to this Pattern.

ZTVP installs a base stack and can add feature sets such as ODF/NooBaa storage, Quay, Network Observability, RHTAS, RHTPA, OpenShift Pipelines/Tekton Chains, secure supply chain, private repository integration, Entra ID integration, and User-Defined Networks. Local `values-hub.yaml`, generated feature values, overrides, and custom edits determine what is actually present. Use the deployed repository revision and live cluster inventory as the source of truth; the default component list is not a complete inventory for a customized installation.

Use this source-based checklist to make the inventory feature-aware. Names can change in customized values, and the listed namespaces can be shared or pre-existing, so verify ownership before deleting them.

| Configuration | Inventory to check |
| --- | --- |
| Base ZTVP | `open-cluster-management` (ACM), `stackrox` (ACS), `openshift-compliance`, `cert-manager-operator` and `cert-manager`, `external-secrets-operator` and `external-secrets`, `keycloak-system`, `zero-trust-workload-identity-manager`, `vault`, `qtodo`, `qtodo-db`, and `openshift-config`. Check subscriptions, operator instances, CRs, Argo apps, and cluster-scoped objects for each. |
| `storage` | `openshift-storage`, ODF subscription/operator, NooBaa MCG, object-storage CRs, and PVC/PV-backed data. |
| `quay` | `quay-enterprise`, Quay subscription/operator (often in `openshift-operators`), Quay CRs, registry storage, and registry data. |
| `netobserv` | `openshift-operators-redhat`, `openshift-netobserv-operator`, `netobserv-loki`, and `netobserv`; Loki and Network Observability CRs and stored flow data. Depends on `storage`. |
| `rhtas` | `trusted-artifact-signer`, RHTAS operator/subscription, signing and transparency service CRs, and persisted artifact data. |
| `rhtpa` | `rhtpa-operator`, `trusted-profile-analyzer`, RHTPA operator/subscription, CRs, and database/object-storage data. Depends on `storage`. |
| `pipelines`, `tekton-chains`, or `supply-chain` | `openshift-pipelines`, OpenShift Pipelines subscription/operator (the subscription can be in shared `openshift-operators`), Tekton CRs and runs, and supply-chain application resources. The `TektonConfig/config` is annotated `Delete=false` and must be audited separately; its lifecycle belongs to the Pipelines operator and it may be shared. |
| `protected-repos`, Entra ID, registry choices | Check generated overrides, Vault roles/secrets, Git credentials, external identity-provider registrations, and the selected registry. BYO registry or Entra ID resources outside the cluster are not removed by deleting a Pattern. |
| `udn` | The `qtodo-isolated-network` `ClusterUserDefinedNetwork` plus related MultiNetworkPolicies and network annotations. Verify no other namespace/workload uses the network before removal. |

The base chart also manages cluster trust through `ztvp-certificates`; optional image pull trust can change `Image/cluster`. These cluster-scoped changes need comparison with the pre-install snapshots even when their Argo Applications are gone.

The normal uninstall removes Pattern-managed Argo applications, namespaced workloads, and their subscriptions/namespaces when those resources are exclusively owned by the Pattern. It does not automatically guarantee removal of:

- OLM-owned CRDs, APIService objects, or custom resources. OLM retains these to avoid data loss.
- Operators or resources that were already installed before ZTVP, shared with another application, or installed in shared namespaces such as `openshift-operators`.
- Cluster-scoped OpenShift configuration that ZTVP changed, including `Proxy/cluster` when the ZTVP certificates chart manages `spec.trustedCA`. Restore only the fields changed by ZTVP to their recorded pre-install values; never delete the OpenShift singleton object.
- Broken or unrelated API services that block namespace deletion. A namespace finalizer override does not remove the APIService or make that API healthy.

If an installation baseline was not recorded and ownership cannot be established, leave ambiguous cluster-scoped resources in place and report the remaining inventory. Their age alone is not proof that a resource belongs to ZTVP.

## 1. Preflight and inventory

Use an account with cluster-admin privileges. Confirm the active context and identify the exact Pattern object; installations may use different Pattern namespaces.

```sh
oc whoami
oc whoami --show-server
oc get patterns.gitops.hybrid-cloud-patterns.io -A
```

Confirm the installed Patterns Operator is at least `0.0.65`, the version that introduced experimental uninstall support. Find its CSV and version with:

```sh
oc get csv -A | grep -i patterns-operator
```

If the operator is installed by another method and has no CSV, inspect the controller Deployment image tag. Follow the operator's supported upgrade process if it is older; do not try to uninstall by deleting Argo applications directly.

Record the Pattern name and namespace from the previous output. In the commands below, replace these placeholders with the actual values:

```sh
PATTERN_NAME=layered-zero-trust
PATTERN_NAMESPACE=patterns-operator
ROOT_APPLICATION=vp-gitops/layered-zero-trust-hub
oc get pattern "$PATTERN_NAME" -n "$PATTERN_NAMESPACE" -o yaml > pattern-before-uninstall.yaml
```

Replace the sample values if the installed Pattern, namespace, or root Application differs.

Store the inventory and backups securely. Pattern objects and related resources can contain references to credentials or sensitive configuration. At minimum, record:

```sh
oc get applications.argoproj.io -A -o wide > applications-before.txt
oc get argocds.argoproj.io,appprojects.argoproj.io -A -o wide > argocd-instances-before.txt
oc get subscriptions.operators.coreos.com,csv.operators.coreos.com,operatorgroups.operators.coreos.com -A -o wide > olm-before.txt
oc get operators.operators.coreos.com -o wide > operators-before.txt
oc get namespaces -o name > namespaces-before.txt
oc get crd -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp > crds-before.txt
oc get apiservices.apiregistration.k8s.io -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp > apiservices-before.txt
oc get proxy.config.openshift.io/cluster -o yaml > proxy-before.yaml
oc get image.config.openshift.io/cluster -o yaml > image-config-before.yaml
```

The `Proxy/cluster` and `Image/cluster` snapshots are needed only to compare/restore fields if the pattern changed them. Keep backups out of Git. Capture any other cluster-scoped objects, namespace contents, and persistent data identified in the customized values and enabled feature set.

### Run the Python automation

Capture a baseline before installing ZTVP. Without `--execute`, `uninstall` only builds and prints a plan:

```sh
python3 scripts/ztvp_uninstall.py snapshot --output ztvp-preinstall-baseline.json
python3 scripts/ztvp_uninstall.py uninstall \
  --baseline ztvp-preinstall-baseline.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION"
```

After completing the preflight and protecting any retained resources, execute the exact plan. Use the confirmation string printed by plan mode:

```sh
python3 scripts/ztvp_uninstall.py uninstall \
  --baseline ztvp-preinstall-baseline.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --execute --ack-preflight \
  --expected-server "$(oc whoami --show-server)" \
  --confirm '<exact confirmation string printed by plan mode>'
```

After the Pattern and target Applications are gone, run `finalize` to restore retained pre-existing state and write the report. If you then remove confirmed OLM or GitOps leftovers manually, run `audit` again so the report reflects the final cluster state:

```sh
python3 scripts/ztvp_uninstall.py finalize \
  --baseline ztvp-preinstall-baseline.json \
  --pre-uninstall ztvp-uninstall-artifacts/pre-uninstall.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --artifacts-dir ztvp-uninstall-artifacts

python3 scripts/ztvp_uninstall.py audit \
  --baseline ztvp-preinstall-baseline.json \
  --pre-uninstall ztvp-uninstall-artifacts/pre-uninstall.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --artifacts-dir ztvp-uninstall-artifacts
```

The script deliberately leaves OLM-retained APIs and ambiguous shared resources for administrator review. Read the complete report; a successful Pattern phase or script exit code alone does not prove a strict zero-residue result.

### If ZTVP is already installed and there is no pre-install baseline

Do not pass a post-install snapshot to `--baseline`. It contains the target Pattern and root Application, so the script correctly rejects it as an invalid pre-install baseline. Instead, capture it as a **current-install inventory**. This inventory is an operational record of what exists now; it is not evidence of what existed before ZTVP.

This inventory-based uninstall command targets the hub cluster that contains the Pattern CR and root Argo Application. For ACM spokes, the hub operator still coordinates child-application deletion, but this command cannot inspect spoke kubeconfig secrets. Capture and review each spoke separately where access is available; do not run the Pattern uninstall against a spoke.

```sh
python3 scripts/ztvp_uninstall.py inventory --output ztvp-current-inventory.json
python3 scripts/ztvp_uninstall.py uninstall \
  --inventory ztvp-current-inventory.json \
  --best-effort \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION"
```

Review the plan, enabled features, PVCs, backups, spoke reachability, shared resources, and external integrations in the preflight checklist below. The script checks that the inventory was captured from the current API server and that the Pattern, root Application, Application tree, and tracked-resource identities have not changed. If those checks fail, take a fresh inventory and review the new plan.

In this mode, the script uses creation times relative to the Pattern as a heuristic. It automatically adds and verifies Argo CD's `Delete=false` option for tracked resources created before the Pattern and for resources with missing or ambiguous timestamps. It records their original sync options, removes only the safeguards it added after the target Application tree is gone, and removes a tracking annotation only when it exactly matches the captured target Argo Application. It leaves namespace ownership labels and other uncertain metadata for review. A resource created after the Pattern may still have been pre-existing and recreated or adopted later; timestamps cannot prove ownership.

After reviewing the plan and completing the preflight checklist below, run the same command with the explicit execution flags and the exact confirmation string printed by plan mode:

```sh
python3 scripts/ztvp_uninstall.py uninstall \
  --inventory ztvp-current-inventory.json \
  --best-effort \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --execute --ack-preflight \
  --expected-server "$(oc whoami --show-server)" \
  --confirm '<exact confirmation string printed by plan mode>'
```

If deletion was already started before the script ran, it can protect eligible resources that still exist, but cannot recover anything Argo has already deleted. If the Pattern phase stalls, resume with the same `--inventory`, `--best-effort`, and `--artifacts-dir` values. Once the Pattern and target Applications are gone, finalize and audit using the saved pre-uninstall inventory:

```sh
python3 scripts/ztvp_uninstall.py finalize \
  --inventory ztvp-current-inventory.json \
  --pre-uninstall ztvp-uninstall-artifacts/pre-uninstall.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --artifacts-dir ztvp-uninstall-artifacts

python3 scripts/ztvp_uninstall.py audit \
  --inventory ztvp-current-inventory.json \
  --pre-uninstall ztvp-uninstall-artifacts/pre-uninstall.json \
  --pattern "$PATTERN_NAME" \
  --namespace "$PATTERN_NAMESPACE" \
  --root-application "$ROOT_APPLICATION" \
  --artifacts-dir ztvp-uninstall-artifacts
```

The report compares the pre-uninstall and post-uninstall inventories and checks the Pattern's tracked resources. It does not label all objects in the earlier inventory as ZTVP-created. Without a pre-install baseline, it does not restore `Proxy/cluster.spec.trustedCA` or `Image/cluster.spec.additionalTrustedCA`, because their original values are unknown. Review those fields against an authoritative platform configuration record and decide whether any known ZTVP trust ConfigMaps can be removed safely. OLM, operator, shared, and cluster-wide leftovers still need ownership review. Report the result as a best-effort Pattern uninstall with unresolved baseline comparisons whenever any ownership or original setting is uncertain; do not call it **zero ZTVP residue**.

Before continuing:

1. Confirm the intended hub and all ACM-managed spoke clusters. Make sure each cluster is reachable and that no required workloads or PVC data are hosted by ZTVP.
2. Review the exact deployed ZTVP values and generated feature values. Note each enabled optional feature, custom namespace, managed cluster group, imported cluster, and external integration.
3. Identify ZTVP components that predate this deployment or are shared. In particular, `cert-manager`, `openshift-operators`, `openshift-operators-redhat`, `openshift-config`, `openshift-storage`, Keycloak, ACM, GitOps, the Pipelines operator, and the Patterns Operator may contain platform or other-application resources.
4. Back up or export any data that must survive. Deleting an application namespace may delete its PVCs and application data.
5. Stop making Git changes that would recreate ZTVP resources while deletion is running.

If ownership or data retention is unclear, stop here and resolve it before deleting the Pattern.

### Protect pre-existing resources adopted by Argo CD (baseline workflow)

An Argo Application can adopt a resource that existed before ZTVP when its manifest has the same kind, namespace, and name. The resource keeps its original UID, but Argo adds a tracking annotation. A cascading Application deletion can then delete that pre-existing object. A simple "new since baseline" comparison will not catch this case.

Before a cascading Application deletion, review the plan for resources whose UIDs match the baseline or whose creation times predate the Pattern. These may be pre-existing resources adopted by the Pattern's Argo tree and must be protected from deletion.

In the baseline workflow, the automation plan reports resources whose UIDs match the baseline or whose creation time predates the Pattern. If it lists any, protect each one before executing the uninstall. The current-inventory workflow applies temporary protection automatically to likely pre-existing and ambiguous tracked resources.

1. Add `Delete=false` to each listed resource. Preserve any existing values in `argocd.argoproj.io/sync-options` by appending `,Delete=false` instead of replacing them.

   ```sh
   oc annotate <resource-type> <resource-name> -n <resource-namespace> \
     argocd.argoproj.io/sync-options=Delete=false --overwrite
   ```

   Omit `-n` for a cluster-scoped resource. Argo CD documents `Delete=false` as retaining a resource when its Application is deleted.

2. Re-run plan-only mode and verify that each listed resource shows `Delete=false set`. The plan may show automatic sync as on: the Pattern/root reconciliation can restore manually patched Application settings while a plan is running.

3. For the Python automation, `uninstall --execute` disables automatic sync on the root and every child Application after its final inventory, verifies it stayed off, then immediately deletes the Pattern. If reconciliation restores sync before deletion, the script stops without deleting the Pattern. If you delete the Pattern manually instead, disable automatic sync on the root first and then every child, and verify all remain off immediately before `oc delete pattern`.

4. After the Pattern and all its Applications are gone, remove the temporary `Delete=false` option and the Argo tracking annotation created for the Pattern from each retained resource. Remove the `argocd.argoproj.io/managed-by: vp-gitops` label from a Namespace only when the pre-install state confirms it was not present. Review any `kubectl.kubernetes.io/last-applied-configuration` annotation that contains the removed Pattern tracking ID.

These safeguards apply only to resources that must remain because they predate ZTVP. Continue removing resources created by ZTVP, then verify the retained objects still match their pre-install identities and settings.

## 2. Start the uninstall

The operator's admission webhook requires an explicit prune opt-in before deletion. Set it after completing preflight. The Python automation sets and verifies the annotation, freezes the Argo Application tree, then immediately deletes the Pattern. The current `make uninstall` target in `Makefile-common` is only a notice and does not perform an uninstall.

```sh
oc annotate pattern "$PATTERN_NAME" -n "$PATTERN_NAMESPACE" patterns.gitops.hybrid-cloud-patterns.io/prune=true --overwrite
oc delete pattern "$PATTERN_NAME" -n "$PATTERN_NAMESPACE"
```

Do not delete the Argo CD root application, child applications, operator subscriptions, or namespaces by hand before or during the normal phase flow. The operator coordinates their removal. Do not remove the Patterns Operator or the cluster-wide OpenShift GitOps installation as part of this procedure.

## 3. Follow the phased deletion

The operator records progress in `.status.deletionPhase`. Watch the Pattern status and Argo applications:

```sh
oc get pattern "$PATTERN_NAME" -n "$PATTERN_NAMESPACE" -w -o yaml
oc get applications.argoproj.io -A -w
```

The object disappears when uninstall completes, so capture status and operator logs before it is gone. The expected phases are:

| Phase | Operator action | What to verify |
| --- | --- | --- |
| `DeleteSpokeChildApps` | Removes child applications from ACM-managed spoke clusters. | Spoke child Applications disappear from every managed cluster. |
| `DeleteSpoke` | Removes spoke app-of-apps and ACM placement/policy objects that created it. | Spoke app-of-apps is gone; expected ACM-managed deletion has completed. |
| `DeleteHubChildApps` | Detaches managed clusters and removes hub child applications. Argo prunes in reverse sync-wave order. | Hub child Applications disappear, including feature applications and the root's managed components. |
| `DeleteHub` | Removes the hub app-of-apps and completes Pattern deletion. | Pattern CR and ZTVP root/child Applications are gone. |

With no ACM hub/spokes, the flow starts at `DeleteHubChildApps`. Do not advance a phase or remove an Application finalizer just to make the status move. If a phase stalls, use the recovery checks below.

## 4. Diagnose a stalled deletion safely

First collect the Pattern status, relevant Application YAML, operator logs, and the affected resources. For example:

```sh
oc get pattern "$PATTERN_NAME" -n "$PATTERN_NAMESPACE" -o yaml
oc get applications.argoproj.io -A -o yaml
oc logs -n <patterns-operator-namespace> deploy/patterns-operator-controller-manager --since=30m
```

The actual controller workload name can vary by operator installation. Find it with `oc get deployments -A | grep patterns-operator` if the example deployment name does not exist.

### ACS `SecurityPolicy` finalizers

The `acs-policies` Application can wait for ACS `SecurityPolicy` resources to finish finalization. ACS Central processes the `securitypolicies.config.stackrox.io/finalizer`. If Central cannot deregister a policy, Argo's foreground deletion can block lower sync waves and leave the Pattern Operator waiting for child Applications.

```sh
oc get applications.argoproj.io -A
oc get securitypolicies.config.stackrox.io -o yaml
oc get pods -n stackrox
oc logs -n stackrox deploy/central --since=30m
```

Restore ACS Central health/connectivity and let the controller process the policy finalizers. Do not remove these finalizers while Central is expected to process them. If a finalizer remains after the controller is healthy and the owning resource is confirmed disposable, follow ACS support guidance before using a manual finalizer override.

### Other operator finalizers, Jobs, or pods

ZTVP testing also required investigation of SPIRE OIDC provider and Compliance `ProfileBundle` finalizers, a failed SPIRE pod, and a Pattern vault-injection Job. Inspect each resource's owner references, finalizers, events, and owning controller before intervening:

```sh
oc get pods,jobs -A
oc get profilebundles.compliance.openshift.io -A -o yaml
oc get events -A --sort-by=.lastTimestamp
```

Use the API resource name shown by `oc api-resources` to inspect the SPIRE OIDC provider. Correct the operator/controller problem and allow normal finalization. Delete an orphan Job or pod only after confirming it is Pattern-owned and no longer required. Never bulk-clear finalizers.

### Namespace stuck terminating

Check the namespace contents and the API services for unavailable backends:

```sh
oc describe namespace <namespace>
oc get apiservices.apiregistration.k8s.io
oc describe apiservice <api-service-name>
```

Restore the API service backend or remove an APIService only when its owner confirms it is obsolete and no other workload depends on it. A namespace finalizer override is a last resort: use it only after proving the namespace contains no remaining resources and the blocking API cannot be restored. Clearing namespace finalizers can orphan objects.

If an unrelated or pre-existing APIService is unavailable, do not delete it or its namespace solely because it blocks ZTVP cleanup. Establish ownership and restore its backing service, or obtain confirmation from its owner before considering removal.

## 5. Audit and remove ZTVP-only leftovers

After the Pattern CR disappears, compare the current state with the preflight inventory. Inspect all configured ZTVP namespaces, enabled feature resources, Argo Applications, OLM objects, cluster-scoped resources, and custom resources on both hub and spokes.

```sh
oc get patterns.gitops.hybrid-cloud-patterns.io -A
oc get applications.argoproj.io -A -o wide
oc get namespaces
oc get subscriptions.operators.coreos.com,csv.operators.coreos.com,operatorgroups.operators.coreos.com -A -o wide
oc get crd -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp
oc get apiservices.apiregistration.k8s.io -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp
```

### Vault and secret-store residue check

For a base ZTVP installation, explicitly check the Vault data store and the credentials used to configure it. The default Vault chart uses the `vault` namespace, StatefulSet `vault`, PVC `data-vault-0`, and a PV bound to `vault/data-vault-0`. The framework also creates `imperative/vaultkeys`, a `vault-backend` `ClusterSecretStore`, and Pattern-owned `ExternalSecret` objects. Compare each object with the baseline; do not delete a pre-existing or shared Vault installation or its data.

```sh
oc get namespaces | grep -E '^(vault|imperative|external-secrets|qtodo|qtodo-db)[[:space:]]' || true
oc get statefulset,pvc -n vault
oc get pv -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy,CLAIM_NAMESPACE:.spec.claimRef.namespace,CLAIM_NAME:.spec.claimRef.name
oc get clustersecretstores.external-secrets.io -o wide
oc get externalsecrets.external-secrets.io -A -o wide
oc get secrets -n imperative -o name
```

When the baseline proves Vault was created by this ZTVP installation, its namespace, StatefulSet, PVC, bound PV, and `vaultkeys` Secret should be gone after cleanup. Also remove the Pattern-owned `vault-backend` and `ExternalSecret` resources. Keep shared External Secrets operator resources and their CRDs when they predate the Pattern or serve other workloads. The script records namespace, PVC, and PV identities in its audit; use the PV claim reference as well as its generated PV name when checking for retained Vault storage.

Then check for ZTVP custom resources through each API installed by the operators that were enabled. `oc api-resources` lists the resource names and scope; query namespaced resources across all namespaces and cluster-scoped resources cluster-wide. A CRD timestamp, name, label, or owner reference alone is not sufficient proof that the resource is safe to remove.

OLM intentionally retains APIs and data when an operator is uninstalled. In particular, deleting a CRD deletes **all** custom resources served by that CRD. Before removing any residual custom resource, CRD, APIService, Subscription, CSV, or namespace:

1. Confirm it was introduced by this ZTVP installation, not by the cluster or another application.
2. Confirm there are no remaining custom-resource instances or data that must be kept.
3. Confirm no other operator or application depends on the API.
4. Remove resources in dependency order, using the owning product's uninstall guidance. Delete an individual CRD or APIService only when its ownership and lack of consumers are established.

Where those checks cannot be made, retain the resource and record it as a known residue. A successful Pattern deletion alone is not evidence that all OLM APIs or data are gone.

### Dedicated OpenShift GitOps instance

The Pattern Operator removes its Argo Applications but does not necessarily remove the `ArgoCD` custom resource that hosted them. Check the instance and its namespace separately:

```sh
oc get argocds.argoproj.io -A -o wide
oc get applications.argoproj.io -A -o wide
oc get appprojects.argoproj.io -A -o wide
```

If the Argo CD instance was absent from the baseline, its namespace was created for this installation, and no other Pattern or application uses it, remove the instance and then inspect the namespace before deleting it:

```sh
oc delete argocd <instance> -n <namespace> --wait=true
oc get all,configmaps,secrets,roles,rolebindings,serviceaccounts -n <namespace>
oc get appprojects.argoproj.io -n <namespace>
```

Delete only newly created, Pattern-specific `AppProject` objects. Delete the namespace only when no shared or user-owned resources remain and its UID confirms it was created after the baseline. Keep the OpenShift GitOps operator and its shared namespaces.

### Operator-generated objects and retained APIs

After the operator Subscriptions and CSVs are gone, inspect product-created console and monitoring objects as well as CRDs and APIServices. Bundle metadata such as `olm.owner`, `operator-sdk/primary-resource`, and product-specific labels can help identify ownership. Remove those objects only after confirming their owning operator, workloads, custom resources, and consumers are gone.

The OpenShift External Secrets operator can leave its automatically created `ExternalSecretsManager/cluster` with `externalsecretsmanagers.operator.openshift.io/external-secrets-manager`. Try normal deletion first. If it remains terminating after its operator, Subscription, CSV, Deployments, and other External Secrets custom resources are absent, verify that no operator-owned workloads or data remain before removing that one finalizer. Record the evidence; never clear finalizers in bulk.

OpenShift can auto-register APIService objects for CRD API groups. Remove confirmed unused CRDs only after checking that they have no custom-resource instances and no consumers; then verify whether their APIService registrations disappear. Do not delete an APIService merely because its creation time is near the installation window.

`operators.operators.coreos.com` objects may be recreated while resources selected by their `status.components.labelSelector` remain. Inspect `status.components.refs` and the referenced resources before deciding they are stale. Do not remove labels from shared CRDs to suppress an OLM inventory record.

Restore cluster-scoped fields changed by ZTVP from the preflight snapshots. The certificates chart manages `Proxy/cluster.spec.trustedCA`; restore the original value after the chart is removed and ensure Argo no longer manages that field. If image pull trust was explicitly enabled, restore only the fields ZTVP changed on `Image/cluster`. Do not replace the whole cluster configuration object with an old snapshot and do not delete either singleton.

## 6. Completion criteria and report

Call the Pattern uninstall complete only when all of the following are true:

- The Pattern CR and all ZTVP root and child Argo Applications are gone on the hub and every spoke.
- No ZTVP workloads, custom resources, or resources in ZTVP-exclusive namespaces remain.
- If Vault was installed by this Pattern, its new namespace and `data-vault-0` PVC/PV are absent; any pre-existing or shared Vault resources are classified and retained.
- ZTVP-owned Subscriptions and operator instances are removed. Pre-existing/shared operators are identified and retained.
- Cluster-scoped configuration changed by ZTVP is restored to the recorded pre-install state.
- Remaining CRDs, APIServices, and resources are classified as pre-existing/shared or intentionally retained by OLM, and are listed in the uninstall report.

Use the phrase **zero ZTVP residue** only when the inventory proves no ZTVP-owned objects remain. The Patterns Operator and cluster-wide OpenShift GitOps are expected framework components and are outside that claim. If any ownership is ambiguous, report the uninstall as complete for Pattern-managed workloads, with residual inventory still under review.

## References

- [Experimental Validated Patterns uninstall support](https://validatedpatterns.io/blog/2026-02-16-pattern-uninstall/)
- [Argo CD sync options: retaining resources when an Application is deleted](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)
- [ZTVP certificates and cluster trust changes](ztvp-certificates.md)
- [ZTVP feature variant generator](../scripts/gen-feature-variants.md)
