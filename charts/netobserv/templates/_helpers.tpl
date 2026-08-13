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

Use .Values.loki.storageClassName when set; otherwise fail. No Helm lookup —
Argo CD does not support it. Set explicitly via chart values, --set, or an
Argo CD / clusterGroup helm parameter override (see values.yaml comments and
scripts/features/netobserv.yaml). Discover classes with: oc get storageclass
*/}}
{{- define "netobserv.lokiStorageClassName" -}}
{{- $sc := .Values.loki.storageClassName | default "" -}}
{{- if $sc -}}
{{- $sc -}}
{{- else -}}
{{- fail "loki.storageClassName is required (LokiStack CRD). Set it in chart values (loki.storageClassName), via --set, or as an Argo CD / clusterGroup helm parameter override. See charts/netobserv/values.yaml. Discover classes: oc get storageclass" -}}
{{- end -}}
{{- end }}
