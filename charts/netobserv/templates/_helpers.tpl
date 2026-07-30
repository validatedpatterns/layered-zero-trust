{{- define "netobserv.name" -}}
netobserv
{{- end }}

{{- define "netobserv.labels" -}}
app.kubernetes.io/name: {{ include "netobserv.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Resolve LokiStack storageClassName (required by the LokiStack CRD).

1. Use .Values.loki.storageClassName when set.
2. Else try Helm lookup for the cluster default StorageClass (works with
   helm install / helm template --dry-run=server; Argo CD does NOT support lookup).
3. Else fail and ask the user to set loki.storageClassName (required for Argo CD).

Do not omit the field: LokiStack validation requires spec.storageClassName.
*/}}
{{- define "netobserv.lokiStorageClassName" -}}
{{- $sc := .Values.loki.storageClassName | default "" -}}
{{- if $sc -}}
{{- $sc -}}
{{- else -}}
{{- $default := "" -}}
{{- range (lookup "storage.k8s.io/v1" "StorageClass" "" "").items | default list -}}
{{- $annotations := .metadata.annotations | default dict -}}
{{- if eq (index $annotations "storageclass.kubernetes.io/is-default-class" | default "") "true" -}}
{{- $default = .metadata.name -}}
{{- end -}}
{{- end -}}
{{- if not $default -}}
{{- fail "loki.storageClassName is required (LokiStack CRD). Set it in values or as an Argo CD helm parameter; Helm lookup cannot discover the default StorageClass under Argo CD." -}}
{{- end -}}
{{- $default -}}
{{- end -}}
{{- end }}
