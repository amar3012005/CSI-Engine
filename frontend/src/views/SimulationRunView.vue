<template>
  <div class="main-view">
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel 
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="3"
          :isSimulating="isSimulating"
          :simulationId="currentSimulationId"
          :csiAutoRefresh="csiShouldAutoRefresh"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Vertical Resizer Handle -->
        <div 
          v-show="viewMode === 'split'"
          class="layout-resizer" 
          :style="{ right: rightPanelWidth + '%' }"
          @mousedown="startDrag"
        ></div>

        <!-- Right Panel: Step3 Start Simulation -->
        <div class="panel-wrapper right" :class="{ dragging: isDragging }" :style="rightPanelStyle">
        <Step3Simulation
          :simulationId="currentSimulationId"
          :maxRounds="maxRounds"
          :minutesPerRound="minutesPerRound"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, getSimulationConfig, stopSimulation, closeSimulationEnv, getEnvStatus } from '../api/simulation'
import { safeGet, safeSet } from '../utils/safeStorage'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// Layout State
const viewMode = ref('split')

// Data State
const currentSimulationId = ref(route.params.simulationId)
// Get maxRounds from query params at init time so child components have it immediately
const maxRounds = ref(route.query.maxRounds ? parseInt(route.query.maxRounds) : null)
const minutesPerRound = ref(30) // default 30 minutes per round
const configMode = ref(route.query.configMode || 'web_research')
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error


// Panel Resizer Logic
const PANEL_WIDTH_KEY = 'mirofish_right_panel_width'
const savedWidth = safeGet(PANEL_WIDTH_KEY)
const rightPanelWidth = ref(savedWidth ? Number(savedWidth) : 42) // Percentage
const isDragging = ref(false)

const startDrag = (e) => {
  isDragging.value = true
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const onDrag = (e) => {
  if (!isDragging.value) return
  const containerWidth = window.innerWidth
  let newWidthPct = 100 - (e.clientX / containerWidth) * 100
  // Constrain between 20% and 80%
  if (newWidthPct < 20) newWidthPct = 20
  if (newWidthPct > 80) newWidthPct = 80
  rightPanelWidth.value = newWidthPct
  safeSet(PANEL_WIDTH_KEY, rightPanelWidth.value)
}

const stopDrag = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  // Graph stays in the background always: 100% width
  return { width: '100%', opacity: 1, zIndex: 1 }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(100%)' }
  return { width: rightPanelWidth.value + '%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Running'
})

const isSimulating = computed(() => currentStatus.value === 'processing')
const isDeepResearchMode = computed(() => configMode.value === 'deepresearch' || configMode.value === 'web_research')
// CSI artifacts should auto-refresh during any simulation, not just deepresearch
const csiShouldAutoRefresh = computed(() => isSimulating.value)

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleGoBack = async () => {
  // Close the running simulation before going back to Step 2
  addLog('Preparing to go back to Step 2, closing simulation...')

  if (currentStatus.value === 'completed') {
    addLog('Simulation already completed; preserving persisted state and returning without restart')
    router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value } })
    return
  }
  
  // Stop polling
  stopGraphRefresh()
  
  try {
    // Try graceful shutdown of simulation environment first
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      addLog('Closing simulation environment...')
      try {
        await closeSimulationEnv({ 
          simulation_id: currentSimulationId.value,
          timeout: 10
        })
        addLog('✓ Simulation environment closed')
      } catch (closeErr) {
        addLog(`Failed to close simulation environment, attempting force stop...`)
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ Simulation force stopped')
        } catch (stopErr) {
          addLog(`Force stop failed: ${stopErr.message}`)
        }
      }
    } else {
      // Environment not running, check if we need to stop the process
      if (isSimulating.value) {
        addLog('Stopping simulation process...')
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ Simulation stopped')
        } catch (err) {
          addLog(`Failed to stop simulation: ${err.message}`)
        }
      }
    }
  } catch (err) {
    addLog(`Failed to check simulation status: ${err.message}`)
  }
  
  // Go back to Step 2 (Environment Setup)
  router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value } })
}

const handleNextStep = () => {
  // Step3Simulation component handles report generation and routing directly
  // This method is a fallback
  addLog('Entering Step 4: Report Generation')
}

// --- Data Logic ---
const loadSimulationData = async () => {
  try {
    addLog(`Loading simulation data: ${currentSimulationId.value}`)
    
    // Get simulation info
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      const simData = simRes.data
      
      // Get simulation config to obtain minutes_per_round
      try {
        const configRes = await getSimulationConfig(currentSimulationId.value)
        if (configRes.success && configRes.data) {
          configMode.value = configRes.data.config_mode || configMode.value
        }
        if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
          minutesPerRound.value = configRes.data.time_config.minutes_per_round
          addLog(`Time config: ${minutesPerRound.value} minutes per round`)
        }
      } catch (configErr) {
        addLog(`Failed to get time config, using defaults: ${minutesPerRound.value} min/round`)
      }
      
      // Get project info
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          addLog(`Project loaded successfully: ${projRes.data.project_id}`)
          
          // Get graph data
          if (projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
          }
        }
      }
    } else {
      addLog(`Failed to load simulation data: ${simRes.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Load exception: ${err.message}`)
  }
}

const loadGraph = async (graphId) => {
  // During simulation, auto-refresh skips full-screen loading to avoid flicker
  // Manual refresh or initial load shows loading
  if (!isSimulating.value) {
    graphLoading.value = true
  }
  
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      if (!isSimulating.value) {
        addLog('Graph data loaded successfully')
      }
    }
  } catch (err) {
    addLog(`Graph load failed: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    loadGraph(projectData.value.graph_id)
  }
}

// --- Auto Refresh Logic ---
let graphRefreshTimer = null

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  addLog('Starting graph auto-refresh (30s)')
  // Refresh immediately, then every 30 seconds
  graphRefreshTimer = setInterval(refreshGraph, 30000)
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
    addLog('Stopping graph auto-refresh')
  }
}

watch(isSimulating, (newValue) => {
  if (newValue) {
    startGraphRefresh()
  } else {
    stopGraphRefresh()
  }
}, { immediate: true })

onMounted(() => {
  addLog('SimulationRunView initialized')

  // Log maxRounds config (value already obtained from query params at init)
  if (maxRounds.value) {
    addLog(`Custom simulation rounds: ${maxRounds.value}`)
  }
  
  loadSimulationData()
})

onUnmounted(() => {
  stopGraphRefresh()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #ebe5df;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Overlay header */
.run-overlay-bar {
  position: absolute;
  top: 12px;
  left: 16px;
  right: 16px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(18px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  z-index: 90;
}

.run-overlay-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.run-overlay-right,
.run-overlay-left {
  display: flex;
  align-items: center;
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 16px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  position: relative;
  overflow: hidden;
  padding-top: 68px;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.dragging {
  transition: none !important;
}

.panel-wrapper.left {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.panel-wrapper.right {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 2;
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(14px);
  box-shadow: -12px 0 36px rgba(15, 23, 42, 0.08);
  border-left: 1px solid rgba(234, 234, 234, 0.9);
}

.panel-wrapper.left {
  border-right: none;
}

.layout-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 12px;
  margin-right: -6px;
  z-index: 100;
  cursor: col-resize;
  background: transparent;
}

.layout-resizer:hover, .layout-resizer:active {
  background: rgba(0,0,0,0.05);
}

</style>
