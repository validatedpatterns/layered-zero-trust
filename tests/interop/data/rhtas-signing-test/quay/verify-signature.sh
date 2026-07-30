oc exec -n rhtas-signing-test rhtas-signer -- bash -c "
  export FULCIO_URL='${FULCIO_URL}'
  export REKOR_URL='${REKOR_URL}'
  export QUAY_IMAGE='${QUAY_IMAGE}'
  
  cosign verify \\
    --certificate-identity-regexp='spiffe://.*' \\
    --certificate-oidc-issuer-regexp='.*spire.*' \\
    --rekor-url=https://\${REKOR_URL} \\
    \${QUAY_IMAGE} | jq .
"
