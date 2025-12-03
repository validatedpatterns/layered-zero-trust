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

  cosign sign-blob "${1}" \
    --fulcio-url "${FULCIO_URL}" \
    --rekor-url "${REKOR_URL}" \
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

  cosign sign "${image_ref}" \
    --fulcio-url "${FULCIO_URL}" \
    --rekor-url "${REKOR_URL}" \
    --yes
}

# Verify the SBOM of the image
verify_image() {

  initialize_cosign

  image_ref="$(get_image_reference "${1}")"

  log_msg "Verifying image"
  log_msg "REKOR_URL: ${REKOR_URL}"
  log_msg "image_ref: ${image_ref}"
  log_msg "OIDC_IDENTITY: ${OIDC_IDENTITY}"
  log_msg "OIDC_ISSUER: ${OIDC_ISSUER}"

  ec validate image \
    --image "${image_ref}" \
    --certificate-identity "${OIDC_IDENTITY}" \
    --certificate-oidc-issuer "${OIDC_ISSUER}" \
    --rekor-url "${REKOR_URL}" \
    --show-successes
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
    --rekor-url="${REKOR_URL}" \
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
    --fulcio-url "${FULCIO_URL}" \
    --rekor-url "${REKOR_URL}" \
    --predicate "${SBOM_FILE}" \
    --type "${SBOM_FORMAT}" \
    --yes
}


# Main
import_ca
download_cosign
download_ec