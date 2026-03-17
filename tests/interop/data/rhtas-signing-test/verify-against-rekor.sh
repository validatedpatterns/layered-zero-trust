export COSIGN_REKOR_URL=https://${REKOR_URL}

cosign verify-blob /tmp/test.txt \
  --bundle /tmp/test.bundle \
  --certificate-identity-regexp='.*' \
  --certificate-oidc-issuer-regexp='.*'