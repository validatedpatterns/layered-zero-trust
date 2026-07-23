{{- define "netobserv.name" -}}
netobserv
{{- end }}

{{- define "netobserv.labels" -}}
app.kubernetes.io/name: {{ include "netobserv.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
