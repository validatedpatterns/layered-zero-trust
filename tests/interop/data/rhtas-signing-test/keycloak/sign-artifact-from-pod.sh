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
echo ''

# Verify token has aud claim
AUD=\$(echo \"\$OIDC_TOKEN\" | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.aud')
echo \"Token aud claim: \$AUD\"
echo ''

# Create test file
echo 'Testing RHTAS with Keycloak from Pod' > /tmp/test-keycloak-pod.txt

# Set environment for cosign
export COSIGN_FULCIO_URL=https://${FULCIO_URL}
export COSIGN_REKOR_URL=https://${REKOR_URL}

# Sign the blob
echo 'Signing artifact with Keycloak token...'
cosign sign-blob /tmp/test-keycloak-pod.txt \
  --identity-token=\"\$OIDC_TOKEN\" \
  --bundle=/tmp/test-keycloak-pod.bundle \
  --yes

echo ''
if [ -f /tmp/test-keycloak-pod.bundle ]; then
  echo 'Signing successful! Bundle created.'
  ls -lh /tmp/test-keycloak-pod.bundle
else
  echo 'Signing failed'
  exit 1
fi

# expect the following, and track the "tlog entry created with index: <>" is increasing if cosign was tested multiple times.
