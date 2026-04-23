# Azure Entra ID integration

This document describes the steps required to integrate the **Zero Trust Validated Pattern** (ZTVP) with **Azure Entra ID**, trusting this service as the Identity Provider for the following components:

* Qtodo demo application

> [!WARNING]
> The integration of Azure Entra ID into the pattern is still **in progress** and does not cover all components. This document describes those that are supported. For components not supported by Entra ID, **Red Hat Build of Keycloak (RHBK)** will continue to be used as the default OIDC.

## Configuration

To configure the components we will need access to Azure Portal with permissions to create App Registrations and a Microsoft Entra ID tenant.

### Qtodo

#### Azure setup

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **App registrations** in the left menu
4. Click **New registration**
5. Fill in the details:
   * **Name**: `qtodo`
   * **Supported account types**: Choose based on your needs
     * **Single tenant**: Only users in your organization
     * **Multi-tenant**: Users from any organization
   * **Redirect URI**: Add the URL of the qtodo application here (for example `https://qtodo-qtodo.apps.ztvp.example.com`)/
6. Click **Register**

After the creation, you will see the _Overview_ page:

* **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
* **Directory (tenant) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

**Save these values** - you will need them later.

Let's create a new secret for our app:

1. Click **Certificates & secrets** in the left menu
2. Click **New client secret**
3. Add a description: `qtodo secret`
4. Choose expiration: 6 months, 12 months, 24 months, or custom
5. Click **Add**
6. **IMPORTANT**: Copy the **Value** immediately - it will not be shown again

**Save this value securely** - We will need to add this secret to the Hashicorp Vault in the OpenShift cluster.

#### ZTVP setup

In the `values-secret.yaml` file, we add a new entry with the secret we generated in the Azure portal. For example:

```yaml
  - name: qtodo-oidc-entraid
    vaultPrefixes:
    - apps/qtodo
    fields:
    - name: client-secret
      path: ~/.azure/ztvp-qtodo-entraid-secret
```

In the `values-hub.yaml file`, we add the following configuration for the qtodo application:

```yaml
    qtodo:
      overrides:
        - name: app.oidc.authServerUrl
          value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
        - name: app.oidc.clientId
          value: <YOUR_CLIENT_ID>
        - name: app.oidc.clientSecret.enabled
          value: true
        - name: app.oidc.clientSecret.vaultPath
          value: secret/data/apps/qtodo/qtodo-oidc-entraid
```
