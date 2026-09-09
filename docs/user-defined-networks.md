# User-Defined Networks (UDN) for Zero Trust Network Isolation

## Overview

User-Defined Networks (UDN) provide layer-2 network isolation for workloads in OpenShift, separate from the default cluster network. This feature implements Zero Trust network segmentation for the qtodo multi-tier application now that the frontend (`qtodo`) and PostgreSQL (`qtodo-db`) run in **different namespaces**.

A cluster-scoped `ClusterUserDefinedNetwork` (CUDN) creates a **shared secondary** Layer2 network that both namespaces join. PostgreSQL is reachable from qtodo **only** on that UDN. qtodo keeps the cluster network as its primary interface for everything else (OpenShift router, Vault, OIDC, DNS). qtodo-db's only permitted cluster-network egress is CoreDNS (`5353/tcp` and `5353/udp`).

## Architecture

### Network Topology

```text
┌──────────────────────────────────────────────────────────────┐
│                     Cluster Network (eth0)                   │
│  ┌────────────┐     ┌─────────┐     ┌──────────┐             │
│  │  Router    │────▶│ qtodo   │────▶│ Vault    │             │
│  │  (Ingress) │     │ (eth0)  │     │ (8200)   │             │
│  └────────────┘     └────┬────┘     └──────────┘             │
│                          │                                   │
│                     OIDC (443), DNS (5353)                   │
│                                                              │
│                     ┌───────────┐                            │
│                     │ qtodo-db  │──── DNS (5353) only        │
│                     │ (eth0)    │    PostgreSQL denied       │
│                     └───────────┘                            │
└──────────────────────────┬───────────────────────────────────┘
                           │
              Shared secondary CUDN (net1, Layer2)
              ClusterUserDefinedNetwork
              namespaces: qtodo, qtodo-db
                            │
              ┌─────────────┴─────────────┐
              │                           │
        ┌─────▼──────┐             ┌──────▼────────┐
        │ qtodo pod  │             │ qtodo-db      │
        │ (net1)     │─────────────│ (net1,        │
        │            │    5432     │  10.100.0.10) │
        └────────────┘             └───────────────┘
```

### Dual Network Interfaces

| Workload | eth0 (cluster network) | net1 (shared secondary UDN) |
| --- | --- | --- |
| **qtodo** | Ingress from OpenShift router. Egress to Vault (8200), OIDC (443), CoreDNS (5353) | JDBC to PostgreSQL at the static UDN IP (`10.100.0.10:5432`) |
| **qtodo-db** | Egress to CoreDNS (`5353/tcp` and `5353/udp`) only; **no** PostgreSQL ingress | PostgreSQL (`5432/tcp`) from qtodo pods only |

Kubernetes `NetworkPolicy` objects apply only to the cluster network. `MultiNetworkPolicy` objects apply to the CUDN.

Secondary UDNs do **not** support Kubernetes Services. qtodo therefore uses the PostgreSQL pod's static UDN IP as the JDBC host instead of `qtodo-db.qtodo-db.svc`.

## Security Benefits

1. **Cross-namespace segmentation**: the database namespace is not on a shared cluster-network path to the application
2. **Explicit allow-lists**: cluster-network `NetworkPolicy` plus UDN `MultiNetworkPolicy`
3. **Blast radius reduction**: qtodo-db is completely isolated. It is not accesible from pods other than qtodo pod.
4. **Compliance**: supports Zero Trust architecture mandates (NIST SP 800-207, NIS2, ISO 27001:2022)

## Components

### ClusterUserDefinedNetwork CR

Template: `charts/qtodo-db/templates/udn-cluster-user-defined-network.yaml`

Created in the `qtodo-db` application (sync-wave 35, before the StatefulSet) so both namespaces receive a NAD before pods start:

- Name: `qtodo-isolated-network`
- Topology: Layer2, role **Secondary** (qtodo's primary interface stays the cluster network)
- Subnet: `10.100.0.0/16`
- Reserved subnet: `10.100.0.0/28` (static DB IP is taken from this range)
- Namespace selector: `qtodo` and `qtodo-db` (`kubernetes.io/metadata.name`)
- OVN-Kubernetes creates a `NetworkAttachmentDefinition` of the same name in each selected namespace, do not create NADs by hand

### Pod attachment

- **qtodo-db** StatefulSet: Multus annotation with a **static** IP (`udn.dbIP`, default `10.100.0.10`)
- **qtodo** Deployment: Multus annotation attaching to the CUDN-managed NAD (IP allocated from the non-reserved range)

### Cluster-network NetworkPolicy

When UDN is enabled:

- `qtodo-db-network-policy.yaml` — **no** PostgreSQL ingress on eth0; egress is CoreDNS 5353 only
- `qtodo-network-policy.yaml` — PostgreSQL egress to the `qtodo-db` namespace is **omitted**; router, Vault, OIDC, and DNS stay on eth0

When UDN is disabled, the previous cluster-network PostgreSQL allow rules remain.

### MultiNetworkPolicy (UDN)

Templates:

- `charts/qtodo-db/templates/udn-multi-network-policy.yaml`
- `charts/qtodo/templates/udn-multi-network-policy.yaml`

- Default-deny on the UDN in both namespaces
- Allow PostgreSQL (`5432/tcp`) from `app=qtodo` in `qtodo` to `app=qtodo-db` in `qtodo-db`
- qtodo is not allowed to receive traffic on the UDN
- qtodo-db is not allowed UDN egress (DNS stays on eth0)

Requires `spec.useMultiNetworkPolicy: true` on `network.operator.openshift.io/cluster`. When `app.udn.networkPolicy.enabled` is `true` (the default), the `qtodo` chart runs a Job at sync-wave 36 that patches this setting if needed and waits for the Cluster Network Operator to expose the MultiNetworkPolicy API before wave 37 policies sync. If that Cluster Network Operator setting cannot be enabled, set `udn.networkPolicy.enabled` and `app.udn.networkPolicy.enabled` to `false`. UDN membership plus cluster-network `NetworkPolicy` still isolate PostgreSQL.

### Cluster Network Operator patch Job

Template: `charts/qtodo/templates/udn-enable-multi-network-policy-job.yaml`

The job runs in the `default` namespace, which has no NetworkPolicies, so it can reach the Kubernetes API server without extra egress rules.

- Runs when `app.udn.enabled` and `app.udn.networkPolicy.enabled` are both `true`
- Checks `spec.useMultiNetworkPolicy` on `network.operator.openshift.io/cluster` and skips the patch when already `true`
- Waits for the `multi-networkpolicies` API to become available (configurable via `app.udn.multiNetworkPolicyJob.waitForReconciliation`)
- The `qtodo-db` MultiNetworkPolicies (deployed at app-wave 37, before `qtodo` at app-wave 38) carry `SkipDryRunOnMissingResource=true` and will be created successfully once the API is available after the job completes

Manual patch (troubleshooting only):

```bash
oc patch network.operator.openshift.io cluster --type merge \
  -p '{"spec":{"useMultiNetworkPolicy":true}}'
```

## Enabling UDN

### Option 1: Feature Variant Generator (Recommended)

```bash
python3 scripts/gen-feature-variants.py \
  --features udn \
  --base values-hub.yaml

cp /tmp/values-hub-udn.yaml values-hub.yaml
./pattern.sh make install
```

The fragment sets `udn.enabled` on `qtodo-db` and `app.udn.enabled` on `qtodo`.

### Option 2: Manual Configuration

Enable **both** applications in `values-hub.yaml`:

```yaml
clusterGroup:
  applications:
    qtodo-db:
      overrides:
        - name: udn.enabled
          value: "true"
    qtodo:
      overrides:
        - name: app.udn.enabled
          value: "true"
```

Then deploy:

```bash
./pattern.sh make install
```

## Verification

### 1. Check CUDN and NADs

```bash
oc get clusteruserdefinednetwork qtodo-isolated-network

oc get network-attachment-definitions -n qtodo
oc get network-attachment-definitions -n qtodo-db
```

Both namespaces should show `qtodo-isolated-network`.

### 2. Confirm pod attachments

```bash
oc get pod -n qtodo -l app=qtodo -o jsonpath='{.items[0].metadata.annotations.k8s\.v1\.cni\.cncf\.io/networks}{"\n"}'
oc get pod -n qtodo-db -l app=qtodo-db -o jsonpath='{.items[0].metadata.annotations.k8s\.v1\.cni\.cncf\.io/networks}{"\n"}'

oc exec -n qtodo deploy/qtodo -c qtodo -- cat /proc/net/fib_trie | grep -B1 '/32 host LOCAL'
oc exec -n qtodo-db qtodo-db-0 -c postgres -- cat /proc/net/fib_trie | grep -B1 '/32 host LOCAL'
```

qtodo-db's `net1` address must be `10.100.0.10`.

### 3. Verify policies

```bash
oc get networkpolicy -n qtodo
oc get networkpolicy -n qtodo-db
oc get multi-networkpolicies.k8s.cni.cncf.io -A
```

### 4. Test connectivity

```bash
# DNS from qtodo via eth0
oc exec -n qtodo deploy/qtodo -c qtodo -- getent hosts vault.vault.svc

# PostgreSQL via UDN static IP (should succeed)
oc exec -n qtodo deploy/qtodo -c qtodo -- timeout 5 bash -c '</dev/tcp/10.100.0.10/5432' && echo "UDN postgres OK"

# PostgreSQL via cluster-network Service (should fail when UDN is enabled)
oc exec -n qtodo deploy/qtodo -c qtodo -- timeout 5 bash -c '</dev/tcp/qtodo-db.qtodo-db.svc/5432' || echo "cluster-network postgres blocked"

# DNS from qtodo-db via eth0 (should succeed)
oc exec -n qtodo-db qtodo-db-0 -c postgres -- getent hosts kubernetes.default.svc

# Vault from qtodo via eth0
oc exec -n qtodo deploy/qtodo -c qtodo -- curl -sk https://vault.vault.svc:8200/v1/sys/health
```

### 5. Verify qtodo Application

```bash
QTODO_URL=$(oc get route -n qtodo qtodo -o jsonpath='{.spec.host}')
curl -k "https://${QTODO_URL}"
```

## Configuration Options

CUDN settings live in `charts/qtodo-db/values.yaml`. The qtodo chart only needs the CUDN name and the database UDN IP.

| Parameter | Chart | Description | Default |
| --- | --- | --- | --- |
| `udn.enabled` / `app.udn.enabled` | both | Enable the shared UDN | `false` |
| `udn.name` / `app.udn.name` | both | CUDN and NAD name (must match) | `qtodo-isolated-network` |
| `udn.dbIP` / `app.udn.dbIP` | both | Static PostgreSQL IP on the UDN (JDBC target) | `10.100.0.10` |
| `udn.topology` | qtodo-db | Must be `Layer2` | `Layer2` |
| `udn.role` | qtodo-db | Must be `Secondary` | `Secondary` |
| `udn.subnet` | qtodo-db | UDN CIDR | `10.100.0.0/16` |
| `udn.reservedSubnet` | qtodo-db | Range reserved for static assignment | `10.100.0.0/28` |
| `udn.mtu` | qtodo-db | MTU | `1400` |
| `udn.namespaces` | qtodo-db | Namespaces that join the CUDN | `qtodo`, `qtodo-db` |
| `udn.networkPolicy.enabled` / `app.udn.networkPolicy.enabled` | both | Create MultiNetworkPolicy objects | `true` |
| `app.udn.multiNetworkPolicyJob.namespace` | qtodo | Namespace for the CNO patch Job | `default` |
| `app.udn.multiNetworkPolicyJob.image.registry` | qtodo | OCI registry for the CNO patch Job | `registry.redhat.io` |
| `app.udn.multiNetworkPolicyJob.image.repository` | qtodo | Container image path for the CNO patch Job | `openshift4/ose-cli-rhel9` |
| `app.udn.multiNetworkPolicyJob.image.tag` | qtodo | Image tag for the CNO patch Job | `latest` |
| `app.udn.multiNetworkPolicyJob.image.pullPolicy` | qtodo | Container image pull policy for the CNO patch Job | `IfNotPresent` |
| `app.udn.multiNetworkPolicyJob.waitForReconciliation.enabled` | qtodo | Wait for MultiNetworkPolicy API after patch | `true` |
| `app.udn.multiNetworkPolicyJob.waitForReconciliation.maxRetries` | qtodo | Reconciliation poll attempts | `60` |
| `app.udn.multiNetworkPolicyJob.waitForReconciliation.intervalSeconds` | qtodo | Seconds between poll attempts | `10` |

Keep `name` and `dbIP` identical in both charts.

## Security Considerations

### Defense in Depth

UDN complements, but does not replace, other security controls:

- **NetworkPolicy** on the cluster network (eth0)
- **MultiNetworkPolicy** on the UDN (net1)
- **ACS policies** for runtime enforcement
- **SPIFFE / Vault** for database credentials (unchanged)

### Attack Surface

- qtodo remains reachable on the cluster network for ingress and for egress to Vault and OIDC
- qtodo-db still has an eth0 address so kubelet probes and CoreDNS work. PostgreSQL on that interface is denied by NetworkPolicy
- Pods with `CAP_NET_ADMIN` could potentially manipulate interfaces. qtodo and qtodo-db drop `ALL` capabilities
- If MultiNetworkPolicy is disabled, any pod attached to the CUDN NAD can reach PostgreSQL on net1. Limit NAD use to these two workloads

## References

- [OpenShift: Understanding multiple networks](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/multiple_networks/understanding-multiple-networks)
- [ClusterUserDefinedNetwork API](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/network_apis/clusteruserdefinednetwork-k8s-ovn-org-v1)
- [Configuring multi-network policies](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/multiple_networks/secondary-networks)
- [OVN-Kubernetes User-Defined Networks](https://github.com/ovn-kubernetes/ovn-kubernetes/blob/master/docs/features/user-defined-networks/user-defined-networks.md)
