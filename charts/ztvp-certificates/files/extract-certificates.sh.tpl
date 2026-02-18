#!/bin/bash
# shellcheck disable=SC1091,SC2050,SC2154
# This is a Helm template file - shellcheck will fail on Helm syntax
set -e
{{- if .Values.debug.verbose }}
set -x
{{- end }}

# Logging functions
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[ERROR] $*" >&2; }

# Initialize variables
INGRESS_CA_FOUND=false
SERVICE_CA_FOUND=false
CUSTOM_CA_FOUND=false
CLUSTER_CA_FOUND=false
TEMP_DIR=$(mktemp -d)

log "==========================================="
log "ZTVP CA Certificate Extraction"
log "==========================================="
log "Auto-detect: {{ .Values.autoDetect }}"
log "Custom CA: {{ .Values.customCA.secretRef.enabled }}"
log "Namespace: {{ .Values.global.namespace }}"
log "ConfigMap: {{ .Values.configMapName }}"

# ===================================================================
# PHASE 1: Extract Custom CA (if configured)
# ===================================================================

{{- if .Values.customCA.secretRef.enabled }}
log "Extracting custom CA from secret: {{ .Values.customCA.secretRef.namespace }}/{{ .Values.customCA.secretRef.name }}"
if oc get secret {{ .Values.customCA.secretRef.name }} -n {{ .Values.customCA.secretRef.namespace }} &>/dev/null; then
  KEY="{{ .Values.customCA.secretRef.key }}"
  ESCAPED_KEY="${KEY//./\\.}"
  oc get secret {{ .Values.customCA.secretRef.name }} \
    -n {{ .Values.customCA.secretRef.namespace }} \
    -o "jsonpath={.data.${ESCAPED_KEY}}" | \
    base64 -d > "${TEMP_DIR}/custom-ca.crt"
  CUSTOM_CA_FOUND=true
  log "Custom CA extracted from secret successfully"
else
  error "Custom secret not found: {{ .Values.customCA.secretRef.namespace }}/{{ .Values.customCA.secretRef.name }}"
  exit 1
fi
{{- end }}

# ===================================================================
# PHASE 2: Extract Ingress CA (if auto-detect enabled)
# ===================================================================

{{- if .Values.autoDetect }}
# Auto-detect from OpenShift
log "Auto-detecting ingress CA certificate"

{{- if .Values.customSource.ingressCA.secretName }}
# Use custom source location
log "Using custom source: {{ .Values.customSource.ingressCA.secretNamespace }}/{{ .Values.customSource.ingressCA.secretName }}"
if oc get secret {{ .Values.customSource.ingressCA.secretName }} -n {{ .Values.customSource.ingressCA.secretNamespace }} &>/dev/null; then
  oc get secret {{ .Values.customSource.ingressCA.secretName }} \
    -n {{ .Values.customSource.ingressCA.secretNamespace }} \
    -o jsonpath='{.data.{{ .Values.customSource.ingressCA.secretKey }}}' | \
    base64 -d > "${TEMP_DIR}/ingress-ca.crt"
  INGRESS_CA_FOUND=true
  log "Ingress CA extracted from custom source"
else
  error "Custom ingress CA secret not found"
fi
{{- else }}
# Standard auto-detection logic
# Loop through all IngressControllers
INGRESSCONTROLLERS=$(oc get ingresscontroller -n openshift-ingress-operator -o name 2>/dev/null || echo "")

if [[ -n "$INGRESSCONTROLLERS" ]]; then
  INGRESS_INDEX=0
  for ic in $INGRESSCONTROLLERS; do
    IC_NAME=$(echo "$ic" | cut -d'/' -f2)
    log "Checking IngressController: $IC_NAME"
    
    # Check for custom certificate reference
    CUSTOM_CERT=$(oc get ingresscontroller "$IC_NAME" -n openshift-ingress-operator \
      -o jsonpath='{.spec.defaultCertificate.name}' 2>/dev/null || echo "")
    
    if [[ -n "$CUSTOM_CERT" ]]; then
      log "Found custom certificate reference: $CUSTOM_CERT"
      if oc get secret "$CUSTOM_CERT" -n openshift-ingress &>/dev/null; then
        oc get secret "$CUSTOM_CERT" -n openshift-ingress \
          -o jsonpath='{.data.tls\.crt}' | base64 -d > "${TEMP_DIR}/ingress-ca-${IC_NAME}.crt"
        INGRESS_CA_FOUND=true
        INGRESS_INDEX=$((INGRESS_INDEX + 1))
        log "Extracted ingress CA from $IC_NAME"
      fi
    else
      # Try default router-certs secret for this IngressController
      SECRET_NAME="router-certs-${IC_NAME}"
      if oc get secret "$SECRET_NAME" -n openshift-ingress &>/dev/null; then
        log "Found router secret: $SECRET_NAME"
        oc get secret "$SECRET_NAME" -n openshift-ingress \
          -o jsonpath='{.data.tls\.crt}' | base64 -d > "${TEMP_DIR}/ingress-ca-${IC_NAME}.crt"
        INGRESS_CA_FOUND=true
        INGRESS_INDEX=$((INGRESS_INDEX + 1))
      fi
    fi
  done
  
  log "Extracted certificates from $INGRESS_INDEX IngressController(s)"
else
  log "WARNING: No IngressControllers found"
fi
{{- end }}
{{- end }}

# ===================================================================
# PHASE 3: Extract Service CA (if auto-detect enabled)
# ===================================================================

{{- if .Values.autoDetect }}
log "Extracting OpenShift service CA"

{{- if .Values.customSource.serviceCA.configMapName }}
# Use custom source location
log "Using custom service CA source: {{ .Values.customSource.serviceCA.configMapNamespace }}/{{ .Values.customSource.serviceCA.configMapName }}"
if oc get configmap {{ .Values.customSource.serviceCA.configMapName }} -n {{ .Values.customSource.serviceCA.configMapNamespace }} &>/dev/null; then
  oc get configmap {{ .Values.customSource.serviceCA.configMapName }} \
    -n {{ .Values.customSource.serviceCA.configMapNamespace }} \
    -o jsonpath='{.data.{{ .Values.customSource.serviceCA.configMapKey }}}' \
    > "${TEMP_DIR}/service-ca.crt"
  SERVICE_CA_FOUND=true
  log "Service CA extracted from custom source"
else
  log "WARNING: Custom service CA ConfigMap not found"
fi
{{- else }}
# Standard location
if oc get configmap openshift-service-ca.crt -n openshift-config &>/dev/null; then
  oc get configmap openshift-service-ca.crt -n openshift-config \
    -o jsonpath='{.data.service-ca\.crt}' > "${TEMP_DIR}/service-ca.crt"
  SERVICE_CA_FOUND=true
  log "Service CA extracted successfully"
else
  log "WARNING: Service CA not found (this may be expected in some environments)"
fi
{{- end }}
{{- end }}

# ===================================================================
# PHASE 4: Extract Proxy/Cluster-wide Trusted CA Bundle
# ===================================================================

{{- if .Values.autoDetect }}
log "Checking for cluster-wide trusted CA bundle"

# Extract from openshift-config-managed/trusted-ca-bundle
if oc get configmap trusted-ca-bundle -n openshift-config-managed &>/dev/null; then
  log "Found trusted-ca-bundle in openshift-config-managed"
  oc get configmap trusted-ca-bundle -n openshift-config-managed \
    -o jsonpath='{.data.ca-bundle\.crt}' > "${TEMP_DIR}/trusted-ca-bundle.crt" 2>/dev/null || true
  
  # Check if we got valid content
  if [[ -s "${TEMP_DIR}/trusted-ca-bundle.crt" ]]; then
    CLUSTER_CA_FOUND=true
    log "Cluster-wide trusted CA bundle extracted successfully"
  else
    log "trusted-ca-bundle ConfigMap exists but has no ca-bundle.crt data"
    rm -f "${TEMP_DIR}/trusted-ca-bundle.crt"
  fi
else
  log "No cluster-wide trusted-ca-bundle found (this is normal for clusters without proxy configuration)"
fi
{{- end }}

# ===================================================================
# PHASE 5: Load Additional Certificates (if configured)
# ===================================================================

{{- if .Values.customCA.additionalCertificates }}
log "Loading {{ len .Values.customCA.additionalCertificates }} additional certificate(s) from secrets"

{{- range $cert := .Values.customCA.additionalCertificates }}
log "Loading additional certificate: {{ $cert.name }}"
if oc get secret {{ $cert.secretRef.name }} -n {{ $cert.secretRef.namespace }} &>/dev/null; then
  ADDL_KEY="{{ $cert.secretRef.key }}"
  ADDL_ESCAPED_KEY="${ADDL_KEY//./\\.}"
  oc get secret {{ $cert.secretRef.name }} \
    -n {{ $cert.secretRef.namespace }} \
    -o "jsonpath={.data.${ADDL_ESCAPED_KEY}}" | \
    base64 -d > "${TEMP_DIR}/{{ $cert.name }}.crt"
  log "OK: Loaded additional certificate: {{ $cert.name }}"
else
  log "WARNING: Additional certificate secret not found: {{ $cert.secretRef.namespace }}/{{ $cert.secretRef.name }}"
  log "WARNING: Skipping {{ $cert.name }} and continuing with other certificates"
fi
{{- end }}
{{- end }}

# ===================================================================
# PHASE 6: Validate Certificates
# ===================================================================

{{- if .Values.validation.enabled }}
log "Validating extracted certificates"

CERT_COUNT=0
for cert_file in "${TEMP_DIR}"/*.crt; do
  [[ -f "$cert_file" ]] || continue
  
  CERT_COUNT=$((CERT_COUNT + 1))
  
  # Check minimum size
  CERT_SIZE=$(wc -c < "$cert_file" 2>/dev/null || echo 0)
  if [[ $CERT_SIZE -lt {{ .Values.validation.minSize }} ]]; then
    error "Certificate too small: $cert_file ($CERT_SIZE bytes)"
    exit 1
  fi
  
  {{- if .Values.validation.parseCheck }}
  # Verify certificate can be parsed
  if ! openssl x509 -in "$cert_file" -noout 2>/dev/null; then
    error "Invalid certificate format: $cert_file"
    exit 1
  fi
  log "OK: Valid certificate: $(basename $cert_file)"
  {{- end }}
done

log "Validated $CERT_COUNT certificate(s)"
{{- end }}

# ===================================================================
# PHASE 7: Combine into Bundle
# ===================================================================

log "Creating combined CA bundle"

# Combine all certificates
> "${TEMP_DIR}/tls-ca-bundle.pem"
for cert_file in "${TEMP_DIR}"/*.crt; do
  [[ -f "$cert_file" ]] || continue
  cat "$cert_file" >> "${TEMP_DIR}/tls-ca-bundle.pem"
  echo "" >> "${TEMP_DIR}/tls-ca-bundle.pem"  # Add blank line between certs
done

# Verify bundle is not empty
BUNDLE_SIZE=$(wc -c < "${TEMP_DIR}/tls-ca-bundle.pem" 2>/dev/null || echo 0)
if [[ $BUNDLE_SIZE -lt 100 ]]; then
  error "=================================================================="
  error "No certificates found or bundle too small"
  error "=================================================================="
  error ""
  error "Certificate Status:"
  error "  Custom CA found: $CUSTOM_CA_FOUND"
  error "  Ingress CA found: $INGRESS_CA_FOUND"
  error "  Service CA found: $SERVICE_CA_FOUND"
  error "  Bundle size: $BUNDLE_SIZE bytes"
  error ""
  error "To resolve this, provide a custom CA certificate via secret:"
  error ""
  error "1. Create a secret with your certificate:"
  error "   oc create secret generic custom-ca-bundle \\"
  error "     --from-file=ca.crt=/path/to/ca.crt \\"
  error "     -n openshift-config"
  error ""
  error "2. Configure values-hub.yaml:"
  error "   ztvp-certificates:"
  error "     overrides:"
  error "       - name: customCA.secretRef.enabled"
  error "         value: \"true\""
  error "       - name: customCA.secretRef.name"
  error "         value: custom-ca-bundle"
  error "       - name: customCA.secretRef.namespace"
  error "         value: openshift-config"
  error ""
  error "For more information, see the chart documentation."
  error "=================================================================="
  exit 1
fi

log "Combined CA bundle created: $BUNDLE_SIZE bytes"

# ===================================================================
# PHASE 8: Create ConfigMap
# ===================================================================

log "Creating ConfigMap: {{ .Values.global.namespace }}/{{ .Values.configMapName }}"

cat <<EOF | oc apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.configMapName }}
  namespace: {{ .Values.global.namespace }}
  annotations:
    {{- range $key, $value := .Values.configMapAnnotations }}
    {{ $key }}: {{ $value | quote }}
    {{- end }}
    ztvp.io/extraction-timestamp: "$(date -Iseconds)"
    ztvp.io/auto-detect: "{{ .Values.autoDetect }}"
    ztvp.io/custom-ca-enabled: "{{ .Values.customCA.secretRef.enabled }}"
    ztvp.io/custom-ca-found: "${CUSTOM_CA_FOUND}"
    ztvp.io/ingress-ca-found: "${INGRESS_CA_FOUND}"
    ztvp.io/service-ca-found: "${SERVICE_CA_FOUND}"
    ztvp.io/cluster-ca-found: "${CLUSTER_CA_FOUND}"
  labels:
    {{- range $key, $value := .Values.configMapLabels }}
    {{ $key }}: {{ $value | quote }}
    {{- end }}
data:
  tls-ca-bundle.pem: |
$(cat "${TEMP_DIR}/tls-ca-bundle.pem" | sed 's/^/      /')
EOF

# Verify ConfigMap was created
if oc get configmap {{ .Values.configMapName }} -n {{ .Values.global.namespace }} &>/dev/null; then
  VERIFY_SIZE=$(oc get configmap {{ .Values.configMapName }} -n {{ .Values.global.namespace }} \
    -o jsonpath='{.data.tls-ca-bundle\.pem}' 2>/dev/null | wc -c || echo 0)
  
  if [[ $VERIFY_SIZE -lt 100 ]]; then
    error "ConfigMap created but certificate data is missing or too small ($VERIFY_SIZE bytes)"
    exit 1
  fi
  
  log "==========================================="
  log "SUCCESS: CA certificate bundle configured"
  log "==========================================="
  log "ConfigMap: {{ .Values.global.namespace }}/{{ .Values.configMapName }}"
  log "Bundle size: $VERIFY_SIZE bytes"
  log "Custom CA: $CUSTOM_CA_FOUND"
  log "Ingress CA: $INGRESS_CA_FOUND"
  log "Service CA: $SERVICE_CA_FOUND"
  log "Cluster CA: $CLUSTER_CA_FOUND"
  log "==========================================="
else
  error "Failed to create ConfigMap"
  exit 1
fi

# ===================================================================
# PHASE 9: Configure Node-Level Image Pull Trust (if enabled)
# Creates a ConfigMap with registry-hostname keys containing the ingress CA,
# then patches image.config.openshift.io/cluster to reference it.
# This allows kubelet to pull images from registries behind the cluster ingress
# (e.g. built-in Quay) without "x509: certificate signed by unknown authority".
# ===================================================================

{{- if .Values.imagePullTrust.enabled }}
{{- if .Values.imagePullTrust.registries }}
log "Configuring node-level image pull trust"

if [[ "$INGRESS_CA_FOUND" != "true" ]]; then
  error "imagePullTrust is enabled but no ingress CA was extracted. Cannot configure image pull trust."
  error "Ensure autoDetect is true or provide a custom ingress CA source."
  exit 1
fi

# Build the ConfigMap data with registry hostnames as keys
# Each key is a registry hostname, value is the ingress CA PEM
REGISTRY_CM_DATA=""
{{- range .Values.imagePullTrust.registries }}
log "Adding registry trust: {{ tpl . $ }}"
{{- end }}

log "Creating ConfigMap: {{ .Values.global.namespace }}/{{ .Values.imagePullTrust.configMapName }}"

# Combine all ingress CA files into one PEM for registry trust
COMBINED_INGRESS_CA="${TEMP_DIR}/combined-ingress-ca.pem"
> "${COMBINED_INGRESS_CA}"
for f in "${TEMP_DIR}"/ingress-ca-*.crt; do
  [[ -f "$f" ]] || continue
  cat "$f" >> "${COMBINED_INGRESS_CA}"
  echo "" >> "${COMBINED_INGRESS_CA}"
done

# Create the ConfigMap with registry hostnames as keys
cat <<'CMEOF' > "${TEMP_DIR}/registry-cas-cm.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.imagePullTrust.configMapName }}
  namespace: {{ .Values.global.namespace }}
  labels:
    app.kubernetes.io/name: ztvp-certificates
    app.kubernetes.io/component: image-pull-trust
    app.kubernetes.io/managed-by: ztvp-certificate-manager
data: {}
CMEOF

oc apply -f "${TEMP_DIR}/registry-cas-cm.yaml"

# Patch each registry hostname as a key with the ingress CA PEM
{{- range .Values.imagePullTrust.registries }}
log "Patching ConfigMap key: {{ tpl . $ }}"
oc create configmap {{ $.Values.imagePullTrust.configMapName }} \
  -n {{ $.Values.global.namespace }} \
  --from-file="{{ tpl . $ }}=${COMBINED_INGRESS_CA}" \
  --dry-run=client -o yaml | oc apply -f -
{{- end }}

# Patch image.config.openshift.io/cluster to reference the ConfigMap
log "Patching image.config.openshift.io/cluster additionalTrustedCA"
oc patch image.config.openshift.io/cluster --type merge \
  -p "{\"spec\":{\"additionalTrustedCA\":{\"name\":\"{{ .Values.imagePullTrust.configMapName }}\"}}}"

log "Node-level image pull trust configured successfully"
log "Note: MCO will roll this out to nodes (may take a few minutes)"

{{- end }}
{{- end }}

# ===================================================================
# PHASE 10: Automatic Rollout (if enabled)
# ===================================================================

{{- if .Values.rollout.enabled }}
log "Triggering automatic rollout for consuming applications"
log "Rollout strategy: {{ .Values.rollout.strategy }}"

ROLLOUT_COUNT=0

{{- if eq .Values.rollout.strategy "specific" }}
# Strategy: specific - restart named resources
{{- range .Values.rollout.targets }}
log "Restarting {{ .kind }}/{{ .name }} in namespace {{ .namespace }}"
if oc get {{ .kind | lower }} {{ .name }} -n {{ .namespace }} &>/dev/null; then
  if oc rollout restart {{ .kind | lower }}/{{ .name }} -n {{ .namespace }}; then
    log "OK: Successfully triggered rollout for {{ .kind }}/{{ .name }}"
    ROLLOUT_COUNT=$((ROLLOUT_COUNT + 1))
  else
    log "WARNING: Failed to restart {{ .kind }}/{{ .name }} (continuing anyway)"
  fi
else
  log "WARNING: {{ .kind }}/{{ .name }} not found in namespace {{ .namespace }}"
fi
{{- end }}

{{- else }}
# Strategy: all or labeled - restart resources in distribution target namespaces
{{- range $ns := .Values.distribution.targetNamespaces }}
log "Processing namespace: {{ $ns }}"

{{- range $kind := $.Values.rollout.resourceKinds }}
{{- if eq $.Values.rollout.strategy "labeled" }}
# Get resources with specific labels
LABEL_SELECTOR="{{ range $key, $value := $.Values.rollout.labelSelector }}{{ $key }}={{ $value }}{{ end }}"
log "Finding {{ $kind }}s with labels: $LABEL_SELECTOR"
RESOURCES=$(oc get {{ $kind | lower }} -n {{ $ns }} -l "$LABEL_SELECTOR" -o name 2>/dev/null || true)
{{- else }}
# Get all resources
log "Finding all {{ $kind }}s in namespace {{ $ns }}"
RESOURCES=$(oc get {{ $kind | lower }} -n {{ $ns }} -o name 2>/dev/null || true)
{{- end }}

if [[ -n "$RESOURCES" ]]; then
  for resource in $RESOURCES; do
    log "Restarting $resource in namespace {{ $ns }}"
    if oc rollout restart "$resource" -n {{ $ns }}; then
      log "OK: Successfully triggered rollout for $resource"
      ROLLOUT_COUNT=$((ROLLOUT_COUNT + 1))
    else
      log "WARNING: Failed to restart $resource (continuing anyway)"
    fi
  done
else
  log "No {{ $kind }}s found in namespace {{ $ns }}"
fi
{{- end }}
{{- end }}
{{- end }}

log "Automatic rollout completed: $ROLLOUT_COUNT resource(s) restarted"
{{- end }}

