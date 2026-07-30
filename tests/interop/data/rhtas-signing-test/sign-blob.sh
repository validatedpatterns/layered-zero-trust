# Create test file
echo 'Testing RHTAS with SPIFFE identity' > /tmp/test.txt

# Sign using the JWT token
export COSIGN_FULCIO_URL=https://${FULCIO_URL}
export COSIGN_REKOR_URL=https://${REKOR_URL}

cosign sign-blob /tmp/test.txt \
  --bundle /tmp/test.bundle \
  --yes

ls -la /tmp/test.bundle
