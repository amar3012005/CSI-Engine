<template>
  <Transition name="sidecar">
    <div
      v-if="node"
      class="graph-node-detail"
      role="complementary"
      aria-label="Node Detail"
    >
      <!-- Sticky header -->
      <div class="detail-header">
        <span class="detail-header-label">Node Detail</span>
        <button
          class="detail-close-btn"
          type="button"
          :aria-label="`Close detail panel for ${node.name}`"
          @click="$emit('close')"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="1" y1="1" x2="13" y2="13" />
            <line x1="13" y1="1" x2="1" y2="13" />
          </svg>
        </button>
      </div>

      <!-- Scrollable body -->
      <div class="detail-body">

        <!-- Type badge + Name -->
        <div class="detail-identity">
          <div class="detail-type-row">
            <span
              class="type-dot"
              :style="{ backgroundColor: typeColor }"
              aria-hidden="true"
            />
            <span class="type-label">{{ node.type || 'node' }}</span>
            <span v-if="node.isCsi" class="csi-badge">CSI</span>
            <span v-if="node.isAgent" class="agent-badge">Agent</span>
          </div>
          <h3 class="detail-name">{{ node.name || node.rawData?.name || 'Unnamed Node' }}</h3>
        </div>

        <!-- Content card (labels as content summary) -->
        <div class="detail-content-card">
          <p v-if="contentLabels.length" class="detail-content-text">
            {{ contentLabels.join(' · ') }}
          </p>
          <p v-else class="detail-content-text detail-content-muted">No description available.</p>
        </div>

        <!-- Properties grid -->
        <div v-if="attributeEntries.length" class="detail-section">
          <p class="section-heading">Properties</p>
          <div class="props-grid">
            <div
              v-for="[key, val] in attributeEntries"
              :key="key"
              class="prop-cell"
            >
              <p class="prop-key">{{ key }}</p>
              <p class="prop-val">{{ val ?? '—' }}</p>
            </div>
          </div>
        </div>

        <!-- Relationships -->
        <div v-if="outboundEdges.length || inboundEdges.length" class="detail-section">
          <p class="section-heading">Relationships</p>
          <div class="edge-list">

            <!-- Outbound -->
            <template v-if="outboundEdges.length">
              <p class="edge-direction-label">Outbound</p>
              <button
                v-for="(edge, i) in outboundEdges"
                :key="`out-${i}`"
                class="edge-btn"
                type="button"
                @click="handleNavigate(edge.target_node_uuid)"
              >
                <span class="edge-icon edge-icon-out" aria-hidden="true">
                  <!-- Branch out icon -->
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M2 8V3m0 0 3-3m-3 3 3 3" />
                    <path d="M8 7V5a2 2 0 0 0-2-2H2" />
                  </svg>
                </span>
                <span class="edge-relation">{{ edge.name || edge.fact_type || 'relates to' }}</span>
                <span class="edge-arrow">→</span>
                <span class="edge-target">{{ resolveNodeName(edge.target_node_uuid) }}</span>
              </button>
            </template>

            <!-- Inbound -->
            <template v-if="inboundEdges.length">
              <p class="edge-direction-label">Inbound</p>
              <button
                v-for="(edge, j) in inboundEdges"
                :key="`in-${j}`"
                class="edge-btn"
                type="button"
                @click="handleNavigate(edge.source_node_uuid)"
              >
                <span class="edge-icon edge-icon-in" aria-hidden="true">
                  <!-- Branch in icon (mirrored) -->
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="transform: scaleX(-1);">
                    <path d="M2 8V3m0 0 3-3m-3 3 3 3" />
                    <path d="M8 7V5a2 2 0 0 0-2-2H2" />
                  </svg>
                </span>
                <span class="edge-relation edge-relation-in">← {{ edge.name || edge.fact_type || 'relates to' }}</span>
                <span class="edge-target">{{ resolveNodeName(edge.source_node_uuid) }}</span>
              </button>
            </template>

          </div>
        </div>

        <!-- Meta -->
        <div class="detail-meta">
          <p v-if="node.rawData?.uuid || node.id">
            <span class="meta-key">ID</span>
            <span class="meta-val">{{ node.rawData?.uuid || node.id }}</span>
          </p>
          <p v-if="node.rawData?.created_at">
            <span class="meta-key">Created</span>
            <span class="meta-val">{{ formatDate(node.rawData.created_at) }}</span>
          </p>
        </div>

      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'

/* ── Props ─────────────────────────────────────────────────────────── */
const props = defineProps({
  /** Selected node — null hides the panel */
  node: {
    type: Object,
    default: null,
  },
  /** All edges in the graph */
  edges: {
    type: Array,
    default: () => [],
  },
  /** All nodes — used to resolve UUIDs to display names */
  nodes: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['close', 'navigate'])

/* ── CSI / type color map ──────────────────────────────────────────── */
const TYPE_COLORS = {
  Claim:       '#7B2D8E',
  Trial:       '#FF8A34',
  Recall:      '#2196F3',
  Source:      '#1A936F',
  AgentAction: '#607D8B',
  Agent:       '#9C27B0',
  // generic fallbacks
  fact:        '#117dff',
  preference:  '#d97706',
  decision:    '#dc2626',
  lesson:      '#16a34a',
  goal:        '#8b5cf6',
  event:       '#0891b2',
  relationship:'#db2777',
  default:     '#a3a3a3',
}

/* ── Computed ──────────────────────────────────────────────────────── */

/** Resolve the display color for the current node type */
const typeColor = computed(() => {
  const t = props.node?.type || ''
  return TYPE_COLORS[t] || TYPE_COLORS.default
})

/** Flatten rawData.labels into readable strings */
const contentLabels = computed(() => {
  const labels = props.node?.rawData?.labels
  if (!labels) return []
  if (Array.isArray(labels)) return labels.filter(Boolean)
  if (typeof labels === 'string') return [labels]
  return []
})

/** Key-value pairs from rawData.attributes */
const attributeEntries = computed(() => {
  const attrs = props.node?.rawData?.attributes
  if (!attrs || typeof attrs !== 'object') return []
  return Object.entries(attrs).filter(([, v]) => v !== undefined && v !== null && v !== '')
})

/** Node UUID lookup map for O(1) name resolution */
const nodeMap = computed(() => {
  const map = {}
  props.nodes.forEach((n) => {
    const uuid = n.rawData?.uuid || n.id
    if (uuid) map[uuid] = n
  })
  return map
})

/** Edges where this node is the source */
const outboundEdges = computed(() => {
  const uuid = props.node?.rawData?.uuid || props.node?.id
  if (!uuid) return []
  return props.edges.filter((e) => e.source_node_uuid === uuid)
})

/** Edges where this node is the target */
const inboundEdges = computed(() => {
  const uuid = props.node?.rawData?.uuid || props.node?.id
  if (!uuid) return []
  return props.edges.filter((e) => e.target_node_uuid === uuid)
})

/* ── Methods ───────────────────────────────────────────────────────── */

/**
 * Resolve a node UUID to a human-readable name.
 * Falls back to a truncated UUID if not found.
 */
function resolveNodeName(uuid) {
  if (!uuid) return '—'
  const n = nodeMap.value[uuid]
  if (n) return n.name || n.rawData?.name || uuid.slice(0, 8) + '…'
  return uuid.slice(0, 12) + '…'
}

/** Format ISO date string to locale-aware short string */
function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** Emit navigate with the other node's UUID */
function handleNavigate(uuid) {
  if (uuid) emit('navigate', uuid)
}
</script>

<style scoped>
/* ── Panel shell ───────────────────────────────────────────────────── */
.graph-node-detail {
  position: absolute;
  top: 0;
  right: 0;
  width: 340px;
  height: 100%;
  background: #ffffff;
  border-left: 1px solid #e3e0db;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.06);
  z-index: 20;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ────────────────────────────────────────────────────────── */
.detail-header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #ffffff;
  border-bottom: 1px solid #e3e0db;
  z-index: 1;
  flex-shrink: 0;
}

.detail-header-label {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #a3a3a3;
}

.detail-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #a3a3a3;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.detail-close-btn:hover {
  background: #f3f1ec;
  color: #0a0a0a;
}

/* ── Body ──────────────────────────────────────────────────────────── */
.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Identity block ────────────────────────────────────────────────── */
.detail-identity {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-type-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.type-label {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #a3a3a3;
}

.csi-badge,
.agent-badge {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.csi-badge {
  background: rgba(17, 125, 255, 0.1);
  color: #117dff;
  border: 1px solid rgba(17, 125, 255, 0.2);
}

.agent-badge {
  background: rgba(156, 39, 176, 0.1);
  color: #9c27b0;
  border: 1px solid rgba(156, 39, 176, 0.2);
}

.detail-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #0a0a0a;
  line-height: 1.4;
}

/* ── Content card ──────────────────────────────────────────────────── */
.detail-content-card {
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  padding: 12px;
}

.detail-content-text {
  margin: 0;
  font-size: 12px;
  color: #525252;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-content-muted {
  color: #a3a3a3;
  font-style: italic;
}

/* ── Generic section ───────────────────────────────────────────────── */
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-heading {
  margin: 0;
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #a3a3a3;
}

/* ── Properties grid ───────────────────────────────────────────────── */
.props-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.prop-cell {
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  padding: 8px;
  min-width: 0;
}

.prop-key {
  margin: 0 0 2px;
  font-size: 9px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #a3a3a3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.prop-val {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: #0a0a0a;
  word-break: break-all;
}

/* ── Edges ─────────────────────────────────────────────────────────── */
.edge-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.edge-direction-label {
  margin: 4px 0 2px;
  font-size: 9px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #c5c0bb;
}

.edge-direction-label:first-child {
  margin-top: 0;
}

.edge-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  background: #faf9f4;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
  min-width: 0;
}

.edge-btn:hover {
  border-color: rgba(17, 125, 255, 0.3);
  background: #f5f3ee;
}

.edge-btn:hover .edge-target {
  color: #117dff;
}

.edge-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.edge-icon-out {
  color: #117dff;
}

.edge-icon-in {
  color: #a3a3a3;
}

.edge-relation {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  color: #117dff;
  white-space: nowrap;
  flex-shrink: 0;
}

.edge-relation-in {
  color: #a3a3a3;
}

.edge-arrow {
  font-size: 10px;
  color: #c5c0bb;
  flex-shrink: 0;
}

.edge-target {
  font-size: 11px;
  color: #525252;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  transition: color 0.15s ease;
}

/* ── Meta ──────────────────────────────────────────────────────────── */
.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 4px;
  border-top: 1px solid #f0ede8;
}

.detail-meta p {
  display: flex;
  gap: 6px;
  margin: 0;
}

.meta-key {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  color: #c5c0bb;
  flex-shrink: 0;
  min-width: 48px;
}

.meta-val {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  color: #a3a3a3;
  word-break: break-all;
}

/* ── Slide-in transition ───────────────────────────────────────────── */
.sidecar-enter-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.sidecar-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.sidecar-enter-from,
.sidecar-leave-to {
  transform: translateX(340px);
  opacity: 0;
}

/* ── Scrollbar ─────────────────────────────────────────────────────── */
.detail-body::-webkit-scrollbar {
  width: 4px;
}

.detail-body::-webkit-scrollbar-track {
  background: transparent;
}

.detail-body::-webkit-scrollbar-thumb {
  background: #e3e0db;
  border-radius: 2px;
}

.detail-body::-webkit-scrollbar-thumb:hover {
  background: #c5c0bb;
}
</style>
