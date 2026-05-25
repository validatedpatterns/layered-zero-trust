# Azure Entra ID integration

This document describes the steps required to integrate the **Zero Trust Validated Pattern** (ZTVP) with **Azure Entra ID**, trusting this service as the Identity Provider for the following components:

* Qtodo demo application
* Red Hat Trusted Artifact Signer (RHTAS)
* Red Hat Trusted Profile Analyzer (RHTPA)

## Configuration

To configure the components we will need access to Azure Portal with permissions to create App Registrations and a Microsoft Entra ID tenant.

### Qtodo

#### Qtodo Azure setup

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **App registrations** in the left menu
4. Click **New registration**
5. Fill in the details:
   * **Name**: `qtodo`
   * **Supported account types**: Choose based on your needs
     * **Single tenant**: Only users in your organization
     * **Multi-tenant**: Users from any organization
   * **Redirect URI**: Add the URL of the qtodo application here (for example `https://qtodo-qtodo.apps.ztvp.example.com/`)
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

#### Qtodo ZTVP setup

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

### RHTAS

#### RHTAS Azure setup

Since in this case we are going to configure some objects that are not visible through the Azure portal, and also require editing within the _App Registration_ Manifest, we will do the configuration using [Azure CLI](https://github.com/Azure/azure-cli).

This configuration uses the [Device code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code) for interactive user authentication in Entra ID.

1. Open a new terminal.
2. Create a new **App Registration**.

    ```shell
    export RHTAS_APP_REGISTRATION=$(
        az ad app create \
            --display-name=rhtas \
            --web-redirect-uris=https://qtodo-qtodo.apps.ztvp.example.com/auth/callback \
            --enable-id-token-issuance \
            --query appId \
            -o tsv \
            | tr -d '\t\n\r')
    ```

3. Create a new **Client Secret** for our _App Registration_. Save this value securely.

    ```shell
    az ad app credential reset \
        --id="$RHTAS_APP_REGISTRATION" \
        --display-name="RHTAS Client Secret" \
        --query 'password' \
        -o tsv
    ```

4. Create a new **Claim Mapping Policy** to define a new JWT claim called `email_verified`.

    ```shell
    az rest -m post \
            --headers Content-Type=application/json \
            --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies \
            --body '{"definition": ["{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\":[{\"value\":\"true\",\"JwtClaimType\":\"email_verified\"}]}}"],"displayName": "EmailVerified"}'
    ```

5. Get the _App Registration_ object ID.

    ```shell
    export RHTAS_APP_OBJECT_ID=$(az ad app list --display-name "rhtas" --query "[0].id" -o tsv | tr -d '\t\n\r')
    ```

6. Enable **Mapped Claims** in the _App Registration_ **manifest**.

    ```shell
    az rest --method patch \
            --uri "https://graph.microsoft.com/v1.0/applications/$RHTAS_APP_OBJECT_ID" \
            --headers 'Content-Type=application/json' \
            --body '{"api":{"acceptMappedClaims":true}}'
    ```

7. Create a new **Service Principal** and associate it with the _App Registration_:

    ```shell
    export SERVICE_PRINCIPAL_ID=$(
        az ad sp create --id="$RHTAS_APP_REGISTRATION" -o tsv --query 'id' \
        | tr -d '\t\n\r')
    ```

8. Get the _Claim Mapping Policy_ ID:

    ```shell
    export CLAIM_MAPPING_POLICY_ID=$(
        az rest --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies \
                --query "value[?displayName=='EmailVerified'] | [0].id" \
                -o tsv)
    ```

9. Associate the _Claim Mapping Policy_ with the _Service Principal_:

    ```shell
    az rest -m post \
            --headers Content-Type=application/json \
            --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SERVICE_PRINCIPAL_ID}/claimsMappingPolicies/\$ref" \
            --body "{\"@odata.id\": \"https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/${CLAIM_MAPPING_POLICY_ID}\"}"
    ```

10. Enable **public client flow** authentication.

    ```shell
    az ad app update --id="$RHTAS_APP_OBJECT_ID" --set isFallbackPublicClient=true
    ```

#### RHTAS ZTVP setup

In the `values-hub.yaml` file, we add the following configuration for the **trusted-artifact-signer** and **supply-chain** applications:

```yaml
    trusted-artifact-signer:
       overrides:
         - name: rhtas.zeroTrust.email.issuer
           value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
         - name: rhtas.fulcio.oidcIssuers.email.clientID
           value: <YOUR_CLIENT_ID>
    supply-chain:
       overrides:
         - name: rhtas.spire.enabled
           value: false
         - name: rhtas.oidc.enabled
           value: true
         - name: rhtas.oidc.url
           value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
         - name: rhtas.oidc.clientId
           value: <YOUR_CLIENT_ID>
         - name: rhtas.oidc.clientSecretName
           value: ""
         - name: rhtas.oidc.issuer
           value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
         - name: rhtas.oidc.identity
           value: <YOUR_ENTRAID_EMAIL>
```

The **device code flow** involves user interaction, so the following tasks in the `qtodo-supply-chain` pipeline require reviewing the output and validating the generated code:

* `qtodo-sign-artifact`
* `qtodo-sign-image`
* `qtodo-sbom-attestation`

When the pipeline reaches any of these tasks, we will need to follow these steps to authorize the signature with our _Azure Entra ID_ credentials:

##### Using the OpenShift Web UI

1. Select **Pipelines -> Pipelines** from the left hand navigation bar.
2. Locate the **qtodo-supply-chain** pipeline. It's within the **layered-zero-trust-hub** project.
3. Select the last `PipelineRun` or start a new one.
4. On the logs tab, select the signing task: `qtodo-sign-artifact`, `qtodo-sign-image` or `qtodo-sbom-attestation`
5. In the log box, on the last lines, you can get the verification code.
6. Go to [https://login.microsoft.com/device](https://login.microsoft.com/device) and enter the verification code
7. Pick your _Microsoft Azure_ account.
8. Authorize the signature by pressing the **Continue** button.

##### Using the OpenShift CLI

1. List the `TaskRuns` in the namespace **layered-zero-trust-hub**.

    ```shell
    oc get taskrun -n layered-zero-trust-hub
    ```

2. Continue monitoring the status of the tasks until one of the signing tasks (`qtodo-sign-artifact`, `qtodo-sign-image` or `qtodo-sbom-attestation`) starts.
3. For each signing task, obtain the verification code and verify it using a Web browser:

    ```shell
    export SIGN_ARTIFACT_POD=$(oc get taskrun -n layered-zero-trust-hub -l tekton.dev/pipelineTask=qtodo-sign-artifact -o jsonpath='{ .items[0].status.podName }')
    oc logs -n layered-zero-trust-hub ${SIGN_ARTIFACT_POD} | grep 'verification code'

    export SIGN_IMAGE_POD=$(oc get taskrun -n layered-zero-trust-hub -l tekton.dev/pipelineTask=qtodo-sign-image -o jsonpath='{ .items[0].status.podName }')
    oc logs -n layered-zero-trust-hub ${SIGN_IMAGE_POD} | grep 'verification code'

    export SIGN_SBOM_POD=$(oc get taskrun -n layered-zero-trust-hub -l tekton.dev/pipelineTask=qtodo-sbom-attestation -o jsonpath='{ .items[0].status.podName }')
    oc logs -n layered-zero-trust-hub ${SIGN_SBOM_POD} | grep 'verification code'
    ```

4. Go to [https://login.microsoft.com/device](https://login.microsoft.com/device) and enter the verification code
5. Pick your _Microsoft Azure_ account.
6. Authorize the signature by pressing the **Continue** button.

### RHTPA

#### RHTPA Azure setup

For RHTPA, we will create two App Registrations in Microsoft Entra ID:

1. **API:** Exposes the Trustify API and defines scopes/permissions
2. **Frontend:** Browser-based authentication for the React frontend

##### RHTPA API configuration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **App registrations** in the left menu
4. Click **New registration**
5. Fill in the details:
   * **Name**: `rhtpa-api`
   * **Supported account types**: Choose based on your needs
     * **Single tenant**: Only users in your organization
     * **Multi-tenant**: Users from any organization
   * **Redirect URI**: Leave it blank (not needed for API)
6. Click **Register**

After the creation, you will see the _Overview_ page:

* **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
* **Directory (tenant) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

**Save these values** - you will need them later.

Let's expose our API:

1. In the left menu, click **Expose an API**
2. Click **Add** next to "Application ID URI"
3. Accept the default value: `api://{API_CLIENT_ID}`
4. Click **Save**

We will continue to define the permissions that clients can request:

1. Still in **Expose an API**, click **Add a scope**
2. Create scopes for different operations:
    1. Create Documents
        * Scope name: `create:document`
        * Who can consent: Admins and users (or Admins only)
        * Admin consent display name: `Create documents in Trustify`
        * Admin consent description: `Allows the application to create documents`
        * User consent display name: `Create documents in Trustify`
        * User consent description: `Allows the application to create documents`
        * State: Enabled
        * Click _Add scope_
    2. Read Documents
        * Scope name: `read:document`
        * Who can consent: Admins and users (or Admins only)
        * Admin consent display name: `Read documents in Trustify`
        * Admin consent description: `Allows the application to read documents`
        * User consent display name: `Read documents in Trustify`
        * User consent description: `Allows the application to read documents`
        * State: Enabled
        * Click _Add scope_
    3. Update Documents
        * Scope name: `update:document`
        * Who can consent: Admins and users (or Admins only)
        * Admin consent display name: `Update documents in Trustify`
        * Admin consent description: `Allows the application to update documents`
        * User consent display name: `Update documents in Trustify`
        * User consent description: `Allows the application to update documents`
        * State: Enabled
        * Click _Add scope_
    4. Delete Documents
        * Scope name: `delete:document`
        * Who can consent: Admins and users (or Admins only)
        * Admin consent display name: `Delete documents in Trustify`
        * Admin consent description: `Allows the application to delete documents`
        * User consent display name: `Delete documents in Trustify`
        * User consent description: `Allows the application to delete documents`
        * State: Enabled
        * Click _Add scope_

After creating all scopes, you'll have:

* `api://{API_CLIENT_ID}/create:document`
* `api://{API_CLIENT_ID}/read:document`
* `api://{API_CLIENT_ID}/update:document`
* `api://{API_CLIENT_ID}/delete:document`

Let's create a new secret for our app:

1. Click **Certificates & secrets** in the left menu
2. Click **New client secret**
3. Add a description: `rhtpa-api secret`
4. Choose expiration: 6 months, 12 months, 24 months, or custom
5. Click **Add**
6. **IMPORTANT**: Copy the **Value** immediately - it will not be shown again

**Save this value securely** - We will need to add this secret to the Hashicorp Vault in the OpenShift cluster.

Let's configure the token version:

1. Click **Manifest** in the left menu
2. Find `"requestedAccessTokenVersion"`, within the `api` attribute, in the JSON
3. Change it from `null` to `2`:

   ```json
   "requestedAccessTokenVersion": 2
   ```

4. Click **Save**

And last but not least, we add application roles for admin consent:

1. Click **App roles** in the left menu
2. Click **Create app role**
3. Create roles for each permission:
    1. **App.Read.Document**
        * Display name: `App.Read.Document`
        * Allowed member types: `Applications`
        * Value: `App.Read.Document`
        * Description: `Allows the application to read documents`
        * Enable the role in the checkbox
        * Click **Apply**
    2. **App.Create.Document**
        * Display name: `App.Create.Document`
        * Allowed member types: `Applications`
        * Value: `App.Create.Document`
        * Description: `Allows the application to create documents`
        * Enable the role in the checkbox
        * Click **Apply**
    3. **App.Update.Document**
        * Display name: `App.Update.Document`
        * Allowed member types: `Applications`
        * Value: `App.Update.Document`
        * Description: `Allows the application to update documents`
        * Enable the role in the checkbox
        * Click **Apply**
    4. **App.Delete.Document**
        * Display name: `App.Delete.Document`
        * Allowed member types: `Applications`
        * Value: `App.Delete.Document`
        * Description: `Allows the application to delete documents`
        * Enable the role in the checkbox
        * Click **Apply**
4. Click **Owners** in the left menu and check if your Azure user is appears in the list. If not, add it by clicking **Add owners**
5. In the left menu, click **API permissions**
6. Click **Add a permission**
7. Go to **My APIs** and select the API application registration you created earlier
8. Select **Application permissions**
9. Check the boxes for:
    * `App.Read.Document`
    * `App.Create.Document`
    * `App.Update.Document`
    * `App.Delete.Document`
10. Click **Add permissions**
11. Click **Grant admin consent** for the application roles we just added. This is **mandatory**

##### RHTPA Frontend configuration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **App registrations** in the left menu
4. Click **New registration**
5. Fill in the details:
   * **Name**: `rhtpa-frontend`
   * **Supported account types**: Choose based on your needs
     * **Single tenant**: Only users in your organization
     * **Multi-tenant**: Users from any organization
   * **Redirect URI**:
     * Platform: `Single-page application (SPA)`
     * URI: Add the URL with your custom domain here (for example `https://servertrustify.apps.ztvp.example.com/`)
6. Click **Register**

After the creation, you will see the _Overview_ page:

* **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
* **Directory (tenant) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

**Save these values** - you will need them later.

The next step is configure the authentication.

1. Click **Authentication** in the left menu
    * **Redirect URI configuration Tab**
      **  * **Single-page application** should be selected.
    * **Settings Tab**
        * **Implicit grant and hybrid flows:**
            * **DO NOT** check "Access tokens" or "ID tokens" - not needed for SPA with PKCE
        * **Allow public client flows**: Disabled
2. Click **Save** if you have made any changes to these parameters

To grant the frontend permission to call your API:

1. Click **API permissions** in the left menu
2. You'll see "Microsoft Graph" with "User.Read" - this is fine to keep
3. Click **Add a permission**
4. Click **My APIs** tab
5. Select **rhtpa-api** (the API app you created in Step 1)
6. Click **Delegated permissions**
7. Check all the scopes you created:
   * `create:document`
   * `read:document`
   * `update:document`
   * `delete:document`
8. Click **Add permissions**

And finally, let's configure the token version:

1. Click **Manifest** in the left menu
2. Find `"requestedAccessTokenVersion"`, within the `api` attribute, in the JSON
3. Change it from `null` to `2`:

   ```json
   "requestedAccessTokenVersion": 2
   ```

4. Click **Save**

#### RHTPA ZTVP setup

In the `values-hub.yaml` file, we add the following configuration for the **trusted-profile-analyzer** application:

```yaml
    trusted-profile-analyzer:
        overrides:
          - name: rhtpa.zeroTrust.oidc.authServerUrl
            value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
          - name: rhtpa.zeroTrust.oidc.clients.frontend.clientId
            value: <RHTPA_FRONTEND_CLIENT_ID>
          - name: rhtpa.zeroTrust.oidc.clients.cli.clientId
            value: <RHTPA_API_CLIENT_ID>
          - name: rhtpa.zeroTrust.oidc.clients.cli.apiId
            value: <RHTPA_API_API_ID>
    supply-chain:
        overrides:
          - name: rhtpa.oidc.enabled
            value: true
          - name: rhtpa.oidc.url
            value: https://login.microsoftonline.com/<YOUR_TENANT_ID>  # Do not include /v2.0 here, the URL for the OAuth token will be generated from this base URL
          - name: rhtpa.oidc.clientId
            value: <RHTPA_API_CLIENT_ID>
          - name: rhtpa.oidc.apiId
            value: <RHTPA_API_API_ID>
```

In the `values-secret.yaml` file, make sure that the secret `rhtpa-oidc-cli` uses the file with the secret associated with the _App Registration_ `rhtpa-api` instead of generating it dynamically.

```yaml
  # - name: rhtpa-oidc-cli
  #   vaultPrefixes:
  #   - hub/infra/rhtpa
  #   fields:
  #   - name: client-secret
  #     onMissingValue: generate
  #     vaultPolicy: alphaNumericPolicy

  # Microsoft Entra ID (Azure AD) OIDC for RHTPA
  # This secret supplies the client secret for the Entra app registration
  # that backs zeroTrust.oidc.clients.cli The value is read from a local file at 'path'
  # Create the client secret in Azure Portal and store it in that file
  - name: rhtpa-oidc-cli
    vaultPrefixes:
    - hub/infra/rhtpa
    fields:
    - name: client-secret
      path: ~/.azure/ztvp-entraid-secret
```
