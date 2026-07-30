#!/bin/bash

# Get total entries
curl -sk "https://${REKOR_URL}/api/v1/log" | jq .

# Get specific entry by index
curl -sk "https://${REKOR_URL}/api/v1/log/entries?logIndex=0" | jq .

# Decode entry body
curl -sk "https://${REKOR_URL}/api/v1/log/entries?logIndex=0" | \
  jq -r '.[].body' | base64 -d | jq .

# Extract certificate
CERT_B64=$(curl -sk "https://${REKOR_URL}/api/v1/log/entries?logIndex=0" | \
  jq -r '.[].body' | base64 -d | jq -r '.spec.signature.publicKey.content')

# View certificate details
echo "$CERT_B64" | base64 -d | openssl x509 -noout -text

# Extract identity (SPIFFE ID or email)
echo "$CERT_B64" | base64 -d | openssl x509 -noout -text | \
  grep -A 2 "Subject Alternative Name"