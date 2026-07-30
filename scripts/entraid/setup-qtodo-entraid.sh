#!/bin/bash
# Setup script for qtodo Azure Entra ID integration with Client Assertion
# This script creates and configures an App Registration for qtodo with SPIFFE federated credentials
#
# This configuration supports:
# - Web-based user authentication via OAuth 2.0 authorization code flow
# - Backend authentication using SPIFFE JWT (client assertion) instead of client secrets

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for az command
if command -v az &> /dev/null; then
    # Use native az cli
    az_cmd="az"
elif podman ps &> /dev/null 2>&1 && podman image exists azcli &> /dev/null 2>&1; then
    # Use containerized az cli
    az_cmd="podman run --rm -h az --net host -w /root -v $HOME/.azure:/root/.azure:Z -v $HOME/.ssh:/root/.ssh:Z azcli az"
else
    echo -e "${RED}ERROR: Azure CLI not found${NC}"
    echo "Please install Azure CLI or create an 'azcli' container image"
    echo "  Native: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    echo "  Container: podman pull mcr.microsoft.com/azure-cli && podman tag mcr.microsoft.com/azure-cli azcli"
    exit 1
fi

# Configuration variables with environment variable support
# Example: export CLUSTER_DOMAIN="ztvp.example.com"
APP_NAME="${APP_NAME:-qtodo}"
CLUSTER_DOMAIN="${CLUSTER_DOMAIN:-ztvp.example.com}"  # Example: ztvp.example.com (without 'apps.' prefix)
APPS_DOMAIN="${APPS_DOMAIN:-apps.${CLUSTER_DOMAIN}}"  # OpenShift applications domain
QTODO_REDIRECT_URI="${QTODO_REDIRECT_URI:-https://qtodo-qtodo.${APPS_DOMAIN}/}"

# SPIRE configuration - auto-detected from cluster or set manually
SPIRE_ISSUER="${SPIRE_ISSUER:-https://spire-spiffe-oidc-discovery-provider.${APPS_DOMAIN}}"
SPIRE_TRUST_DOMAIN="${SPIRE_TRUST_DOMAIN:-${APPS_DOMAIN}}"

# SPIFFE ID for qtodo workload
QTODO_NAMESPACE="${QTODO_NAMESPACE:-qtodo}"
QTODO_SA="${QTODO_SA:-qtodo}"
SPIFFE_SUBJECT="spiffe://${SPIRE_TRUST_DOMAIN}/ns/${QTODO_NAMESPACE}/sa/${QTODO_SA}"

# Audience for SPIFFE JWT token validation
# This is a generic audience value that can be safely used with Entra ID
AUDIENCE="${AUDIENCE:-api://AzureADTokenExchange}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}QTodo Azure Entra ID Setup${NC}"
echo -e "${GREEN}Client Assertion with SPIFFE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Verify Azure CLI is installed and logged in
echo -e "${YELLOW}Checking Azure CLI...${NC}"

# Check if logged in
if ! $az_cmd account show &> /dev/null; then
    echo -e "${RED}ERROR: Not logged in to Azure${NC}"
    echo "Run: az login"
    exit 1
fi

TENANT_ID=$($az_cmd account show --query tenantId -o tsv | tr -d '\t\n\r')
echo -e "${GREEN}✓ Logged in to Azure${NC}"
echo -e "  Tenant ID: ${TENANT_ID}"
echo ""

# Display configuration
echo -e "${YELLOW}Configuration:${NC}"
echo "  App Name:           ${APP_NAME}"
echo "  Redirect URI:       ${QTODO_REDIRECT_URI}"
echo "  Cluster Domain:     ${CLUSTER_DOMAIN}"
echo "  Apps Domain:        ${APPS_DOMAIN}"
echo "  SPIRE Issuer:       ${SPIRE_ISSUER}"
echo "  SPIRE Trust Domain: ${SPIRE_TRUST_DOMAIN}"
echo "  SPIFFE Subject:     ${SPIFFE_SUBJECT}"
echo "  Audience:           ${AUDIENCE}"
echo ""

read -p "Continue with this configuration? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 1: Creating App Registration...${NC}"

# Create the app registration with web redirect URIs for OAuth 2.0 authorization code flow
# The redirect URI is where Entra ID sends users after authentication
CLIENT_ID=$($az_cmd ad app create \
    --display-name="${APP_NAME}" \
    --web-redirect-uris="${QTODO_REDIRECT_URI}" \
    --enable-id-token-issuance \
    --query appId \
    -o tsv \
    | tr -d '\t\n\r')

if [ -z "$CLIENT_ID" ]; then
    echo -e "${RED}ERROR: Failed to create app registration${NC}"
    exit 1
fi

echo -e "${GREEN}✓ App Registration created${NC}"
echo -e "  Client ID: ${CLIENT_ID}"

# Get the object ID
OBJECT_ID=$($az_cmd ad app show --id="${CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')
echo -e "  Object ID: ${OBJECT_ID}"

echo ""
echo -e "${YELLOW}Step 2: Verifying identifierUris configuration...${NC}"

# Check current identifierUris value
CURRENT_URIS=$($az_cmd ad app show --id="${CLIENT_ID}" --query identifierUris -o json)

if [ "$CURRENT_URIS" = "[]" ] || [ "$CURRENT_URIS" = "null" ]; then
    echo -e "${GREEN}✓ identifierUris is empty (correct for client assertion with generic audience)${NC}"
else
    echo -e "${YELLOW}  Warning: identifierUris is set to: ${CURRENT_URIS}${NC}"
    echo -e "${YELLOW}  Clearing identifierUris to avoid conflicts...${NC}"
    $az_cmd ad app update --id="${CLIENT_ID}" --identifier-uris "[]"
    echo -e "${GREEN}✓ identifierUris cleared${NC}"
fi

echo ""
echo -e "${YELLOW}Step 3: Configuring Federated Credentials...${NC}"

# Create federated credential for SPIFFE
# This enables qtodo to authenticate using SPIFFE JWT tokens instead of client secrets
# Users still log in via browser redirect - this is for backend authentication only
CREDENTIAL_NAME="${APP_NAME}-spiffe-federation"

# Use the configured audience value (e.g., api://AzureADTokenExchange)
$az_cmd ad app federated-credential create \
    --id="${CLIENT_ID}" \
    --parameters "{
        \"name\": \"${CREDENTIAL_NAME}\",
        \"issuer\": \"${SPIRE_ISSUER}\",
        \"subject\": \"${SPIFFE_SUBJECT}\",
        \"audiences\": [\"${AUDIENCE}\"],
        \"description\": \"SPIFFE workload identity for ${APP_NAME} application\"
    }"

echo -e "${GREEN}✓ Federated credential created${NC}"
echo -e "  Name:     ${CREDENTIAL_NAME}"
echo -e "  Issuer:   ${SPIRE_ISSUER}"
echo -e "  Subject:  ${SPIFFE_SUBJECT}"
echo -e "  Audience: ${AUDIENCE}"

echo ""
echo -e "${YELLOW}Step 4: Configuring optional claims...${NC}"

# Add optional claims for email and preferred_username
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{
        "optionalClaims": {
            "idToken": [
                {
                    "name": "email",
                    "source": null,
                    "essential": false,
                    "additionalProperties": []
                },
                {
                    "name": "preferred_username",
                    "source": null,
                    "essential": false,
                    "additionalProperties": []
                }
            ]
        }
    }'

echo -e "${GREEN}✓ Optional claims configured${NC}"
echo -e "  Added: email, preferred_username"

echo ""
echo -e "${YELLOW}Step 5: Disabling user assignment requirement...${NC}"

# Create service principal if it doesn't exist
SP_ID=$($az_cmd ad sp list --filter "appId eq '${CLIENT_ID}'" --query "[0].id" -o tsv | tr -d '\t\n\r')

if [ -z "$SP_ID" ]; then
    echo "  Creating service principal..."
    SP_ID=$($az_cmd ad sp create --id="${CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')
fi

# Disable assignment requirement to allow all users in the tenant to access the app
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{
        "appRoleAssignmentRequired": false
    }'

echo -e "${GREEN}✓ User assignment requirement disabled${NC}"
echo -e "  All tenant users can now access the application"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration Data:${NC}"
echo ""
echo "Tenant ID:    ${TENANT_ID}"
echo "Client ID:    ${CLIENT_ID}"
echo "Audience:     ${AUDIENCE}"
echo ""
echo -e "${YELLOW}Verification Commands:${NC}"
echo ""
echo "# View the app registration:"
echo "az ad app show --id=${CLIENT_ID}"
echo ""
echo "# View federated credentials:"
echo "az ad app federated-credential list --id=${CLIENT_ID}"
echo ""
echo "# Verify identifierUris is empty:"
echo "az ad app show --id=${CLIENT_ID} --query identifierUris"
echo ""
echo "# Test SPIRE OIDC Discovery (requires public access):"
echo "curl ${SPIRE_ISSUER}/.well-known/openid-configuration"
echo ""
echo -e "${GREEN}Done!${NC}"
