# Azure Entra ID integration

This document describes the steps required to integrate the **Zero Trust Validated Pattern** (ZTVP) with **Azure Entra ID**, trusting this service as the Identity Provider for the following components:

* Qtodo demo application
* Red Hat Trusted Artifact Signer (RHTAS)

> [!WARNING]
> The integration of Azure Entra ID into the pattern is still **in progress** and does not cover all components. This document describes those that are supported. For components not supported by Entra ID, **Red Hat Build of Keycloak (RHBK)** will continue to be used as the default OIDC.

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
