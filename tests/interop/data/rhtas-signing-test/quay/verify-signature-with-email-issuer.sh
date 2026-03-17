#!/bin/bash

export REKOR_URL='${REKOR_URL}'
export QUAY_IMAGE='${QUAY_IMAGE}'

cosign verify \\
  --certificate-identity='rhtas-user@example.com' \\
  --certificate-oidc-issuer-regexp='.*keycloak.*' \\
  --rekor-url=https://\${REKOR_URL} \\
  \${QUAY_IMAGE} | jq .
