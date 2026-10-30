#!/usr/bin/env bash

set -euo pipefail

case "$(uname)" in
  Darwin)
    os="darwin"
    os_arch="arm64"
    ;;
  Linux)
    os="linux"
    os_arch="amd64"
    ;;
  *)
    echo "Unsupported OS: $(uname)"
    exit 1
    ;;
esac

# Download the Cosign CLI
download_cosign() {
  test -f /usr/local/bin/cosign || {
    log_msg "Downloading Cosign CLI"
    log_msg "CLI_SERVER_URL: ${CLI_SERVER_URL}"
    log_msg "os: ${os}"
    log_msg "os_arch: ${os_arch}"

    curl -sSf "${CLI_SERVER_URL}/clients/${os}/cosign-${os_arch}.gz" -o - | gunzip -c > /usr/local/bin/cosign
    chmod +x /usr/local/bin/cosign
  }
}

# Download the EC CLI
download_ec() {
  test -f /usr/local/bin/ec || {
    log_msg "Downloading EC CLI"
    log_msg "CLI_SERVER_URL: ${CLI_SERVER_URL}"
    log_msg "os: ${os}"
    log_msg "os_arch: ${os_arch}"

    curl -sSf "${CLI_SERVER_URL}/clients/${os}/ec-${os_arch}.gz" -o - | gunzip -c > /usr/local/bin/ec
    chmod +x /usr/local/bin/ec
  }
}

# print log message
log_msg() {
  echo "$(date +'[%Y/%m/%d %H:%M:%S] ') $*"
}

# get image reference
get_image_reference() {
  test -f /usr/bin/skopeo || dnf install -q -y skopeo > /dev/null

  image_digest=$(skopeo inspect docker://"${1}" --format '{{ .Digest }}')
  image_ref="$(echo "${1}" | cut -d':' -f1)@${image_digest}"
  echo "${image_ref}"
}

# Initialize cosign
initialize_cosign() {

  log_msg "Initializing cosign"
  log_msg "TUF_URL: ${TUF_URL}"

  test -d /root/.sigstore || mkdir -p /root/.sigstore
  test -f /root/.sigstore/tuf-root.json || {
    echo "Downloading TUF root"
    curl -sSfk "${TUF_URL}/root.json" -o "/root/.sigstore/tuf-root.json"
    sha256sum "/root/.sigstore/tuf-root.json" | cut -d' ' -f1 > "/root/.sigstore/tuf-root.json.sha256"
  }

  log_msg "Initializing cosign with TUF root"
  cosign initialize \
    --root "/root/.sigstore/tuf-root.json" \
    --root-checksum "$(sha256sum "/root/.sigstore/tuf-root.json" | cut -d' ' -f1)" \
    --mirror "${TUF_URL}"
}

# Sign the artifact
sign_artifact() {
  bundle="${1}.bundle"

  initialize_cosign
  log_msg "Signing artifact"
  log_msg "FULCIO_URL: ${FULCIO_URL}"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "bundle: ${bundle}"

  if [ -v OIDC_CLIENT_ID ]; then
    log_msg "OIDC_CLIENT_ID: ${OIDC_CLIENT_ID}"
  fi
  if [ -v OIDC_ISSUER ]; then
    log_msg "OIDC_ISSUER: ${OIDC_ISSUER}"
  fi
  if [ -v OIDC_IDENTITY ]; then
    log_msg "OIDC_IDENTITY: ${OIDC_IDENTITY}"
  fi
  if [ -v OIDC_CLIENT_SECRET_FILE ]; then
    log_msg "OIDC_CLIENT_SECRET_FILE: ${OIDC_CLIENT_SECRET_FILE}"
    if ! [ -f "${OIDC_CLIENT_SECRET_FILE}" ]; then
      log_msg "ERROR: ${OIDC_CLIENT_SECRET_FILE} not found"
      exit 1
    fi
  fi

  cosign sign-blob "${1}" \
    ${OIDC_CLIENT_ID:+"--oidc-client-id=${OIDC_CLIENT_ID}"} \
    ${OIDC_CLIENT_SECRET_FILE:+"--oidc-client-secret-file=${OIDC_CLIENT_SECRET_FILE}"} \
    --bundle "${bundle}" \
    --yes
}

# Sign the image
sign_image() {

  initialize_cosign

  image_ref="$(get_image_reference "${1}")"

  log_msg "Signing image"
  log_msg "FULCIO_URL: ${FULCIO_URL}"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "image_ref: ${image_ref}"

  if [ -v OIDC_CLIENT_ID ]; then
    log_msg "OIDC_CLIENT_ID: ${OIDC_CLIENT_ID}"
  fi
  if [ -v OIDC_ISSUER ]; then
    log_msg "OIDC_ISSUER: ${OIDC_ISSUER}"
  fi
  if [ -v OIDC_IDENTITY ]; then
    log_msg "OIDC_IDENTITY: ${OIDC_IDENTITY}"
  fi
  if [ -v OIDC_CLIENT_SECRET_FILE ]; then
    log_msg "OIDC_CLIENT_SECRET_FILE: ${OIDC_CLIENT_SECRET_FILE}"
    if ! [ -f "${OIDC_CLIENT_SECRET_FILE}" ]; then
      log_msg "ERROR: ${OIDC_CLIENT_SECRET_FILE} not found"
      exit 1
    fi
  fi

  cosign sign "${image_ref}" \
    ${OIDC_CLIENT_ID:+"--oidc-client-id=${OIDC_CLIENT_ID}"} \
    ${OIDC_CLIENT_SECRET_FILE:+"--oidc-client-secret-file=${OIDC_CLIENT_SECRET_FILE}"} \
    --yes
}

# Verify the image signature and SBOM attestation
#
# NOTE: We deliberately use 'cosign verify' + 'cosign verify-attestation' here
# instead of 'ec validate image'.  Tekton Chains creates its SLSA provenance
# attestation *after* the PipelineRun completes, so the attestation does not
# exist in the OCI registry while verify-image is still running (it is the last
# pipeline step).  EC v0.9.125+ (RHTAS ≥ v1.4.4) enforces builtin.attestation
# .syntax_check which requires valid SLSA provenance — an attestation that can
# never be present at this point in the pipeline.
#
# Using cosign directly verifies exactly what the pipeline itself produces:
#   1. The image signature  (created by the sign-image step)
#   2. The SBOM attestation (created by the sbom-attestation step)
# Both are written to the OCI registry before verify-image starts.
verify_image() {

  initialize_cosign

  image_ref="$(get_image_reference "${1}")"

  log_msg "Verifying image"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "image_ref: ${image_ref}"
  log_msg "OIDC_IDENTITY: ${OIDC_IDENTITY}"
  log_msg "OIDC_ISSUER: ${OIDC_ISSUER}"

  log_msg "Verifying image signature"
  cosign verify "${image_ref}" \
    --certificate-identity "${OIDC_IDENTITY}" \
    --certificate-oidc-issuer "${OIDC_ISSUER}" \
    --rekor-url "${REKOR_URL}"

  # Rekor builds its Merkle tree asynchronously after accepting a new entry.
  # The SBOM attestation is pushed seconds before this step runs, so the
  # inclusion proof may not yet be in the tree.  Retry up to 5 times
  # (75 s total) to let Rekor catch up before giving up.
  log_msg "Verifying SBOM attestation"
  for attempt in 1 2 3 4 5; do
    cosign verify-attestation "${image_ref}" \
      --type spdxjson \
      --certificate-identity "${OIDC_IDENTITY}" \
      --certificate-oidc-issuer "${OIDC_ISSUER}" \
      --rekor-url "${REKOR_URL}" \
      > /dev/null && break
    if [ "${attempt}" -lt 5 ]; then
      log_msg "SBOM attestation verification attempt ${attempt} failed, retrying in 15s..."
      sleep 15
    else
      log_msg "SBOM attestation verification failed after ${attempt} attempts"
      exit 1
    fi
  done
}

# Verify the artifact
verify_artifact() {

  initialize_cosign

  log_msg "Verifying artifact"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "artifact: ${1}"
  log_msg "OIDC_IDENTITY: ${OIDC_IDENTITY}"
  log_msg "OIDC_ISSUER: ${OIDC_ISSUER}"

  cosign verify-blob "${1}" \
    --bundle "${1}.bundle" \
    --certificate-identity "${OIDC_IDENTITY}" \
    --certificate-oidc-issuer "${OIDC_ISSUER}"
}

# Import Openshift Ingress CA certificate
import_ca() {
  test -f "${CA_FILE}" && {
    cp "${CA_FILE}" /etc/pki/ca-trust/source/anchors/
  }
  update-ca-trust
}

# Attest the SBOM of the image
attest_sbom_image() {

  initialize_cosign

  image_ref="$(get_image_reference "${1}")"

  log_msg "Attesting SBOM"
  log_msg "FULCIO_URL: ${FULCIO_URL}"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "image_ref: ${image_ref}"
  log_msg "SBOM_FILE: ${SBOM_FILE}"
  log_msg "SBOM_FORMAT: ${SBOM_FORMAT}"

  cosign attest "${image_ref}" \
    --predicate "${SBOM_FILE}" \
    --type "${SBOM_FORMAT}" \
    --yes
}


# Main
import_ca
download_cosign