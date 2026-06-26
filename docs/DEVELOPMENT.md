# Development

This document describes recommended practices for developing and testing against this pattern.

## Testing Environments

While you may bring your own (BYO) OpenShift cluster, Red Hat associates and partners may utilize [Red Hat Demo Platform (RHDP)](https://catalog.demo.redhat.com) to provision OpenShift environments for use as targets for pattern development and testing.

### Provisioning

The following Catalog Item (CI) has been verified and is recommended when provisioning OpenShift clusters as it meets the prerequisites set form within the pattern:

* [Red Hat OpenShift Container Platform Cluster (Multi-Cloud)](https://catalog.demo.redhat.com/catalog/all?search=multi+cloud&item=babylon-catalog-prod%2Fpublished.ocp4-cluster.prod)

The following options should be selected:

* Activity: Practice / Enablement
* Purpose: Trying out a technical solution
* Salesforce ID: Can be omitted (See note below)
* Cloud Provider: AWS
* OpenShift Version: 4.20, 4.21
* Cluster Size: multinode
* OpenShift Worker count: 5
* OpenShift Worker instance type: m5a.4xlarge

NOTE: The Salesforce ID requirement is not needed by those that are members of the RHDP development team.

NOTE: Update the OpenShift Worker Count and instance type based on the desired capacity required.

Once a cluster has been provisioned, there are additional steps which need to be performed in order to avoid overlapping capabilities that are implemented within this pattern:

### Cert-Manager Removal

While cert-manager is a key feature offered within this pattern, RHDP deploys an instance to support the generation of API and Ingress certificates. Utilize the following steps to remove the conflicting resources.

1. Login to the Web Console of the provisioned OpenShift cluster with the provided authentication details.
2. Under _Operators_ on the left hand navigation ad select **Installed Operators**
3. Locate _cert-manager Operator for Red Hat OpenShift_ and click the kabob (3 vertical dots) from the right hand column and select **Uninstall Operator**
4. The `OperatorGroup` associated with Cert Manager must also be uninstalled. Under _Home_ on the left hand navigation, select **API Explorer**
5. From the project dropdown at the top of the screen, select `cert-manager-operator` as the _Project_
6. In the search textbox, enter `OperatorGroup` and select the link underneath the _Name_ column associated with API Version `v1` in the _Version_ column.
7. Click on the **Instances** tab
8. Locate any instances and click the kabob (3 vertical dots) from the right hand column and select **Delete OperatorGroup**

### Inactivity Timeout

RHDP enables an inactivity timeout on tokens generated from the OpenShift OAuth server which logs a user out of the Web Console and CLI. To avoid such timeouts, the setting can be disabled by executing the following command:

```shell
oc patch oauth cluster  --type json   -p='[{"op": "remove", "path": "/spec/tokenConfig/accessTokenInactivityTimeout"}]'
```

The updated setting will become enabled upon next login.

### Reducing the storage required

By default, NooBaa requires 100 Gi of disk space: 50 Gi for the database and 50 Gi for the default `BackingStore`. While this might make sense for production, in our development environment we will only be using a few images for testing, so it may be excessive.

If we want to save some space, we can add these overrides to the `noobaa-mcg` component in the `values-hub.yaml` file:

```yaml
    noobaa-mcg:
      name: noobaa-mcg
      namespace: openshift-storage
      project: hub
      path: charts/noobaa-mcg
      annotations:
        argocd.argoproj.io/sync-wave: "36"
      overrides:
        - name: noobaa.dbSize
          value: 10Gi
        - name: noobaa.pvPool.resources.requests.storage
          value: 25Gi
```

## Accessing Credentials for Testing

All sensitive credentials in this pattern are generated automatically and stored in HashiCorp Vault during deployment. There are no static default passwords. This section explains how to retrieve credentials for testing and exploration.

### Retrieve the Vault Root Token

The Vault initialization data, including the root token, is stored in a Kubernetes Secret in the `imperative` namespace. Run the following command to extract the root token:

```shell
oc extract -n imperative secret/vaultkeys --to=- --keys=vault_data_json 2>/dev/null \
  | jq -r ".root_token"
```

Save this value — you will need it to authenticate to Vault in the steps below.

### Access the Vault Web UI

Get the Vault route URL and open it in a browser:

```shell
echo "https://$(oc get route -n vault vault -o jsonpath='{.spec.host}')"
```

On the login screen select **Token** as the authentication method and paste the root token retrieved above.

### Access Vault via CLI (`oc exec`)

You can query Vault directly from inside the `vault-0` pod without installing any local tooling. First export the token into a shell variable:

```shell
VAULT_TOKEN=$(oc extract -n imperative secret/vaultkeys --to=- --keys=vault_data_json 2>/dev/null \
  | jq -r ".root_token")
```

Then use `oc exec` to run Vault commands. For example, to list the top-level secret paths:

```shell
oc exec -n vault vault-0 -- env VAULT_TOKEN="$VAULT_TOKEN" vault kv list secret/
```

To read a specific secret, use `vault kv get`. For example, to read the Keycloak user credentials:

```shell
oc exec -n vault vault-0 -- env VAULT_TOKEN="$VAULT_TOKEN" \
  vault kv get secret/hub/infra/users/keycloak-users
```

### Key Secret Paths

Secrets are organized by component under the `secret/` KV mount. The table below lists the paths relevant to testing the default pattern deployment.

| Path | Contents |
|---|---|
| `secret/apps/qtodo/qtodo-db` | `admin-password`, `db-password` — PostgreSQL credentials for the qtodo app |
| `secret/apps/qtodo/qtodo-truststore` | `truststore-password` — Keycloak TLS truststore password for qtodo |
| `secret/hub/infra/keycloak/keycloak` | `admin-password`, `db-password` — Keycloak admin and database credentials |
| `secret/hub/infra/users/keycloak-users` | `qtodo-admin-password`, `qtodo-user1-password`, `rhtpa-user-password`, `rhtas-user-password` — application user passwords provisioned in Keycloak |
| `secret/hub/infra/acs/acs-central` | `admin-password` — ACS Central admin password |
| `secret/hub/infra/quay/quay-users` | `quay-admin-password`, `quay-user-password` — Quay registry credentials _(optional component)_ |
| `secret/hub/infra/rhtpa/rhtpa-db` | `db-password` — RHTPA PostgreSQL password _(optional component)_ |
| `secret/hub/infra/rhtpa/rhtpa-oidc-cli` | `client-secret` — RHTPA Keycloak OIDC client secret _(optional component)_ |

### Shortcut: Reading ESO-Synced Secrets from Kubernetes

Several secrets are automatically synchronized from Vault to Kubernetes Secrets by the External Secrets Operator (ESO). These can be read directly without going through Vault and are useful when you just need a quick credential lookup.

Keycloak user passwords (synced to `keycloak-system`):

```shell
oc get secret -n keycloak-system keycloak-users -o json \
  | jq -r '.data | map_values(@base64d)'
```

ACS Central admin password (synced to `stackrox`):

```shell
oc get secret -n stackrox central-htpasswd -o jsonpath='{.data.password}' | base64 -d
```

> [!NOTE]
> The root token grants unrestricted access to all secrets in Vault. Use it only for development and testing. For day-to-day exploration of a specific component's credentials, prefer the narrower ESO-synced Kubernetes Secrets shown above.

## Analytics Tracking

Metrics are captured to track the use of any of the Validated Patterns. It is important than an accurate depiction of pattern use by customers, partners and those from the community are captured. Red Hat associates should not factor into this calculation and support is available in the Validated Patterns framework to opt out of being captured.

To implement the opt-out capability, create a file in the location `~/.config/validated-patterns/pattern-uuid`. The file does not need to have to be populated with any specific content. Its mere presence is all that is necessary for usage of the pattern to not be tracked.
