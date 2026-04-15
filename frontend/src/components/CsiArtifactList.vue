<template>
  <div class="csi-artifact-list" :class="{ compact }">
    <div v-if="title || showRefresh" class="artifact-header">
      <div class="header-copy">
        <span v-if="title" class="artifact-title">{{ title }}</span>
        <span v-if="description" class="artifact-desc">{{ description }}</span>
      </div>
      <button v-if="showRefresh" class="refresh-btn" @click="loadState()" :disabled="loading || refreshing" title="Refresh CSI state">
        <span :class="{ spinning: loading || refreshing }">↻</span>
      </button>
    </div>

    <div v-if="loading" class="artifact-state">Loading...</div>
    <div v-else-if="error && !state" class="artifact-state error">{{ error }}</div>
    <template v-else-if="state">
      <!-- Ranked artifacts by confidence -->
      <div class="ranked-list">
        <article
          v-for="item in rankedArtifacts"
          :key="item.uid"
          class="ranked-card"
          :class="{ selected: selectedArtifact?.raw === item.raw }"
          @click="selectArtifact(item.kind, item.raw)"
        >
          <div class="ranked-top">
            <span class="ranked-type-dot" :style="{ background: item.color }"></span>
            <span class="ranked-type">{{ item.typeLabel }}</span>
            <span v-if="item.status" class="ranked-status" :class="`s-${slugify(item.status)}`">{{ item.status }}</span>
            <span class="ranked-conf">{{ item.confLabel }}</span>
          </div>
          <p class="ranked-text">{{ item.text }}</p>
          <div v-if="item.agent" class="ranked-foot">
            <span class="ranked-agent">{{ item.agent }}</span>
            <span v-if="item.round != null" class="ranked-round">R{{ item.round }}</span>
          </div>
        </article>
      </div>

      <div v-if="selectedArtifact" class="artifact-preview">
        <div class="preview-header">
          <div class="preview-title-wrap">
            <span class="preview-kicker">{{ selectedArtifact.label }}</span>
            <span class="preview-title">{{ selectedArtifact.title }}</span>
          </div>
          <button class="preview-close" @click="selectedArtifact = null">&times;</button>
        </div>
        <div v-if="selectedArtifact.summary" class="preview-summary">{{ selectedArtifact.summary }}</div>
        <div class="preview-grid">
          <div v-for="field in selectedArtifact.fields" :key="field.key" class="preview-field">
            <span class="preview-field-label">{{ field.key }}</span>
            <span class="preview-field-value">{{ field.value }}</span>
          </div>
        </div>
      </div>

      <div v-if="!hasAnyArtifacts" class="artifact-state empty">No artifacts yet.</div>
    </template>
    <div v-else class="artifact-state empty">Waiting for CSI state...</div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { getSimulationCsiState } from '../api/csi'

const emit = defineEmits(['artifact-select'])

const props = defineProps({
  simulationId: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    default: 'CSI Artifacts'
  },
  description: {
    type: String,
    default: 'Claims, trials, and relations derived from the current simulation.'
  },
  compact: {
    type: Boolean,
    default: false
  },
  showRefresh: {
    type: Boolean,
    default: true
  },
  autoRefresh: {
    type: Boolean,
    default: false
  },
  refreshIntervalMs: {
    type: Number,
    default: 5000
  }
})

const state = ref(null)
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const expanded = ref(false)
const activeTab = ref('claims')
const selectedArtifact = ref(null)
let refreshTimer = null

const normalizeArray = (value) => {
  if (Array.isArray(value)) return value
  if (value && Array.isArray(value.items)) return value.items
  return []
}

const normalizeState = (payload) => {
  const data = payload?.data || payload?.state || payload || {}
  const summary = data.summary || data.stats || {}
  return {
    summary,
    claims: normalizeArray(data.claims || data.claim_items || summary.claims),
    trials: normalizeArray(data.trials || data.trial_items || summary.trials),
    relations: normalizeArray(data.relations || data.edges || summary.relations),
    sources: normalizeArray(data.sources || summary.sources),
    recalls: normalizeArray(data.recalls || summary.recalls),
    agentActions: normalizeArray(data.agent_actions || summary.agent_actions),
    updates: normalizeArray(data.updates || summary.updates),
    derives: normalizeArray(data.derives || summary.derives)
  }
}

const formatConfidence = (value) => {
  if (value === null || value === undefined || value === '') return ''
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  if (numeric <= 1) return `${Math.round(numeric * 100)}%`
  return `${Math.round(numeric)}%`
}

const slugify = (value) => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

const loadState = async (options = {}) => {
  const { silent = false } = options
  if (!props.simulationId) {
    state.value = null
    return
  }

  const backgroundRefresh = silent && !!state.value
  if (loading.value || refreshing.value) return
  if (backgroundRefresh) {
    refreshing.value = true
  } else {
    loading.value = true
  }

  error.value = ''
  try {
    const res = await getSimulationCsiState(props.simulationId)
    state.value = normalizeState(res)
  } catch (err) {
    if (err?.response?.status === 404) {
      state.value = null
      error.value = ''
      return
    }
    state.value = null
    error.value = err?.response?.data?.error || err.message || 'Failed to load CSI state'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!props.autoRefresh || !props.simulationId) return

  refreshTimer = setInterval(() => {
    loadState({ silent: true })
  }, props.refreshIntervalMs)
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const claims = computed(() => state.value?.claims || [])
const trials = computed(() => state.value?.trials || [])
const relations = computed(() => state.value?.relations || [])
const recalls = computed(() => state.value?.recalls || [])
const agentActions = computed(() => state.value?.agentActions || [])
const hasAnyArtifacts = computed(() => claims.value.length > 0 || trials.value.length > 0 || relations.value.length > 0 || recalls.value.length > 0 || agentActions.value.length > 0)

const ARTIFACT_COLORS = {
  claim: '#117dff',
  trial: '#FF8A34',
  relation: '#1A936F',
  recall: '#2196F3',
  action: '#607D8B',
}

const rankedArtifacts = computed(() => {
  const items = []

  claims.value.forEach((c, i) => items.push({
    uid: `claim-${c.id || c.claim_id || i}`,
    kind: 'claims',
    raw: c,
    typeLabel: 'Claim',
    color: ARTIFACT_COLORS.claim,
    status: c.status || c.verdict || 'proposed',
    confidence: Number(c.confidence) || 0,
    confLabel: formatConfidence(c.confidence) || '-',
    text: truncate(c.claim_text || c.text || c.content || c.statement || '', 120),
    agent: c.agent_name || c.query_agent_name || null,
    round: c.round_num ?? null,
  }))

  trials.value.forEach((t, i) => items.push({
    uid: `trial-${t.id || t.trial_id || i}`,
    kind: 'trials',
    raw: t,
    typeLabel: 'Trial',
    color: ARTIFACT_COLORS.trial,
    status: t.verdict || t.status || t.outcome || 'pending',
    confidence: Number(t.confidence) || 0,
    confLabel: formatConfidence(t.confidence) || '-',
    text: truncate(t.response || t.summary || t.description || t.text || '', 120),
    agent: t.query_agent_name || t.agent_name || null,
    round: t.round_num ?? null,
  }))

  relations.value.forEach((r, i) => items.push({
    uid: `rel-${r.id || r.relation_id || i}`,
    kind: 'relations',
    raw: r,
    typeLabel: 'Relation',
    color: ARTIFACT_COLORS.relation,
    status: null,
    confidence: Number(r.confidence) || 0,
    confLabel: formatConfidence(r.confidence) || '-',
    text: `${r.from_name || r.from_id || 'Source'} → ${r.relation_type || r.relation || 'related_to'} → ${r.to_name || r.to_id || 'Target'}`,
    agent: null,
    round: null,
  }))

  recalls.value.forEach((rc, i) => items.push({
    uid: `recall-${rc.recall_id || rc.id || i}`,
    kind: 'recalls',
    raw: rc,
    typeLabel: 'Recall',
    color: ARTIFACT_COLORS.recall,
    status: null,
    confidence: 0,
    confLabel: '-',
    text: truncate(rc.query || '', 100),
    agent: rc.agent_name || `Agent ${rc.agent_id || '?'}`,
    round: rc.round_num ?? null,
  }))

  agentActions.value.forEach((a, i) => items.push({
    uid: `action-${a.action_id || a.id || i}`,
    kind: 'actions',
    raw: a,
    typeLabel: a.action_type || 'Action',
    color: ARTIFACT_COLORS.action,
    status: null,
    confidence: 0,
    confLabel: '-',
    text: truncate(typeof a.detail === 'string' ? a.detail : (a.action_summary || ''), 100),
    agent: a.agent_name || `Agent ${a.agent_id || '?'}`,
    round: a.round_num ?? null,
  }))

  // Sort by confidence descending, then claims first
  items.sort((a, b) => {
    if (b.confidence !== a.confidence) return b.confidence - a.confidence
    const kindOrder = { claims: 0, trials: 1, relations: 2, recalls: 3, actions: 4 }
    return (kindOrder[a.kind] || 5) - (kindOrder[b.kind] || 5)
  })

  return expanded.value ? items : items.slice(0, 20)
})

const statItems = computed(() => {
  const summary = state.value?.summary || {}
  return [
    { label: 'Claims', value: summary.claim_count ?? claims.value.length ?? 0 },
    { label: 'Trials', value: summary.trial_count ?? trials.value.length ?? 0 },
    { label: 'Relations', value: summary.relation_count ?? relations.value.length ?? 0 },
    { label: 'Recalls', value: summary.recall_count ?? recalls.value.length ?? 0 },
    { label: 'Actions', value: summary.agent_action_count ?? agentActions.value.length ?? 0 },
    { label: 'Sources', value: summary.source_count ?? state.value?.sources?.length ?? 0 }
  ]
})

const itemLimit = computed(() => expanded.value ? 999 : (props.compact ? 2 : 4))
const visibleClaims = computed(() => claims.value.slice(0, itemLimit.value))
const visibleTrials = computed(() => trials.value.slice(0, itemLimit.value))
const visibleRelations = computed(() => relations.value.slice(0, itemLimit.value))
const visibleRecalls = computed(() => recalls.value.slice(0, itemLimit.value))
const visibleAgentActions = computed(() => agentActions.value.slice(0, itemLimit.value))

const truncate = (text, max) => {
  if (!text) return ''
  return text.length > max ? text.substring(0, max) + '...' : text
}

const stringifyValue = (value) => {
  if (value === null || value === undefined || value === '') return 'None'
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'None'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const buildArtifactPreview = (kind, item) => {
  if (!item) return null

  const builders = {
    claims: {
      label: 'Claim',
      title: item.claim_text || item.text || item.content || item.statement || item.title || 'Claim',
      summary: item.summary || item.reasoning || '',
      fields: [
        ['Status', item.status || item.verdict || 'draft'],
        ['Confidence', formatConfidence(item.confidence)],
        ['Sources', item.source_refs?.length || item.source_ids?.length || '0'],
        ['Agent', item.agent_name || item.query_agent_name],
        ['Round', item.round_num]
      ]
    },
    trials: {
      label: 'Trial',
      title: item.verdict || item.status || item.outcome || 'Trial',
      summary: item.response || item.summary || item.description || item.text || '',
      fields: [
        ['Agent', item.query_agent_name || item.agent_name],
        ['Round', item.round_num],
        ['Sources', item.source_ids?.length || item.source_refs?.length || '0'],
        ['Claim ID', item.claim_id || item.id],
        ['Confidence', formatConfidence(item.confidence)]
      ]
    },
    relations: {
      label: 'Relation',
      title: `${item.from_name || item.source_name || item.from_id || 'Source'} → ${item.relation_type || item.relation || item.type || 'related_to'} → ${item.to_name || item.target_name || item.to_id || 'Target'}`,
      summary: item.fact || item.description || '',
      fields: [
        ['Type', item.relation_type || item.relation || item.type || 'related_to'],
        ['Confidence', formatConfidence(item.confidence)],
        ['From', item.from_name || item.source_name || item.from_id],
        ['To', item.to_name || item.target_name || item.to_id],
        ['ID', item.relation_id || item.id]
      ]
    },
    recalls: {
      label: 'Recall',
      title: item.query || item.summary || `Recall ${item.recall_id || item.id || ''}`,
      summary: item.answer || item.snippets?.join('\n') || '',
      fields: [
        ['Agent', item.agent_name || `Agent ${item.agent_id || '?'}`],
        ['Round', item.round_num],
        ['Sources', item.source_ids?.length || '0'],
        ['Snippets', item.snippets?.length || '0'],
        ['ID', item.recall_id || item.id]
      ]
    },
    actions: {
      label: 'Action',
      title: item.action_type || 'Action',
      summary: typeof item.detail === 'string' ? item.detail : stringifyValue(item.detail),
      fields: [
        ['Agent', item.agent_name || `Agent ${item.agent_id || '?'}`],
        ['Round', item.round_num],
        ['Platform', item.platform],
        ['Timestamp', item.timestamp],
        ['ID', item.action_id || item.id]
      ]
    }
  }

  const config = builders[kind]
  return {
    kind,
    raw: item,
    label: config.label,
    title: truncate(config.title || config.label, 180),
    summary: config.summary,
    fields: config.fields
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([key, value]) => ({ key, value: stringifyValue(value) }))
  }
}

const selectArtifact = (kind, item) => {
  selectedArtifact.value = buildArtifactPreview(kind, item)
  // Emit the artifact's UUID so the graph can highlight the corresponding node
  const uuid = item.uuid || item.id || item.claim_id || item.trial_id || item.recall_id || item.action_id || item.relation_id
  if (uuid) {
    emit('artifact-select', uuid)
  }
}

const isSelected = (kind, item) => {
  return selectedArtifact.value?.kind === kind && selectedArtifact.value?.raw === item
}

const availableTabs = computed(() => {
  const tabs = []
  tabs.push({ key: 'claims', label: 'Claims', count: claims.value.length, color: '#7B2D8E' })
  tabs.push({ key: 'trials', label: 'Trials', count: trials.value.length, color: '#FF8A34' })
  tabs.push({ key: 'relations', label: 'Relations', count: relations.value.length, color: '#1A936F' })
  tabs.push({ key: 'recalls', label: 'Recalls', count: recalls.value.length, color: '#2196F3' })
  tabs.push({ key: 'actions', label: 'Actions', count: agentActions.value.length, color: '#607D8B' })
  return tabs
})

const currentTabItems = computed(() => {
  const map = { claims: claims.value.length, trials: trials.value.length, relations: relations.value.length, recalls: recalls.value.length, actions: agentActions.value.length }
  return map[activeTab.value] || 0
})

watch(() => [props.simulationId, props.autoRefresh, props.refreshIntervalMs], () => {
  loadState()
  startAutoRefresh()
}, { immediate: true })

watch(activeTab, () => {
  selectedArtifact.value = null
})

onUnmounted(() => {
  stopAutoRefresh()
})

const getArtifactByUuid = (uuid) => {
  if (!state.value) return null
  for (const kind of ['claims', 'trials', 'recalls', 'agentActions']) {
    const list = state.value[kind] || []
    const item = list.find(it => (it.uuid === uuid || it.id === uuid || it.claim_id === uuid || it.trial_id === uuid || it.recall_id === uuid || it.action_id === uuid))
    if (item) return { kind, item }
  }
  return null
}

const selectByUuid = (uuid) => {
  const result = getArtifactByUuid(uuid)
  if (result) {
    const { kind, item } = result
    // Normalize kind matches with builders keys
    const kindMap = {
      claims: 'claims',
      trials: 'trials',
      recalls: 'recalls',
      agentActions: 'actions'
    }
    const finalKind = kindMap[kind] || kind
    activeTab.value = finalKind
    selectedArtifact.value = buildArtifactPreview(finalKind, item)
    return true
  }
  return false
}

defineExpose({
  loadState,
  selectByUuid
})
</script>

<style scoped>
/* ─── Base ────────────────────────────────────── */
.csi-artifact-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #fff;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 14px;
}

.csi-artifact-list.compact {
  padding: 0;
  gap: 0;
  border: none;
  border-radius: 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

/* ─── Header (when not compact) ───────────────── */
.artifact-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.header-copy { display: flex; flex-direction: column; gap: 2px; }
.artifact-title { font-size: 11px; font-weight: 700; letter-spacing: 0.4px; text-transform: uppercase; color: #E91E63; }
.artifact-desc { font-size: 11px; color: #888; }
.refresh-btn { flex-shrink: 0; width: 26px; height: 26px; border: 1px solid #e3e3e3; border-radius: 6px; background: #fff; color: #888; cursor: pointer; }
.refresh-btn:hover:not(:disabled) { color: #333; border-color: #ccc; }
.refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.spinning { display: inline-block; animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ─── States ──────────────────────────────────── */
.artifact-state { padding: 16px; font-size: 12px; color: #999; text-align: center; }
.artifact-state.error { color: #dc2626; }

/* ─── Stats row (inline) ─────────────────────── */
.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border-bottom: 1px solid #f0efeb;
}

.stat-inline {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 10px 4px;
  border-right: 1px solid #f0efeb;
}

.stat-inline:last-child { border-right: none; }

.si-value {
  font-size: 15px;
  font-weight: 700;
  color: #0a0a0a;
  font-family: 'JetBrains Mono', monospace;
  line-height: 1;
}

.si-label {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #a3a3a3;
  font-weight: 500;
}

/* ─── Ranked artifacts list ───────────────────── */
.ranked-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.ranked-card {
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #f0efeb;
  cursor: pointer;
  transition: border-color 0.15s;
}

.ranked-card:hover { border-color: #d4d0ca; }
.ranked-card.selected { border-color: #117dff; background: rgba(17, 125, 255, 0.03); }

.ranked-top {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
}

.ranked-type-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ranked-type {
  font-size: 10px;
  font-weight: 600;
  color: #525252;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.ranked-status {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
  background: #f0efeb;
  color: #666;
}

.ranked-status.s-proposed { background: #eff6ff; color: #117dff; }
.ranked-status.s-approved, .ranked-status.s-passed, .ranked-status.s-verified { background: #dcfce7; color: #16a34a; }
.ranked-status.s-rejected, .ranked-status.s-failed { background: #fef2f2; color: #dc2626; }
.ranked-status.s-pending { background: #fff7ed; color: #ea580c; }

.ranked-conf {
  margin-left: auto;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

.ranked-text {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: #404040;
}

.ranked-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.ranked-agent {
  font-size: 10px;
  font-weight: 500;
  color: #737373;
}

.ranked-round {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
  background: #f5f5f5;
  padding: 0 4px;
  border-radius: 2px;
}

/* ─── Artifact preview panel ─────────────────── */
.artifact-preview {
  border-top: 1px solid #e3e0db;
  padding: 10px;
  background: #faf9f4;
}

.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.preview-title-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.preview-kicker { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #a3a3a3; }
.preview-title { font-size: 12px; font-weight: 600; color: #0a0a0a; line-height: 1.3; }
.preview-close { border: none; background: none; color: #a3a3a3; font-size: 16px; cursor: pointer; padding: 0 2px; }
.preview-close:hover { color: #333; }

.preview-summary {
  font-size: 11px;
  line-height: 1.5;
  color: #525252;
  margin-bottom: 8px;
  max-height: 80px;
  overflow-y: auto;
}

.preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.preview-field {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 6px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #f0efeb;
}

.preview-field-label { font-size: 9px; color: #a3a3a3; text-transform: uppercase; letter-spacing: 0.04em; }
.preview-field-value { font-size: 11px; color: #0a0a0a; font-family: 'JetBrains Mono', monospace; word-break: break-all; }

/* ─── Section tabs ────────────────────────────── */
.section-tabs {
  display: flex;
  gap: 1px;
  padding: 6px 10px;
  overflow-x: auto;
  border-bottom: 1px solid #f0efeb;
}

.section-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  padding: 4px 8px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 11px;
  color: #999;
  white-space: nowrap;
  transition: all 0.15s;
}

.section-tab:hover { background: #f5f5f5; color: #555; }

.section-tab.active {
  background: #f0efeb;
  color: #0a0a0a;
  font-weight: 600;
}

.tab-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tab-name { font-size: 11px; }

.tab-count {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #bbb;
}

.section-tab.active .tab-count { color: #666; }

/* ─── Section content ─────────────────────────── */
.section-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
}

/* ─── Artifact card ───────────────────────────── */
.art-card {
  padding: 8px 10px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #f0efeb;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.art-card:hover { border-color: #ddd; }

.art-card.selected {
  border-color: rgba(123, 45, 142, 0.28);
  background: #fcf8ff;
  box-shadow: inset 0 0 0 1px rgba(123, 45, 142, 0.08);
}

.art-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.art-badge {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f0efeb;
  color: #666;
}

.art-badge.s-proposed, .art-badge.s-draft { background: #f3e8ff; color: #7B2D8E; }
.art-badge.s-approved, .art-badge.s-passed, .art-badge.s-verified { background: #dcfce7; color: #16a34a; }
.art-badge.s-rejected, .art-badge.s-failed, .art-badge.s-contradicted { background: #fef2f2; color: #dc2626; }
.art-badge.s-pending { background: #fff7ed; color: #ea580c; }

.art-conf {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #999;
  margin-left: auto;
}

.art-agent {
  font-size: 10px;
  font-weight: 600;
  color: #525252;
}

.art-text {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: #404040;
}

.art-foot {
  display: flex;
  gap: 4px;
  margin-top: 5px;
}

.af-pill {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #999;
  background: #f5f5f5;
  padding: 1px 6px;
  border-radius: 3px;
}

/* ─── Relation card ───────────────────────────── */
.rel-card { padding: 6px 10px; }

.rel-flow {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 11px;
}

.rel-entity {
  font-weight: 600;
  color: #0a0a0a;
}

.rel-arrow {
  color: #ccc;
  font-size: 10px;
}

.rel-type {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #1A936F;
  background: #ecfdf5;
  padding: 1px 5px;
  border-radius: 3px;
}

/* ─── Preview panel ──────────────────────────── */
.artifact-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 2px 10px 10px;
  padding: 12px;
  border: 1px solid #ede7f3;
  border-radius: 10px;
  background: linear-gradient(180deg, #fcfbff 0%, #f8f6fb 100%);
}

.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.preview-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.preview-kicker {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7B2D8E;
}

.preview-title {
  font-size: 12px;
  font-weight: 700;
  color: #18181b;
  line-height: 1.45;
}

.preview-close {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 999px;
  background: #fff;
  color: #777;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
}

.preview-close:hover {
  color: #222;
  background: #f3f3f3;
}

.preview-summary {
  white-space: pre-wrap;
  font-size: 11px;
  line-height: 1.55;
  color: #3f3f46;
}

.preview-grid {
  display: grid;
  gap: 8px;
}

.preview-field {
  display: grid;
  gap: 2px;
}

.preview-field-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #8b8b95;
}

.preview-field-value {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 11px;
  line-height: 1.45;
  color: #27272a;
}

/* ─── Expand button ───────────────────────────── */
.expand-btn {
  display: block;
  width: 100%;
  padding: 6px;
  border: none;
  background: none;
  font-size: 11px;
  font-weight: 600;
  color: #7B2D8E;
  cursor: pointer;
  text-align: center;
  border-top: 1px solid #f0efeb;
}

.expand-btn:hover { background: #faf5fd; }
</style>
