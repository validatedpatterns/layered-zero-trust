#!/bin/bash

# Get OIDC token from Keycloak
echo 'Fetching OIDC token from Keycloak...'
OIDC_TOKEN=\$(python3 /tmp/get-keycloak-token.py \
  'https://${KEYCLOAK_URL}' \
  'ztvp' \
  'trusted-artifact-signer' \
  'rhtas-user' \
  '${RHTAS_USER_PASS}')

if [ -z \"\$OIDC_TOKEN\" ]; then
  echo 'ERROR: Failed to get OIDC token'
  exit 1
fi

echo \"Token obtained (length: \${#OIDC_TOKEN})\"

# Set environment for cosign
export COSIGN_FULCIO_URL=https://${FULCIO_URL}
export COSIGN_REKOR_URL=https://${REKOR_URL}
export QUAY_IMAGE='${QUAY_IMAGE}'

# Sign the IMAGE
echo 'Signing IMAGE with Keycloak token...'
cosign sign \${QUAY_IMAGE} \
  --identity-token=\"\$OIDC_TOKEN\" \
  --yes
