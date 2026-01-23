#!/usr/bin/env bash
set -eu

get_abs_filename() {
  # $1 : relative filename
  echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
}

SCRIPT=$(get_abs_filename "$0")
SCRIPTPATH=$(dirname "${SCRIPT}")
COMMONPATH=$(dirname "${SCRIPTPATH}")
PATTERNPATH=$(dirname "${COMMONPATH}")
MAIN_CLUSTERGROUP_FILE="./values-$(common/scripts/determine-main-clustergroup.sh).yaml"

# Parse arguments
if [ $# -lt 1 ]; then
  echo "Specify at least the command ($#): $*"
  exit 1
fi

TASK="${1}"
PATTERN_NAME=${2:-$(basename "`pwd`")}

if [ -z "${TASK}" ]; then
	echo "Task is unset"
	exit 1
fi

EXTRA_PLAYBOOK_OPTS="${EXTRA_PLAYBOOK_OPTS:-}"

EXTRA_VARS_FILE=$(mktemp)
trap "rm -f ${EXTRA_VARS_FILE}" EXIT

if [ "$(yq ".clusterGroup.applications.vault.jwt.enabled // \"false\"" "${MAIN_CLUSTERGROUP_FILE}")" == "true" ]; then
  OCP_DOMAIN="$(oc get dns cluster -o jsonpath='{.spec.baseDomain}')"
  OIDC_DISCOVERY_URL="$(yq ".clusterGroup.applications.vault.jwt.oidcDiscoveryUrl" "${MAIN_CLUSTERGROUP_FILE}" | sed "s/{{ \$.Values.global.clusterDomain }}/${OCP_DOMAIN}/g")"
  JWT_ROLES="$(yq -o json ".clusterGroup.applications.vault.jwt.roles" "${MAIN_CLUSTERGROUP_FILE}" | sed "s/{{ \$.Values.global.clusterDomain }}/${OCP_DOMAIN}/g")"
  # Extract JWT policies (policies ending in -jwt-secret)
  JWT_POLICIES="$(yq -o json ".clusterGroup.applications.vault.policies" "${MAIN_CLUSTERGROUP_FILE}" | jq '[.[] | select(.name | test("-jwt-secret$"))]')"

  if [ "${OIDC_DISCOVERY_URL}" == "null" ] || [ "${JWT_ROLES}" == "null" ] || [ "${JWT_ROLES}" == "[]" ]; then
    echo "Vault JWT config is disabled because of missing required fields"
    VAULT_JWT_CONFIG="false"
    echo "OIDC_DISCOVERY_URL: ${OIDC_DISCOVERY_URL}"
    echo "JWT_ROLES: ${JWT_ROLES}"
    echo "Vault JWT config is disabled"
  else
    VAULT_JWT_CONFIG="true"
    echo "Vault JWT config is enabled"
  fi

else
  VAULT_JWT_CONFIG="false"
  JWT_ROLES="[]"
  JWT_POLICIES="[]"
  echo "Vault JWT config is disabled"
fi

# Write extra vars to temp file to handle complex JSON with embedded quotes
cat > "${EXTRA_VARS_FILE}" <<EOF
vault_jwt_roles: ${JWT_ROLES:-[]}
vault_jwt_policies: ${JWT_POLICIES:-[]}
EOF

ansible-playbook -t "${TASK}" \
  -e pattern_name="${PATTERN_NAME}" \
  -e pattern_dir="${PATTERNPATH}" \
  -e vault_jwt_config="${VAULT_JWT_CONFIG}" \
  -e oidc_discovery_url="${OIDC_DISCOVERY_URL:-}" \
  -e "@${EXTRA_VARS_FILE}" \
  ${EXTRA_PLAYBOOK_OPTS} "rhvp.cluster_utils.vault"
