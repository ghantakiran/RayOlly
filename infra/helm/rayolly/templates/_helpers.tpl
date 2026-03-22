{{/*
Expand the name of the chart.
*/}}
{{- define "rayolly.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "rayolly.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "rayolly.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "rayolly.labels" -}}
helm.sh/chart: {{ include "rayolly.chart" . }}
{{ include "rayolly.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: rayolly
{{- end }}

{{/*
Selector labels
*/}}
{{- define "rayolly.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rayolly.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "rayolly.serviceAccountName" -}}
{{- if .Values.serviceAccount }}
{{- if .Values.serviceAccount.create }}
{{- default (include "rayolly.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- else }}
{{- include "rayolly.fullname" . }}
{{- end }}
{{- end }}

{{/*
Image tag — falls back to appVersion
*/}}
{{- define "rayolly.imageTag" -}}
{{- .tag | default $.Chart.AppVersion }}
{{- end }}

{{/*
Component labels helper
*/}}
{{- define "rayolly.componentLabels" -}}
{{ include "rayolly.labels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Component selector labels helper
*/}}
{{- define "rayolly.componentSelectorLabels" -}}
{{ include "rayolly.selectorLabels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
