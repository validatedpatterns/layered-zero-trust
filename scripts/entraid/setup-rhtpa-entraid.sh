#!/bin/bash
# Setup script for RHTPA Azure Entra ID integration
# This script creates and configures two App Registrations for RHTPA:
# 1. API: Exposes the Trustify API with scopes and app roles
# 2. Frontend: Browser-based authentication for the React frontend

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
API_APP_NAME="${API_APP_NAME:-rhtpa-api}"
FRONTEND_APP_NAME="${FRONTEND_APP_NAME:-rhtpa-frontend}"
CLUSTER_DOMAIN="${CLUSTER_DOMAIN:-ztvp.example.com}"  # Example: ztvp.example.com (without 'apps.' prefix)
APPS_DOMAIN="${APPS_DOMAIN:-apps.${CLUSTER_DOMAIN}}"  # OpenShift applications domain
RHTPA_REDIRECT_URI="${RHTPA_REDIRECT_URI:-https://servertrustify.${APPS_DOMAIN}/}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RHTPA Azure Entra ID Setup${NC}"
echo -e "${GREEN}API + Frontend Configuration${NC}"
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
echo "  API App Name:      ${API_APP_NAME}"
echo "  Frontend App Name: ${FRONTEND_APP_NAME}"
echo "  Redirect URI:      ${RHTPA_REDIRECT_URI}"
echo "  Cluster Domain:    ${CLUSTER_DOMAIN}"
echo "  Apps Domain:       ${APPS_DOMAIN}"
echo ""

read -p "Continue with this configuration? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Part 1: API App Registration${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Step 1: Creating API App Registration...${NC}"

# Create the API app registration (no redirect URI needed for API)
API_CLIENT_ID=$($az_cmd ad app create \
    --display-name="${API_APP_NAME}" \
    --query appId \
    -o tsv \
    | tr -d '\t\n\r')

if [ -z "$API_CLIENT_ID" ]; then
    echo -e "${RED}ERROR: Failed to create API app registration${NC}"
    exit 1
fi

echo -e "${GREEN}✓ API App Registration created${NC}"
echo -e "  API Client ID: ${API_CLIENT_ID}"

# Get the object ID
API_OBJECT_ID=$($az_cmd ad app show --id="${API_CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')
echo -e "  API Object ID: ${API_OBJECT_ID}"

# Application ID URI
API_ID_URI="api://${API_CLIENT_ID}"

echo ""
echo -e "${YELLOW}Step 2: Setting Application ID URI...${NC}"

# Set the Application ID URI (Expose an API)
$az_cmd ad app update \
    --id="${API_CLIENT_ID}" \
    --identifier-uris="${API_ID_URI}"

echo -e "${GREEN}✓ Application ID URI configured${NC}"
echo -e "  URI: ${API_ID_URI}"

echo ""
echo -e "${YELLOW}Step 3: Creating API Scopes...${NC}"

# Generate UUIDs for scopes and store them
SCOPE_CREATE_ID=$(uuidgen)
SCOPE_READ_ID=$(uuidgen)
SCOPE_UPDATE_ID=$(uuidgen)
SCOPE_DELETE_ID=$(uuidgen)

# Define scopes using Microsoft Graph API
# We need to add oauth2PermissionScopes to the api section
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${API_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body "{
        \"api\": {
            \"oauth2PermissionScopes\": [
                {
                    \"adminConsentDescription\": \"Allows the application to create documents\",
                    \"adminConsentDisplayName\": \"Create documents in Trustify\",
                    \"id\": \"${SCOPE_CREATE_ID}\",
                    \"isEnabled\": true,
                    \"type\": \"User\",
                    \"userConsentDescription\": \"Allows the application to create documents\",
                    \"userConsentDisplayName\": \"Create documents in Trustify\",
                    \"value\": \"create:document\"
                },
                {
                    \"adminConsentDescription\": \"Allows the application to read documents\",
                    \"adminConsentDisplayName\": \"Read documents in Trustify\",
                    \"id\": \"${SCOPE_READ_ID}\",
                    \"isEnabled\": true,
                    \"type\": \"User\",
                    \"userConsentDescription\": \"Allows the application to read documents\",
                    \"userConsentDisplayName\": \"Read documents in Trustify\",
                    \"value\": \"read:document\"
                },
                {
                    \"adminConsentDescription\": \"Allows the application to update documents\",
                    \"adminConsentDisplayName\": \"Update documents in Trustify\",
                    \"id\": \"${SCOPE_UPDATE_ID}\",
                    \"isEnabled\": true,
                    \"type\": \"User\",
                    \"userConsentDescription\": \"Allows the application to update documents\",
                    \"userConsentDisplayName\": \"Update documents in Trustify\",
                    \"value\": \"update:document\"
                },
                {
                    \"adminConsentDescription\": \"Allows the application to delete documents\",
                    \"adminConsentDisplayName\": \"Delete documents in Trustify\",
                    \"id\": \"${SCOPE_DELETE_ID}\",
                    \"isEnabled\": true,
                    \"type\": \"User\",
                    \"userConsentDescription\": \"Allows the application to delete documents\",
                    \"userConsentDisplayName\": \"Delete documents in Trustify\",
                    \"value\": \"delete:document\"
                }
            ]
        }
    }"

echo -e "${GREEN}✓ API Scopes created${NC}"
echo -e "  - create:document (${SCOPE_CREATE_ID})"
echo -e "  - read:document (${SCOPE_READ_ID})"
echo -e "  - update:document (${SCOPE_UPDATE_ID})"
echo -e "  - delete:document (${SCOPE_DELETE_ID})"

echo ""
echo -e "${YELLOW}Step 4: Creating API Client Secret...${NC}"

# Create client secret
API_CLIENT_SECRET=$($az_cmd ad app credential reset \
    --id="${API_CLIENT_ID}" \
    --display-name="RHTPA API Secret" \
    --query 'password' \
    -o tsv | tr -d '\t\n\r')

echo -e "${GREEN}✓ API Client Secret created${NC}"
echo -e "${RED}  IMPORTANT: Save this secret securely - it won't be shown again${NC}"

echo ""
echo -e "${YELLOW}Step 5: Configuring Token Version...${NC}"

# Set requestedAccessTokenVersion to 2
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${API_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{
        "api": {
            "requestedAccessTokenVersion": 2
        }
    }'

echo -e "${GREEN}✓ Token version set to v2${NC}"

echo ""
echo -e "${YELLOW}Step 6: Creating Application Roles...${NC}"

# Create app roles for service-to-service authentication
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${API_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body "{
        \"appRoles\": [
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"Allows the application to read documents\",
                \"displayName\": \"App.Read.Document\",
                \"id\": \"$(uuidgen)\",
                \"isEnabled\": true,
                \"value\": \"App.Read.Document\"
            },
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"Allows the application to create documents\",
                \"displayName\": \"App.Create.Document\",
                \"id\": \"$(uuidgen)\",
                \"isEnabled\": true,
                \"value\": \"App.Create.Document\"
            },
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"Allows the application to update documents\",
                \"displayName\": \"App.Update.Document\",
                \"id\": \"$(uuidgen)\",
                \"isEnabled\": true,
                \"value\": \"App.Update.Document\"
            },
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"Allows the application to delete documents\",
                \"displayName\": \"App.Delete.Document\",
                \"id\": \"$(uuidgen)\",
                \"isEnabled\": true,
                \"value\": \"App.Delete.Document\"
            }
        ]
    }"

echo -e "${GREEN}✓ Application Roles created${NC}"
echo -e "  - App.Read.Document"
echo -e "  - App.Create.Document"
echo -e "  - App.Update.Document"
echo -e "  - App.Delete.Document"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Part 2: Frontend App Registration${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Step 7: Creating Frontend App Registration...${NC}"

# Create the frontend app registration (without redirect URI first)
FRONTEND_CLIENT_ID=$($az_cmd ad app create \
    --display-name="${FRONTEND_APP_NAME}" \
    --query appId \
    -o tsv \
    | tr -d '\t\n\r')

if [ -z "$FRONTEND_CLIENT_ID" ]; then
    echo -e "${RED}ERROR: Failed to create frontend app registration${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Frontend App Registration created${NC}"
echo -e "  Frontend Client ID: ${FRONTEND_CLIENT_ID}"

# Get the object ID
FRONTEND_OBJECT_ID=$($az_cmd ad app show --id="${FRONTEND_CLIENT_ID}" --query id -o tsv | tr -d '\t\n\r')
echo -e "  Frontend Object ID: ${FRONTEND_OBJECT_ID}"

# Configure SPA redirect URI via Graph API
echo -e "${YELLOW}  Configuring SPA redirect URI...${NC}"

$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${FRONTEND_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body "{
        \"spa\": {
            \"redirectUris\": [\"${RHTPA_REDIRECT_URI}\"]
        }
    }"

echo -e "${GREEN}  SPA redirect URI configured${NC}"

echo ""
echo -e "${YELLOW}Step 8: Configuring Frontend Token Version...${NC}"

# Set requestedAccessTokenVersion to 2 for frontend
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${FRONTEND_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body '{
        "api": {
            "requestedAccessTokenVersion": 2
        }
    }'

echo -e "${GREEN}✓ Frontend token version set to v2${NC}"

echo ""
echo -e "${YELLOW}Step 9: Granting Frontend Permissions to API...${NC}"

# Add API permissions to frontend app using the stored scope IDs
# We need to add requiredResourceAccess for the API scopes
$az_cmd rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${FRONTEND_OBJECT_ID}" \
    --headers 'Content-Type=application/json' \
    --body "{
        \"requiredResourceAccess\": [
            {
                \"resourceAppId\": \"${API_CLIENT_ID}\",
                \"resourceAccess\": [
                    {
                        \"id\": \"${SCOPE_CREATE_ID}\",
                        \"type\": \"Scope\"
                    },
                    {
                        \"id\": \"${SCOPE_READ_ID}\",
                        \"type\": \"Scope\"
                    },
                    {
                        \"id\": \"${SCOPE_UPDATE_ID}\",
                        \"type\": \"Scope\"
                    },
                    {
                        \"id\": \"${SCOPE_DELETE_ID}\",
                        \"type\": \"Scope\"
                    }
                ]
            }
        ]
    }"

echo -e "${GREEN}✓ Frontend permissions configured${NC}"
echo -e "${YELLOW}  Note: Admin consent is required but must be granted by an administrator${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration Data:${NC}"
echo ""
echo "Tenant ID:              ${TENANT_ID}"
echo "API Client ID:          ${API_CLIENT_ID}"
echo "API Client Secret:      ${API_CLIENT_SECRET}"
echo "Frontend Client ID:     ${FRONTEND_CLIENT_ID}"
echo ""
echo -e "${RED}IMPORTANT: Save the API client secret to a file:${NC}"
echo ""
echo "mkdir -p ~/.azure"
echo "echo '${API_CLIENT_SECRET}' > ~/.azure/ztvp-rhtpa-entraid-secret"
echo "chmod 600 ~/.azure/ztvp-rhtpa-entraid-secret"
echo ""
echo -e "${YELLOW}IMPORTANT: Grant Admin Consent${NC}"
echo ""
echo "The API permissions require admin consent. Ask your Azure administrator to:"
echo "1. Go to Azure Portal > App registrations > ${FRONTEND_APP_NAME}"
echo "2. Navigate to API permissions"
echo "3. Click 'Grant admin consent' for the application roles"
echo ""
echo -e "${YELLOW}Verification Commands:${NC}"
echo ""
echo "# View API app registration:"
echo "az ad app show --id=${API_CLIENT_ID}"
echo ""
echo "# View frontend app registration:"
echo "az ad app show --id=${FRONTEND_CLIENT_ID}"
echo ""
echo "# View API scopes:"
echo "az ad app show --id=${API_CLIENT_ID} --query 'api.oauth2PermissionScopes[].value'"
echo ""
echo "# View API app roles:"
echo "az ad app show --id=${API_CLIENT_ID} --query 'appRoles[].value'"
echo ""
echo -e "${GREEN}Done!${NC}"
