# Azure Entra ID integration

This document describes the steps required to integrate the **Zero Trust Validated Pattern** (ZTVP) with **Azure Entra ID**, trusting this service as the Identity Provider for the following components:

* Qtodo demo application
* Red Hat Trusted Artifact Signer (RHTAS)
* Red Hat Trusted Profile Analyzer (RHTPA)

## Configuration

To configure the components we will need access to Azure Portal with permissions to create App Registrations and a Microsoft Entra ID tenant.

### Qtodo

The qtodo application supports two authentication methods with Azure Entra ID:

1. **Client Assertion (Recommended)**: Uses SPIFFE JWT tokens for workload identity. No client secrets needed
2. **Client Secret**: Traditional secret-based authentication

We recommend the **Client Assertion** method, which aligns with zero-trust principles by eliminating static credentials.

#### Qtodo Azure setup with Client Assertion

> **⚠️ Important: SSL Certificate Requirement**
>
> For client assertion authentication to work with Azure Entra ID, Microsoft's platform must be able to reach the SPIRE OIDC discovery endpoints over HTTPS with a **valid SSL certificate**:
>
> * `https://spire-spiffe-oidc-discovery-provider.apps.<your-cluster-domain>/.well-known/openid-configuration`
> * `https://spire-spiffe-oidc-discovery-provider.apps.<your-cluster-domain>/keys`
>
> The hostname in these URLs matches the `issuer` value in the SPIFFE JWT token. If Azure Entra ID cannot reach these endpoints or encounters an SSL certificate error (self-signed, expired, untrusted CA, etc.), the federated credential validation will fail and authentication will not work.
>
> **Requirements:**
>
> * The SPIRE OIDC Discovery Provider route must be publicly accessible from the internet
> * The SSL certificate must be issued by a trusted Certificate Authority
> * The certificate must be valid (not expired, correct hostname, complete certificate chain)
>
> Self-signed certificates or certificates from internal/private CAs will cause authentication failures.

You can configure qtodo with Azure Entra ID using either the **Azure Portal** (GUI) or **Azure CLI** (automated).

##### Option A: Automated Setup with Azure CLI

For a quick, automated setup, use the provided script:

```bash
# Set your environment variables
export CLUSTER_DOMAIN="ztvp.example.com"
export QTODO_REDIRECT_URI="https://qtodo-qtodo.apps.${CLUSTER_DOMAIN}/"

# Run the setup script
./scripts/entraid/setup-qtodo-entraid.sh
```

The script will:

1. Create the app registration
2. Set up federated credentials with SPIFFE (using generic audience)
3. Add optional claims
4. Disable user assignment requirement
5. Output configuration data

**Manual Azure CLI Commands:**

If you prefer to run commands individually:

```bash
# Login to Azure
az login

# Get your tenant ID
export TENANT_ID=$(az account show --query tenantId -o tsv | tr -d '\t\n\r')

# Set configuration
export APP_NAME="qtodo"
export CLUSTER_DOMAIN="ztvp.example.com"
export APPS_DOMAIN="apps.${CLUSTER_DOMAIN}"
export QTODO_REDIRECT_URI="https://qtodo-qtodo.${APPS_DOMAIN}/"
export SPIRE_ISSUER="https://spire-spiffe-oidc-discovery-provider.${APPS_DOMAIN}"
export SPIFFE_SUBJECT="spiffe://${APPS_DOMAIN}/ns/qtodo/sa/qtodo"
export AUDIENCE="api://AzureADTokenExchange"

# Create app registration
export CLIENT_ID=$(az ad app create \
    --display-name="${APP_NAME}" \
    --web-redirect-uris="${QTODO_REDIRECT_URI}" \
    --enable-id-token-issuance \
    --query appId \
    -o tsv | tr -d '\t\n\r')

echo "Client ID: ${CLIENT_ID}"

# Get object ID
export OBJECT_ID=$(az ad app show --id="${CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')

# Create federated credential
az ad app federated-credential create \
    --id="${CLIENT_ID}" \
    --parameters "{
        \"name\": \"qtodo-spiffe-federation\",
        \"issuer\": \"${SPIRE_ISSUER}\",
        \"subject\": \"${SPIFFE_SUBJECT}\",
        \"audiences\": [\"${AUDIENCE}\"],
        \"description\": \"SPIFFE workload identity for qtodo application\"
    }"

# Add optional claims
az rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{
        "optionalClaims": {
            "idToken": [
                {"name": "email", "source": null, "essential": false, "additionalProperties": []},
                {"name": "preferred_username", "source": null, "essential": false, "additionalProperties": []}
            ]
        }
    }'

# Create service principal and disable assignment requirement
export SP_ID=$(az ad sp create --id="${CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')
az rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{"appRoleAssignmentRequired": false}'

echo "Setup complete!"
echo "Tenant ID: ${TENANT_ID}"
echo "Client ID: ${CLIENT_ID}"
echo "Audience: ${AUDIENCE}"
```

##### Option B: Manual Setup via Azure Portal

##### Step 1: Create the App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID**
3. Click **App registrations** in the left menu
4. Click **New registration**
5. Fill in the details:
   * **Name**: `qtodo`
   * **Supported account types**: Choose based on your needs
     * **Single tenant**: Only users in your organization (recommended for enterprise deployments)
     * **Multi-tenant**: Users from any organization
   * **Redirect URI**: Add the URL of the qtodo application (for example `https://qtodo-qtodo.apps.ztvp.example.com/`)
6. Click **Register**

After creation, note down these values from the **Overview** page:

* **Application (client) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
* **Directory (tenant) ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

**Save these values** - you will need them for the ZTVP configuration.

##### Step 2: Configure Federated Credentials

Federated credentials allow Azure Entra ID to trust SPIFFE JWT tokens issued by your SPIRE server.

1. Click **Certificates & secrets** in the left menu
2. Click the **Federated credentials** tab
3. Click **Add credential**
4. Select **Other issuer** as the federated credential scenario
5. Fill in the credential details:
   * **Issuer**: Your SPIRE OIDC Discovery Provider URL
     * Format: `https://spire-spiffe-oidc-discovery-provider.<your-cluster-domain>`
     * Example: `https://spire-spiffe-oidc-discovery-provider.apps.ztvp.example.com`
   * **Subject identifier**: SPIFFE ID of the qtodo workload
     * Format: `spiffe://<trust-domain>/ns/<namespace>/sa/<service-account>`
     * Example: `spiffe://apps.ztvp.example.com/ns/qtodo/sa/qtodo`
   * **Name**: `qtodo-spiffe-federation` (or any descriptive name)
   * **Description**: `SPIFFE workload identity for qtodo application`
   * **Audience**: Use the generic audience value
     * Value: `api://AzureADTokenExchange`
6. Click **Add**

**Important Notes**:

* The **Issuer** must match exactly what your SPIRE server publishes in its OIDC discovery document
* The **Subject** must match the SPIFFE ID assigned to the qtodo pod's service account
* The **Audience** must match the value you'll configure in `app.oidc.entraid.audience` (`api://AzureADTokenExchange`)

To verify your SPIRE OIDC issuer URL, run:

```bash
oc get cm -n zero-trust-workload-identity-manager spire-server -o jsonpath='{.data.server\.conf}' | jq -r '.server.jwt_issuer'
```

##### Step 3: Configure Authentication settings

1. Click **Authentication** in the left menu
2. Under **Platform configurations**, verify your redirect URI is listed
3. Under **Implicit grant and hybrid flows**:
   * Check **ID tokens** (used for user authentication)
4. Click **Save**

##### Step 4: Configure Token settings

1. Click **Token configuration** in the left menu
2. Click **Add optional claim**
3. Select **ID** token type
4. Add the following claims (check the boxes):
   * `email`
   * `preferred_username`
5. Click **Add**
6. If prompted about Microsoft Graph permissions, check the box to grant them

##### Step 5: Disable User Assignment Requirement (Optional)

By default, Azure Entra ID requires users to be explicitly assigned to an application before they can access it. To allow all users in your tenant to access qtodo without explicit assignment:

1. Go to **Enterprise applications** in the left menu (not App registrations)
2. Find and click on your **qtodo** application
   * If you don't see it, make sure "Application type" filter is set to "All applications"
3. Click **Properties** in the left menu
4. Find the setting **Assignment required?**
5. Toggle it to **No**
6. Click **Save**

This allows all users in your Azure AD tenant to authenticate to qtodo without requiring explicit role assignments.

**Note:** If you need to restrict access to specific users or groups, keep this setting as **Yes** and use the **Users and groups** section to assign users.

#### Qtodo ZTVP setup with Client Assertion

Now configure your ZTVP deployment to use the Entra ID app registration with client assertion authentication.

In the `values-hub.yaml` file, add the following configuration for the qtodo application:

```yaml
    qtodo:
      overrides:
        # Enable OIDC authentication
        - name: app.oidc.enabled
          value: true
        # Set Entra ID as the OIDC provider
        - name: app.oidc.provider
          value: entraid
        # Entra ID tenant ID (from Azure portal)
        - name: app.oidc.entraid.tenantId
          value: <YOUR_TENANT_ID>
        # Application (client) ID from Azure portal
        - name: app.oidc.clientId
          value: <YOUR_CLIENT_ID>
        # Audience for SPIFFE JWT token validation
        - name: app.oidc.entraid.audience
          value: api://AzureADTokenExchange
        # Enable client assertion (SPIFFE JWT)
        - name: app.oidc.clientAssertion.enabled
          value: true
        # Disable client secret
        - name: app.oidc.clientSecret.enabled
          value: false
```

#### How it works

When using client assertion with Entra ID for a **web application**, there are TWO authentication flows:

##### User Authentication (Web Browser)

1. **User visits qtodo**: User opens `https://qtodo-qtodo.apps.example.com` in their web browser
2. **Redirect to Entra ID**: qtodo redirects the browser to Entra IDs authorization endpoint
3. **User authenticates**: User enters credentials (username/password, MFA, etc.) in Entra ID
4. **Redirect back with code**: Entra ID redirects back to qtodo with an authorization code
5. **Token exchange**: qtodo exchanges the code for tokens (see Backend Authentication below)
6. **User logged in**: User can now access qtodo with an active session

##### Backend Authentication (Client Assertion)

When qtodo needs to exchange the authorization code for tokens:

1. **SPIRE issues JWT token**: The SPIRE agent running on the qtodo pod issues a JWT token (SVID) with:
   * `iss` (issuer): Your SPIRE OIDC Discovery Provider URL
   * `sub` (subject): The qtodo workload's SPIFFE ID
   * `aud` (audience): The generic audience value `api://AzureADTokenExchange`

2. **Qtodo uses JWT for authentication**: Instead of a client secret, qtodo presents the SPIFFE JWT token to Entra ID when requesting access tokens:

   ```text
   POST /token
   grant_type=authorization_code
   code={AUTHORIZATION_CODE}
   client_id={CLIENT_ID}
   client_assertion={SPIFFE_JWT}
   client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
   ```

3. **Entra ID validates the token**: Azure verifies:
   * The JWT is signed by the trusted SPIRE server (via OIDC discovery)
   * The subject matches a registered federated credential
   * The audience matches the configured value

4. **Access granted**: If validation succeeds, Entra ID issues tokens (ID token, access token, refresh token)

**Key Point**: Client assertion replaces the client secret in the token exchange step. Users still log in via browser redirect - nothing changes from their perspective.

This eliminates the need to store and rotate client secrets, reducing the attack surface and following zero-trust principles.

#### Qtodo Vault JWT Role Configuration

To enable the qtodo application to authenticate to HashiCorp Vault using SPIFFE JWT tokens, you need to configure a Vault JWT auth role in `overrides/values-vault-jwt.yaml`:

```yaml
vault_jwt_roles:
- name: qtodo
  audience: api://AzureADTokenExchange
  subject: spiffe://apps.{{ $.Values.global.clusterDomain }}/ns/qtodo/sa/qtodo
  policies:
  - apps-qtodo-jwt-secret
```

**Key Parameters**:

* **audience**: Must match the value configured in `app.oidc.entraid.audience` (e.g., `api://AzureADTokenExchange`)
* **subject**: The SPIFFE ID of the qtodo workload (`spiffe://<trust-domain>/ns/<namespace>/sa/<service-account>`)
* **policies**: Vault policies granting access to qtodo secrets (e.g., `apps-qtodo-jwt-secret` grants read access to `secret/data/apps/qtodo/*`)

This role allows qtodo to exchange its SPIFFE JWT token for a Vault token with the specified policies, enabling secure access to database credentials and other secrets stored in Vault.

#### Alternative: Using Client Secret (Not Recommended)

If you need to use traditional client secret authentication instead of client assertion, follow these steps:

1. In Azure Portal, go to your app registration
2. Click **Certificates & secrets** → **Client secrets** tab
3. Click **New client secret**
4. Add description and expiration, then click **Add**
5. **Copy the secret value immediately** - it won't be shown again

Then update your ZTVP configuration:

```yaml
    qtodo:
      overrides:
        - name: app.oidc.enabled
          value: true
        - name: app.oidc.provider
          value: entraid
        - name: app.oidc.entraid.tenantId
          value: <YOUR_TENANT_ID>
        - name: app.oidc.clientId
          value: <YOUR_CLIENT_ID>
        - name: app.oidc.clientAssertion.enabled
          value: false
        - name: app.oidc.clientSecret.enabled
          value: true
        - name: app.oidc.clientSecret.vaultPath
          value: secret/data/apps/qtodo/qtodo-oidc-entraid
```

And add to `values-secret.yaml`:

```yaml
  - name: qtodo-oidc-entraid
    vaultPrefixes:
    - apps/qtodo
    fields:
    - name: client-secret
      path: ~/.azure/ztvp-qtodo-entraid-secret
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
        az ad sp create --id="$RHTAS_APP_REGISTRATION" --query 'id' -o tsv \
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
           value: <RHTAS_CLIENT_ID>
    supply-chain:
       overrides:
         - name: rhtas.spire.enabled
           value: false
         - name: rhtas.oidc.enabled
           value: true
         - name: rhtas.oidc.url
           value: https://login.microsoftonline.com/<YOUR_TENANT_ID>/v2.0
         - name: rhtas.oidc.clientId
           value: <RHTAS_CLIENT_ID>
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
        * **Single-page application** should be selected.
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
            value: <RHTPA_API_CLIENT_ID>  # UUID only - Helm template prepends api://
    supply-chain:
        overrides:
          - name: rhtpa.oidc.enabled
            value: true
          - name: rhtpa.oidc.url
            value: https://login.microsoftonline.com/<YOUR_TENANT_ID>  # Do not include /v2.0 here, the URL for the OAuth token will be generated from this base URL
          - name: rhtpa.oidc.clientId
            value: <RHTPA_API_CLIENT_ID>
          - name: rhtpa.oidc.apiId
            value: <RHTPA_API_CLIENT_ID>  # UUID only - script prepends api://
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

#### RHTPA Vault JWT Role Configuration

To enable the RHTPA application to authenticate to HashiCorp Vault using SPIFFE JWT tokens, configure a Vault JWT auth role in `overrides/values-vault-jwt.yaml`:

```yaml
vault_jwt_roles:
- name: rhtpa
  audience: rhtpa
  subject: "spiffe://apps.{{ $.Values.global.clusterDomain }}/ns/trusted-profile-analyzer/sa/rhtpa"
  policies:
  - hub-infra-rhtpa-jwt-secret
```

**Key Parameters**:

* **audience**: Internal identifier for RHTPA's Vault authentication (`rhtpa`)
* **subject**: The SPIFFE ID of the RHTPA workload
* **policies**: Vault policies granting access to RHTPA secrets (e.g., `hub-infra-rhtpa-jwt-secret` grants read access to `secret/data/hub/infra/rhtpa/*`)

This role allows RHTPA to exchange its SPIFFE JWT token for a Vault token with the specified policies, enabling secure access to the Entra ID client secret and database credentials stored in Vault.

### Supply Chain

#### Supply Chain Vault JWT Role Configuration

To enable the supply chain pipelines to authenticate to HashiCorp Vault using SPIFFE JWT tokens, configure a Vault JWT auth role in `overrides/values-vault-jwt.yaml`:

```yaml
vault_jwt_roles:
- name: supply-chain
  audience: supply-chain
  subject: "spiffe://apps.{{ $.Values.global.clusterDomain }}/ns/{{ $.Values.global.pattern }}-hub/sa/pipeline"
  policies:
  - hub-supply-chain-jwt-secret
```

**Key Parameters**:

* **audience**: Internal identifier for supply chain Vault authentication (`supply-chain`)
* **subject**: The SPIFFE ID of the Tekton pipeline service account (e.g., `spiffe://apps.<domain>/ns/layered-zero-trust-hub/sa/pipeline`)
* **policies**: Vault policies granting access to supply chain secrets

**Vault Policy for Supply Chain**:

The `hub-supply-chain-jwt-secret` policy grants access to:

* **Quay registry credentials**: `secret/data/hub/infra/quay/*` (read)
* **BYO registry credentials**: `secret/data/hub/infra/registry/*` (read, create, update)
* **RHTPA OIDC credentials**: `secret/data/hub/infra/rhtpa/rhtpa-oidc-cli` (read)
* **Git credentials**: `secret/data/hub/supply-chain/*` (read)

Example policy definition in `overrides/values-vault-jwt.yaml`:

```yaml
vault_jwt_policies:
- name: hub-supply-chain-jwt-secret
  policy: |
    path "secret/data/hub/infra/quay/*" {
      capabilities = ["read"]
    }
    path "secret/data/hub/infra/registry/*" {
      capabilities = ["read", "create", "update"]
    }
    path "secret/data/hub/infra/rhtpa/rhtpa-oidc-cli" {
      capabilities = ["read"]
    }
    path "secret/data/hub/supply-chain/*" {
      capabilities = ["read"]
    }
```

This configuration enables the Tekton pipeline to:

1. Authenticate to Vault using its SPIFFE JWT token
2. Retrieve registry credentials for pushing container images
3. Retrieve RHTPA OIDC credentials for SBOM upload
4. Retrieve Git credentials for cloning protected repositories
