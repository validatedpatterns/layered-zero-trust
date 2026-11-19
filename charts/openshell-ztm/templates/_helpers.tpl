{{/*
Cluster domain — uses the VP framework's global.localClusterDomain,
with fallback to OpenShift Ingress auto-detection.
*/}}
{{- define "ztm.clusterDomain" -}}
{{- if .Values.global.localClusterDomain -}}
{{- .Values.global.localClusterDomain -}}
{{- else -}}
{{- $ing := (lookup "config.openshift.io/v1" "Ingress" "" "cluster") -}}
{{- if and $ing $ing.spec $ing.spec.domain -}}
{{- $ing.spec.domain -}}
{{- else -}}
{{- fail "Cannot auto-detect cluster domain. Set global.localClusterDomain" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Default OpenShift Route hostname for OpenShell gateway.
When spec.host is empty, OpenShift auto-generates: {route-name}-{namespace}.{cluster-domain}
*/}}
{{- define "ztm.routeHostname" -}}
{{- if .Values.openshell.openshiftRoute.host -}}
{{- .Values.openshell.openshiftRoute.host -}}
{{- else -}}
{{ include "ztm.gatewayServiceName" . }}-{{ .Values.namespace }}.{{ include "ztm.clusterDomain" . }}
{{- end -}}
{{- end -}}

{{/*
Keycloak base URL derived from cluster domain.
*/}}
{{- define "ztm.keycloakUrl" -}}
https://keycloak.{{ include "ztm.clusterDomain" . }}
{{- end -}}

{{/*
SPIFFE trust domain derived from cluster domain.
*/}}
{{- define "ztm.trustDomain" -}}
{{- if .Values.spiffe.trustDomain -}}
{{- .Values.spiffe.trustDomain -}}
{{- else -}}
{{ include "ztm.clusterDomain" . }}
{{- end -}}
{{- end -}}

{{/*
Vault internal (in-cluster) URL.
*/}}
{{- define "ztm.vaultInternalUrl" -}}
{{- if .Values.vault.internalUrl -}}
{{- .Values.vault.internalUrl -}}
{{- else -}}
https://vault.{{ .Values.vault.namespace }}.svc.cluster.local:8200
{{- end -}}
{{- end -}}

{{/*
Vault external URL derived from cluster domain.
*/}}
{{- define "ztm.vaultExternalUrl" -}}
https://vault-vault.{{ include "ztm.clusterDomain" . }}
{{- end -}}

{{/*
Gateway in-cluster service name — mirrors the subchart's openshell.fullname logic.
*/}}
{{- define "ztm.gatewayServiceName" -}}
{{- $name := .Values.openshell.nameOverride | default "openshell" -}}
{{- if contains $name .Release.Name -}}
{{ .Release.Name }}
{{- else -}}
{{ .Release.Name }}-{{ $name }}
{{- end -}}
{{- end -}}

{{/*
Gateway in-cluster gRPC endpoint (used by openshell CLI in hook jobs).
*/}}
{{- define "ztm.gatewayEndpoint" -}}
https://{{ include "ztm.gatewayServiceName" . }}.{{ .Values.namespace }}.svc.cluster.local:8080
{{- end -}}

{{/*
Standard labels for ZTM resources.
*/}}
{{- define "ztm.labels" -}}
app.kubernetes.io/name: openshell-ztm
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: layered-zero-trust
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
