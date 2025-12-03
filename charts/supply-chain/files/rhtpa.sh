#!/usr/bin/env bash

set -euo pipefail

# Import Openshift Ingress CA certificate
import_ca() {
  test -f "${CA_FILE}" && {
    cp "${CA_FILE}" /etc/pki/ca-trust/source/anchors/
  }
  update-ca-trust
}

# print log message
log_msg() {
  echo "$(date +'[%Y/%m/%d %H:%M:%S] ') $*"
}

get_oidc_token() {
  # Get the OIDC Issuer URL from Keycloak route
  export OIDC_TOKEN_URL="${OIDC_URL}/protocol/openid-connect/token"

  # Request a new access token
  curl -sSf -X POST "${OIDC_TOKEN_URL}" \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d 'grant_type=client_credentials' \
    -d "client_id=${OIDC_CLIENT_ID}" \
    -d "client_secret=${OIDC_CLIENT_SECRET}" | jq -r .access_token
}

# Upload the SBOM to RHTPA
upload_sbom() {

  log_msg "Getting OIDC token"
  log_msg "OIDC_URL: ${OIDC_URL}"
  log_msg "OIDC_TOKEN_URL: ${OIDC_URL}/protocol/openid-connect/token"
  log_msg "OIDC_CLIENT_ID: ${OIDC_CLIENT_ID}"

  TOKEN=$(get_oidc_token)

  log_msg "Uploading SBOM to RHTPA"
  log_msg "RHTPA_URL: ${RHTPA_URL}"
  log_msg "SBOM_FILE: ${SBOM_FILE}"

  # Upload the SBOM using curl
  curl -s -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data-binary "@${SBOM_FILE}" \
    "${RHTPA_URL}/api/v2/sbom"
}


# Main
import_ca
dnf install -q -y jq > /dev/null