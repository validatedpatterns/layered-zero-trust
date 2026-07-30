#!/bin/bash
# Setup script for RHTAS Azure Entra ID integration
# This script creates and configures an App Registration for RHTAS with device code flow

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
APP_NAME="${APP_NAME:-rhtas-ztvp}"
CLUSTER_DOMAIN="${CLUSTER_DOMAIN:-ztvp.example.com}"  # Example: ztvp.example.com (without 'apps.' prefix)
APPS_DOMAIN="${APPS_DOMAIN:-apps.${CLUSTER_DOMAIN}}"  # OpenShift applications domain
RHTAS_REDIRECT_URI="${RHTAS_REDIRECT_URI:-https://qtodo-qtodo.${APPS_DOMAIN}/auth/callback}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RHTAS Azure Entra ID Setup${NC}"
echo -e "${GREEN}Device Code Flow Authentication${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

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
echo "  App Name:       ${APP_NAME}"
echo "  Redirect URI:   ${RHTAS_REDIRECT_URI}"
echo "  Cluster Domain: ${CLUSTER_DOMAIN}"
echo "  Apps Domain:    ${APPS_DOMAIN}"
echo ""

read -p "Continue with this configuration? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 1: Creating App Registration...${NC}"

# Create the app registration
CLIENT_ID=$($az_cmd ad app create \
    --display-name="${APP_NAME}" \
    --web-redirect-uris="${RHTAS_REDIRECT_URI}" \
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
echo -e "${YELLOW}Step 2: Creating Client Secret...${NC}"

# Create client secret
CLIENT_SECRET=$($az_cmd ad app credential reset \
    --id="${CLIENT_ID}" \
    --display-name="RHTAS Client Secret" \
    --query 'password' \
    -o tsv | tr -d '\t\n\r')

echo -e "${GREEN}✓ Client Secret created${NC}"
echo -e "${RED}  IMPORTANT: Save this secret securely - it won't be shown again${NC}"

echo ""
echo -e "${YELLOW}Step 3: Creating Claims Mapping Policy...${NC}"

# Create claims mapping policy for email_verified
POLICY_RESULT=$($az_cmd rest -m post \
    --headers Content-Type=application/json \
    --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies \
    --body '{
        "definition": [
            "{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\",\"ClaimsSchema\":[{\"value\":\"true\",\"JwtClaimType\":\"email_verified\"}]}}"
        ],
        "displayName": "EmailVerified-RHTAS"
    }')

POLICY_ID=$(echo "$POLICY_RESULT" | jq -r '.id')

if [ -z "$POLICY_ID" ] || [ "$POLICY_ID" = "null" ]; then
    # Policy might already exist, try to get it
    POLICY_ID=$($az_cmd rest \
        --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies \
        --query "value[?displayName=='EmailVerified-RHTAS'] | [0].id" \
        -o tsv)

    if [ -z "$POLICY_ID" ] || [ "$POLICY_ID" = "null" ]; then
        echo -e "${RED}ERROR: Failed to create or find claims mapping policy${NC}"
        exit 1
    fi
    echo -e "${YELLOW}  Using existing claims mapping policy${NC}"
fi

echo -e "${GREEN}✓ Claims Mapping Policy configured${NC}"
echo -e "  Policy ID: ${POLICY_ID}"

echo ""
echo -e "${YELLOW}Step 4: Enabling Mapped Claims in manifest...${NC}"

# Enable acceptMappedClaims in the app manifest
$az_cmd rest --method patch \
    --uri "https://graph.microsoft.com/v1.0/applications/${OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{"api":{"acceptMappedClaims":true}}'

echo -e "${GREEN}✓ Mapped claims enabled${NC}"

echo ""
echo -e "${YELLOW}Step 5: Creating Service Principal...${NC}"

# Create service principal
SP_ID=$($az_cmd ad sp create --id="${CLIENT_ID}" -o tsv --query 'id' | tr -d '\t\n\r')

if [ -z "$SP_ID" ]; then
    echo -e "${RED}ERROR: Failed to create service principal${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Service Principal created${NC}"
echo -e "  Service Principal ID: ${SP_ID}"

echo ""
echo -e "${YELLOW}Step 6: Associating Claims Mapping Policy with Service Principal...${NC}"

# Associate the claims mapping policy with the service principal
$az_cmd rest -m post \
    --headers Content-Type=application/json \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/claimsMappingPolicies/\$ref" \
    --body "{\"@odata.id\": \"https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/${POLICY_ID}\"}"

echo -e "${GREEN}✓ Claims Mapping Policy associated${NC}"

echo ""
echo -e "${YELLOW}Step 7: Enabling Public Client Flow...${NC}"

# Enable public client flow (isFallbackPublicClient)
$az_cmd ad app update --id="${OBJECT_ID}" --set isFallbackPublicClient=true

echo -e "${GREEN}✓ Public client flow enabled${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration Data:${NC}"
echo ""
echo "Tenant ID:     ${TENANT_ID}"
echo "Client ID:     ${CLIENT_ID}"
echo "Client Secret: ${CLIENT_SECRET}"
echo ""
echo -e "${RED}IMPORTANT: Save the client secret to a file:${NC}"
echo ""
echo "mkdir -p ~/.azure"
echo "echo '${CLIENT_SECRET}' > ~/.azure/ztvp-rhtas-entraid-secret"
echo "chmod 600 ~/.azure/ztvp-rhtas-entraid-secret"
echo ""
echo -e "${YELLOW}Note: You'll need your Azure Entra ID email address for the supply-chain configuration${NC}"
echo ""
echo -e "${YELLOW}Verification Commands:${NC}"
echo ""
echo "# View the app registration:"
echo "az ad app show --id=${CLIENT_ID}"
echo ""
echo "# View service principal:"
echo "az ad sp show --id=${SP_ID}"
echo ""
echo "# View claims mapping policy:"
echo "az rest --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/${POLICY_ID}"
echo ""
echo -e "${GREEN}Done!${NC}"
