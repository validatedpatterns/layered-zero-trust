{{- /*
  Validations for the acme issuer
*/ -}}
{{- define "acme.validations" -}}
{{- if not .solvers }}
{{- fail "For the acme issuer, you must specify the properties solvers" }}
{{- end }}
{{- end }}

{{- /*
  Validations for the credentials-request
*/ -}}
{{- define "credential-request.validations" -}}
{{- if not .secretRef }}
{{- fail "CredentialRequest requires a SecretRef definition" }}
{{- end }}
{{- if not .providerSpec }}
{{- fail "CredentialRequest requires a providerSpec definition" }}
{{- end }}
{{- end }}