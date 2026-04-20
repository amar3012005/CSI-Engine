<template>
  <div class="ingestion-panel">
    <div class="scroll-container">
      <div class="hero-card">
        <div class="hero-copy">
          <span class="hero-kicker">Environment</span>
          <h2>Document & URL Ingestion</h2>
          <p>
            Uploaded sources are processed here before the DeepResearch simulation is created. The graph build
            stays inside the workspace, then the environment hands off to research-team setup.
          </p>
        </div>
        <button class="action-btn secondary" type="button" @click="$emit('go-back')">Back to Home</button>
      </div>

      <div class="step-card" :class="{ active: phase === 0, completed: phase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">Source Intake & Ontology</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 0" class="badge success">Completed</span>
            <span v-else class="badge processing">{{ ontologyStatus }}</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/ontology/generate</p>
          <div v-if="phase === 0" class="realtime-status-bar">
            <div class="bar-fill animate-pulse"></div>
            <span class="bar-text">Analyzing documents & building ontology...</span>
          </div>
          <p class="description">
            Files and URLs are normalized, extracted, and attached to a project so ontology generation can begin.
          </p>

          <div class="source-stats">
            <div class="stat-card">
              <span class="stat-value">{{ pending.files.length }}</span>
              <span class="stat-label">Files</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ pending.urls.length }}</span>
              <span class="stat-label">URLs</span>
            </div>
            <div class="stat-card wide">
              <span class="stat-label">Research Query</span>
              <span class="stat-query">{{ pending.simulationRequirement || 'Pending workspace query' }}</span>
            </div>
          </div>

          <div class="asset-list" v-if="pending.files.length || pending.urls.length">
            <div v-for="file in pending.files" :key="file.name + file.size" class="asset-row">
              <span class="asset-kind">FILE</span>
              <span class="asset-name">{{ file.name }}</span>
            </div>
            <div v-for="url in pending.urls" :key="url" class="asset-row">
              <span class="asset-kind">URL</span>
              <span class="asset-name">{{ url }}</span>
            </div>
          </div>

          <div v-if="projectData" class="info-card">
            <div class="info-row">
              <span class="info-label">Project ID</span>
              <span class="info-value mono">{{ projectData.project_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Project Status</span>
              <span class="info-value">{{ projectData.status }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="step-card" :class="{ active: phase === 1, completed: phase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">Graph Build & Validation</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 1" class="badge success">Completed</span>
            <span v-else-if="phase === 1" class="badge processing">{{ buildBadge }}</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/build</p>
          <p class="description">
            The project graph is built and hydrated into the background canvas. This preserves the existing document
            pipeline before any DeepResearch agent setup begins.
          </p>

          <div v-if="buildProgress" class="progress-card">
            <div class="progress-topline">
              <span>{{ buildProgress.message || 'Building graph...' }}</span>
              <span>{{ Math.round(buildProgress.progress || 0) }}%</span>
            </div>
            <div class="progress-track">
              <span class="progress-bar" :style="{ width: `${Math.round(buildProgress.progress || 0)}%` }"></span>
            </div>
          </div>

          <div v-if="graphSummary.nodeCount || graphSummary.edgeCount" class="stats-grid compact">
            <div class="stat-card">
              <span class="stat-value">{{ graphSummary.nodeCount }}</span>
              <span class="stat-label">Nodes</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphSummary.edgeCount }}</span>
              <span class="stat-label">Edges</span>
            </div>
            <div class="stat-card wide">
              <span class="stat-label">Graph ID</span>
              <span class="stat-query mono">{{ projectData?.graph_id || 'Pending' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="step-card" :class="{ active: phase === 2, completed: phase > 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">Create DeepResearch Session</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 2" class="badge success">Completed</span>
            <span v-else-if="phase === 2" class="badge processing">{{ simulationStatus }}</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">
            Once the graph is ready, a DeepResearch simulation is created and the workspace transitions into the
            standard environment setup for agent-team generation and CSI preparation.
          </p>

          <div v-if="createdSimulationId" class="info-card">
            <div class="info-row">
              <span class="info-label">Simulation ID</span>
              <span class="info-value mono">{{ createdSimulationId }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Mode</span>
              <span class="info-value">deepresearch</span>
            </div>
          </div>
        </div>
      </div>

      <div class="step-card final" :class="{ active: phase === 3 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">Environment Ready</span>
          </div>
          <div class="step-status">
            <span v-if="phase >= 3" class="badge success">Handing off</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="description">
            The project is attached to a real DeepResearch simulation. Agent generation and CSI environment setup
            continue in the next environment panel.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { buildGraph, generateOntology, getGraphData, getProject, getTaskStatus } from '../api/graph'
import { createSimulation } from '../api/simulation'
import { clearPendingUpload } from '../store/pendingUpload'

const props = defineProps({
  pending: {
    type: Object,
    required: true
  }
})

const emit = defineEmits([
  'add-log',
  'project-updated',
  'graph-updated',
  'simulation-created',
  'go-back'
])

const phase = ref(0)
const ontologyStatus = ref('Uploading')
const buildProgress = ref(null)
const simulationStatus = ref('Creating')
const projectData = ref(null)
const createdSimulationId = ref('')
const graphSummary = ref({
  nodeCount: 0,
  edgeCount: 0
})

let taskPollTimer = null
let graphPollTimer = null

const log = (message) => emit('add-log', message)

const buildBadge = computed(() => {
  if (!buildProgress.value) return 'Building'
  return `${Math.round(buildProgress.value.progress || 0)}%`
})

const fetchGraphSnapshot = async () => {
  if (!projectData.value?.project_id) return
  try {
    const projRes = await getProject(projectData.value.project_id)
    if (projRes.success && projRes.data) {
      projectData.value = projRes.data
      emit('project-updated', projRes.data)
    }
    if (!projRes?.data?.graph_id) return
    const graphRes = await getGraphData(projRes.data.graph_id)
    if (graphRes.success && graphRes.data) {
      graphSummary.value = {
        nodeCount: graphRes.data.node_count || graphRes.data.nodes?.length || 0,
        edgeCount: graphRes.data.edge_count || graphRes.data.edges?.length || 0
      }
      emit('graph-updated', graphRes.data)
    }
  } catch (err) {
    console.warn('Graph snapshot refresh failed', err)
  }
}

const stopTaskPolling = () => {
  if (taskPollTimer) {
    clearInterval(taskPollTimer)
    taskPollTimer = null
  }
}

const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
  }
}

const createDeepResearchSimulation = async () => {
  phase.value = 2
  simulationStatus.value = 'Creating'
  log('Graph completed. Creating DeepResearch simulation...')

  const res = await createSimulation({
    project_id: projectData.value.project_id,
    graph_id: projectData.value.graph_id,
    simulation_requirement: props.pending.simulationRequirement,
    config_mode: 'deepresearch'
  })

  if (!res.success || !res.data?.simulation_id) {
    throw new Error(res.error || 'Failed to create deepresearch simulation')
  }

  createdSimulationId.value = res.data.simulation_id
  phase.value = 3
  simulationStatus.value = 'Created'
  log(`DeepResearch simulation created: ${createdSimulationId.value}`)
  clearPendingUpload()

  emit('simulation-created', {
    simulationId: createdSimulationId.value,
    projectData: projectData.value
  })
}

const pollTaskStatus = async (taskId) => {
  const res = await getTaskStatus(taskId)
  if (!res.success || !res.data) {
    throw new Error(res.error || 'Unable to fetch graph build status')
  }

  buildProgress.value = {
    progress: res.data.progress || 0,
    message: res.data.message || 'Building graph...'
  }

  if (res.data.message) {
    log(res.data.message)
  }

  if (res.data.status === 'completed') {
    stopTaskPolling()
    stopGraphPolling()
    phase.value = 2
    log('Graph build completed. Loading final graph snapshot...')
    const latestProject = await getProject(projectData.value.project_id)
    if (latestProject.success && latestProject.data) {
      projectData.value = latestProject.data
      emit('project-updated', latestProject.data)
    }
    await fetchGraphSnapshot()
    await createDeepResearchSimulation()
  } else if (res.data.status === 'failed') {
    stopTaskPolling()
    stopGraphPolling()
    throw new Error(res.data.error || 'Graph build failed')
  }
}

const beginGraphBuild = async () => {
  phase.value = 1
  buildProgress.value = {
    progress: 0,
    message: 'Starting graph build...'
  }
  log(`Ontology ready for project ${projectData.value.project_id}. Starting graph build...`)

  const res = await buildGraph({ project_id: projectData.value.project_id })
  if (!res.success || !res.data?.task_id) {
    throw new Error(res.error || 'Failed to start graph build')
  }

  await fetchGraphSnapshot()
  graphPollTimer = setInterval(fetchGraphSnapshot, 10000)
  await pollTaskStatus(res.data.task_id)
  taskPollTimer = setInterval(() => {
    pollTaskStatus(res.data.task_id).catch((err) => {
      stopTaskPolling()
      stopGraphPolling()
      log(`Graph build polling failed: ${err.message}`)
    })
  }, 2000)
}

const startIngestion = async () => {
  if (!props.pending?.isPending) {
    log('No pending upload payload found for environment ingestion.')
    return
  }

  try {
    phase.value = 0
    ontologyStatus.value = 'Uploading'
    log('Starting environment ingestion for uploaded files and URLs...')

    const formData = new FormData()
    props.pending.files.forEach(file => formData.append('files', file))
    props.pending.urls.forEach(url => formData.append('urls', url))
    formData.append('simulation_requirement', props.pending.simulationRequirement)
    formData.append('project_name', 'DeepResearch Workspace')

    const res = await generateOntology(formData)
    if (!res.success || !res.data?.project_id) {
      throw new Error(res.error || 'Ontology generation failed')
    }

    projectData.value = res.data
    ontologyStatus.value = 'Completed'
    emit('project-updated', res.data)
    log(`Ontology generated for project ${res.data.project_id}`)

    await beginGraphBuild()
  } catch (err) {
    log(`Environment ingestion failed: ${err.message}`)
  }
}

onMounted(() => {
  startIngestion()
})

onBeforeUnmount(() => {
  stopTaskPolling()
  stopGraphPolling()
})
</script>

<style scoped>
.ingestion-panel {
  height: 100%;
  background: #fff;
}

.scroll-container {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.step-card,
.stat-card,
.info-card,
.progress-card,
.asset-row {
  border: 1px solid #e6e1d7;
  border-radius: 18px;
  background: #fffdfa;
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
  align-items: flex-start;
}

.hero-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #857664;
}

.hero-card h2 {
  margin: 6px 0 8px;
  font-size: 26px;
  line-height: 1.1;
}

.hero-card p,
.description {
  margin: 0;
  color: #5f5548;
  line-height: 1.6;
}

.step-card {
  padding: 18px;
  border-color: #ece6da;
}

.step-card.active {
  border-color: #117dff;
  box-shadow: 0 16px 32px rgba(17, 125, 255, 0.08);
}

.step-card.completed {
  background: #fafaf6;
}

.card-header,
.step-info,
.step-status,
.progress-topline,
.info-row,
.asset-row {
  display: flex;
  align-items: center;
}

.card-header {
  justify-content: space-between;
  gap: 12px;
}

.step-info {
  gap: 12px;
}

.realtime-status-bar {
  margin: 10px 0;
  background: #f0f7ff;
  border-radius: 8px;
  height: 36px;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border: 1px solid #cce4ff;
}

.bar-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, #117dff 0%, #00b8ff 50%, #117dff 100%);
  background-size: 200% 100%;
  opacity: 0.15;
}

.animate-pulse {
  animation: bar-slide 2s linear infinite;
}

@keyframes bar-slide {
  0% { background-position: 200% 0; }
  100% { background-position: 0% 0; }
}

.bar-text {
  font-size: 13px;
  color: #117dff;
  font-weight: 600;
  position: relative;
  z-index: 1;
}

.step-num {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: #111;
  color: #fff;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.step-title {
  font-size: 18px;
  font-weight: 700;
}

.card-content {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.api-note {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #8f816f;
}

.badge {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.badge.processing {
  background: rgba(17, 125, 255, 0.1);
  color: #0d67d0;
}

.badge.pending {
  background: #f2efe8;
  color: #857664;
}

.badge.success {
  background: rgba(43, 145, 78, 0.12);
  color: #1f7b45;
}

.source-stats,
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.stats-grid.compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stat-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 80px;
}

.stat-card.wide {
  grid-column: span 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
}

.stat-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8f816f;
}

.stat-query {
  font-size: 14px;
  line-height: 1.5;
  color: #221c16;
}

.asset-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.asset-row {
  gap: 10px;
  padding: 12px 14px;
}

.asset-kind {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #117dff;
  min-width: 34px;
}

.asset-name {
  font-size: 14px;
  color: #221c16;
  word-break: break-word;
}

.info-card,
.progress-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-row {
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;
}

.info-label {
  color: #8f816f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 11px;
}

.info-value {
  color: #221c16;
  text-align: right;
}

.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

.progress-topline {
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  color: #3a3128;
}

.progress-track {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #ece6da;
}

.progress-bar {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #117dff, #38bdf8);
  border-radius: inherit;
}

.action-btn {
  border: none;
  border-radius: 999px;
  padding: 12px 18px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.action-btn.secondary {
  background: #f2efe8;
  color: #33291f;
}

@media (max-width: 900px) {
  .hero-card {
    flex-direction: column;
  }

  .source-stats,
  .stats-grid,
  .stats-grid.compact {
    grid-template-columns: 1fr;
  }
}
</style>
