
cosign login -u <username> -p <password> ${QUAY_URL}

# Set environment variables in pod and sign
oc exec -n rhtas-signing-test rhtas-signer -- bash -c "
  export FULCIO_URL='${FULCIO_URL}'
  export REKOR_URL='${REKOR_URL}'
  export QUAY_IMAGE='${QUAY_IMAGE}'
  
  # Sign with SPIFFE identity
  cosign sign \\
    --fulcio-url=https://\${FULCIO_URL} \\
    --rekor-url=https://\${REKOR_URL} \\
    --yes \\
    \${QUAY_IMAGE}
"
