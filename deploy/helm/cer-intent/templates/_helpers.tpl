{{- define "cer-intent.name" -}}{{ .Release.Name }}-cer-intent{{- end -}}
{{- define "cer-intent.labels" -}}
app.kubernetes.io/name: cer-intent
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "cer-intent.image" -}}{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}{{- end -}}
{{- define "cer-intent.env" -}}
- name: ADAPTER_BACKEND
  value: teraflow
- name: TERAFLOW_URL
  value: {{ .Values.teraflow.url | quote }}
- name: TFS_REALIZATION
  value: {{ .Values.sliceController.realization | quote }}
- name: NSC_DEFAULT_TECHNOLOGY
  value: {{ .Values.sliceController.defaultTechnology | quote }}
- name: CER_INTENT_MCP_MODE
  value: {{ .Values.mcp.mode | quote }}
- name: FLASK_DEBUG
  value: "false"
- name: CER_IMF_POLICY
  value: /etc/cer-intent/imf_policy.json
- name: CER_SITE_PLAN
  value: /etc/cer-intent/site_plan.json
- name: CER_IMF_ALIASES
  value: /etc/cer-intent/imf_aliases.json
- name: CER_IMF_DISCOVERY
  value: {{ ternary "1" "0" .Values.intentManager.discovery | quote }}
- name: CER_IMF_DISCOVERY_TTL_S
  value: {{ .Values.intentManager.discoveryTtlS | quote }}
- name: CER_IMF_TICK_S
  value: {{ .Values.intentManager.tickS | quote }}
- name: CER_IMF_LLM
  value: {{ .Values.llm.provider | quote }}
- name: CER_IMF_TWIN
  value: {{ ternary "1" "0" (not (empty .Values.twin.url)) | quote }}
{{- if .Values.twin.url }}
- name: TWIN_URL
  value: {{ .Values.twin.url | quote }}
{{- end }}
- name: CER_AUTH
  value: {{ .Values.auth.mode | quote }}
- name: CER_AUTH_OPEN_READ
  value: {{ ternary "1" "0" .Values.auth.openRead | quote }}
- name: CER_COOKIE_SECURE
  value: {{ ternary "1" "0" .Values.auth.cookieSecure | quote }}
{{- if .Values.auth.tokensSecret }}
- name: CER_AUTH_TOKENS_FILE
  value: /etc/cer-intent-auth/tokens.yaml
{{- end }}
{{- if .Values.auth.sessionSecret }}
- name: CER_SECRET_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.auth.sessionSecret }}, key: CER_SECRET_KEY}}
{{- end }}
- name: CER_READY_REQUIRE
  value: {{ .Values.readiness.require | quote }}
{{- end -}}
{{- define "cer-intent.envFrom" -}}
{{- if or .Values.teraflow.credentialsSecret .Values.llm.secret }}
envFrom:
  {{- if .Values.teraflow.credentialsSecret }}
  - secretRef: {name: {{ .Values.teraflow.credentialsSecret }}}
  {{- end }}
  {{- if .Values.llm.secret }}
  - secretRef: {name: {{ .Values.llm.secret }}}
  {{- end }}
{{- end }}
{{- end -}}
