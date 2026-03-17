#!/bin/bash

dnf install -y python3 python3-pip jq --nobest --skip-broken
pip3 install requests

python3 --version
jq --version
pip3 list | grep requests

TOKEN=$(python3 /tmp/get-keycloak-token.py \
  https://${KEYCLOAK_URL} \
  ztvp \
  trusted-artifact-signer \
  rhtas-user \
  ${RHTAS_USER_PASS})

echo 'Token claims:'
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .
