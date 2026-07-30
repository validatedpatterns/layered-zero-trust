#!/bin/sh
set -eu

VAULT_URL="${VAULT_URL:?VAULT_URL is required}"
VAULT_ROLE="${VAULT_ROLE:-supply-chain}"
VAULT_SECRET_PATH="${VAULT_SECRET_PATH:?VAULT_SECRET_PATH is required}"
VAULT_SECRET_KEY="${VAULT_SECRET_KEY:?VAULT_SECRET_KEY is required}"
SA_NAME="${SA_NAME:-pipeline}"
SA_NAMESPACE="${SA_NAMESPACE:?SA_NAMESPACE is required}"
TOKEN_DURATION="${TOKEN_DURATION:-172800}"
JWT_TOKEN_FILE="${JWT_TOKEN_FILE:-/svids/jwt.token}"
CA_CERT="${CA_CERT:-/run/secrets/kubernetes.io/serviceaccount/service-ca.crt}"

APISERVER="https://kubernetes.default.svc"
SA_TOKEN="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
CACERT="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

vault_curl() {
  if [ -f "${CA_CERT}" ]; then
    curl -sS --cacert "${CA_CERT}" "$@"
  else
    curl -sSk "$@"
  fi
}

log "Starting OpenShift registry token refresh"

# 1. Read SPIFFE JWT for Vault authentication
if [ ! -f "${JWT_TOKEN_FILE}" ]; then
  log "ERROR: JWT token file not found at ${JWT_TOKEN_FILE}"
  exit 1
fi
JWT="$(cat "${JWT_TOKEN_FILE}")"
log "Read SPIFFE JWT from ${JWT_TOKEN_FILE}"

# 2. Authenticate to Vault using SPIFFE JWT (with retry for seed Job timing)
VAULT_MAX_RETRIES="${VAULT_MAX_RETRIES:-20}"
VAULT_RETRY_INTERVAL="${VAULT_RETRY_INTERVAL:-15}"
VAULT_TOKEN=""

log "Authenticating to Vault at ${VAULT_URL} with role ${VAULT_ROLE}..."
attempt=0
while [ "${attempt}" -lt "${VAULT_MAX_RETRIES}" ]; do
  AUTH_RESP=$(vault_curl -X POST "${VAULT_URL}/v1/auth/jwt/login" \
    -H "Content-Type: application/json" \
    -d "{\"role\":\"${VAULT_ROLE}\",\"jwt\":\"${JWT}\"}" 2>&1) || true

  VAULT_TOKEN=$(echo "${AUTH_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['client_token'])" 2>/dev/null) || true

  if [ -n "${VAULT_TOKEN}" ]; then
    break
  fi

  attempt=$((attempt + 1))
  if [ "${attempt}" -lt "${VAULT_MAX_RETRIES}" ]; then
    log "Vault not ready (attempt ${attempt}/${VAULT_MAX_RETRIES}). Retrying in ${VAULT_RETRY_INTERVAL}s..."
    sleep "${VAULT_RETRY_INTERVAL}"
  fi
done

if [ -z "${VAULT_TOKEN}" ]; then
  log "ERROR: Vault authentication failed after ${VAULT_MAX_RETRIES} attempts"
  log "${AUTH_RESP}"
  exit 1
fi
log "Vault authentication successful"

# 3. Create a fresh SA token via the Kubernetes TokenRequest API
log "Creating ${SA_NAME} SA token (duration: ${TOKEN_DURATION}s)..."
TOKEN_RESP=$(curl -sS --cacert "${CACERT}" \
  -X POST "${APISERVER}/api/v1/namespaces/${SA_NAMESPACE}/serviceaccounts/${SA_NAME}/token" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"apiVersion\":\"authentication.k8s.io/v1\",\"kind\":\"TokenRequest\",\"spec\":{\"expirationSeconds\":${TOKEN_DURATION}}}")

NEW_TOKEN=$(echo "${TOKEN_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['token'])" 2>/dev/null) || {
  log "ERROR: TokenRequest API failed"
  log "${TOKEN_RESP}"
  exit 1
}
log "SA token created successfully"

# 4. Write the new token to Vault
log "Writing token to Vault at ${VAULT_SECRET_PATH}..."
WRITE_RESP=$(vault_curl -X POST "${VAULT_URL}/v1/${VAULT_SECRET_PATH}" \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"data\":{\"${VAULT_SECRET_KEY}\":\"${NEW_TOKEN}\"}}")

# Check for errors in the response
echo "${WRITE_RESP}" | python3 -c "
import sys, json
resp = json.load(sys.stdin)
if 'errors' in resp and resp['errors']:
    print('ERROR: ' + str(resp['errors']), file=sys.stderr)
    sys.exit(1)
" || {
  log "ERROR: Failed to write token to Vault"
  log "${WRITE_RESP}"
  exit 1
}

log "Token successfully written to Vault at ${VAULT_SECRET_PATH}"
log "Registry token refresh complete"
