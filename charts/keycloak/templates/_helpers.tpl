{{/*
Generate the name of the Service.
*/}}
{{- define "keycloak.service.name" -}}
{{- if eq .Values.keycloak.tls.serviceServing true }}
{{- printf "%s-service-serving" .Values.keycloak.name }}
{{- else }}
{{- printf "%s-service" .Values.keycloak.name }}
{{- end }}
{{- end }}

{{/*
Generate the hostname for the Ingress.
*/}}

{{- define "keycloak.ingress.hostname" -}}
{{- if eq .Values.keycloak.ingress.hostname "" }}
{{- printf "%s.%s" .Values.keycloak.name .Values.global.localClusterDomain }}
{{- else }}
{{- print .Values.keycloak.ingress.hostname }}
{{- end }}
{{- end }}