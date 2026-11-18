{{- define "cer-intent.name" -}}{{ .Release.Name }}-cer-intent{{- end -}}
{{- define "cer-intent.labels" -}}
app.kubernetes.io/name: cer-intent
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "cer-intent.env" -}}
- name: TERAFLOW_URL
  value: {{ .Values.teraflow.url | quote }}
- name: TFS_REALIZATION
  value: {{ .Values.sliceController.realization | quote }}
- name: NSC_DEFAULT_TECHNOLOGY
  value: {{ .Values.sliceController.defaultTechnology | quote }}
- name: CER_INTENT_MCP_MODE
  value: {{ .Values.mcp.mode | quote }}
{{- if .Values.twin.url }}
- name: TWIN_URL
  value: {{ .Values.twin.url | quote }}
{{- end }}
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
