<template>
  <div class="app-root-shell">
    <!-- Persistent top navbar -->
    <header class="top-navbar">
      <div class="navbar-left">
        <img :src="davinciLogo" alt="Da'vinci" class="navbar-logo" />
        <span class="navbar-divider"></span>
        <span class="navbar-title">Deep Research</span>
        <span v-if="simulationRequirement" class="navbar-subtitle">{{ simulationRequirement }}</span>
        <span v-else class="navbar-subtitle">AI-powered multi-agent research engine</span>
      </div>
      <div v-if="showSimulationOverlay" class="navbar-right">
        <div class="navbar-token-counter">
          <span class="tokens-label">Usage:</span>
          <span class="tokens-value">{{ formatTokenCount((tokenUsage?.input || 0) + (tokenUsage?.output || 0)) }}</span>
          <div class="tokens-tooltip">
            <span>Input: {{ (tokenUsage?.input || 0).toLocaleString() }}</span>
            <span>Output: {{ (tokenUsage?.output || 0).toLocaleString() }}</span>
          </div>
        </div>
        <div class="navbar-status">
          <span class="navbar-status-dot" :class="canContinue ? 'ready' : 'processing'"></span>
          <span class="navbar-status-text">{{ canContinue ? 'Ready' : 'Active' }}</span>
        </div>
      </div>
    </header>

    <!-- Page content fills below navbar -->
    <div class="app-main">
      <div v-if="showSimulationOverlay" class="chat-card-wrapper">
        <div class="chat-card" :class="{ 'can-continue': canContinue }">
          <div class="card-chrome">
            <div class="traffic-lights">
              <span class="dot red"></span>
              <span class="dot yellow"></span>
              <span class="dot green"></span>
            </div>
            <span class="card-label">{{ canContinue ? 'Follow-up' : 'AI Research' }}</span>
            <span v-if="isContinuing" class="card-status-pill">Continuing...</span>
          </div>
          <div class="card-body">
            <textarea
              v-model="draftMessage"
              :placeholder="chatboxPlaceholder"
              rows="1"
              class="chat-input"
              :disabled="!canContinue || isContinuing"
              @keydown.enter.prevent="handleChatboxSend"
            ></textarea>
          </div>
          <div class="card-footer">
            <div class="footer-left">
              <span class="status-text">
                <span v-if="canContinue" class="status-dot ready"></span>
                <span v-else class="status-dot active"></span>
                {{ overlayStatusText }}
              </span>
            </div>
            <button
              class="submit-btn"
              type="button"
              :disabled="!canContinue || isContinuing || !draftMessage.trim()"
              @click="handleChatboxSend"
            >
              {{ isContinuing ? 'Sending...' : 'Send' }}
            </button>
          </div>
        </div>
      </div>

      <router-view />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProject } from './api/graph'
import { getSimulation, getRunStatus, getSimulationHistory, continueSimulation, deleteSimulation, getSimulationTokenUsage } from './api/simulation'
import { persistence } from './utils/persistence'
import { getReport } from './api/report'
import AppSidebar from './components/ui/AppSidebar.vue'
import { useSidebar } from './store/sidebar'
import davinciLogo from './assets/davinci-logo.svg'

const route = useRoute()
const router = useRouter()
const { sidebarCollapsed } = useSidebar()
const recentSessions = ref([])
const simulationRequirement = ref('')
const loadedSimulationId = ref('')
const loadedReportId = ref('')
const draftMessage = ref('')
const overlayMounted = ref(false)
const simulationStatus = ref('')
const runnerStatus = ref('')
const isContinuing = ref(false)
const tokenUsage = ref({ input: 0, output: 0 })

const formatTokenCount = (n) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

const refreshTokenUsage = async () => {
  if (!currentSimulationId.value || currentSimulationId.value === 'new') {
    tokenUsage.value = { input: 0, output: 0 }
    return
  }

  try {
    const res = await getSimulationTokenUsage(currentSimulationId.value)
    if (res?.success && res.data) {
      tokenUsage.value = {
        input: Number(res.data.prompt_tokens || 0),
        output: Number(res.data.completion_tokens || 0),
      }
    }
  } catch {
    tokenUsage.value = { input: 0, output: 0 }
  }
}

const currentSimulationId = computed(() => String(route.params.simulationId || route.query.simulationId || loadedSimulationId.value || ''))
const currentReportId = computed(() => String(route.params.reportId || ''))
const currentWorkspaceStage = computed(() => String(route.query.stage || 'environment'))

const showSimulationOverlay = computed(() => {
  return ['Simulation', 'SimulationRun', 'Report', 'PaperReport'].includes(String(route.name || '')) && Boolean(currentSimulationId.value || currentReportId.value)
})

const canContinue = computed(() => {
  if (!showSimulationOverlay.value) return false
  const sim = simulationStatus.value.toLowerCase()
  const runner = runnerStatus.value.toLowerCase()
  // Allow continuation if either sim meta or runner says completed/stopped
  return sim === 'completed' || sim === 'stopped' ||
    runner === 'completed' || runner === 'stopped' || runner === 'failed'
})

const chatboxPlaceholder = computed(() => {
  if (isContinuing.value) return 'Continuing current session...'
  if (canContinue.value) return 'Ask a follow-up question...'
  if (currentWorkspaceStage.value === 'simulation') return 'Simulation in progress...'
  return 'Setting up environment...'
})

const overlayStatusText = computed(() => {
  if (isContinuing.value) return 'Starting follow-up research...'
  if (canContinue.value) return 'Ready for follow-up'
  if (currentWorkspaceStage.value === 'report') return 'Report workspace active'
  if (currentWorkspaceStage.value === 'simulation') return 'Simulation workspace active'
  return 'Setting up research environment...'
})

const handleChatboxSend = async () => {
  const query = draftMessage.value.trim()
  if (!query || !canContinue.value || isContinuing.value) return

  isContinuing.value = true
  try {
    const simId = currentSimulationId.value
    const res = await continueSimulation(simId, query)
    if (res?.success) {
      draftMessage.value = ''
      // Reset status so chatbox disables during new run
      simulationStatus.value = 'ready'
      runnerStatus.value = ''
      // Navigate to environment stage to show agents re-spawning
      router.replace({
        name: 'Simulation',
        params: { simulationId: simId },
        query: { stage: 'environment' }
      })
    }
  } catch (err) {
    console.warn('Continuation failed:', err)
  } finally {
    isContinuing.value = false
  }
}

// Persistent sidebar
const activeSessionForSidebar = computed(() => {
  if (!currentSimulationId.value) return null
  return {
    title: simulationRequirement.value || currentSimulationId.value,
    id: currentSimulationId.value,
    checkpoints: []
  }
})

const goHome = () => {
  router.push('/')
}

const navigateToSimulation = (simId) => {
  router.push({ name: 'Simulation', params: { simulationId: simId } })
}

const handleDeleteSession = async (simId) => {
  if (!confirm('Delete this session and all its data? This cannot be undone.')) return
  try {
    const res = await deleteSimulation(simId)
    if (res?.success) {
      recentSessions.value = recentSessions.value.filter(s => s.simulationId !== simId)
      if (simId === currentSimulationId.value) {
        goHome()
      }
    }
  } catch { /* ignore */ }
}

const loadSessions = async () => {
  try {
    // Try merged cloud + local sessions first
    const sessions = await persistence.listSessions()
    if (sessions.length > 0) {
      recentSessions.value = sessions.map(s => ({
        id: s.simulation_id,
        label: (s.query || '').substring(0, 50) || `Session ${s.simulation_id?.slice(-8) || ''}`,
        simulationId: s.simulation_id,
        source: s.source
      }))
      return
    }
  } catch { /* fallback below */ }

  // Fallback: local backend history
  try {
    const res = await getSimulationHistory(20)
    if (res?.success && res?.data) {
      recentSessions.value = (res.data.simulations || res.data || [])
        .map(s => {
          const label = s.simulation_requirement || s.project_name || ''
          const displayLabel = label && !label.startsWith('sim_') ? label.substring(0, 50) : ''
          return {
            id: s.simulation_id,
            label: displayLabel || `Session ${s.simulation_id?.slice(-8) || ''}`,
            simulationId: s.simulation_id,
          }
        })
    }
  } catch { /* best-effort */ }
}

const overlayStageLabel = computed(() => {
  if (currentWorkspaceStage.value === 'report') return 'Report'
  if (currentWorkspaceStage.value === 'simulation') return 'Simulation'
  return 'Environment'
})

const chatPlaceholder = computed(() => {
  if (currentWorkspaceStage.value === 'report') {
    return 'Report chat routing will be attached here.'
  }
  if (currentWorkspaceStage.value === 'simulation') {
    return 'Simulation chat routing will be attached here.'
  }
  return 'Environment setup is in progress.'
})

const loadSimulationRequirement = async (simulationId) => {
  if (!simulationId) return
  loadedSimulationId.value = simulationId

  try {
    const [simRes, runRes] = await Promise.all([
      getSimulation(simulationId),
      getRunStatus(simulationId).catch(() => null)
    ])
    if (simRes?.success && simRes?.data) {
      simulationStatus.value = simRes.data.status || ''
      if (simRes.data.project_id) {
        const projRes = await getProject(simRes.data.project_id)
        if (projRes?.success && projRes?.data) {
          simulationRequirement.value = projRes.data.simulation_requirement || ''
        }
      }
    }
    if (runRes?.success && runRes?.data) {
      runnerStatus.value = runRes.data.runner_status || ''
    }
    loadedSimulationId.value = simulationId
  } catch {
    simulationRequirement.value = ''
    simulationStatus.value = ''
    runnerStatus.value = ''
  }
}

const loadReportSimulation = async (reportId) => {
  if (!reportId || loadedReportId.value === reportId) return

  try {
    const repRes = await getReport(reportId)
    if (repRes.success && repRes.data?.simulation_id) {
      loadSimulationRequirement(repRes.data.simulation_id)
    }
    loadedReportId.value = reportId
  } catch {
    // Ignore error
  }
}

// Poll simulation + runner status + token usage to detect completion + usage for navbar
let statusPollTimer = null
const startStatusPoll = () => {
  if (statusPollTimer) clearInterval(statusPollTimer)
  statusPollTimer = setInterval(async () => {
    if (!currentSimulationId.value || !showSimulationOverlay.value) return
    try {
      const [simRes, runRes, usageRes] = await Promise.all([
        getSimulation(currentSimulationId.value),
        getRunStatus(currentSimulationId.value).catch(() => null),
        getSimulationTokenUsage(currentSimulationId.value).catch(() => null)
      ])
      if (simRes?.success && simRes?.data) {
        simulationStatus.value = simRes.data.status || ''
      }
      if (runRes?.success && runRes?.data) {
        runnerStatus.value = runRes.data.runner_status || ''
      }
      if (usageRes?.success && usageRes?.data) {
        tokenUsage.value = {
          input: Number(usageRes.data.prompt_tokens || 0),
          output: Number(usageRes.data.completion_tokens || 0),
        }
      }
    } catch { /* ignore */ }
  }, 4000)
}

watch(showSimulationOverlay, (val) => {
  if (val) startStatusPoll()
  else if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
})

watch(
  showSimulationOverlay,
  (val) => {
    if (val) {
      setTimeout(() => {
        overlayMounted.value = true
      }, 50)
    } else {
      overlayMounted.value = false
    }
  },
  { immediate: true }
)

// Load sessions on mount and when route changes
onMounted(() => {
  // Clean any stale OAuth callback params from URL
  try {
    const params = new URLSearchParams(window.location.search)
    if (params.get('hivemind_auth')) {
      const cleanUrl = new URL(window.location.href)
      cleanUrl.searchParams.delete('token')
      cleanUrl.searchParams.delete('hivemind_auth')
      window.history.replaceState({}, '', cleanUrl.toString())
    }
  } catch {}

  loadSessions()
})

watch(() => route.path, () => {
  loadSessions()
})

watch(
  [() => route.params.simulationId, () => route.params.reportId],
  ([newSimId, newRepId]) => {
    if (newSimId) {
      loadSimulationRequirement(newSimId)
    } else if (newRepId) {
      loadReportSimulation(newRepId)
    } else {
      simulationRequirement.value = ''
      loadedSimulationId.value = ''
      loadedReportId.value = ''
    }
  },
  { immediate: true }
)
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

.app-root-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Persistent top navbar */
.top-navbar {
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(250, 249, 244, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #e3e0db;
  z-index: 60;
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.navbar-logo {
  height: 18px;
  width: auto;
  filter: invert(1);
}

.navbar-divider {
  width: 1px;
  height: 18px;
  background: #d4d0ca;
}

.navbar-title {
  font-size: 14px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.navbar-subtitle {
  font-size: 12px;
  color: #a3a3a3;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.navbar-token-counter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f0ede6;
  border: 1px solid #dcd8cf;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #4a4a4a;
  cursor: help;
  position: relative;
}

.navbar-token-counter:hover .tokens-tooltip {
  display: flex;
}

.tokens-tooltip {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  background: #333;
  color: #fff;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 10px;
  flex-direction: column;
  gap: 4px;
  white-space: nowrap;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.tokens-label {
  opacity: 0.6;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 9px;
}

.tokens-value {
  color: #000;
}

.navbar-status {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  background: #f3f1ec;
  border: 1px solid #e3e0db;
}

.navbar-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #a3a3a3;
}

.navbar-status-dot.processing { background: #117dff; }
.navbar-status-dot.ready { background: #16a34a; }

.navbar-status-text {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

/* Main content area (below navbar) */
.app-main {
  flex: 1;
  overflow: hidden;
  position: relative;
  background: #faf9f4;
}

.chat-card-wrapper {
  position: fixed;
  left: 50%;
  bottom: 16px;
  width: 44vw;
  max-width: 560px;
  z-index: 1100;
  pointer-events: none;
  transform: translateX(-50%);
}

.chat-card-wrapper .chat-input {
  min-height: 32px;
  font-size: 13px;
}

.chat-card-wrapper .card-body {
  padding: 6px 14px 4px;
}

.chat-card {
  width: 100%;
  background: #FFF;
  border: 1px solid #e3e0db;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  pointer-events: auto;
  transition: all 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}

.card-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #faf9f4;
  border-bottom: 1px solid #f0efeb;
}

.traffic-lights {
  display: flex;
  gap: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot.red { background: #FF5F57; }
.dot.yellow { background: #FEBC2E; }
.dot.green { background: #28C840; }

.card-label {
  font-size: 11px;
  font-weight: 500;
  color: #a3a3a3;
  letter-spacing: 0.3px;
  text-transform: none;
}

.card-chrome-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-stage {
  font-size: 11px;
  font-weight: 600;
  color: #111827;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.card-body {
  padding: 14px 20px 14px;
}

.chat-context {
  display: none;
}

.chat-input {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #000000;
  background: transparent;
  min-height: 56px;
}

.chat-input::placeholder {
  color: #b0ada8;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  border-top: 1px solid #f0efeb;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.attach-btn {
  width: 30px;
  height: 30px;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  background: #FFF;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #737373;
  font-size: 16px;
  flex-shrink: 0;
}

.attach-plus {
  line-height: 1;
}

.status-text {
  font-size: 12px;
  color: #117dff;
  display: flex;
  align-items: center;
  gap: 4px;
}

.spin {
  display: inline-block;
  animation: spinning 0.8s linear infinite;
  line-height: 1;
}

@keyframes spinning {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.submit-btn {
  padding: 5px 14px;
  border-radius: 8px;
  border: none;
  background: #000000;
  color: #FFF;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.submit-btn:hover:not(:disabled) {
  background: #333;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Continuation-ready state */
.chat-card.can-continue {
  border-color: #117dff;
  box-shadow: 0 0 0 1px rgba(17, 125, 255, 0.1), 0 -8px 40px rgba(0,0,0,0.06);
}

.chat-card.can-continue .submit-btn {
  background: #117dff;
}

.chat-card.can-continue .submit-btn:hover:not(:disabled) {
  background: #0d5fcc;
}

.card-status-pill {
  font-size: 10px;
  font-weight: 500;
  color: #117dff;
  background: rgba(17, 125, 255, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
  margin-left: auto;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
}

.status-dot.ready {
  background: #16a34a;
}

.status-dot.active {
  background: #117dff;
  animation: dot-pulse 1.4s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

@media (max-width: 768px) {
  .chat-card-wrapper {
    width: calc(100% - 32px);
    max-width: none;
  }
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #000000;
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>
