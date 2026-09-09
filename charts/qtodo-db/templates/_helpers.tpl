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

{{/*
True when the shared secondary UDN is enabled (bool or string "true").
*/}}
{{- define "qtodo-db.udn.enabled" -}}
{{- if eq (.Values.udn.enabled | default false | toString) "true" -}}
true
{{- end -}}
{{- end -}}

{{/*
IPv4 prefix length from udn.subnet (e.g. 10.100.0.0/16 -> 16).
*/}}
{{- define "qtodo-db.udn.prefixlen" -}}
{{- regexReplaceAll "^[^/]+/" .Values.udn.subnet "" -}}
{{- end -}}

{{/*
Multus annotation attaching the postgres pod to the CUDN-managed NAD.
Uses simple <namespace>/<name> format — static IP is driven by the
k8s.ovn.org/pod-networks pre-annotation, not by the Multus ips field
(which OVN-K does not support for secondary Layer2 UDN networks).
*/}}
{{- define "qtodo-db.udn.networksAnnotation" -}}
{{ .Release.Namespace }}/{{ .Values.udn.name }}
{{- end -}}

{{/*
OVN-K pod-networks pre-annotation that requests a static IP on the
secondary UDN. The key format is <namespace>/<nad-name> — matching the
key OVN-K writes when it allocates dynamically. OVN-K reads this before
the CNI call and honours the specified ip_addresses instead of allocating
a new one from the pool.
*/}}
{{- define "qtodo-db.udn.ovnPodNetworks" -}}
{{- $ip := printf "%s/%s" .Values.udn.dbIP (include "qtodo-db.udn.prefixlen" .) -}}
{{- $key := printf "%s/%s" .Release.Namespace .Values.udn.name -}}
{"{{ $key }}":{"ip_addresses":["{{ $ip }}"],"ip_address":"{{ $ip }}","role":"secondary"}}
{{- end -}}
