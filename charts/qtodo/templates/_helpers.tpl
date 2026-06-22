{{/*
Create the image path for the passed in image field.
When global.registry is enabled with domain and repository, the image
reference is derived from global.registry.domain/repository (e.g.
quay.io/ztvp/qtodo) so no VP --set override is needed.
*/}}
{{- define "qtodo.image" -}}
{{- $name := tpl .value.name .context -}}
{{- $useRegistry := default false .useRegistry -}}
{{- if and $useRegistry .context.Values.global.registry.enabled .context.Values.global.registry.domain .context.Values.global.registry.repository -}}
{{- $name = printf "%s/%s" (tpl .context.Values.global.registry.domain .context) .context.Values.global.registry.repository -}}
{{- end -}}
{{- if eq (substr 0 7 (tpl .value.version .context)) "sha256:" -}}
{{- printf "%s@%s" $name (tpl .value.version .context) -}}
{{- else -}}
{{- printf "%s:%s" $name (tpl .value.version .context) -}}
{{- end -}}
{{- end -}}

{{/*
Generate the URL of the OIDC service
*/}}
{{- define "qtodo.oidc.url" }}
{{- if not .Values.app.oidc.authServerUrl }}
{{- printf "https://keycloak.%s/realms/%s" .Values.global.localClusterDomain .Values.app.oidc.realm }}
{{- else }}
{{- print .Values.app.oidc.authServerUrl }}
{{- end }}
{{- end }}

{{/*
Generate the JWT Audience
*/}}
{{- define "qtodo.jwt.audience" }}
{{- if not .Values.app.vault.audience }}
{{- printf "https://keycloak.%s/realms/%s" .Values.global.localClusterDomain .Values.app.oidc.realm }}
{{- else }}
{{- print .Values.app.vault.audience }}
{{- end }}
{{- end }}

{{/*
Returns true if the termination is secure (https) and false otherwise
*/}}
{{- define "qtodo.isSecureTermination" }}
{{- if or (eq .Values.app.route.termination "reencrypt") (eq .Values.app.route.termination "passthrough") }}
true
{{- end }}
{{- end }}

{{/*
Returns the port the application should list on
*/}}
{{- define "qtodo.app.port" -}}
{{- if include "qtodo.isSecureTermination" . -}}
{{ .Values.app.securePort }}
{{- else -}}
{{ .Values.app.insecurePort }}
{{- end -}}
{{- end -}}