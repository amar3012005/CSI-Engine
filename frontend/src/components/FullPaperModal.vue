<template>
  <Teleport to="body">
    <Transition name="paper-fade">
      <div v-if="modelValue" class="paper-overlay" @click.self="close">
        <!-- Top bar -->
        <div class="paper-topbar">
          <div class="pt-left">
            <img :src="davinciLogo" alt="Da'vinci" class="pt-logo" />
            <span class="pt-divider"></span>
            <span class="pt-label">Cognitive Swarm Intelligence Deep Research Report</span>
          </div>
          <div class="pt-right">
            <span class="pt-id">{{ reportId }}</span>
            <button class="pt-close" @click="close">&times;</button>
          </div>
        </div>

        <!-- Paper -->
        <div class="paper-viewport">
          <div class="paper-sheet">
            <div v-if="loading" class="paper-loading">
              <div class="load-spinner"></div>
              <span class="load-text">Generating report...</span>
            </div>

            <div v-else class="paper-content">
              <!-- Report header -->
              <div class="rpt-header">
                <div class="rpt-brand-row">
                  <img :src="davinciLogo" alt="Da'vinci" class="rpt-logo" />
                  <span class="rpt-divider"></span>
                  <span class="rpt-brand-label">Cognitive Swarm Intelligence Deep Research Report</span>
                </div>

                <h1 class="rpt-title">{{ reportTitle }}</h1>

                <div class="rpt-meta-grid">
                  <div class="rpt-meta-item">
                    <span class="rpt-meta-label">Report ID</span>
                    <span class="rpt-meta-value">{{ reportId }}</span>
                  </div>
                  <div class="rpt-meta-item">
                    <span class="rpt-meta-label">Generated</span>
                    <span class="rpt-meta-value">{{ formatDate(reportData?.created_at) }}</span>
                  </div>
                  <div class="rpt-meta-item">
                    <span class="rpt-meta-label">Status</span>
                    <span class="rpt-meta-value">{{ reportData?.status || 'completed' }}</span>
                  </div>
                  <div v-if="reportData?.outline?.sections?.length" class="rpt-meta-item">
                    <span class="rpt-meta-label">Sections</span>
                    <span class="rpt-meta-value">{{ reportData.outline.sections.length }}</span>
                  </div>
                </div>
              </div>

              <!-- Summary -->
              <div v-if="reportSummary" class="rpt-summary">
                <span class="rpt-summary-label">Executive Summary</span>
                <p class="rpt-summary-text">{{ reportSummary }}</p>
              </div>

              <!-- Outline TOC -->
              <div v-if="sectionTitles.length > 1" class="rpt-toc">
                <span class="rpt-toc-label">Contents</span>
                <div class="rpt-toc-list">
                  <a
                    v-for="(title, idx) in sectionTitles"
                    :key="idx"
                    class="rpt-toc-item"
                    :href="`#section-${idx}`"
                  >
                    <span class="toc-num">{{ idx + 1 }}</span>
                    <span class="toc-title">{{ title }}</span>
                  </a>
                </div>
              </div>

              <!-- Body -->
              <div class="rpt-body markdown-body" v-html="renderedContent"></div>

              <!-- Footer -->
              <div class="rpt-footer">
                <div class="rpt-footer-line"></div>
                <div class="rpt-footer-row">
                  <span class="rpt-footer-brand">Da'vinci AI &mdash; Cognitive Swarm Intelligence Deep Research</span>
                  <span class="rpt-footer-id">{{ reportId }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import davinciLogo from '../assets/davinci-logo.svg'

const props = defineProps({
  modelValue: Boolean,
  reportId: String,
  reportData: Object,
  loading: Boolean
})

const emit = defineEmits(['update:modelValue'])

const close = () => {
  emit('update:modelValue', false)
}

const reportTitle = computed(() => {
  return props.reportData?.outline?.title || props.reportData?.title || 'Research Report'
})

const reportSummary = computed(() => {
  return props.reportData?.outline?.summary || ''
})

const sectionTitles = computed(() => {
  const sections = props.reportData?.outline?.sections || props.reportData?.sections || []
  return sections.map(s => s.title).filter(Boolean)
})

const reportMarkdown = computed(() => {
  if (!props.reportData) return ''
  if (props.reportData.markdown_content) return props.reportData.markdown_content
  if (props.reportData.content) return props.reportData.content
  if (props.reportData.sections?.length) {
    return props.reportData.sections.map((section) => section.content || '').join('\n\n')
  }
  return ''
})

const renderedContent = computed(() => {
  if (!reportMarkdown.value) return ''
  return DOMPurify.sanitize(marked.parse(reportMarkdown.value))
})

const formatDate = (dateStr) => {
  if (!dateStr) return 'N/A'
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
/* ─── Overlay ─────────────────────────────────── */
.paper-overlay {
  position: fixed;
  inset: 0;
  background: rgba(250, 249, 244, 0.97);
  backdrop-filter: blur(12px);
  z-index: 10000;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

/* ─── Top bar ─────────────────────────────────── */
.paper-topbar {
  position: sticky;
  top: 0;
  z-index: 10001;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #e3e0db;
}

.pt-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pt-logo {
  height: 16px;
  filter: invert(1);
}

.pt-divider {
  width: 1px;
  height: 16px;
  background: #d4d0ca;
}

.pt-label {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.pt-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pt-id {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

.pt-close {
  width: 32px;
  height: 32px;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  background: #fff;
  color: #a3a3a3;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.pt-close:hover {
  border-color: #117dff;
  color: #117dff;
}

/* ─── Paper viewport ──────────────────────────── */
.paper-viewport {
  flex: 1;
  display: flex;
  justify-content: center;
  padding: 32px 24px 60px;
}

.paper-sheet {
  width: 100%;
  max-width: 780px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

/* ─── Loading ─────────────────────────────────── */
.paper-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 12px;
}

.load-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #e3e0db;
  border-top-color: #117dff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.load-text {
  font-size: 13px;
  color: #a3a3a3;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

/* ─── Report content ──────────────────────────── */
.paper-content {
  padding: 40px 48px 48px;
}

/* Header */
.rpt-header {
  margin-bottom: 32px;
}

.rpt-brand-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.rpt-logo {
  height: 20px;
  filter: invert(1);
}

.rpt-divider {
  width: 1px;
  height: 20px;
  background: #d4d0ca;
  flex-shrink: 0;
}

.rpt-brand-label {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  letter-spacing: 0.01em;
}

.rpt-title {
  font-size: 24px;
  font-weight: 700;
  color: #0a0a0a;
  line-height: 1.25;
  margin: 0 0 20px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.rpt-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.rpt-meta-item {
  padding: 8px 12px;
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rpt-meta-label {
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #a3a3a3;
}

.rpt-meta-value {
  font-size: 12px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'JetBrains Mono', monospace;
  word-break: break-all;
}

/* Summary */
.rpt-summary {
  margin-bottom: 24px;
  padding: 16px;
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
}

.rpt-summary-label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #a3a3a3;
  margin-bottom: 6px;
}

.rpt-summary-text {
  font-size: 14px;
  line-height: 1.65;
  color: #404040;
  margin: 0;
}

/* TOC */
.rpt-toc {
  margin-bottom: 28px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 8px;
}

.rpt-toc-label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #a3a3a3;
  margin-bottom: 8px;
}

.rpt-toc-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rpt-toc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  text-decoration: none;
  transition: background 0.12s;
}

.rpt-toc-item:hover {
  background: #faf9f4;
}

.toc-num {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: #f3f1ec;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: #737373;
  font-family: 'JetBrains Mono', monospace;
  flex-shrink: 0;
}

.toc-title {
  font-size: 13px;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

/* Body markdown */
.rpt-body {
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.rpt-body :deep(h1),
.rpt-body :deep(h2),
.rpt-body :deep(h3) {
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-weight: 600;
  color: #0a0a0a;
}

.rpt-body :deep(h2) {
  font-size: 17px;
  margin-top: 32px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0efeb;
}

.rpt-body :deep(h3) {
  font-size: 14px;
  margin-top: 22px;
  margin-bottom: 8px;
}

.rpt-body :deep(p) {
  font-size: 14px;
  line-height: 1.7;
  color: #404040;
  margin-bottom: 14px;
}

.rpt-body :deep(ul),
.rpt-body :deep(ol) {
  font-size: 14px;
  line-height: 1.6;
  color: #404040;
  padding-left: 22px;
  margin-bottom: 14px;
}

.rpt-body :deep(li) {
  margin-bottom: 4px;
}

.rpt-body :deep(blockquote) {
  border-left: 3px solid #117dff;
  padding: 8px 16px;
  margin: 14px 0;
  background: rgba(17, 125, 255, 0.04);
  border-radius: 0 6px 6px 0;
  color: #525252;
}

.rpt-body :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  background: #faf9f4;
  border: 1px solid #e3e0db;
  padding: 1px 4px;
  border-radius: 3px;
  color: #525252;
}

.rpt-body :deep(pre) {
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  padding: 14px;
  overflow-x: auto;
  margin-bottom: 14px;
}

.rpt-body :deep(pre code) {
  background: none;
  border: none;
  padding: 0;
}

.rpt-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 14px;
}

.rpt-body :deep(th),
.rpt-body :deep(td) {
  border: 1px solid #e3e0db;
  padding: 8px 12px;
  text-align: left;
}

.rpt-body :deep(th) {
  background: #faf9f4;
  font-weight: 600;
  color: #0a0a0a;
  font-size: 12px;
}

.rpt-body :deep(a) {
  color: #117dff;
  text-decoration: none;
}

.rpt-body :deep(a:hover) {
  text-decoration: underline;
}

/* Footer */
.rpt-footer {
  margin-top: 48px;
}

.rpt-footer-line {
  height: 1px;
  background: #e3e0db;
  margin-bottom: 12px;
}

.rpt-footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.rpt-footer-brand {
  font-size: 10px;
  color: #a3a3a3;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.rpt-footer-id {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #c4c0ba;
}

/* ─── Transitions ─────────────────────────────── */
.paper-fade-enter-active,
.paper-fade-leave-active {
  transition: opacity 0.3s ease;
}

.paper-fade-enter-from,
.paper-fade-leave-to {
  opacity: 0;
}

.paper-fade-enter-active .paper-sheet {
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.paper-fade-enter-from .paper-sheet {
  transform: translateY(40px);
}

/* ─── Responsive ──────────────────────────────── */
@media (max-width: 768px) {
  .paper-content {
    padding: 24px 20px 32px;
  }

  .rpt-title {
    font-size: 20px;
  }

  .rpt-meta-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
