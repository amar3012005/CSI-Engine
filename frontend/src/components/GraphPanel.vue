<template>
  <div class="graph-panel">
    <div class="graph-container" ref="graphContainer">
      <!-- Canvas graph visualization (always render canvas for consistent background) -->
      <div class="graph-view">
        <canvas ref="graphCanvas" class="graph-canvas"></canvas>

        <!-- Building/simulating hint -->
        <div v-if="currentPhase === 1 || isSimulating" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
              <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
            </svg>
          </div>
          {{ isSimulating ? 'GraphRAG memory updating in real-time' : 'Updating in real-time...' }}
        </div>

        <!-- Simulation finished hint -->
        <div v-if="showSimulationFinishedHint" class="graph-building-hint finished-hint">
          <div class="hint-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <span class="hint-text">Some content still processing, refresh graph manually later</span>
          <button class="hint-close-btn" @click="dismissFinishedHint" title="Dismiss hint">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <!-- Node/edge detail panel -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <span class="detail-title">{{ selectedItem.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge" :style="{ background: selectedItem.color, color: '#fff' }">
              {{ selectedItem.entityType }}
            </span>
            <button class="detail-close" @click="closeDetailPanel">&times;</button>
          </div>

          <!-- Node details -->
          <div v-if="selectedItem.type === 'node'" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">Name:</span>
              <span class="detail-value">{{ selectedItem.data.name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">UUID:</span>
              <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
            </div>
            <div class="detail-row" v-if="selectedItem.data.created_at">
              <span class="detail-label">Created:</span>
              <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
            </div>

            <!-- Properties -->
            <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
              <div class="section-title">Properties:</div>
              <div class="properties-list">
                <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                  <span class="property-key">{{ key }}:</span>
                  <span class="property-value">{{ value || 'None' }}</span>
                </div>
              </div>
            </div>

            <!-- Summary -->
            <div class="detail-section" v-if="selectedItem.data.summary">
              <div class="section-title">Summary:</div>
              <div class="summary-text">{{ selectedItem.data.summary }}</div>
            </div>

            <!-- Agent Traces -->
            <div class="detail-section agent-traces" v-if="selectedItem.entityType === 'Agent' && getAgentTraces(selectedItem.data.uuid).length > 0">
              <div class="section-title">Agent Traces:</div>
              <div class="trace-list">
                <div v-for="trace in getAgentTraces(selectedItem.data.uuid)" :key="trace.id" class="trace-item">
                  <span class="trace-type" :style="{ backgroundColor: trace.color }">{{ trace.type }}</span>
                  <div class="trace-details">
                    <div class="trace-target">{{ trace.targetName }} <span class="trace-target-type">({{ trace.targetType }})</span></div>
                    <div class="trace-desc">{{ trace.desc }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Labels -->
            <div class="detail-section" v-if="selectedItem.data.labels && selectedItem.data.labels.length > 0">
              <div class="section-title">Labels:</div>
              <div class="labels-list">
                <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">
                  {{ label }}
                </span>
              </div>
            </div>
          </div>

          <!-- Edge details -->
          <div v-else class="detail-content">
            <!-- Self-loop group details -->
            <template v-if="selectedItem.data.isSelfLoopGroup">
              <div class="edge-relation-header self-loop-header">
                {{ selectedItem.data.source_name }} - Self Relations
                <span class="self-loop-count">{{ selectedItem.data.selfLoopCount }} items</span>
              </div>

              <div class="self-loop-list">
                <div
                  v-for="(loop, idx) in selectedItem.data.selfLoopEdges"
                  :key="loop.uuid || idx"
                  class="self-loop-item"
                  :class="{ expanded: expandedSelfLoops.has(loop.uuid || idx) }"
                >
                  <div
                    class="self-loop-item-header"
                    @click="toggleSelfLoop(loop.uuid || idx)"
                  >
                    <span class="self-loop-index">#{{ idx + 1 }}</span>
                    <span class="self-loop-name">{{ loop.name || loop.fact_type || 'RELATED' }}</span>
                    <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
                  </div>

                  <div class="self-loop-item-content" v-show="expandedSelfLoops.has(loop.uuid || idx)">
                    <div class="detail-row" v-if="loop.uuid">
                      <span class="detail-label">UUID:</span>
                      <span class="detail-value uuid-text">{{ loop.uuid }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact">
                      <span class="detail-label">Fact:</span>
                      <span class="detail-value fact-text">{{ loop.fact }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact_type">
                      <span class="detail-label">Type:</span>
                      <span class="detail-value">{{ loop.fact_type }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.created_at">
                      <span class="detail-label">Created:</span>
                      <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
                    </div>
                    <div v-if="loop.episodes && loop.episodes.length > 0" class="self-loop-episodes">
                      <span class="detail-label">Episodes:</span>
                      <div class="episodes-list compact">
                        <span v-for="ep in loop.episodes" :key="ep" class="episode-tag small">{{ ep }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- Normal edge details -->
            <template v-else>
              <div class="edge-relation-header">
                {{ selectedItem.data.source_name }} &rarr; {{ selectedItem.data.name || 'RELATED_TO' }} &rarr; {{ selectedItem.data.target_name }}
              </div>

              <div class="detail-row">
                <span class="detail-label">UUID:</span>
                <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Label:</span>
                <span class="detail-value">{{ selectedItem.data.name || 'RELATED_TO' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ selectedItem.data.fact_type || 'Unknown' }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.fact">
                <span class="detail-label">Fact:</span>
                <span class="detail-value fact-text">{{ selectedItem.data.fact }}</span>
              </div>

              <!-- Episodes -->
              <div class="detail-section" v-if="selectedItem.data.episodes && selectedItem.data.episodes.length > 0">
                <div class="section-title">Episodes:</div>
                <div class="episodes-list">
                  <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">
                    {{ ep }}
                  </span>
                </div>
              </div>

              <div class="detail-row" v-if="selectedItem.data.created_at">
                <span class="detail-label">Created:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.valid_at">
                <span class="detail-label">Valid From:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.valid_at) }}</span>
              </div>
            </template>
          </div>
        </div>

        <!-- Hover tooltip -->
        <div
          v-if="hoveredNode && !selectedItem"
          class="graph-tooltip"
          :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
        >
          <span class="tooltip-icon">{{ ENTITY_FILTER_MAP[hoveredNode.type]?.icon || '●' }}</span>
          <span class="tooltip-name">{{ hoveredNode.name }}</span>
        </div>

        <!-- Graph layer toggles (top right) -->
        <div class="graph-toggles" :style="{ right: rightOffset }">
          <div class="toggle-row agent-toggle">
            <label class="toggle-switch">
              <input type="checkbox" v-model="highlightAgents" />
              <span class="slider agent-slider"></span>
            </label>
            <span class="toggle-label" style="color: #9C27B0; font-weight: 600;">Highlight Agents</span>
          </div>
          <div class="toggle-row">
            <label class="toggle-switch">
              <input type="checkbox" v-model="showEdgeLabels" />
              <span class="slider"></span>
            </label>
            <span class="toggle-label">Edge Labels</span>
          </div>
          <div v-if="simulationId" class="toggle-row csi-toggle">
            <label class="toggle-switch">
              <input type="checkbox" v-model="showCsiLayer" />
              <span class="slider csi-slider"></span>
            </label>
            <span class="toggle-label">CSI Artifacts</span>
            <span v-if="csiNodeCount > 0" class="csi-count-badge">{{ csiNodeCount }}</span>
          </div>
        </div>

        <!-- Zoom controls -->
        <div class="zoom-controls">
          <button class="zoom-btn" @click="zoomIn" title="Zoom in">+</button>
          <button class="zoom-btn" @click="zoomOut" title="Zoom out">&minus;</button>
          <button class="zoom-btn zoom-fit" @click="zoomFit" title="Fit to view">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Loading overlay -->
      <div v-if="loading && !displayGraphData" class="graph-state">
        <div class="loading-spinner"></div>
        <p>Loading graph data...</p>
      </div>

      <!-- Empty overlay -->
      <div v-else-if="!displayGraphData && !loading" class="graph-state">
        <div class="empty-icon">&#x2756;</div>
        <p class="empty-text">Waiting for entities...</p>
      </div>
    </div>

    <!-- Bottom left legend -->
    <div v-if="displayGraphData && entityTypes.length" class="graph-legend">
      <span class="legend-title">Entity Types</span>
      <div class="legend-items">
        <template v-for="type in entityTypes" :key="type.name">
          <div v-if="type.isCsi && entityTypes.filter(t => !t.isCsi).length > 0 && entityTypes.indexOf(type) === entityTypes.findIndex(t => t.isCsi)" class="legend-separator"></div>
          <div class="legend-item" :class="{ 'csi-legend-item': type.isCsi }">
            <span class="legend-dot" :class="{ 'csi-dot': type.isCsi }" :style="{ background: type.color }"></span>
            <span class="legend-label">{{ type.name }}</span>
            <span class="legend-count">{{ type.count }}</span>
          </div>
        </template>
      </div>
    </div>

    <div v-if="simulationId" class="csi-artifact-rail" :class="{ 'collapsed': isCsiPanelCollapsed }">
      <div class="csi-rail-header" @click="isCsiPanelCollapsed = !isCsiPanelCollapsed">
        <span class="csi-rail-title">CSI Artifacts Preview</span>
        <button class="csi-refresh-btn" @click.stop="$emit('refresh')" :disabled="loading" title="Refresh graph">
          <span class="icon-refresh" :class="{ 'spinning': loading }">&#x21BB;</span>
        </button>
        <button class="csi-collapse-btn">
          <svg v-if="isCsiPanelCollapsed" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
          <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
        </button>
      </div>
      <CsiArtifactList
        ref="csiArtifactListRef"
        v-show="!isCsiPanelCollapsed"
        :simulationId="simulationId"
        title=""
        description=""
        :showRefresh="false"
        :compact="true"
        :autoRefresh="csiAutoRefresh"
        :refreshIntervalMs="csiRefreshIntervalMs"
        @artifact-select="handleArtifactSelect"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed, shallowRef } from 'vue'
import * as d3 from 'd3'
import CsiArtifactList from './CsiArtifactList.vue'
import { getSimulationCsiGraph } from '../api/csi'
import { getGoldenTrail } from '../api/report'

/* ─── Props ─────────────────────────────────────────────────────── */
const props = defineProps({
  graphData: Object,
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean,
  simulationId: String,
  csiAutoRefresh: {
    type: Boolean,
    default: false
  },
  csiRefreshIntervalMs: {
    type: Number,
    default: 5000
  },
  reportId: {
    type: String,
    default: null
  },
  rightInset: {
    type: Number,
    default: 0
  },
  leftInset: {
    type: Number,
    default: 0
  },
  agentProfiles: {
    type: Array,
    default: () => []
  }
})

const rightOffset = computed(() => `${props.rightInset + 20}px`)

const emit = defineEmits(['refresh', 'toggle-maximize'])

/* ─── Constants ─────────────────────────────────────────────────── */
const CSI_COLORS = {
  'Claim': '#7B2D8E',
  'Trial': '#FF8A34',
  'Recall': '#2196F3',
  'AgentAction': '#607D8B',
  'Source': '#1A936F',
}

const CSI_TYPE_COLORS = {
  'Agent': '#9C27B0',
  'Source': '#1A936F',
  'Claim': '#117dff',
  'Trial': '#FF8A34',
  'Recall': '#2196F3',
  'AgentAction': '#607D8B',
}

// Shape per entity type
const CSI_TYPE_SHAPE = {
  'Agent': 'hexagon',
  'AgentAction': 'square',
  'Claim': 'circle',
  'Trial': 'diamond',
  'Source': 'circle',
  'Recall': 'circle',
}

const CSI_TYPE_SIZE = {
  'Agent': 1.6,
  'Source': 0.85,
  'Claim': 1.1,
  'Trial': 1.0,
  'Recall': 0.58,
  'AgentAction': 0.65,
}

const EDGE_COLORS = {
  // Da-vinci canonical
  'Updates': '#117dff',
  'Extends': '#16a34a',
  'Derives': '#8b5cf6',
  // MiroFish CSI edge types
  'PROPOSED_CLAIM': '#117dff',
  'CHALLENGED_CLAIM': '#dc2626',
  'VERIFIED_CLAIM': '#16a34a',
  'SEARCHED_WEB': '#0891b2',
  'READ_SOURCE': '#0891b2',
  'INTERACTS_WITH': '#a3a3a3',
  'HAS_ROLE': '#9C27B0',
  'PRODUCED': '#FF8A34',
  'CITED': '#1A936F',
  'SUPPORTS': '#16a34a',
  'CONTRADICTS': '#dc2626',
  'RELATED': '#a3a3a3',
  'SELF_LOOP': '#78909C',
}

// Fallback: infer color from edge type name
function getEdgeColor(relType) {
  if (EDGE_COLORS[relType]) return EDGE_COLORS[relType]
  const lower = relType.toLowerCase()
  if (lower.includes('claim') || lower.includes('propos')) return '#117dff'
  if (lower.includes('challeng') || lower.includes('contra')) return '#dc2626'
  if (lower.includes('verif') || lower.includes('support') || lower.includes('extend')) return '#16a34a'
  if (lower.includes('deriv') || lower.includes('infer')) return '#8b5cf6'
  if (lower.includes('search') || lower.includes('read') || lower.includes('source')) return '#0891b2'
  if (lower.includes('role') || lower.includes('agent')) return '#9C27B0'
  if (lower.includes('produc') || lower.includes('action')) return '#FF8A34'
  return '#c4c0ba'
}

const ENTITY_FILTERS = [
  { key: 'all', label: 'All', icon: null, color: null },
  { key: 'Claim', label: 'Claims', icon: '\u25C6', color: '#7B2D8E' },
  { key: 'Agent', label: 'Agents', icon: '\u2B21', color: '#9C27B0' },
  { key: 'Source', label: 'Sources', icon: '\u25A2', color: '#1A936F' },
  { key: 'Trial', label: 'Trials', icon: '\u2B50', color: '#FF8A34' },
  { key: 'Recall', label: 'Recalls', icon: '\u25CF', color: '#2196F3' },
  { key: 'AgentAction', label: 'Actions', icon: '\u25CB', color: '#607D8B' },
]

const ENTITY_FILTER_MAP = {}
ENTITY_FILTERS.forEach(f => { ENTITY_FILTER_MAP[f.key] = f })

/* ─── Refs ──────────────────────────────────────────────────────── */
const graphContainer = ref(null)
const graphCanvas = ref(null)
const selectedItem = ref(null)
const csiArtifactListRef = ref(null)
const isCsiPanelCollapsed = ref(false)
const showCsiLayer = ref(true)
const showEdgeLabels = ref(true)
const highlightAgents = ref(false)
const expandedSelfLoops = ref(new Set())
const showSimulationFinishedHint = ref(false)
const wasSimulating = ref(false)
const csiGraphData = ref(null)
const goldenTrailIds = ref(new Set())
const activeFilter = ref('all')
const searchInput = ref('')
const searchQuery = ref('')
const highlightNodes = ref(new Set())
const hoveredNode = ref(null)
const tooltipPos = ref({ x: 0, y: 0 })

let csiRefreshTimer = null
let currentSimulation = null
let canvasNodes = []
let canvasEdges = []
let canvasTransform = d3.zoomIdentity
let zoomBehavior = null
let animFrameId = null

/* ─── CSI data helpers ──────────────────────────────────────────── */
const _isCsiNode = (node) => node?.labels?.includes('CSI')
const _isCsiEdge = (edge, csiNodeIds) => csiNodeIds.has(edge.source_node_uuid) || csiNodeIds.has(edge.target_node_uuid)

const mergeGraphData = (baseGraph, csiGraph, includeCsi) => {
  if (!baseGraph && !csiGraph) return null
  const baseNodes = baseGraph?.nodes || []
  const baseEdges = baseGraph?.edges || []
  const extraNodes = csiGraph?.nodes || []
  const extraEdges = csiGraph?.edges || []
  const nodesById = new Map()
  const edgesById = new Map()

  for (const node of [...baseNodes, ...extraNodes]) {
    if (node?.uuid) nodesById.set(node.uuid, node)
  }
  for (const edge of [...baseEdges, ...extraEdges]) {
    if (edge?.uuid) edgesById.set(edge.uuid, edge)
  }

  let finalNodes = Array.from(nodesById.values())
  let finalEdges = Array.from(edgesById.values())

  if (!includeCsi) {
    const csiNodeIds = new Set(finalNodes.filter(_isCsiNode).map(n => n.uuid))
    finalNodes = finalNodes.filter(n => !_isCsiNode(n))
    finalEdges = finalEdges.filter(e => !_isCsiEdge(e, csiNodeIds))
  }

  return {
    ...(baseGraph || {}),
    nodes: finalNodes,
    edges: finalEdges,
    node_count: finalNodes.length,
    edge_count: finalEdges.length
  }
}

const displayGraphData = computed(() => {
  const merged = mergeGraphData(props.graphData, csiGraphData.value, showCsiLayer.value)
  if (props.agentProfiles.length === 0) return merged

  const existing = merged || { nodes: [], edges: [], node_count: 0, edge_count: 0 }
  const existingIds = new Set((existing.nodes || []).map(n => n.uuid))
  const agentNodes = props.agentProfiles
    .filter(p => !existingIds.has(`agent_${p.id}`))
    .map(p => ({
      uuid: `agent_${p.id}`,
      name: p.name || `Agent ${p.id}`,
      labels: ['Agent'],
      attributes: {
        researchRole: p.researchRole || '',
        persona: p.persona || '',
        qualificationScore: p.qualificationScore || 0,
        skills: (p.skills || []).join(', '),
      },
      summary: p.bio || p.responsibility || '',
    }))

  if (agentNodes.length === 0) return existing
  return {
    ...existing,
    nodes: [...(existing.nodes || []), ...agentNodes],
    node_count: (existing.node_count || 0) + agentNodes.length,
  }
})

const csiNodeCount = computed(() => {
  if (!csiGraphData.value?.nodes) return 0
  return csiGraphData.value.nodes.filter(_isCsiNode).length
})

/* ─── Entity types for legend ───────────────────────────────────── */
const entityTypes = computed(() => {
  if (!displayGraphData.value?.nodes) return []
  const typeMap = {}
  const colors = ['#FF6B35', '#004E89', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#27ae60', '#f39c12']
  let colorIdx = 0

  displayGraphData.value.nodes.forEach(node => {
    const isCsi = node.labels?.includes('CSI')
    const isAgent = node.labels?.includes('Agent') || Boolean(node.attributes?.agent_id)

    let type = isCsi
      ? (node.labels?.find(l => l !== 'Entity' && l !== 'CSI' && l !== 'Node') || 'CSI')
      : (node.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity')

    if (isAgent && !isCsi) {
      type = 'Agent'
    }

    if (!typeMap[type]) {
      const csiColor = isCsi ? CSI_COLORS[type] : null
      const defaultAgentColors = ['#9C27B0', '#E91E63', '#673AB7', '#3F51B5']
      typeMap[type] = {
        name: isCsi ? `CSI: ${type}` : type,
        count: 0,
        color: type === 'Agent' ? defaultAgentColors[0] : (csiColor || colors[colorIdx++ % colors.length]),
        isCsi,
        isAgent
      }
    }
    typeMap[type].count++
  })
  return Object.values(typeMap).sort((a, b) => (a.isCsi ? 1 : 0) - (b.isCsi ? 1 : 0))
})

/* ─── Search ────────────────────────────────────────────────────── */
let searchDebounceTimer = null

watch(searchInput, (val) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    searchQuery.value = val
  }, 300)
})

watch(searchQuery, (q) => {
  if (!q || !q.trim()) {
    highlightNodes.value = new Set()
    return
  }
  const lq = q.toLowerCase()
  const matches = new Set()
  canvasNodes.forEach(n => {
    if (
      n.name?.toLowerCase().includes(lq) ||
      n.type?.toLowerCase().includes(lq) ||
      n.rawData?.summary?.toLowerCase().includes(lq)
    ) {
      matches.add(n.id)
    }
  })
  highlightNodes.value = matches

  // Auto-center on first match
  if (matches.size > 0 && graphCanvas.value && zoomBehavior) {
    const firstId = [...matches][0]
    const node = canvasNodes.find(n => n.id === firstId)
    if (node && node.x != null && node.y != null) {
      const canvas = graphCanvas.value
      const cx = canvas.width / (2 * (window.devicePixelRatio || 1))
      const cy = canvas.height / (2 * (window.devicePixelRatio || 1))
      const targetScale = 3
      const tx = cx - node.x * targetScale
      const ty = cy - node.y * targetScale
      const newTransform = d3.zoomIdentity.translate(tx, ty).scale(targetScale)
      d3.select(canvas).transition().duration(600).call(zoomBehavior.transform, newTransform)
    }
  }
})

const searchPlaceholder = computed(() => {
  const count = highlightNodes.value.size
  return count > 0 ? `Search nodes... (${count} matches)` : 'Search nodes...'
})

/* ─── Helpers ───────────────────────────────────────────────────── */
const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

watch(() => props.isSimulating, (newValue) => {
  if (wasSimulating.value && !newValue) {
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })

const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

const getAgentTraces = (agentUuid) => {
  if (!displayGraphData.value) return []
  const traces = []

  displayGraphData.value.edges.forEach(e => {
    const isSource = e.source_node_uuid === agentUuid
    const isTarget = e.target_node_uuid === agentUuid
    if (!isSource && !isTarget) return

    const otherUuid = isSource ? e.target_node_uuid : e.source_node_uuid
    const otherNode = displayGraphData.value.nodes.find(n => n.uuid === otherUuid)
    if (!otherNode) return

    const type = otherNode.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Node'
    const color = CSI_COLORS[type] || '#3498db'
    let desc = e.name || e.fact_type || 'Interacts with'
    if (e.attributes && e.attributes.verdict) {
      desc += ` (verdict: ${e.attributes.verdict})`
    }

    traces.push({
      id: e.uuid || Math.random().toString(36),
      type: e.name || e.fact_type || 'Link',
      targetName: otherNode.name,
      targetType: type,
      desc: desc,
      color: color
    })
  })
  return traces.reverse()
}

const formatDateTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  } catch {
    return dateStr
  }
}

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set()
}

/* ─── Handle artifact click from CSI sidebar ───────────────────── */
function handleArtifactSelect(uuid) {
  if (!uuid) return
  const node = canvasNodes.find(n => n.id === uuid)
  if (!node) return

  // Select the node in the detail panel
  selectedItem.value = {
    type: 'node',
    data: node.rawData,
    entityType: node.type,
    color: getNodeColor(node, buildColorMap())
  }

  // Center camera on the node
  if (graphCanvas.value && zoomBehavior && node.x != null && node.y != null) {
    const dpr = window.devicePixelRatio || 1
    const cx = graphCanvas.value.width / (2 * dpr)
    const cy = graphCanvas.value.height / (2 * dpr)
    const targetScale = Math.max(canvasTransform.k, 2)
    const newTx = cx - node.x * targetScale
    const newTy = cy - node.y * targetScale
    const newTransform = d3.zoomIdentity.translate(newTx, newTy).scale(targetScale)
    d3.select(graphCanvas.value).transition().duration(400).call(zoomBehavior.transform, newTransform)
  }
}

/* ─── Canvas drawing helpers ────────────────────────────────────── */
function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function getNodeColor(node, colorMap) {
  const typeColor = CSI_TYPE_COLORS[node.type]
  if (typeColor) return typeColor
  return colorMap[node.type] || colorMap[`CSI: ${node.type}`] || '#999'
}

function getNodeRadius(node) {
  const baseR = 7
  const sizeMod = CSI_TYPE_SIZE[node.type] || 1.0
  return baseR * sizeMod
}

/* ─── paintNode — Da-vinci MemoryGraph replica ─────────────────── */
function paintNode(node, ctx, globalScale, opts) {
  const { colorMap, selectedId, highlightSet, filterKey, goldenIds } = opts
  const baseColor = getNodeColor(node, colorMap)
  const r = getNodeRadius(node)
  const shape = CSI_TYPE_SHAPE[node.type] || 'circle'

  const isSelected = selectedId === node.id
  const isHighlighted = highlightSet.size > 0 && highlightSet.has(node.id)
  const isDimmedBySearch = highlightSet.size > 0 && !highlightSet.has(node.id)
  const isDimmedByFilter = filterKey !== 'all' && node.type !== filterKey
  const isDimmedByAgentHighlight = opts.highlightAgents && node.type !== 'Agent'
  const isDimmed = isDimmedBySearch || isDimmedByFilter || isDimmedByAgentHighlight
  const isGolden = goldenIds.has(node.id)
  const glow = node.rawData?.temporalWeight || 0.3

  // ── Concentric rings around every node ──
  if (!isDimmed) {
    // Ring 3 (outermost)
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 3.0, 0, 2 * Math.PI)
    ctx.strokeStyle = hexToRgba(baseColor, 0.06)
    ctx.lineWidth = 0.5 / globalScale
    ctx.stroke()
    ctx.fillStyle = hexToRgba(baseColor, 0.03)
    ctx.fill()

    // Ring 2
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 2.2, 0, 2 * Math.PI)
    ctx.strokeStyle = hexToRgba(baseColor, 0.1)
    ctx.lineWidth = 0.5 / globalScale
    ctx.stroke()
    ctx.fillStyle = hexToRgba(baseColor, 0.05)
    ctx.fill()

    // Ring 1 (inner glow)
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 1.5, 0, 2 * Math.PI)
    ctx.fillStyle = hexToRgba(baseColor, 0.1)
    ctx.fill()
  }

  // Agent highlight — extra purple concentric
  if (opts.highlightAgents && node.type === 'Agent' && !isDimmed) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 3.5, 0, 2 * Math.PI)
    ctx.strokeStyle = hexToRgba('#9C27B0', 0.15)
    ctx.lineWidth = 1 / globalScale
    ctx.stroke()
  }

  // Golden trail ring
  if (isGolden && !isDimmed) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI)
    ctx.strokeStyle = '#FFD700'
    ctx.lineWidth = 2 / globalScale
    ctx.stroke()
  }

  // Selection ring
  if (isSelected) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI)
    ctx.strokeStyle = '#117dff'
    ctx.lineWidth = 2 / globalScale
    ctx.stroke()
  }

  // Search highlight ring
  if (isHighlighted && !isSelected) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI)
    ctx.strokeStyle = '#d97706'
    ctx.lineWidth = 1.5 / globalScale
    ctx.stroke()
  }

  // ── Node body shape (Da-vinci layer shapes) ──
  const fillAlpha = isDimmed ? 0.15 : (0.6 + glow * 0.4)
  const strokeAlpha = isDimmed ? 0.1 : 0.8

  if (shape === 'hexagon') {
    // Hexagon for Agents
    ctx.beginPath()
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i - Math.PI / 6
      ctx.lineTo(node.x + r * Math.cos(angle), node.y + r * Math.sin(angle))
    }
    ctx.closePath()
  } else if (shape === 'diamond') {
    // Diamond for Claims / Trials
    ctx.beginPath()
    ctx.moveTo(node.x, node.y - r)
    ctx.lineTo(node.x + r, node.y)
    ctx.lineTo(node.x, node.y + r)
    ctx.lineTo(node.x - r, node.y)
    ctx.closePath()
  } else if (shape === 'square') {
    // Rounded square for AgentActions (small, like Da-vinci observations)
    const s = r * 0.6
    ctx.beginPath()
    ctx.roundRect(node.x - s, node.y - s, s * 2, s * 2, 2)
  } else {
    // Circle for Sources, Recalls, default
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
  }

  ctx.fillStyle = hexToRgba(baseColor, fillAlpha)
  ctx.fill()
  ctx.strokeStyle = hexToRgba(baseColor, strokeAlpha)
  ctx.lineWidth = 0.5 / globalScale
  ctx.stroke()

  // ── Label (always visible like old MiroFish, not zoom-gated) ──
  if (!isDimmed) {
    const label = node.name.length > 18 ? node.name.substring(0, 18) + '\u2026' : node.name
    const fontSize = Math.max(9, 10 / globalScale)
    ctx.font = `${fontSize}px 'Space Grotesk', system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = 'rgba(10,10,10,0.7)'
    ctx.fillText(label, node.x, node.y + r + 2)
  }
}

/* ─── paintLink — Da-vinci MemoryGraph replica ─────────────────── */
function paintLink(edge, ctx, globalScale) {
  const sx = typeof edge.source === 'object' ? edge.source.x : 0
  const sy = typeof edge.source === 'object' ? edge.source.y : 0
  const tx = typeof edge.target === 'object' ? edge.target.x : 0
  const ty = typeof edge.target === 'object' ? edge.target.y : 0

  if (sx === 0 && sy === 0 && tx === 0 && ty === 0) return

  const confidence = edge.rawData?.confidence || edge.rawData?.attributes?.confidence || 0.7
  const relType = edge.type || 'RELATED'
  const color = getEdgeColor(relType)
  const opacity = 0.35 + (confidence || 0.5) * 0.3
  const width = 0.5 + (confidence || 0.5) * 2

  ctx.strokeStyle = hexToRgba(color, opacity)
  ctx.lineWidth = width

  // Dashed for low confidence or derived/inferred relations
  const isDashed = confidence < 0.5 ||
    relType === 'Derives' ||
    relType.toLowerCase().includes('deriv') ||
    relType.toLowerCase().includes('infer')
  if (isDashed) {
    ctx.setLineDash([5, 4])
  }

  // Simple straight line (Da-vinci style — clean, no curves)
  ctx.beginPath()
  ctx.moveTo(sx, sy)
  ctx.lineTo(tx, ty)
  ctx.stroke()
  ctx.setLineDash([])

  // Directional arrow at 90%
  const t = 0.9
  const ax = sx + (tx - sx) * t
  const ay = sy + (ty - sy) * t
  const adx = tx - sx
  const ady = ty - sy
  const arrowLen = 3
  const angle = Math.atan2(ady, adx)
  ctx.fillStyle = hexToRgba(color, opacity + 0.15)
  ctx.beginPath()
  ctx.moveTo(ax, ay)
  ctx.lineTo(ax - arrowLen * Math.cos(angle - 0.4), ay - arrowLen * Math.sin(angle - 0.4))
  ctx.lineTo(ax - arrowLen * Math.cos(angle + 0.4), ay - arrowLen * Math.sin(angle + 0.4))
  ctx.closePath()
  ctx.fill()

  // Label at midpoint (Da-vinci: only at high zoom, with white bg)
  if (showEdgeLabels.value && globalScale > 0.8 && edge.name) {
    const midX = (sx + tx) / 2
    const midY = (sy + ty) / 2
    const label = `${edge.name} ${((confidence || 1) * 100).toFixed(0)}%`
    ctx.font = `${10 / globalScale}px 'Space Grotesk', system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    // White background for readability
    const tw = ctx.measureText(label).width
    ctx.fillStyle = 'rgba(255,255,255,0.8)'
    ctx.fillRect(midX - tw / 2 - 2, midY - 6, tw + 4, 12)
    ctx.fillStyle = 'rgba(10,10,10,0.8)'
    ctx.fillText(label, midX, midY)
  }
}

/* ─── Canvas hit testing ────────────────────────────────────────── */
function getNodeAtPosition(screenX, screenY) {
  const gx = (screenX - canvasTransform.x) / canvasTransform.k
  const gy = (screenY - canvasTransform.y) / canvasTransform.k
  for (let i = canvasNodes.length - 1; i >= 0; i--) {
    const node = canvasNodes[i]
    const r = getNodeRadius(node) + 2
    if (Math.hypot((node.x || 0) - gx, (node.y || 0) - gy) < r) return node
  }
  return null
}

function getEdgeAtPosition(screenX, screenY) {
  const gx = (screenX - canvasTransform.x) / canvasTransform.k
  const gy = (screenY - canvasTransform.y) / canvasTransform.k
  const threshold = 6 / canvasTransform.k
  for (let i = canvasEdges.length - 1; i >= 0; i--) {
    const edge = canvasEdges[i]
    const s = typeof edge.source === 'object' ? edge.source : null
    const t = typeof edge.target === 'object' ? edge.target : null
    if (!s || !t) continue
    // Simple distance-to-line check
    const dx = t.x - s.x
    const dy = t.y - s.y
    const lenSq = dx * dx + dy * dy
    if (lenSq === 0) continue
    const param = Math.max(0, Math.min(1, ((gx - s.x) * dx + (gy - s.y) * dy) / lenSq))
    const px = s.x + param * dx
    const py = s.y + param * dy
    if (Math.hypot(gx - px, gy - py) < threshold) return edge
  }
  return null
}

/* ─── Render frame ──────────────────────────────────────────────── */
function renderFrame() {
  const canvas = graphCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const w = canvas.width / dpr
  const h = canvas.height / dpr

  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.save()
  ctx.scale(dpr, dpr)
  ctx.translate(canvasTransform.x, canvasTransform.y)
  ctx.scale(canvasTransform.k, canvasTransform.k)

  // Build color map from entity types
  const colorMap = {}
  entityTypes.value.forEach(t => {
    colorMap[t.name] = t.color
    if (t.name.startsWith('CSI: ')) {
      colorMap[t.name.substring(5)] = t.color
    }
  })

  const opts = {
    colorMap,
    selectedId: selectedItem.value?.type === 'node' ? selectedItem.value.data?.uuid : null,
    highlightSet: highlightNodes.value,
    filterKey: activeFilter.value,
    goldenIds: goldenTrailIds.value,
    highlightAgents: highlightAgents.value,
  }

  // Paint links first
  canvasEdges.forEach(edge => paintLink(edge, ctx, canvasTransform.k))

  // Paint nodes on top
  canvasNodes.forEach(node => paintNode(node, ctx, canvasTransform.k, opts))

  ctx.restore()
}

/* ─── Main render graph ─────────────────────────────────────────── */
function renderGraph() {
  if (!graphCanvas.value || !displayGraphData.value) return

  if (currentSimulation) {
    currentSimulation.stop()
  }
  if (animFrameId) {
    cancelAnimationFrame(animFrameId)
    animFrameId = null
  }

  const container = graphContainer.value
  if (!container) return
  const width = container.clientWidth
  const height = container.clientHeight
  const dpr = window.devicePixelRatio || 1

  const canvas = graphCanvas.value
  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = width + 'px'
  canvas.style.height = height + 'px'

  const nodesData = displayGraphData.value.nodes || []
  const edgesData = displayGraphData.value.edges || []

  if (nodesData.length === 0) {
    canvasNodes = []
    canvasEdges = []
    renderFrame()
    return
  }

  // Build node map
  const nodeMap = {}
  nodesData.forEach(n => { nodeMap[n.uuid] = n })

  const nodes = nodesData.map(n => {
    const isCsi = n.labels?.includes('CSI')
    const isAgent = n.labels?.includes('Agent') || Boolean(n.attributes?.agent_id)

    let type = isCsi
      ? (n.labels?.find(l => l !== 'Entity' && l !== 'CSI' && l !== 'Node') || 'CSI')
      : (n.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity')

    if (isAgent && !isCsi) {
      type = 'Agent'
    }

    return {
      id: n.uuid,
      name: n.name || 'Unnamed',
      type: type,
      rawData: n
    }
  })

  const nodeIds = new Set(nodes.map(n => n.id))

  // Process edges
  const edgePairCount = {}
  const selfLoopEdges = {}
  const tempEdges = edgesData.filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))

  tempEdges.forEach(e => {
    if (e.source_node_uuid === e.target_node_uuid) {
      if (!selfLoopEdges[e.source_node_uuid]) {
        selfLoopEdges[e.source_node_uuid] = []
      }
      selfLoopEdges[e.source_node_uuid].push({
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      })
    } else {
      const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
      edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
    }
  })

  const edgePairIndex = {}
  const processedSelfLoopNodes = new Set()
  const edges = []

  tempEdges.forEach(e => {
    const isSelfLoop = e.source_node_uuid === e.target_node_uuid

    if (isSelfLoop) {
      if (processedSelfLoopNodes.has(e.source_node_uuid)) return
      processedSelfLoopNodes.add(e.source_node_uuid)

      const allSelfLoops = selfLoopEdges[e.source_node_uuid]
      const nodeName = nodeMap[e.source_node_uuid]?.name || 'Unknown'

      edges.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: 'SELF_LOOP',
        name: `Self Relations (${allSelfLoops.length})`,
        curvature: 0,
        isSelfLoop: true,
        rawData: {
          isSelfLoopGroup: true,
          source_name: nodeName,
          target_name: nodeName,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops
        }
      })
      return
    }

    const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
    const totalCount = edgePairCount[pairKey]
    const currentIndex = edgePairIndex[pairKey] || 0
    edgePairIndex[pairKey] = currentIndex + 1

    const isReversed = e.source_node_uuid > e.target_node_uuid

    let curvature = 0
    if (totalCount > 1) {
      const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
      curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2
      if (isReversed) {
        curvature = -curvature
      }
    }

    edges.push({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || 'RELATED',
      name: e.name || e.fact_type || 'RELATED',
      curvature,
      isSelfLoop: false,
      pairIndex: currentIndex,
      pairTotal: totalCount,
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      }
    })
  })

  canvasNodes = nodes
  canvasEdges = edges

  // D3 force simulation — Da-vinci MemoryGraph physics (wide spread)
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(120).strength(0.3))
    .force('charge', d3.forceManyBody().strength(-350).distanceMax(500))
    .force('center', d3.forceCenter(width / 2, height / 2).strength(0.03))
    .force('collide', d3.forceCollide().radius(d => getNodeRadius(d) + 20).strength(0.8))
    .force('x', d3.forceX(width / 2).strength(0.015))
    .force('y', d3.forceY(height / 2).strength(0.015))
    .alphaDecay(0.015)
    .velocityDecay(0.25)
    .alpha(1)

  // Warm up — light pre-settle, nodes still animate after
  simulation.tick(30)

  currentSimulation = simulation

  // Render on simulation tick
  simulation.on('tick', () => {
    renderFrame()
  })

  // Zoom behavior
  zoomBehavior = d3.zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (event) => {
      canvasTransform = event.transform
      renderFrame()
    })

  const canvasSelection = d3.select(canvas)
  canvasSelection.call(zoomBehavior)

  // Reset transform to identity centered
  canvasTransform = d3.zoomIdentity
  canvasSelection.call(zoomBehavior.transform, canvasTransform)

  // Canvas mouse events for hit testing
  let isDragging = false
  let dragNode = null
  let dragStartX = 0
  let dragStartY = 0

  canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const node = getNodeAtPosition(mx, my)
    if (node) {
      isDragging = false
      dragNode = node
      dragStartX = e.clientX
      dragStartY = e.clientY
      node.fx = node.x
      node.fy = node.y
      e.stopPropagation()
      // Prevent zoom from starting
      canvasSelection.on('.zoom', null)
    }
  })

  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (dragNode) {
      const dx = e.clientX - dragStartX
      const dy = e.clientY - dragStartY
      if (!isDragging && Math.sqrt(dx * dx + dy * dy) > 3) {
        isDragging = true
        // Da-vinci: gentle reheat during drag
        simulation.alphaTarget(0.1).restart()
      }
      if (isDragging) {
        const gx = (mx - canvasTransform.x) / canvasTransform.k
        const gy = (my - canvasTransform.y) / canvasTransform.k
        dragNode.fx = gx
        dragNode.fy = gy
        renderFrame()
      }
      return
    }

    // Hover detection
    const node = getNodeAtPosition(mx, my)
    if (node) {
      hoveredNode.value = node
      tooltipPos.value = { x: e.clientX - graphContainer.value.getBoundingClientRect().left + 12, y: e.clientY - graphContainer.value.getBoundingClientRect().top + 12 }
      canvas.style.cursor = 'pointer'
    } else {
      hoveredNode.value = null
      canvas.style.cursor = 'default'
    }
  })

  canvas.addEventListener('mouseup', (e) => {
    if (dragNode) {
      if (isDragging) {
        // Da-vinci: gently cool down, node floats back
        simulation.alphaTarget(0)
        // Keep node pinned briefly then release for organic settle
        const releasedNode = dragNode
        setTimeout(() => {
          releasedNode.fx = null
          releasedNode.fy = null
        }, 300)
      } else {
        // This was a click, not a drag — open detail panel
        const node = dragNode
        // Center camera on clicked node
        const cx = canvas.width / (2 * (window.devicePixelRatio || 1))
        const cy = canvas.height / (2 * (window.devicePixelRatio || 1))
        const targetScale = Math.max(canvasTransform.k, 2)
        const newTx = cx - node.x * targetScale
        const newTy = cy - node.y * targetScale
        const newTransform = d3.zoomIdentity.translate(newTx, newTy).scale(targetScale)
        d3.select(canvas).transition().duration(400).call(zoomBehavior.transform, newTransform)

        selectedItem.value = {
          type: 'node',
          data: node.rawData,
          entityType: node.type,
          color: getNodeColor(node, buildColorMap())
        }

        // Try to trigger side preview in CsiArtifactList
        if (node.id && csiArtifactListRef.value) {
          const found = csiArtifactListRef.value.selectByUuid(node.id)
          if (found) {
            isCsiPanelCollapsed.value = false
          }
        }

        dragNode.fx = null
        dragNode.fy = null
      }
      dragNode = null
      isDragging = false
      // Re-enable zoom
      canvasSelection.call(zoomBehavior)
      return
    }

    // Check for edge click
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const edge = getEdgeAtPosition(mx, my)
    if (edge) {
      selectedItem.value = {
        type: 'edge',
        data: edge.rawData
      }
    } else {
      // Click on empty space
      selectedItem.value = null
    }
  })

  canvas.addEventListener('mouseleave', () => {
    hoveredNode.value = null
    if (dragNode) {
      if (isDragging) simulation.alphaTarget(0)
      dragNode.fx = null
      dragNode.fy = null
      dragNode = null
      isDragging = false
      canvasSelection.call(zoomBehavior)
    }
  })
}

function buildColorMap() {
  const colorMap = {}
  entityTypes.value.forEach(t => {
    colorMap[t.name] = t.color
    if (t.name.startsWith('CSI: ')) {
      colorMap[t.name.substring(5)] = t.color
    }
  })
  return colorMap
}

/* ─── Zoom controls ─────────────────────────────────────────────── */
function zoomIn() {
  if (!graphCanvas.value || !zoomBehavior) return
  d3.select(graphCanvas.value).transition().duration(300).call(zoomBehavior.scaleBy, 1.5)
}

function zoomOut() {
  if (!graphCanvas.value || !zoomBehavior) return
  d3.select(graphCanvas.value).transition().duration(300).call(zoomBehavior.scaleBy, 0.67)
}

function zoomFit() {
  if (!graphCanvas.value || !zoomBehavior || canvasNodes.length === 0) return
  const dpr = window.devicePixelRatio || 1
  const w = graphCanvas.value.width / dpr
  const h = graphCanvas.value.height / dpr

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  canvasNodes.forEach(n => {
    if (n.x != null && n.y != null) {
      minX = Math.min(minX, n.x)
      maxX = Math.max(maxX, n.x)
      minY = Math.min(minY, n.y)
      maxY = Math.max(maxY, n.y)
    }
  })
  if (!isFinite(minX)) return

  const padding = 60
  const graphW = maxX - minX + padding * 2
  const graphH = maxY - minY + padding * 2
  const scale = Math.min(w / graphW, h / graphH, 2)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const tx = w / 2 - cx * scale
  const ty = h / 2 - cy * scale

  const newTransform = d3.zoomIdentity.translate(tx, ty).scale(scale)
  d3.select(graphCanvas.value).transition().duration(500).call(zoomBehavior.transform, newTransform)
}

/* ─── Watchers ──────────────────────────────────────────────────── */
watch(() => props.graphData, () => {
  loadCsiGraph()
  nextTick(renderGraph)
}, { deep: true })

watch(displayGraphData, () => {
  nextTick(renderGraph)
}, { deep: true })

// Re-render when filter or search highlights change
watch([activeFilter, highlightNodes], () => {
  renderFrame()
})

// Re-render when layer toggles change
watch(highlightAgents, () => renderFrame())
watch(showEdgeLabels, () => renderFrame())
watch(showCsiLayer, () => renderFrame())

// Re-render graph when agent profiles arrive
watch(() => props.agentProfiles.length, (newLen, oldLen) => {
  if (newLen > 0 && newLen !== oldLen) {
    nextTick(renderGraph)
  }
})

const handleResize = () => {
  nextTick(renderGraph)
}

/* ─── CSI graph loading ─────────────────────────────────────────── */
const loadCsiGraph = async () => {
  if (!props.simulationId) {
    csiGraphData.value = null
    return
  }
  try {
    const res = await getSimulationCsiGraph(props.simulationId)
    csiGraphData.value = res?.data || null
  } catch (err) {
    if (err?.response?.status === 404) {
      csiGraphData.value = null
      return
    }
    // Structured logging would be used in production
  }
}

const startCsiRefresh = () => {
  stopCsiRefresh()
  if (!props.csiAutoRefresh || !props.simulationId) return

  csiRefreshTimer = setInterval(() => {
    loadCsiGraph()
  }, props.csiRefreshIntervalMs)
}

const stopCsiRefresh = () => {
  if (csiRefreshTimer) {
    clearInterval(csiRefreshTimer)
    csiRefreshTimer = null
  }
}

/* ─── Golden trail ──────────────────────────────────────────────── */
const fetchGoldenTrail = async () => {
  if (!props.reportId) return
  try {
    const res = await getGoldenTrail(props.reportId)
    if (res.data?.success && res.data?.data) {
      const trail = res.data.data
      const ids = new Set([
        ...(trail.claim_ids || []),
        ...(trail.trial_ids || []),
        ...(trail.source_ids || []),
      ])
      goldenTrailIds.value = ids
    }
  } catch {
    // Golden trail fetch failure is non-critical
  }
}

watch(() => props.reportId, (id) => {
  if (id) fetchGoldenTrail()
}, { immediate: true })

/* ─── Lifecycle ─────────────────────────────────────────────────── */
onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadCsiGraph()
  startCsiRefresh()
})

watch(() => [props.simulationId, props.csiAutoRefresh, props.csiRefreshIntervalMs], () => {
  loadCsiGraph()
  startCsiRefresh()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  stopCsiRefresh()
  if (currentSimulation) {
    currentSimulation.stop()
  }
  if (animFrameId) {
    cancelAnimationFrame(animFrameId)
  }
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #faf9f4;
  background-image: radial-gradient(#e3e0db 1px, transparent 1px);
  background-size: 20px 20px;
  overflow: hidden;
}

.graph-container {
  width: 100%;
  height: 100%;
}

.graph-view {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #faf9f4;
  background-image: radial-gradient(#e3e0db 1px, transparent 1px);
  background-size: 20px 20px;
}

.graph-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #999;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.2;
}

/* ─── Search ───────────────────────────────────────────────────── */
.graph-search {
  position: absolute;
  top: 14px;
  right: 20px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: #FFF;
  border: 1px solid #E0E0E0;
  border-radius: 20px;
  padding: 6px 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  z-index: 10;
  transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  min-width: 200px;
}

.search-icon {
  flex-shrink: 0;
  color: #999;
}

.search-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  color: #333;
  width: 160px;
  font-family: system-ui, sans-serif;
}

.search-input::placeholder {
  color: #aaa;
}

.search-clear {
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
}

.search-clear:hover {
  color: #333;
}

/* ─── Filter chips ─────────────────────────────────────────────── */
.graph-filters {
  position: absolute;
  top: 52px;
  right: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  z-index: 10;
  transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  max-width: 400px;
}

.filter-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid #E0E0E0;
  border-radius: 16px;
  background: #FFF;
  font-size: 11px;
  color: #666;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  white-space: nowrap;
}

.filter-chip:hover {
  background: #F5F5F5;
  border-color: #CCC;
}

.filter-chip.active {
  font-weight: 600;
  color: #333;
}

.filter-chip-icon {
  font-size: 10px;
  line-height: 1;
}

.filter-chip-label {
  line-height: 1;
}

.csi-count-badge {
  font-size: 9px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: #7B2D8E;
  background: #F3E8F9;
  padding: 1px 5px;
  border-radius: 8px;
  line-height: 1;
}

/* ─── Zoom controls ────────────────────────────────────────────── */
.zoom-controls {
  position: absolute;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  z-index: 10;
}

.zoom-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #E0E0E0;
  border-radius: 8px;
  background: #FFF;
  color: #555;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
  transition: all 0.15s;
}

.zoom-btn:hover {
  background: #F5F5F5;
  border-color: #CCC;
  color: #000;
}

.zoom-fit {
  font-size: 12px;
}

/* ─── Hover tooltip ────────────────────────────────────────────── */
.graph-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(255,255,255,0.95);
  border: 1px solid #E0E0E0;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  color: #333;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 25;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.tooltip-icon {
  font-size: 10px;
  opacity: 0.7;
}

.tooltip-name {
  font-weight: 500;
}

/* ─── Graph layer toggles ──────────────────────────────────────── */
.graph-toggles {
  position: absolute;
  top: 14px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 10;
  transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(6px);
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid #e3e0db;
}

.toggle-row.csi-toggle {
  border-color: rgba(123, 45, 142, 0.2);
}

.toggle-label {
  font-size: 11px;
  color: #525252;
  white-space: nowrap;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 28px;
  height: 16px;
  flex-shrink: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background-color: #d4d0ca;
  border-radius: 16px;
  transition: 0.2s;
}

.slider::before {
  content: '';
  position: absolute;
  height: 12px;
  width: 12px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle-switch input:checked + .slider {
  background-color: #117dff;
}

.toggle-switch input:checked + .slider.agent-slider {
  background-color: #9C27B0;
}

.toggle-switch input:checked + .slider.csi-slider {
  background-color: #7B2D8E;
}

.toggle-switch input:checked + .slider::before {
  transform: translateX(12px);
}

.csi-count-badge {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(123, 45, 142, 0.12);
  color: #7B2D8E;
  padding: 1px 5px;
  border-radius: 999px;
  margin-left: 2px;
}

/* ─── Legend ────────────────────────────────────────────────────── */
.graph-legend {
  position: absolute;
  bottom: 24px;
  left: 20px;
  transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  background: rgba(255,255,255,0.95);
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #EAEAEA;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  z-index: 10;
}

.legend-title {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #E91E63;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  max-width: 320px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #555;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  white-space: nowrap;
}

.legend-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-left: 2px;
}

.legend-separator {
  width: 100%;
  height: 1px;
  background: #E0D4E8;
  margin: 2px 0;
}

.csi-legend-item {
  opacity: 0.9;
}

.csi-dot {
  border: 1.5px solid rgba(0,0,0,0.2);
  box-sizing: border-box;
}

/* ─── CSI Artifact Rail ────────────────────────────────────────── */
.csi-artifact-rail {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 150px;
  width: min(340px, calc(50% - 40px));
  z-index: 11;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.97);
  border-right: 1px solid #e5e5e5;
  overflow: hidden;
  transition: all 0.3s ease;
}

.csi-artifact-rail.collapsed {
  bottom: auto;
  height: 40px;
  overflow: hidden;
}

.csi-rail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  background: transparent;
  border-bottom: 1px solid transparent;
}

.csi-rail-title {
  flex: 1;
  font-weight: 600;
  font-size: 13px;
  color: #333;
}

.csi-refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #737373;
  font-size: 14px;
  padding: 2px 4px;
  border-radius: 4px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.csi-refresh-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #333;
}

.csi-refresh-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.csi-artifact-rail:not(.collapsed) .csi-rail-header {
  border-bottom: 1px solid #EAEAEA;
}

.csi-collapse-btn {
  background: none;
  border: none;
  color: #666;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
}

.csi-collapse-btn:hover {
  background: rgba(0,0,0,0.05);
}

.csi-artifact-rail > .csi-artifact-list {
  flex: 1;
  overflow: auto;
}

.csi-artifact-rail :deep(.csi-artifact-list) {
  backdrop-filter: blur(8px);
}

.icon-refresh.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ─── Detail Panel (overlays above right drawer) ──────────────── */
.detail-panel {
  position: fixed;
  top: 48px;
  right: 0;
  width: 340px;
  bottom: 0;
  background: #faf9f4;
  border-left: 1px solid #e3e0db;
  border-radius: 0;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 13px;
  z-index: 50;
  display: flex;
  flex-direction: column;
}

.detail-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #f3efe7;
  border-bottom: 1px solid #e6dfd3;
  flex-shrink: 0;
}

.detail-title {
  font-weight: 700;
  color: #2d2418;
  font-size: 14px;
  letter-spacing: 0.02em;
}

.detail-type-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  margin-left: auto;
  margin-right: 12px;
}

.detail-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #8f816f;
  line-height: 1;
  padding: 0;
  transition: color 0.2s;
}

.detail-close:hover {
  color: #2d2418;
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
  background: linear-gradient(180deg, rgba(255,255,255,0.86) 0%, rgba(250,249,244,0.96) 100%);
}

.detail-row {
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-label {
  color: #8f816f;
  font-size: 12px;
  font-weight: 600;
  min-width: 80px;
}

.detail-value {
  color: #2d2418;
  flex: 1;
  word-break: break-word;
}

.detail-value.uuid-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #666;
}

.detail-value.fact-text {
  line-height: 1.5;
  color: #3c3226;
}

.detail-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #e8e2d8;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: #5a4b38;
  margin-bottom: 10px;
  letter-spacing: 0.03em;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-item {
  display: flex;
  gap: 8px;
}

.property-key {
  color: #8f816f;
  font-weight: 600;
  min-width: 90px;
}

.property-value {
  color: #2d2418;
  flex: 1;
}

.agent-traces {
  margin-top: 12px;
  background: rgba(17, 125, 255, 0.05);
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(17, 125, 255, 0.14);
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.trace-item {
  display: flex;
  flex-direction: column;
  background: #fffdfa;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid #ece6da;
  gap: 4px;
}

.trace-type {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  color: white;
  font-size: 10px;
  font-weight: bold;
  align-self: flex-start;
  text-transform: uppercase;
}

.trace-details {
  display: flex;
  flex-direction: column;
}

.trace-target {
  font-size: 12px;
  font-weight: 600;
  color: #2d2418;
}

.trace-target-type {
  font-weight: normal;
  color: #888;
  font-size: 11px;
}

.trace-desc {
  font-size: 11px;
  color: #6b5a45;
  margin-top: 2px;
}

.summary-text {
  line-height: 1.6;
  color: #3c3226;
  font-size: 12px;
}

.labels-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.label-tag {
  display: inline-block;
  padding: 4px 12px;
  background: #f4f0e8;
  border: 1px solid #e1d8ca;
  border-radius: 16px;
  font-size: 11px;
  color: #4e4030;
}

.episodes-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-tag {
  display: inline-block;
  padding: 6px 10px;
  background: #f5f1e8;
  border: 1px solid #e4dccf;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #5f5140;
  word-break: break-all;
}

/* Edge relation header */
.edge-relation-header {
  background: #f3efe7;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  font-weight: 600;
  color: #2d2418;
  line-height: 1.5;
  word-break: break-word;
}

/* Building hint */
.graph-building-hint {
  position: absolute;
  bottom: 160px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  color: #fff;
  padding: 10px 20px;
  border-radius: 30px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-weight: 500;
  letter-spacing: 0.5px;
  z-index: 100;
}

.memory-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 2s ease-in-out infinite;
}

.memory-icon {
  width: 18px;
  height: 18px;
  color: #4CAF50;
}

@keyframes breathe {
  0%, 100% { opacity: 0.7; transform: scale(1); filter: drop-shadow(0 0 2px rgba(76, 175, 80, 0.3)); }
  50% { opacity: 1; transform: scale(1.15); filter: drop-shadow(0 0 8px rgba(76, 175, 80, 0.6)); }
}

.graph-building-hint.finished-hint {
  background: rgba(0, 0, 0, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.finished-hint .hint-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.finished-hint .hint-icon {
  width: 18px;
  height: 18px;
  color: #FFF;
}

.finished-hint .hint-text {
  flex: 1;
  white-space: nowrap;
}

.hint-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: #FFF;
  transition: all 0.2s;
  margin-left: 8px;
  flex-shrink: 0;
}

.hint-close-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  transform: scale(1.1);
}

/* Loading spinner */
.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #E0E0E0;
  border-top-color: #7B2D8E;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

/* Self-loop styles */
.self-loop-header {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #E8F5E9 0%, #F1F8E9 100%);
  border: 1px solid #C8E6C9;
}

.self-loop-count {
  margin-left: auto;
  font-size: 11px;
  color: #666;
  background: rgba(255,255,255,0.8);
  padding: 2px 8px;
  border-radius: 10px;
}

.self-loop-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.self-loop-item {
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
}

.self-loop-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #F5F5F5;
  cursor: pointer;
  transition: background 0.2s;
}

.self-loop-item-header:hover {
  background: #EEEEEE;
}

.self-loop-item.expanded .self-loop-item-header {
  background: #E8E8E8;
}

.self-loop-index {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  background: #E0E0E0;
  padding: 2px 6px;
  border-radius: 4px;
}

.self-loop-name {
  font-size: 12px;
  font-weight: 500;
  color: #333;
  flex: 1;
}

.self-loop-toggle {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #888;
  background: #E0E0E0;
  border-radius: 4px;
  transition: all 0.2s;
}

.self-loop-item.expanded .self-loop-toggle {
  background: #D0D0D0;
  color: #666;
}

.self-loop-item-content {
  padding: 12px;
  border-top: 1px solid #EAEAEA;
}

.self-loop-item-content .detail-row {
  margin-bottom: 8px;
}

.self-loop-item-content .detail-label {
  font-size: 11px;
  min-width: 60px;
}

.self-loop-item-content .detail-value {
  font-size: 12px;
}

.self-loop-episodes {
  margin-top: 8px;
}

.episodes-list.compact {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 4px;
}

.episode-tag.small {
  padding: 3px 6px;
  font-size: 9px;
}
</style>
