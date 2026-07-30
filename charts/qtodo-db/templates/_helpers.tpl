{{/*
Create the image path for the passed in image field.
*/}}
{{- define "qtodo-db.image" -}}
{{- $name := tpl .value.name .context -}}
{{- if eq (substr 0 7 (tpl .value.version .context)) "sha256:" -}}
{{- printf "%s@%s" $name (tpl .value.version .context) -}}
{{- else -}}
{{- printf "%s:%s" $name (tpl .value.version .context) -}}
{{- end -}}
{{- end -}}
