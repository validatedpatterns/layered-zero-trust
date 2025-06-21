{{/*
Expand the name of the chart.
*/}}
{{- define "zero-trust-workload-identity-manager.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "zero-trust-workload-identity-manager.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "zero-trust-workload-identity-manager.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "zero-trust-workload-identity-manager.labels" -}}
helm.sh/chart: {{ include "zero-trust-workload-identity-manager.chart" . }}
{{ include "zero-trust-workload-identity-manager.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "zero-trust-workload-identity-manager.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zero-trust-workload-identity-manager.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "zero-trust-workload-identity-manager.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "zero-trust-workload-identity-manager.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the Spire server persistence configuration.
*/}}
{{- define "zero-trust-workload-identity-manager.server.persistence" -}}
{{- if (eq .Values.spire.server.persistence.type "pvc") }}
size: {{ .Values.spire.server.persistence.size }}
accessMode: {{ .Values.spire.server.persistence.accessMode }}
{{- else if (eq .Values.spire.server.persistence.type "hostPath") }}
hostPath: {{ .Values.spire.server.persistence.hostPath }}
{{- else }}
{{- fail (printf "Unsupported persistence type: '%s'. Valid values are 'pvc' or 'hostPath'" .Values.spire.server.persistence.type) }}
{{- end }}
type: {{ .Values.spire.server.persistence.type }}
{{- end }}