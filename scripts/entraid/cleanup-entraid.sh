#!/bin/bash
# Cleanup script for Azure Entra ID integration
# This script removes all App Registrations and related configurations created by the setup scripts
#
# WARNING: This will permanently delete:
# - qtodo App Registration and its Service Principal
# - rhtas-ztvp App Registration and its Service Principal
# - Claims Mapping Policy for RHTAS (EmailVerified-RHTAS)
# - rhtpa-api App Registration and its Service Principal
# - rhtpa-frontend App Registration and its Service Principal

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

# Configuration variables - use same names as setup scripts
QTODO_APP_NAME="${APP_NAME:-qtodo}"
RHTAS_APP_NAME="${RHTAS_APP_NAME:-rhtas-ztvp}"
RHTPA_API_APP_NAME="${API_APP_NAME:-rhtpa-api}"
RHTPA_FRONTEND_APP_NAME="${FRONTEND_APP_NAME:-rhtpa-frontend}"
RHTAS_POLICY_NAME="EmailVerified-RHTAS"

echo -e "${RED}========================================${NC}"
echo -e "${RED}Azure Entra ID Cleanup${NC}"
echo -e "${RED}WARNING: This will delete all ZTVP App Registrations${NC}"
echo -e "${RED}========================================${NC}"
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

# Function to find app by display name
find_app_id() {
    local app_name="$1"
    $az_cmd ad app list --display-name "${app_name}" --query "[0].appId" -o tsv 2>/dev/null | tr -d '\t\n\r'
}

# Function to find service principal by app ID
find_sp_id() {
    local app_id="$1"
    $az_cmd ad sp list --filter "appId eq '${app_id}'" --query "[0].id" -o tsv 2>/dev/null | tr -d '\t\n\r'
}

# Function to find claims mapping policy
find_policy_id() {
    local policy_name="$1"
    $az_cmd rest --uri https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies \
        --query "value[?displayName=='${policy_name}'] | [0].id" -o tsv 2>/dev/null
}

echo -e "${YELLOW}Scanning for ZTVP resources...${NC}"
echo ""

# Scan for qtodo
QTODO_APP_ID=$(find_app_id "${QTODO_APP_NAME}")
if [ -n "$QTODO_APP_ID" ]; then
    QTODO_SP_ID=$(find_sp_id "${QTODO_APP_ID}")
    echo -e "${YELLOW}Found: ${QTODO_APP_NAME}${NC}"
    echo "  App ID: ${QTODO_APP_ID}"
    [ -n "$QTODO_SP_ID" ] && echo "  Service Principal ID: ${QTODO_SP_ID}"
    QTODO_FOUND=true
else
    echo -e "${GREEN}Not found: ${QTODO_APP_NAME} (already deleted or never created)${NC}"
    QTODO_FOUND=false
fi
echo ""

# Scan for rhtas-ztvp
RHTAS_APP_ID=$(find_app_id "${RHTAS_APP_NAME}")
if [ -n "$RHTAS_APP_ID" ]; then
    RHTAS_SP_ID=$(find_sp_id "${RHTAS_APP_ID}")
    echo -e "${YELLOW}Found: ${RHTAS_APP_NAME}${NC}"
    echo "  App ID: ${RHTAS_APP_ID}"
    [ -n "$RHTAS_SP_ID" ] && echo "  Service Principal ID: ${RHTAS_SP_ID}"
    RHTAS_FOUND=true
else
    echo -e "${GREEN}Not found: ${RHTAS_APP_NAME} (already deleted or never created)${NC}"
    RHTAS_FOUND=false
fi
echo ""

# Scan for Claims Mapping Policy
POLICY_ID=$(find_policy_id "${RHTAS_POLICY_NAME}")
if [ -n "$POLICY_ID" ]; then
    echo -e "${YELLOW}Found: Claims Mapping Policy '${RHTAS_POLICY_NAME}'${NC}"
    echo "  Policy ID: ${POLICY_ID}"
    POLICY_FOUND=true
else
    echo -e "${GREEN}Not found: Claims Mapping Policy '${RHTAS_POLICY_NAME}' (already deleted or never created)${NC}"
    POLICY_FOUND=false
fi
echo ""

# Scan for rhtpa-api
RHTPA_API_APP_ID=$(find_app_id "${RHTPA_API_APP_NAME}")
if [ -n "$RHTPA_API_APP_ID" ]; then
    RHTPA_API_SP_ID=$(find_sp_id "${RHTPA_API_APP_ID}")
    echo -e "${YELLOW}Found: ${RHTPA_API_APP_NAME}${NC}"
    echo "  App ID: ${RHTPA_API_APP_ID}"
    [ -n "$RHTPA_API_SP_ID" ] && echo "  Service Principal ID: ${RHTPA_API_SP_ID}"
    RHTPA_API_FOUND=true
else
    echo -e "${GREEN}Not found: ${RHTPA_API_APP_NAME} (already deleted or never created)${NC}"
    RHTPA_API_FOUND=false
fi
echo ""

# Scan for rhtpa-frontend
RHTPA_FRONTEND_APP_ID=$(find_app_id "${RHTPA_FRONTEND_APP_NAME}")
if [ -n "$RHTPA_FRONTEND_APP_ID" ]; then
    RHTPA_FRONTEND_SP_ID=$(find_sp_id "${RHTPA_FRONTEND_APP_ID}")
    echo -e "${YELLOW}Found: ${RHTPA_FRONTEND_APP_NAME}${NC}"
    echo "  App ID: ${RHTPA_FRONTEND_APP_ID}"
    [ -n "$RHTPA_FRONTEND_SP_ID" ] && echo "  Service Principal ID: ${RHTPA_FRONTEND_SP_ID}"
    RHTPA_FRONTEND_FOUND=true
else
    echo -e "${GREEN}Not found: ${RHTPA_FRONTEND_APP_NAME} (already deleted or never created)${NC}"
    RHTPA_FRONTEND_FOUND=false
fi
echo ""

# Check if anything was found
if [ "$QTODO_FOUND" = false ] && [ "$RHTAS_FOUND" = false ] && [ "$POLICY_FOUND" = false ] && \
   [ "$RHTPA_API_FOUND" = false ] && [ "$RHTPA_FRONTEND_FOUND" = false ]; then
    echo -e "${GREEN}No ZTVP resources found. Nothing to clean up.${NC}"
    exit 0
fi

echo -e "${RED}========================================${NC}"
echo -e "${RED}The following resources will be DELETED:${NC}"
echo -e "${RED}========================================${NC}"
echo ""

[ "$QTODO_FOUND" = true ] && echo -e "${RED}✗ ${QTODO_APP_NAME} App Registration${NC}"
[ "$RHTAS_FOUND" = true ] && echo -e "${RED}✗ ${RHTAS_APP_NAME} App Registration${NC}"
[ "$POLICY_FOUND" = true ] && echo -e "${RED}✗ Claims Mapping Policy '${RHTAS_POLICY_NAME}'${NC}"
[ "$RHTPA_API_FOUND" = true ] && echo -e "${RED}✗ ${RHTPA_API_APP_NAME} App Registration${NC}"
[ "$RHTPA_FRONTEND_FOUND" = true ] && echo -e "${RED}✗ ${RHTPA_FRONTEND_APP_NAME} App Registration${NC}"

echo ""
echo -e "${YELLOW}NOTE: Deleting App Registrations will also delete:${NC}"
echo "  - Service Principals"
echo "  - Client Secrets"
echo "  - Federated Credentials"
echo "  - App Roles"
echo "  - API Scopes"
echo "  - Optional Claims"
echo ""
echo -e "${RED}This action cannot be undone!${NC}"
echo ""

read -p "Are you sure you want to delete these resources? Type 'yes' to confirm: " -r
echo
if [ "$REPLY" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo -e "${YELLOW}Starting cleanup...${NC}"
echo ""

# Delete qtodo
if [ "$QTODO_FOUND" = true ]; then
    echo -e "${YELLOW}Deleting ${QTODO_APP_NAME}...${NC}"

    # Delete service principal first (if exists)
    if [ -n "$QTODO_SP_ID" ]; then
        echo "  Deleting service principal..."
        $az_cmd ad sp delete --id "${QTODO_SP_ID}" 2>/dev/null || echo "  Warning: Service principal already deleted"
    fi

    # Delete app registration
    echo "  Deleting app registration..."
    $az_cmd ad app delete --id "${QTODO_APP_ID}"

    echo -e "${GREEN}✓ ${QTODO_APP_NAME} deleted${NC}"
    echo ""
fi

# Delete rhtas-ztvp
if [ "$RHTAS_FOUND" = true ]; then
    echo -e "${YELLOW}Deleting ${RHTAS_APP_NAME}...${NC}"

    # Delete service principal first (if exists)
    if [ -n "$RHTAS_SP_ID" ]; then
        echo "  Deleting service principal..."
        $az_cmd ad sp delete --id "${RHTAS_SP_ID}" 2>/dev/null || echo "  Warning: Service principal already deleted"
    fi

    # Delete app registration
    echo "  Deleting app registration..."
    $az_cmd ad app delete --id "${RHTAS_APP_ID}"

    echo -e "${GREEN}✓ ${RHTAS_APP_NAME} deleted${NC}"
    echo ""
fi

# Delete Claims Mapping Policy
if [ "$POLICY_FOUND" = true ]; then
    echo -e "${YELLOW}Deleting Claims Mapping Policy '${RHTAS_POLICY_NAME}'...${NC}"

    $az_cmd rest -m delete \
        --uri "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/${POLICY_ID}"

    echo -e "${GREEN}✓ Claims Mapping Policy deleted${NC}"
    echo ""
fi

# Delete rhtpa-api
if [ "$RHTPA_API_FOUND" = true ]; then
    echo -e "${YELLOW}Deleting ${RHTPA_API_APP_NAME}...${NC}"

    # Delete service principal first (if exists)
    if [ -n "$RHTPA_API_SP_ID" ]; then
        echo "  Deleting service principal..."
        $az_cmd ad sp delete --id "${RHTPA_API_SP_ID}" 2>/dev/null || echo "  Warning: Service principal already deleted"
    fi

    # Delete app registration
    echo "  Deleting app registration..."
    $az_cmd ad app delete --id "${RHTPA_API_APP_ID}"

    echo -e "${GREEN}✓ ${RHTPA_API_APP_NAME} deleted${NC}"
    echo ""
fi

# Delete rhtpa-frontend
if [ "$RHTPA_FRONTEND_FOUND" = true ]; then
    echo -e "${YELLOW}Deleting ${RHTPA_FRONTEND_APP_NAME}...${NC}"

    # Delete service principal first (if exists)
    if [ -n "$RHTPA_FRONTEND_SP_ID" ]; then
        echo "  Deleting service principal..."
        $az_cmd ad sp delete --id "${RHTPA_FRONTEND_SP_ID}" 2>/dev/null || echo "  Warning: Service principal already deleted"
    fi

    # Delete app registration
    echo "  Deleting app registration..."
    $az_cmd ad app delete --id "${RHTPA_FRONTEND_APP_ID}"

    echo -e "${GREEN}✓ ${RHTPA_FRONTEND_APP_NAME} deleted${NC}"
    echo ""
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}All ZTVP Azure Entra ID resources have been removed.${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Remove or comment out Entra ID configuration from values-hub.yaml"
echo "2. Remove saved secrets from local files:"
echo "   rm -f ~/.azure/ztvp-qtodo-entraid-secret"
echo "   rm -f ~/.azure/ztvp-rhtas-entraid-secret"
echo "   rm -f ~/.azure/ztvp-rhtpa-entraid-secret"
echo "   rm -f ~/.azure/ztvp-entraid-secret"
echo "3. Redeploy the pattern if needed"
echo ""
echo -e "${GREEN}Done!${NC}"
