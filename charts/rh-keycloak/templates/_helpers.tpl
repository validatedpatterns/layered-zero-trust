{{/*
Generate the qtodo OIDC Client ID based on provider and authentication method
*/}}
{{- define "rh-keycloak.qtodo.oidc.clientId" }}
{{- if .Values.qtodo.oidc.clientId }}
{{- print .Values.qtodo.oidc.clientId }}
{{- else if .Values.qtodo.oidc.clientAssertion.enabled }}
{{- printf "spiffe://apps.%s/ns/%s/sa/%s" .Values.global.clusterDomain .Values.qtodo.namespace .Values.qtodo.serviceAccount }}
{{- else }}
{{- print "qtodo-app" }}
{{- end }}
{{- end }}
