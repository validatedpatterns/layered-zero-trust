export COSIGN_REKOR_URL=https://${REKOR_URL}

# Verify the signature
echo '1. Verifying signature...'
cosign verify-blob /tmp/test-keycloak-pod.txt \
  --bundle=/tmp/test-keycloak-pod.bundle \
  --certificate-identity=rhtas-user@example.com \
  --certificate-oidc-issuer=https://${KEYCLOAK_URL}/realms/ztvp

echo ''
echo '2. Inspecting certificate...'
cat /tmp/test-keycloak-pod.bundle | jq -r .cert | base64 -d | \
  openssl x509 -noout -text | grep -A 3 'Subject Alternative Name'
