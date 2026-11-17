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
Generate OIDC issuer
*/}}
{{- define "rhtas.oidc.issuer" }}
{{- if not .Values.rhtas.oidc.enabled }}
{{- printf "https://spire-spiffe-oidc-discovery-provider.%s" .Values.global.hubClusterDomain }}
{{- else }}
{{- print .Values.rhtas.oidc.issuer }}
{{- end }}
{{- end }}

{{/*
Generate OIDC identity
*/}}
{{- define "rhtas.oidc.identity" }}
{{- if not .Values.rhtas.oidc.enabled }}
{{- printf "spiffe://%s/ns/%s/sa/pipeline" .Values.global.hubClusterDomain .Values.global.namespace }}
{{- else }}
{{- print .Values.rhtas.oidc.identity }}
{{- end }}
{{- end }}

{{/*
Generate the RHTPA URL
*/}}
{{- define "rhtpa.url" }}
{{- if not .Values.rhtpa.url }}
{{- printf "https://servertrustify.%s" .Values.global.hubClusterDomain }}
{{- else }}
{{- print .Values.rhtpa.url }}
{{- end }}
{{- end }}

{{/*
Generate the URL of the OIDC service used by RHTPA
*/}}
{{- define "rhtpa.oidc.url" }}
{{- if not .Values.rhtpa.oidc.url }}
{{- printf "https://keycloak.%s/realms/%s" .Values.global.hubClusterDomain .Values.rhtpa.oidc.realm }}
{{- else }}
{{- print .Values.rhtpa.oidc.url }}
{{- end }}
{{- end }}

{{/*
Sigstore environment variables used in Pipeline Tasks
*/}}
{{- define "rhtas.tasks.sigstoreEnvVars" -}}
{{- if .Values.rhtas.spire.enabled }}
- name: SPIFFE_ENDPOINT_SOCKET
  value: {{ .Values.spire.endpointSocketPath }}
{{- end }}
- name: CLI_SERVER_URL
  value: $(params.cli-server-url)
- name: TUF_URL
  value: $(params.tuf-url)
- name: FULCIO_URL
  value: $(params.fulcio-url)
- name: REKOR_URL
  value: $(params.rekor-url)
- name: CA_FILE
  value: $(params.ca-file)
- name: COSIGN_YES
  value: "true"
- name: OIDC_IDENTITY
  value: $(params.oidc-identity)
- name: OIDC_ISSUER
  value: $(params.oidc-issuer)
- name: OIDC_ISSUER_URL
  value: $(params.oidc-issuer)
{{- if eq .Values.rhtas.oidc.enabled true }}
- name: OIDC_CLIENT_ID
  value: $(params.rhtas-oidc-client-id)
- name: COSIGN_OIDC_CLIENT_ID
  value: $(params.rhtas-oidc-client-id)
- name: SIGTORE_OIDC_CLIENT_ID
  value: $(params.rhtas-oidc-client-id)
{{- if ne .Values.rhtas.oidc.clientSecretName "" }}
- name: OIDC_CLIENT_SECRET_FILE
  value: /run/secrets/rhtas/oidc/client-secret
- name: COSIGN_OIDC_CLIENT_SECRET_FILE
  value: /run/secrets/rhtas/oidc/client-secret
{{- end }}
{{- end }}
{{- end }}

{{/*
Sigstore params used in Pipeline Tasks
*/}}
{{- define "rhtas.tasks.sigstoreParams" -}}
- name: ca-file
  value: $(params.ca-file)
- name: fulcio-url
  value: $(params.fulcio-url)
- name: rekor-url
  value: $(params.rekor-url)
- name: tuf-url
  value: $(params.tuf-url)
- name: cli-server-url
  value: $(params.cli-server-url)
- name: oidc-identity
  value: $(params.oidc-identity)
- name: oidc-issuer
  value: $(params.oidc-issuer)
{{- if eq .Values.rhtas.oidc.enabled true }}
- name: rhtas-oidc-client-id
  value: $(params.rhtas-oidc-client-id)
{{- end }}
{{- end }}

{{/*
Sigstore params descriptions used in Pipeline Tasks
*/}}
{{- define "rhtas.tasks.sigstoreParamsDesc" -}}
- description: PEM encoded file containing the CA certificate to validate RHTAS services
  name: ca-file
  type: string
- description: Fulcio service URL
  name: fulcio-url
  type: string
- description: Rekor service URL
  name: rekor-url
  type: string
- description: TUF service URL
  name: tuf-url
  type: string
- description: Cosign CLI server URL
  name: cli-server-url
  type: string
- description: OIDC identity in signatures
  name: oidc-identity
  type: string
- description: OIDC issuer in signatures
  name: oidc-issuer
  type: string
{{- if eq .Values.rhtas.oidc.enabled true }}
- description: RHTAS OIDC client ID
  name: rhtas-oidc-client-id
  type: string
{{- end }}
{{- end }}
{{/*
Whether the short-lived Quay robot token generator is enabled
(quayTokenGenerator.enabled or global.registry.quayTokenGenerator.enabled)
*/}}
{{- define "supply-chain.quayTokenGenerator.enabled" -}}
{{- $local := dig "enabled" false (.Values.quayTokenGenerator | default dict) -}}
{{- $global := dig "registry" "quayTokenGenerator" "enabled" false (.Values.global | default dict) -}}
{{- if or $local $global -}}true{{- end -}}
{{- end }}

{{/*
Quay registry repository (namespace/name) used by the robot token generator
*/}}
{{- define "supply-chain.quayTokenGenerator.repository" -}}
{{- $repository := .Values.registry.repository | default .Values.global.registry.repository -}}
{{- if not (contains "/" ($repository | default "")) }}
{{- fail "quayTokenGenerator requires registry.repository (or global.registry.repository) in the form <organization>/<name>" }}
{{- end }}
{{- $repository -}}
{{- end }}

{{/*
Quay organization that owns the robots (first component of the repository)
*/}}
{{- define "supply-chain.quayTokenGenerator.organization" -}}
{{- index (splitList "/" (include "supply-chain.quayTokenGenerator.repository" .)) 0 -}}
{{- end }}

{{/*
Vault URL used by the Quay token generator (Vault route by default)
*/}}
{{- define "supply-chain.quayTokenGenerator.vaultUrl" -}}
{{- .Values.quayTokenGenerator.vault.url | default (printf "https://vault-vault.%s" .Values.global.hubClusterDomain) }}
{{- end }}

{{/*
Pod spec shared by the Quay robot provisioner Job and CronJob
Usage: include "supply-chain.quayRobotProvisioner.podSpec" (dict "ctx" . "softFail" false)
*/}}
{{- define "supply-chain.quayRobotProvisioner.podSpec" -}}
{{- $softFail := .softFail | default false }}
{{- with .ctx }}
{{- $gen := .Values.quayTokenGenerator }}
serviceAccountName: {{ $gen.provisioner.serviceAccount }}
restartPolicy: Never
containers:
- name: provision-robots
  image: {{ .Values.images.ubi }}
  command: ["python3", "/app/quay_robots.py"]
  env:
    - name: QUAY_HOST
      value: {{ tpl (required "registry.domain (or global.registry.domain) is required" (.Values.registry.domain | default .Values.global.registry.domain)) . | quote }}
    - name: QUAY_ADMIN_USER
      value: {{ required "registry.user (or global.registry.user) is required" (.Values.registry.user | default .Values.global.registry.user) | quote }}
    - name: QUAY_ADMIN_PASSWORD
      valueFrom:
        secretKeyRef:
          name: quay-robot-provisioner-credentials
          key: password
    - name: QUAY_REPOSITORY
      value: {{ include "supply-chain.quayTokenGenerator.repository" . | quote }}
    - name: ROBOTS_FILE
      value: /app/robots.json
    - name: SOFT_FAIL
      value: {{ $softFail | quote }}
  volumeMounts:
    - name: script-volume
      readOnly: true
      mountPath: /app
volumes:
  - name: script-volume
    configMap:
      name: quay-robot-provisioner
      defaultMode: 0755
{{- end }}
{{- end }}
