# User-Defined Networks (UDN) for Zero Trust Network Isolation

## Overview

User-Defined Networks (UDN) provide layer 2/3 network isolation for workloads in OpenShift, separate from the default cluster network. This feature implements Zero Trust network segmentation principles by creating an isolated network for the qtodo application, restricting communication to only necessary services.

## Architecture

### Network Topology

The UDN implementation creates a dedicated isolated network for qtodo workloads:

```text
┌─────────────────────────────────────────────────────┐
│                      Cluster Network                │
│  ┌────────────┐    ┌─────────┐    ┌──────────┐      │
│  │  Router    │───▶│ qtodo   │───▶│ Vault    │      │
│  │  (Ingress) │    │ (eth0)  │    │ (8200)   │      │
│  └────────────┘    └────┬────┘    └──────────┘      │
│                         │                           │
│                         │ UDN Attachment            │
└─────────────────────────┼───────────────────────────┘
                          │
                    ┌─────▼──────┐
                    │    UDN     │
                    │ (net1/     │
                    │  Layer2)   │
                    └─────┬──────┘
                          │
                ┌─────────┴────────┐
                │                  │
          ┌─────▼──────┐      ┌────▼─────┐
          │ qtodo pod  │      │ qtodo-db │
          │ (isolated) │──────│  (5432)  │
          └────────────┘      └──────────┘
               │
               └─────────▶ DNS (5353) via cluster network
```

### Dual Network Interfaces

When UDN is enabled, qtodo pods have two network interfaces:

1. **eth0 (Primary - Cluster Network)**
   - Ingress from OpenShift Router (port 8080)
   - Egress to Vault (SPIFFE auth, port 8200)
   - Egress to OIDCs (OIDC back-channel, port 443)
   - DNS resolution (CoreDNS, port 5353)

2. **net1 (Secondary - UDN)**
   - PostgreSQL communication (qtodo ↔ qtodo-db, port 5432)
   - Isolated from other cluster workloads
   - Layer 2 topology (same subnet across nodes)

## Security Benefits

1. **Network Segmentation**: qtodo workloads are isolated from arbitrary cluster traffic
2. **Explicit Allow-Lists**: AdminNetworkPolicy enforces allow-only-required communication
3. **Defense in Depth**: Combines with existing NetworkPolicy for dual-layer protection
4. **Blast Radius Reduction**: Compromise of qtodo cannot pivot to unrelated services
5. **Compliance**: Supports Zero Trust architecture mandates (NIST 800-207, NIS2, ISO 27001:2022)

## Components

UDN is integrated into the qtodo Helm chart (`charts/qtodo`). When enabled, the following resources are created:

### UserDefinedNetwork CR

Template: `charts/qtodo/templates/udn-user-defined-network.yaml`

Creates the isolated network with Layer2 topology:

- Subnet: `10.100.0.0/16`
- MTU: 1400 (avoids fragmentation)
- IPAM: Persistent IP assignment
- Sync-wave: 35 (before NAD)

### NetworkAttachmentDefinition

Template: `charts/qtodo/templates/udn-network-attachment-definition.yaml`

Defines how pods attach to the UDN:

- CNI type: `ovn-k8s-cni-overlay`
- References the UserDefinedNetwork
- Used via pod annotation `k8s.v1.cni.cncf.io/networks`
- Sync-wave: 36 (before policies)

### AdminNetworkPolicy

Template: `charts/qtodo/templates/udn-admin-network-policy.yaml`

Explicit allow-list for UDN traffic:

- **Ingress**:
  - OpenShift router (port 8080)
  - qtodo pods to qtodo-db (port 5432)
- **Egress**: DNS, PostgreSQL, Vault, Keycloak (HTTPS connections)
- Priority: 50 (higher = processed first)
- Sync-wave: 37 (before qtodo app)

## Enabling UDN

### Option 1: Feature Variant Generator (Recommended)

```bash
python3 scripts/gen-feature-variants.py \
  --features udn \
  --base values-hub.yaml

# Apply the variant
cp /tmp/values-hub-udn.yaml values-hub.yaml
./pattern.sh make install
```

### Option 2: Manual Configuration

1. **Enable UDN in the qtodo application** in `values-hub.yaml`:

   ```yaml
   clusterGroup:
     applications:
       qtodo:
         # ... existing config ...
         overrides:
           # ... existing overrides ...
           - name: app.udn.enabled
             value: "true"
   ```

2. **Deploy**:

   ```bash
   ./pattern.sh make install
   ```

## Verification

### 1. Check UDN Resources

```bash
# UserDefinedNetwork
oc get userdefinednetwork -n qtodo
NAME                      AGE
qtodo-isolated-network    5m

# NetworkAttachmentDefinition
oc get network-attachment-definitions -n qtodo
NAME            AGE
qtodo-udn-nad   5m
```

### 2. Verify Network Policies

```bash
# AdminNetworkPolicy
oc get adminnetworkpolicy
NAME              PRIORITY   AGE
qtodo-udn-policy  50         5m
```

### 3. Test Connectivity

```bash
# DNS resolution (should work via eth0)
oc exec -n qtodo deploy/qtodo -c qtodo -- getent hosts qtodo-db

# PostgreSQL connectivity (should work via net1)
oc exec -n qtodo deploy/qtodo -c qtodo -- timeout 5 bash -c '</dev/tcp/qtodo-db/5433 &>/dev/null' && echo "OK"

# Vault API (should work via eth0)
oc exec -n qtodo deploy/qtodo -c qtodo -- curl -sk https://vault.vault.svc:8200/v1/sys/health
```

### 4. Verify qtodo Application

```bash
# Get the route
QTODO_URL=$(oc get route -n qtodo qtodo -o jsonpath='{.spec.host}')

# Access the application
curl https://$QTODO_URL
```

## Configuration Options

UDN is configured via the `app.udn` section in `charts/qtodo/values.yaml`:

| Parameter                        | Description                      | Default                  |
| -------------------------------- | -------------------------------- | ------------------------ |
| `app.udn.enabled`                | Enable UDN                       | `false`                  |
| `app.udn.name`                   | UserDefinedNetwork name          | `qtodo-isolated-network` |
| `app.udn.nadName`                | NetworkAttachmentDefinition name | `qtodo-udn-nad`          |
| `app.udn.topology`               | Network topology (Layer2/Layer3) | `Layer2`                 |
| `app.udn.subnet`                 | CIDR for UDN                     | `10.100.0.0/16`          |
| `app.udn.mtu`                    | MTU for the network              | `1400`                   |
| `app.udn.networkPolicy.enabled`  | Enable AdminNetworkPolicy        | `true`                   |

### Layer3 Topology

For larger deployments, Layer3 provides better scalability. Override in `values-hub.yaml`:

```yaml
clusterGroup:
  applications:
    qtodo:
      overrides:
        - name: app.udn.enabled
          value: "true"
        - name: app.udn.topology
          value: "Layer3"
        - name: app.udn.joinSubnet
          value: "100.64.0.0/16"
```

## Security Considerations

### Defense in Depth

UDN complements, but does not replace, other security controls:

- **NetworkPolicy**: Still applied on the cluster network (eth0)
- **Service Mesh**: mTLS can layer on top of UDN
- **ACS Policies**: Runtime enforcement still active

### Attack Surface

- UDN pods are still reachable via cluster network (eth0) for ingress/egress to external services
- AdminNetworkPolicy must be correctly configured to avoid bypasses
- Pods with `CAP_NET_ADMIN` could potentially manipulate interfaces
- For integration with IDPs (_Keycloak_, _EntraID_), HTTPS connections to any destination are enabled. In a more secure environment, this rule should be more restrictive and only allow access to specific destinations.

## References

- [OpenShift UDN Documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/latest/html/multiple_networks/understanding-multiple-networks)
- [OVN-Kubernetes User-Defined Networks](https://github.com/ovn-kubernetes/ovn-kubernetes/blob/master/docs/features/user-defined-networks/user-defined-networks.md)
