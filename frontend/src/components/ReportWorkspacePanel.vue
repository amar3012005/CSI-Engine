<template>
  <div class="report-workspace-panel">
    <!-- Health mode: structured diagnostic report -->
    <HealthReportPanel
      v-if="resolvedHealthMode"
      :simulationId="simulationId"
    />

    <!-- Standard mode: markdown paper report -->
    <template v-else>
      <!-- Loading -->
      <div v-if="loading" class="report-state">
        <div class="state-spinner"></div>
        <span class="state-title">Generating report</span>
        <span class="state-desc">Drafting from simulation artifacts...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="report-state">
        <span class="state-icon error-icon">!</span>
        <span class="state-title">Report unavailable</span>
        <span class="state-desc">{{ error }}</span>
      </div>

      <!-- Report content -->
      <div v-else-if="reportData" class="report-content">
        <!-- Header bar -->
        <div class="report-bar">
          <div class="rb-left">
            <span class="rb-tag">Report</span>
            <span class="rb-id">{{ currentReportId }}</span>
            <span v-if="!isComplete" class="rb-generating">
              <span class="rb-gen-dot"></span>
              Generating
            </span>
          </div>
          <div class="rb-right">
            <span v-if="reportData.created_at" class="rb-date">{{ formatDate(reportData.created_at) }}</span>
            <div class="download-container">
              <button class="rb-btn download-btn" @click="toggleDownloadMenu">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              </button>
              <div v-if="showDownloadMenu" class="download-dropdown">
                <button @click="downloadAs('pdf')">.pdf</button>
                <button @click="downloadAs('docx')">.docx</button>
                <button @click="downloadAs('md')">.md</button>
              </div>
            </div>
            <button class="rb-btn" @click="showPaper = true">View Paper</button>
          </div>
        </div>

        <!-- Section-by-section rendering -->
        <div class="report-body">
          <div
            v-for="(section, idx) in reportSections"
            :key="idx"
            class="report-section"
          >
            <div v-if="section.content" class="section-rendered markdown-body" v-html="renderSection(section.content)"></div>
            <div v-else class="section-skeleton">
              <div class="skel-title"></div>
              <div class="skel-line long"></div>
              <div class="skel-line medium"></div>
              <div class="skel-line short"></div>
            </div>
          </div>

          <!-- Loading skeleton for remaining sections -->
          <div v-if="!isComplete && reportSections.length > 0" class="section-skeleton loading-next">
            <div class="skel-spinner"></div>
            <span class="skel-label">Writing next section...</span>
          </div>
        </div>
      </div>

      <!-- Full page modal -->
      <FullPaperModal
        v-model="showPaper"
        :report-id="currentReportId"
        :report-data="reportData"
        :loading="loading"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { getPaperReportBySimulation, getReport } from '../api/report'
import { getSimulation } from '../api/simulation'
import FullPaperModal from './FullPaperModal.vue'
import HealthReportPanel from './HealthReportPanel.vue'

const props = defineProps({
  simulationId: {
    type: String,
    default: ''
  },
  reportId: {
    type: String,
    default: ''
  },
  reportStarted: {
    type: Boolean,
    default: false
  },
  isHealthMode: {
    type: Boolean,
    default: false
  },
  simulationConfigMode: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['report-loaded'])

const reportData = ref(null)
const loading = ref(false)
const showPaper = ref(false)
// Self-determined health mode — verified from simulation API, not relying solely on prop
const resolvedHealthMode = ref(props.isHealthMode)
const error = ref('')
const currentReportId = ref(props.reportId || '')
const showDownloadMenu = ref(false)
let pollTimer = null

const toggleDownloadMenu = (e) => {
  e.stopPropagation()
  showDownloadMenu.value = !showDownloadMenu.value
}

const downloadAs = (format) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const url = `${baseUrl}/api/report/${currentReportId.value}/download?format=${format}`
  window.open(url, '_blank')
  showDownloadMenu.value = false
}

// Close menu on click outside
onMounted(() => {
  window.addEventListener('click', () => { showDownloadMenu.value = false })
})

onBeforeUnmount(() => {
  window.removeEventListener('click', () => { showDownloadMenu.value = false })
})

const paperTitle = computed(() => {
  return reportData.value?.outline?.title || reportData.value?.title || 'Technical Report'
})

const paperSummary = computed(() => {
  return reportData.value?.outline?.summary || ''
})

const isComplete = computed(() => {
  const status = String(reportData.value?.status || '').toLowerCase()
  return status === 'completed' || status === 'done'
})

const reportSections = computed(() => {
  if (!reportData.value) return []

  // If full markdown, return as single section
  if (reportData.value.markdown_content || reportData.value.content) {
    return [{ content: reportData.value.markdown_content || reportData.value.content }]
  }

  // Sections array
  if (reportData.value.sections?.length) {
    return reportData.value.sections.map(s => ({
      title: s.title || '',
      content: s.content || ''
    }))
  }

  // Outline sections
  if (reportData.value.outline?.sections?.length) {
    return reportData.value.outline.sections.map(s => ({
      title: s.title || '',
      content: s.content ? `## ${s.title}\n\n${s.content}` : ''
    }))
  }

  return []
})

const renderSection = (md) => {
  if (!md) return ''
  return DOMPurify.sanitize(marked.parse(md))
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}

const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    fetchReport(currentReportId.value)
  }, 5000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const fetchReport = async (id) => {
  if (!id) return
  try {
    const res = await getReport(id)
    if (res.success && res.data) {
      reportData.value = res.data
      const status = String(res.data.status || '').toLowerCase()
      if (status === 'completed' || status === 'failed') {
        stopPolling()
      }
      emit('report-loaded', res.data)
    }
  } catch (err) {
    error.value = 'Failed to load report data.'
    stopPolling()
  }
}

const resolveHealthMode = async () => {
  // Fast path: prop or already-loaded config_mode
  if (props.isHealthMode || props.simulationConfigMode === 'health') {
    resolvedHealthMode.value = true
    return
  }
  // Fallback: fetch directly (handles cold-load where prop hasn't propagated yet)
  if (!props.simulationId) return
  try {
    const res = await getSimulation(props.simulationId)
    if (res.success && res.data?.config_mode === 'health') {
      resolvedHealthMode.value = true
    }
  } catch {
    // keep as prop value
  }
}

const initialize = async () => {
  // Health mode uses HealthReportPanel (rendered via v-if in template) — skip paper polling
  if (resolvedHealthMode.value) return

  error.value = ''
  loading.value = true

  try {
    if (props.reportId) {
      currentReportId.value = props.reportId
      await fetchReport(props.reportId)
    } else if (props.simulationId) {
      const lookup = await getPaperReportBySimulation(props.simulationId)
      if (lookup.success && lookup.data) {
        currentReportId.value = lookup.data.report_id
        await fetchReport(lookup.data.report_id)
      }
    }

    if (props.reportStarted && reportData.value?.status !== 'completed') {
      startPolling()
    }
  } finally {
    loading.value = false
  }
}

watch(() => props.isHealthMode, (val) => {
  if (val) resolvedHealthMode.value = true
})

watch(() => props.simulationConfigMode, (val) => {
  if (val === 'health') resolvedHealthMode.value = true
})

watch(() => props.reportId, (newId) => {
  if (!resolvedHealthMode.value && newId && newId !== currentReportId.value) {
    currentReportId.value = newId
    initialize()
  }
})

watch(() => props.reportStarted, (started) => {
  if (!resolvedHealthMode.value && started && !reportData.value) {
    initialize()
  }
})

onMounted(async () => {
  await resolveHealthMode()
  if (!resolvedHealthMode.value) {
    initialize()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
/* ─── Da-vinci HIVEMIND theme ─────────────────── */
.report-workspace-panel {
  height: 100%;
  background: #fff;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  display: flex;
  flex-direction: column;
}

/* ─── Loading / Error states ──────────────────── */
.report-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
}

.state-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #e3e0db;
  border-top-color: #117dff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 4px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.state-title {
  font-size: 14px;
  font-weight: 600;
  color: #0a0a0a;
}

.state-desc {
  font-size: 12px;
  color: #a3a3a3;
  text-align: center;
  max-width: 240px;
}

.error-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(220, 38, 38, 0.1);
  color: #dc2626;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}

/* ─── Report content ──────────────────────────── */
.report-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header bar */
.report-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #e3e0db;
  background: #faf9f4;
  flex-shrink: 0;
}

.rb-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.rb-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #117dff;
  background: rgba(17, 125, 255, 0.08);
  padding: 2px 7px;
  border-radius: 4px;
}

.rb-id {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rb-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.rb-date {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

.rb-btn {
  padding: 4px 10px;
  border: 1px solid #e3e0db;
  border-radius: 6px;
  background: #fff;
  color: #525252;
  font-size: 11px;
  font-weight: 600;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  cursor: pointer;
  transition: all 0.15s;
}

.rb-btn:hover {
  border-color: #117dff;
  color: #117dff;
  background: rgba(17, 125, 255, 0.04);
}

.download-container {
  position: relative;
  display: flex;
}

.download-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 5px;
  background: white;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  z-index: 1000;
  min-width: 90px;
  overflow: hidden;
  padding: 4px 0;
}

.download-dropdown button {
  width: 100%;
  padding: 8px 16px;
  border: none;
  background: none;
  text-align: left;
  font-size: 13px;
  cursor: pointer;
  color: #1a1a1a;
  font-family: inherit;
  transition: background 0.12s;
}

.download-dropdown button:hover {
  background: #f0f7ff;
  color: #117dff;
}

/* Intro section */
.report-intro {
  padding: 16px 20px;
  border-bottom: 1px solid #f0efeb;
}

.ri-title {
  font-size: 16px;
  font-weight: 600;
  color: #0a0a0a;
  margin: 0 0 6px;
  line-height: 1.3;
}

.ri-summary {
  font-size: 13px;
  line-height: 1.6;
  color: #525252;
  margin: 0;
}

/* Markdown body */
.report-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  scrollbar-width: thin;
  scrollbar-color: #d4d0ca transparent;
}

.report-body::-webkit-scrollbar { width: 3px; }
.report-body::-webkit-scrollbar-thumb { background: #d4d0ca; border-radius: 3px; }

.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3) {
  color: #0a0a0a;
  font-weight: 600;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.report-body :deep(h2) {
  font-size: 15px;
  margin-top: 24px;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0efeb;
}

.report-body :deep(h3) {
  font-size: 13px;
  margin-top: 18px;
  margin-bottom: 8px;
}

.report-body :deep(p) {
  font-size: 13px;
  line-height: 1.65;
  color: #404040;
  margin-bottom: 12px;
}

.report-body :deep(ul),
.report-body :deep(ol) {
  font-size: 13px;
  line-height: 1.6;
  color: #404040;
  padding-left: 20px;
  margin-bottom: 12px;
}

.report-body :deep(li) {
  margin-bottom: 4px;
}

.report-body :deep(blockquote) {
  border-left: 3px solid #e3e0db;
  padding-left: 14px;
  margin: 12px 0;
  color: #737373;
  font-style: italic;
}

.report-body :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  background: #faf9f4;
  border: 1px solid #e3e0db;
  padding: 1px 4px;
  border-radius: 3px;
  color: #525252;
}

.report-body :deep(pre) {
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin-bottom: 12px;
}

.report-body :deep(pre code) {
  background: none;
  border: none;
  padding: 0;
}

.report-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 12px;
}

.report-body :deep(th),
.report-body :deep(td) {
  border: 1px solid #e3e0db;
  padding: 6px 10px;
  text-align: left;
}

.report-body :deep(th) {
  background: #faf9f4;
  font-weight: 600;
  color: #0a0a0a;
}

.report-body :deep(a) {
  color: #117dff;
  text-decoration: none;
}

.report-body :deep(a:hover) {
  text-decoration: underline;
}

/* ─── Generating indicator ────────────────────── */
.rb-generating {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 500;
  color: #117dff;
}

.rb-gen-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #117dff;
  animation: gen-pulse 1.2s ease-in-out infinite;
}

@keyframes gen-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ─── Section rendering ───────────────────────── */
.report-section {
  padding-bottom: 8px;
}

.report-section + .report-section {
  border-top: 1px solid #f0efeb;
  padding-top: 8px;
}

/* ─── Skeleton loading ────────────────────────── */
.section-skeleton {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-skeleton.loading-next {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
}

.skel-title {
  width: 40%;
  height: 14px;
  background: linear-gradient(90deg, #f0efeb 25%, #e8e5e0 50%, #f0efeb 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: skel-shimmer 1.5s ease-in-out infinite;
}

.skel-line {
  height: 10px;
  background: linear-gradient(90deg, #f0efeb 25%, #e8e5e0 50%, #f0efeb 75%);
  background-size: 200% 100%;
  border-radius: 3px;
  animation: skel-shimmer 1.5s ease-in-out infinite;
}

.skel-line.long { width: 90%; }
.skel-line.medium { width: 70%; }
.skel-line.short { width: 45%; }

.skel-spinner {
  width: 14px;
  height: 14px;
  border: 1.5px solid #e3e0db;
  border-top-color: #117dff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.skel-label {
  font-size: 11px;
  color: #a3a3a3;
}

@keyframes skel-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>

