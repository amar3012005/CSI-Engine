<template>
  <div class="workspace-view">
    <AppSidebar
      :collapsed="leftNavCollapsed"
      :activeSession="activeSessionInfo"
      :sessions="sidebarHistory"
      @toggle="leftNavCollapsed = !leftNavCollapsed"
      @go-home="goHome"
      @select-session="navigateToSimulation"
      @delete-session="handleDeleteSession"
    />

    <div class="graph-stage" :style="{ left: leftNavCollapsed ? '68px' : '260px' }">
      <GraphPanel
        :graphData="graphData"
        :loading="graphLoading"
        :currentPhase="currentPhase"
        :isSimulating="simulationRunning"
        :simulationId="graphSimulationId"
        :csiAutoRefresh="csiAutoRefresh"
        :reportId="currentReportId"
        :rightInset="sidebarCollapsed ? 0 : drawerWidth"
        :agentProfiles="agentProfiles"
        @refresh="refreshGraph"
      />
    </div>

    <aside class="workspace-drawer" :class="{ collapsed: sidebarCollapsed }" :style="{ width: `${drawerWidth}px` }">
      <!-- Resize handle (left edge) -->
      <div
        v-if="!sidebarCollapsed"
        class="drawer-resize-handle"
        :class="{ active: isResizing }"
        @mousedown.prevent="startResize"
      ></div>
      <div class="drawer-shell">
        <!-- Minimal tab bar -->
        <div v-if="!sidebarCollapsed" class="drawer-tab-bar">
          <div class="drawer-tabs-row">
            <button
              v-for="stage in STAGES"
              :key="stage.key"
              class="drawer-tab"
              :class="{
                active: activeStage === stage.key,
                running: isStageRunning(stage.key)
              }"
              type="button"
              @click="selectStage(stage.key)"
            >
              <span v-if="isStageRunning(stage.key)" class="tab-live-dot"></span>
              <span class="tab-label">{{ stage.label }}</span>
            </button>
          </div>
          <div class="drawer-tab-actions">
            <button class="drawer-collapse-btn" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
              <span class="collapse-chevron">&#8250;</span>
            </button>
            <button class="drawer-close-btn" type="button" @click="sidebarCollapsed = true">&times;</button>
          </div>
        </div>

        <!-- Collapsed expand button -->
        <div v-if="sidebarCollapsed" class="drawer-expand-trigger" @click="sidebarCollapsed = false">
          <span class="expand-chevron">&#8249;</span>
        </div>

        <div v-if="!sidebarCollapsed" class="drawer-body">
          <EnvironmentIngestionPanel
            v-if="activeStage === 'environment' && hasPendingIngestion"
            :pending="pendingUpload"
            @go-back="goHome"
            @add-log="addLog"
            @project-updated="handlePendingProjectUpdated"
            @graph-updated="handlePendingGraphUpdated"
            @simulation-created="handlePendingSimulationCreated"
          />

          <Step2EnvSetup
            v-else-if="activeStage === 'environment' && hasRealSimulation"
            :simulationId="currentSimulationId"
            :projectData="projectData"
            :graphData="graphData"
            :configMode="workspaceConfigMode"
            :systemLogs="systemLogs"
            :autoStart="environmentAutoStart"
            :agentProfiles="agentProfiles"
            @go-back="goHome"
            @next-step="handleEnvironmentNext"
            @add-log="addLog"
            @update-status="updateWorkspaceStatus"
            @agent-click="openAgentDetail"
            @profiles-updated="handleProfilesUpdated"
          />

          <Step3Simulation
            v-if="activeStage === 'simulation'"
            :simulationId="currentSimulationId"
            :maxRounds="currentMaxRounds"
            :projectData="projectData"
            :graphData="graphData"
            :systemLogs="systemLogs"
            :minutesPerRound="minutesPerRound"
            :embedded="true"
            :reportStarted="reportStarted"
            :agentProfiles="agentProfiles"
            @go-back="selectStage('environment')"
            @next-step="handleSimulationNext"
            @add-log="addLog"
            @update-status="updateWorkspaceStatus"
          />

          <ReportWorkspacePanel
            v-else-if="activeStage === 'report'"
            :simulationId="currentSimulationId"
            :reportId="currentReportId"
            :reportStarted="reportStarted"
            @report-loaded="handleReportLoaded"
          />
        </div>

      </div>
    </aside>

    <AgentMessageDock
      :profiles="agentProfiles"
      :simulationId="currentSimulationId"
      @agent-click="openAgentDetail"
    />

    <AgentDetailOverlay
      :agent="selectedAgent"
      @close="closeAgentDetail"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EnvironmentIngestionPanel from '../components/EnvironmentIngestionPanel.vue'
import GraphPanel from '../components/GraphPanel.vue'
import ReportWorkspacePanel from '../components/ReportWorkspacePanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import { getProject, getGraphData } from '../api/graph'
import { getPaperReportBySimulation, getReport } from '../api/report'
import { continueSimulation, getSimulation, getSimulationConfigRealtime, getRunStatus, getSimulationTokenUsage } from '../api/simulation'
import { getPendingUpload } from '../store/pendingUpload'
import { useSidebar } from '../store/sidebar'
import AgentDetailOverlay from '../components/ui/AgentDetailOverlay.vue'
import AppSidebar from '../components/ui/AppSidebar.vue'
import AgentMessageDock from '../components/ui/AgentMessageDock.vue'
import { getSimulationProfilesRealtime } from '../api/simulation'
import { getAvatarUrl } from '../utils/avatarResolver'
import davinciLogo from '../assets/davinci-logo.svg'

const route = useRoute()
const router = useRouter()
const { sidebarCollapsed } = useSidebar()

const STAGE_STORAGE_PREFIX = 'mirofish_workspace_stage_'
const REPORT_STORAGE_PREFIX = 'mirofish_workspace_report_'
const DRAWER_WIDTH_KEY = 'mirofish_workspace_drawer_width'

const STAGES = [
  { key: 'environment', label: 'Environment', index: '01' },
  { key: 'simulation', label: 'Simulation', index: '02' },
  { key: 'report', label: 'Report', index: '03' }
]

const props = defineProps({
  simulationId: String
})

const currentSimulationId = computed(() => String(route.params.simulationId || props.simulationId || ''))
const stageStorageKey = computed(() => `${STAGE_STORAGE_PREFIX}${currentSimulationId.value}`)
const reportStorageKey = computed(() => `${REPORT_STORAGE_PREFIX}${currentSimulationId.value}`)
const hasRealSimulation = computed(() => Boolean(currentSimulationId.value) && currentSimulationId.value !== 'new')
const pendingUpload = ref(getPendingUpload())
const hasPendingIngestion = computed(() => !hasRealSimulation.value && pendingUpload.value?.isPending)
const graphSimulationId = computed(() => {
  if (!hasRealSimulation.value) return ''
  // Keep a single graph renderer, but only attach CSI stream outside environment stage.
  return activeStage.value === 'simulation' || activeStage.value === 'report'
    ? currentSimulationId.value
    : ''
})

const activeStage = ref('environment')
const leftNavCollapsed = ref(true)
const tokenUsage = ref({ input: 0, output: 0 })
const followUpQuery = ref('')
const isContinuing = ref(false)

const formatTokenCount = (n) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}
const sidebarHistory = ref([])

const loadSidebarHistory = async () => {
  try {
    const { getSimulationHistory } = await import('../api/simulation')
    if (getSimulationHistory) {
      const res = await getSimulationHistory(20)
      if (res?.success && res?.data) {
        sidebarHistory.value = (res.data.simulations || res.data || []).map(s => ({
          id: s.simulation_id,
          label: (s.simulation_requirement || s.project_name || s.simulation_id || '').substring(0, 50),
          simulationId: s.simulation_id,
        }))
      }
    }
  } catch {
    // best-effort
  }
}

const refreshTokenUsage = async () => {
  if (!hasRealSimulation.value) {
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

const navigateToSimulation = (simId) => {
  router.push({ name: 'Simulation', params: { simulationId: simId } })
}

const handleDeleteSession = async (simId) => {
  if (!confirm('Delete this session and all its data? This cannot be undone.')) return
  try {
    const { deleteSimulation } = await import('../api/simulation')
    const res = await deleteSimulation(simId)
    if (res?.success) {
      // Remove from sidebar history
      sidebarHistory.value = sidebarHistory.value.filter(s => s.simulationId !== simId)
      // If deleting the current session, go home
      if (simId === currentSimulationId.value) {
        goHome()
      }
    }
  } catch (err) {
    addLog(`Failed to delete session: ${err.message}`)
  }
}
const drawerWidth = ref(Math.min(Number(localStorage.getItem(DRAWER_WIDTH_KEY) || 400), window.innerWidth * 0.25))
const isResizing = ref(false)
let resizeStartX = 0
let resizeStartWidth = 0

const startResize = (e) => {
  isResizing.value = true
  resizeStartX = e.clientX
  resizeStartWidth = drawerWidth.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const onResize = (e) => {
  if (!isResizing.value) return
  const delta = resizeStartX - e.clientX
  const next = Math.max(280, Math.min(resizeStartWidth + delta, window.innerWidth * 0.25))
  drawerWidth.value = next
}

const stopResize = () => {
  isResizing.value = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  localStorage.setItem(DRAWER_WIDTH_KEY, String(drawerWidth.value))
}

const graphLoading = ref(false)
const graphData = ref(null)
const projectData = ref(null)
const simulationData = ref(null)
const systemLogs = ref([])
const workspaceStatus = ref('processing')
const currentMaxRounds = ref(null)
const simulationUnlocked = ref(false)
const simulationRunning = ref(false)
const simulationCompleted = ref(false)
const reportStarted = ref(false)
const reportCompleted = ref(false)
const currentReportId = ref(String(route.query.reportId || localStorage.getItem(reportStorageKey.value) || ''))
const minutesPerRound = ref(30)
const agentProfiles = ref([])
const selectedAgentId = ref(null)
const workspaceConfigMode = ref(String(route.query.configMode || 'web_research'))
let workspaceTimer = null

const visibleStages = computed(() => {
  return STAGES.filter((stage) => {
    if (stage.key === 'environment') return true
    if (!hasRealSimulation.value) return false
    if (stage.key === 'simulation') return simulationUnlocked.value
    if (stage.key === 'report') return reportUnlocked.value
    return false
  })
})

const reportUnlocked = computed(() => reportStarted.value || Boolean(currentReportId.value))

const environmentAutoStart = computed(() => !simulationUnlocked.value && !reportUnlocked.value)

const currentPhase = computed(() => {
  const map = {
    environment: 2,
    simulation: 3,
    report: 4
  }
  return map[activeStage.value] || 2
})

const csiAutoRefresh = computed(() => {
  // Always refresh during active work — environment prep, simulation running, report generating
  if (simulationRunning.value) return true
  if (reportUnlocked.value && !reportCompleted.value) return true
  // During environment stage when not yet completed (agents spawning)
  if (activeStage.value === 'environment' && !simulationCompleted.value && hasRealSimulation.value) return true
  return false
})

const projectRequirementTitle = computed(() => {
  if (hasPendingIngestion.value) {
    return pendingUpload.value?.simulationRequirement || 'Pending DeepResearch workspace'
  }
  return projectData.value?.simulation_requirement || `Simulation ${currentSimulationId.value}`
})

const activeSessionInfo = computed(() => {
  if (!hasRealSimulation.value) return null
  return {
    title: projectRequirementTitle.value,
    id: currentSimulationId.value,
    checkpoints: simulationData.value?.checkpoints || []
  }
})

const canContinueSimulation = computed(() => hasRealSimulation.value && simulationCompleted.value && !simulationRunning.value)

const continuationPlaceholder = computed(() => {
  if (isContinuing.value) return 'Continuing current session...'
  if (simulationRunning.value) return 'Simulation in progress...'
  if (canContinueSimulation.value) return 'Ask a follow-up question...'
  return 'Continuation unlocks after the current run completes'
})

const workspaceStatusLabel = computed(() => {
  if (hasPendingIngestion.value) return 'Processing uploaded sources'
  if (workspaceStatus.value === 'error') return 'Attention needed'
  if (reportCompleted.value) return 'Report completed'
  if (reportStarted.value) return 'Generating report'
  if (simulationRunning.value) return 'Simulation running'
  if (simulationUnlocked.value) return 'Environment ready'
  return 'Preparing environment'
})

const workspaceStatusClass = computed(() => {
  if (hasPendingIngestion.value) return 'processing'
  if (workspaceStatus.value === 'error') return 'error'
  if (reportCompleted.value) return 'completed'
  if (reportStarted.value) return 'processing'
  if (simulationRunning.value) return 'processing'
  if (simulationUnlocked.value) return 'ready'
  return 'processing'
})

const normalizeProfiles = (rawProfiles) => {
  return rawProfiles.map((profile, index) => {
    const name = profile.username || profile.name || profile.agent_name || `Agent ${index + 1}`
    return {
      id: profile.agent_id ?? profile.id ?? index,
      name,
      entityType: profile.entity_type || profile.profession || 'Researcher',
      bio: profile.bio || '',
      persona: profile.persona || '',
      researchRole: profile.research_role || profile.role || '',
      responsibility: profile.responsibility || '',
      evidencePriority: profile.evidence_priority || '',
      skills: profile.skills || [],
      worldActions: profile.world_actions || [],
      peerActions: profile.peer_actions || [],
      challengeTargets: profile.challenge_targets || [],
      qualificationScore: profile.qualification_score || 0,
      avatarPath: getAvatarUrl(index),
      initials: String(name)
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join('')
        .toUpperCase(),
      roleEmoji: roleEmojiForProfile(profile.research_role)
    }
  })
}

const roleEmojiForProfile = (role) => {
  const lowered = String(role || '').toLowerCase()
  if (lowered.includes('challenge')) return '\u2694\uFE0F'
  if (lowered.includes('fact')) return '\u2705'
  if (lowered.includes('domain')) return '\uD83D\uDD2C'
  if (lowered.includes('synth')) return '\uD83E\uDDEC'
  if (lowered.includes('method')) return '\uD83D\uDCD0'
  if (lowered.includes('editor')) return '\u270D\uFE0F'
  return '\uD83E\uDDE0'
}

const selectedAgent = computed(() => {
  if (selectedAgentId.value === null) return null
  return agentProfiles.value.find((a) => a.id === selectedAgentId.value) || null
})

const openAgentDetail = (id) => {
  selectedAgentId.value = id
}

const closeAgentDetail = () => {
  selectedAgentId.value = null
}

const handleProfilesUpdated = (rawProfiles) => {
  agentProfiles.value = normalizeProfiles(rawProfiles)
}

const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const stageStateClass = (stage) => {
  if (stage === activeStage.value) return 'active'
  if (stage === 'report' && reportCompleted.value) return 'completed'
  if (stage === 'simulation' && simulationCompleted.value) return 'completed'
  if (stage === 'simulation' && simulationUnlocked.value) return 'ready'
  if (stage === 'report' && reportUnlocked.value) return 'ready'
  return 'pending'
}

const stageStateLabel = (stage) => {
  if (stage === activeStage.value) return 'Current'
  if (stage === 'report' && reportCompleted.value) return 'Done'
  if (stage === 'simulation' && simulationCompleted.value) return 'Done'
  if (stage === 'simulation' && simulationUnlocked.value) return 'Ready'
  if (stage === 'report' && reportUnlocked.value) return 'Ready'
  return 'Locked'
}

const updateWorkspaceStatus = (status) => {
  workspaceStatus.value = status
}

const persistStage = () => {
  if (!hasRealSimulation.value) return
  localStorage.setItem(stageStorageKey.value, activeStage.value)
  if (currentReportId.value) {
    localStorage.setItem(reportStorageKey.value, currentReportId.value)
  } else {
    localStorage.removeItem(reportStorageKey.value)
  }
}

const replaceWorkspaceQuery = async () => {
  const nextQuery = {
    ...route.query,
    stage: activeStage.value
  }
  if (currentReportId.value) {
    nextQuery.reportId = currentReportId.value
  } else {
    delete nextQuery.reportId
  }
  if (workspaceConfigMode.value) {
    nextQuery.configMode = workspaceConfigMode.value
  }

  const currentStageQuery = String(route.query.stage || '')
  const currentReportQuery = String(route.query.reportId || '')
  const currentConfigQuery = String(route.query.configMode || '')
  if (
    currentStageQuery === String(nextQuery.stage || '') &&
    currentReportQuery === String(nextQuery.reportId || '') &&
    currentConfigQuery === String(nextQuery.configMode || '')
  ) {
    return
  }

  await router.replace({
    name: 'Simulation',
    params: { simulationId: currentSimulationId.value },
    query: nextQuery
  })
}

const isStageRunning = (stage) => {
  if (stage === 'environment') return workspaceStatus.value === 'processing' && !simulationUnlocked.value
  if (stage === 'simulation') return simulationRunning.value
  if (stage === 'report') return reportStarted.value && !reportCompleted.value
  return false
}

const selectStage = async (stage) => {
  activeStage.value = stage
  persistStage()
  await replaceWorkspaceQuery()
}

const goHome = () => {
  router.push('/')
}

const refreshGraph = async () => {
  if (!projectData.value?.graph_id) return
  graphLoading.value = true
  try {
    const res = await getGraphData(projectData.value.graph_id)
    if (res.success) {
      graphData.value = res.data
    }
  } catch (err) {
    addLog(`Graph refresh failed: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const inferSimulationStatus = (runData = {}) => {
  const runnerStatus = String(runData.runner_status || '')
  simulationRunning.value = runnerStatus === 'running' || runnerStatus === 'processing'
  simulationCompleted.value =
    runnerStatus === 'completed' ||
    runnerStatus === 'stopped' ||
    runnerStatus === 'failed' ||
    runData.twitter_completed === true ||
    runData.reddit_completed === true
}

const chooseInitialStage = async () => {
  if (!hasRealSimulation.value) {
    activeStage.value = 'environment'
    return
  }
  const requested = String(route.query.stage || '')
  const saved = localStorage.getItem(stageStorageKey.value) || ''
  const fallback = reportUnlocked.value ? 'report' : simulationUnlocked.value ? 'simulation' : 'environment'
  const desired = requested || saved || fallback

  if (desired === 'report' && reportUnlocked.value) {
    await selectStage('report')
    return
  }
  if (desired === 'simulation' && simulationUnlocked.value) {
    await selectStage('simulation')
    return
  }
  await selectStage('environment')
}

const hydrateWorkspace = async ({ initial = false } = {}) => {
  if (!hasRealSimulation.value) {
    if (initial) {
      activeStage.value = 'environment'
    }
    return
  }

  try {
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      simulationData.value = simRes.data
      workspaceConfigMode.value = String(simRes.data.config_mode || workspaceConfigMode.value || 'web_research')

      if (simRes.data.project_id) {
        const projectRes = await getProject(simRes.data.project_id)
        if (projectRes.success && projectRes.data) {
          projectData.value = projectRes.data
          workspaceConfigMode.value = String(route.query.configMode || projectRes.data.config_mode || workspaceConfigMode.value || 'web_research')
          if (!graphData.value && projectRes.data.graph_id) {
            graphLoading.value = true
            try {
              const graphRes = await getGraphData(projectRes.data.graph_id)
              if (graphRes.success) {
                graphData.value = graphRes.data
              }
            } finally {
              graphLoading.value = false
            }
          }
        }
      }

      simulationUnlocked.value = Boolean(
        simRes.data.config_generated ||
        ['ready', 'running', 'completed', 'stopped', 'failed'].includes(String(simRes.data.status || ''))
      )

      // Fetch agent profiles for roster
      try {
        const profilesRes = await getSimulationProfilesRealtime(currentSimulationId.value, 'reddit')
        if (profilesRes?.success && profilesRes.data?.profiles) {
          agentProfiles.value = normalizeProfiles(profilesRes.data.profiles)
        }
      } catch {
        // Profiles may not exist yet
      }
    }

    await refreshTokenUsage()

    try {
      const configRes = await getSimulationConfigRealtime(currentSimulationId.value)
      if (configRes.success && configRes.data) {
        workspaceConfigMode.value = String(configRes.data.config?.config_mode || workspaceConfigMode.value)
        if (configRes.data.config_generated && configRes.data.config?.time_config?.minutes_per_round) {
          simulationUnlocked.value = true
          minutesPerRound.value = configRes.data.config.time_config.minutes_per_round
        }
      }
    } catch {
      // Config may not exist yet.
    }

    try {
      const runRes = await getRunStatus(currentSimulationId.value)
      if (runRes.success && runRes.data) {
        inferSimulationStatus(runRes.data)
        if (simulationRunning.value || simulationCompleted.value) {
          simulationUnlocked.value = true
        }
      }
    } catch {
      simulationRunning.value = false
    }

    const incomingReportId = String(route.query.reportId || currentReportId.value || '')
    if (incomingReportId) {
      currentReportId.value = incomingReportId
      reportStarted.value = true
      try {
        const reportRes = await getReport(incomingReportId)
        if (reportRes.success && reportRes.data) {
          reportCompleted.value = String(reportRes.data.status || '').toLowerCase() === 'completed'
        }
      } catch {
        reportCompleted.value = false
      }
    } else if (simulationCompleted.value || reportUnlocked.value) {
      try {
        const reportLookup = await getPaperReportBySimulation(currentSimulationId.value)
        if (reportLookup.success && reportLookup.data) {
          currentReportId.value = reportLookup.data.report_id
          reportStarted.value = true
          reportCompleted.value = String(reportLookup.data.status || '').toLowerCase() === 'completed'
        }
      } catch {
        // No report yet.
      }
    }

    persistStage()
    if (initial) {
      await chooseInitialStage()
    }
  } catch (err) {
    addLog(`Failed to hydrate workspace: ${err.message}`)
  }
}

const startWorkspacePolling = () => {
  if (!hasRealSimulation.value) return
  if (workspaceTimer) return
  workspaceTimer = setInterval(() => {
    // Stop polling only when fully idle: sim done + report done (or no report) + not continuing
    if (simulationCompleted.value && (reportCompleted.value || !reportStarted.value) && !isContinuing.value) {
      stopWorkspacePolling()
      return
    }
    hydrateWorkspace()
  }, 5000)
}

const stopWorkspacePolling = () => {
  if (!workspaceTimer) return
  clearInterval(workspaceTimer)
  workspaceTimer = null
}

const handleEnvironmentNext = async (payload = {}) => {
  currentMaxRounds.value = payload?.maxRounds || null
  simulationUnlocked.value = true
  await selectStage('simulation')
}

const handlePendingProjectUpdated = (project) => {
  if (!project) return
  projectData.value = project
}

const handlePendingGraphUpdated = (graph) => {
  if (!graph) return
  graphData.value = graph
}

const handlePendingSimulationCreated = async ({ simulationId }) => {
  pendingUpload.value = getPendingUpload()
  const nextQuery = { ...route.query, stage: 'environment', configMode: 'deepresearch' }
  delete nextQuery.pendingUpload
  await router.replace({
    name: 'Simulation',
    params: { simulationId },
    query: nextQuery
  })
}

const handleSimulationNext = async (payload = {}) => {
  if (payload?.reportId) {
    currentReportId.value = payload.reportId
    reportStarted.value = true
    reportCompleted.value = false
    persistStage()
    await selectStage('report')
    startWorkspacePolling()
    return
  }

  simulationUnlocked.value = true
  await selectStage('simulation')
}

const handleReportLoaded = (report) => {
  if (!report) return
  if (report.report_id) {
    currentReportId.value = report.report_id
    reportStarted.value = true
  }
  reportCompleted.value = String(report.status || '').toLowerCase() === 'completed'
  persistStage()
}

const submitContinuation = async () => {
  const query = followUpQuery.value.trim()
  if (!query || !canContinueSimulation.value || isContinuing.value) return

  isContinuing.value = true
  addLog(`Continuing simulation with follow-up query: ${query}`)

  try {
    const res = await continueSimulation(currentSimulationId.value, query)
    if (!res?.success) {
      throw new Error(res?.error || 'Failed to continue simulation')
    }

    followUpQuery.value = ''
    currentReportId.value = ''
    reportStarted.value = false
    reportCompleted.value = false
    simulationCompleted.value = false
    simulationRunning.value = false
    simulationUnlocked.value = false

    addLog(`Checkpoint ${res.data?.checkpoint_id || 'saved'} created. Ready for a new run.`)
    // Go to Environment to show agents re-spawning
    await selectStage('environment')
    await hydrateWorkspace({ initial: true })
    loadSidebarHistory()
    // Restart polling to detect the new simulation starting
    stopWorkspacePolling()
    startWorkspacePolling()
  } catch (err) {
    addLog(`Continuation failed: ${err.message}`)
  } finally {
    isContinuing.value = false
  }
}

watch(
  () => route.params.simulationId,
  async () => {
    stopWorkspacePolling()
    pendingUpload.value = getPendingUpload()
    currentReportId.value = String(route.query.reportId || localStorage.getItem(reportStorageKey.value) || '')
    reportStarted.value = Boolean(currentReportId.value)
    reportCompleted.value = false
    graphData.value = null
    projectData.value = null
    simulationData.value = null
    simulationUnlocked.value = false
    simulationRunning.value = false
    simulationCompleted.value = false
    await hydrateWorkspace({ initial: true })
    startWorkspacePolling()
  }
)

watch(
  () => route.query.stage,
  (stage) => {
    const requested = String(stage || '')
    if (!requested || requested === activeStage.value) return
    if (requested === 'report' && reportUnlocked.value) {
      activeStage.value = 'report'
    } else if (requested === 'simulation' && simulationUnlocked.value) {
      activeStage.value = 'simulation'
    } else {
      activeStage.value = 'environment'
    }
    persistStage()
  }
)

watch(
  () => route.query.reportId,
  (reportId) => {
    const nextId = String(reportId || '')
    if (!nextId || nextId === currentReportId.value) return
    currentReportId.value = nextId
    reportStarted.value = true
    persistStage()
  }
)

// Auto-navigate between stages based on progress
// Environment → Simulation (when simulation starts running)
watch(simulationRunning, (running) => {
  if (running && activeStage.value === 'environment') {
    selectStage('simulation')
  }
})

// Simulation → Report (when simulation completes and report starts)
watch(simulationCompleted, (completed) => {
  if (completed && activeStage.value === 'simulation' && reportStarted.value) {
    selectStage('report')
  }
})

watch(reportStarted, (started) => {
  if (started && simulationCompleted.value && activeStage.value === 'simulation') {
    selectStage('report')
  }
})

onMounted(async () => {
  // Start with sidebar collapsed for the reveal effect
  sidebarCollapsed.value = true
  
  // Start data loading immediately but don't await blocking UI
  hydrateWorkspace({ initial: true })

  addLog('Unified simulation workspace initialized')
  pendingUpload.value = getPendingUpload()
  loadSidebarHistory()
  
  // Elegantly reveal elements like a movie sequence
  setTimeout(() => {
    // Open the right-side preview/drawer
    sidebarCollapsed.value = false
  }, 400)

  startWorkspacePolling()
})

onBeforeUnmount(() => {
  stopWorkspacePolling()
})
</script>

<style scoped>
/* ─── Workspace Layout ─────────────────────────── */
.workspace-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #faf9f4;
  display: flex;
  flex-direction: column;
}

/* ─── Top Navbar ──────────────────────────────── */
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
  letter-spacing: -0.01em;
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
  gap: 8px;
}

.navbar-tokens {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  background: #f3f1ec;
  border: 1px solid #e3e0db;
}

.token-label {
  font-size: 9px;
  font-weight: 600;
  color: #a3a3a3;
  letter-spacing: 0.04em;
}

.token-value {
  font-size: 11px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'JetBrains Mono', monospace;
}

.token-sep {
  font-size: 10px;
  color: #d4d0ca;
  margin: 0 2px;
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

.navbar-status-dot.processing {
  background: #117dff;
  animation: nav-blink 1.4s ease-in-out infinite;
}

.navbar-status-dot.ready,
.navbar-status-dot.completed {
  background: #16a34a;
}

.navbar-status-dot.error {
  background: #dc2626;
}

@keyframes nav-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.navbar-status-text {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
  white-space: nowrap;
}

/* ─── Left sidebar (Da-vinci HIVEMIND theme) ──── */
.sim-sidebar {
  position: absolute;
  top: 48px;
  left: 0;
  bottom: 0;
  width: 260px;
  z-index: 50;
  background: #faf9f4;
  border-right: 1px solid #e3e0db;
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}

.sim-sidebar.collapsed {
  width: 68px;
}

/* Logo row */
.sb-logo-row {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid #e3e0db;
  flex-shrink: 0;
}

.sb-logo-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.sb-hex-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: rgba(17, 125, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #117dff;
  flex-shrink: 0;
}

.sb-logo-text {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sb-brand-name {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.sb-brand-sub {
  font-size: 10px;
  color: #a3a3a3;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}

.sb-collapse-btn {
  padding: 4px;
  border: none;
  background: none;
  color: #a3a3a3;
  font-size: 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.sb-collapse-btn:hover {
  background: #f3f1ec;
  color: #525252;
}

/* Navigation */
.sb-nav {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sb-nav-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sb-section-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a3a3a3;
  padding: 0 10px;
  margin-bottom: 4px;
}

.sb-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: #525252;
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
  position: relative;
}

.sb-nav-item:hover {
  background: #f3f1ec;
  color: #0a0a0a;
}

.sb-nav-item.active {
  background: #f3f1ec;
  color: #0a0a0a;
  font-weight: 500;
}

.sb-nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
  color: #a3a3a3;
}

.sb-nav-item.active .sb-nav-icon {
  color: #0a0a0a;
}

.sb-nav-item:hover .sb-nav-icon {
  color: #525252;
}

.sb-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Current session card */
.sb-session-card {
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sb-session-text {
  font-size: 12px;
  font-weight: 500;
  color: #0a0a0a;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sb-session-id {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

.sb-empty {
  font-size: 11px;
  color: #a3a3a3;
  padding: 4px 10px;
}

/* Collapsed nav */
.sb-nav-collapsed {
  flex: 1;
  padding: 10px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.sb-icon-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: none;
  border-radius: 8px;
  font-size: 18px;
  color: #a3a3a3;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.sb-icon-btn:hover {
  background: #f3f1ec;
  color: #525252;
}

.sb-icon-btn.active {
  background: #f3f1ec;
  color: #0a0a0a;
}

.sb-collapsed-sep {
  width: 24px;
  height: 1px;
  background: #e3e0db;
  margin: 4px 0;
}

:deep(.app-sidebar) {
  flex-shrink: 0;
  height: 100%;
}

.graph-stage {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 260px;
  transition: left 0.2s ease;
}

/* ─── Drawer (right-side panel, max 25vw) ──────── */
.workspace-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  max-width: 25vw;
  background: #ffffff;
  border-left: 1px solid #e3e0db;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.06);
  transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: visible;
}

.workspace-drawer.collapsed {
  width: 0 !important;
  max-width: none;
  border-left: 0;
  transform: translateX(100%);
}

.drawer-resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 50;
  background: transparent;
  transition: background 0.2s;
  transform: translateX(-50%);
}

.drawer-resize-handle:hover,
.drawer-resize-handle.active {
  background: rgba(17, 125, 255, 0.3);
}

.drawer-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ─── Tab bar (top of drawer) ─────────────────── */
.drawer-tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 0 12px;
  height: 42px;
  border-bottom: 1px solid #e8e5e0;
  background: #faf9f4;
  flex-shrink: 0;
}

.drawer-tabs-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.drawer-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: transparent;
  color: #8a8a8a;
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.drawer-tab:hover {
  background: rgba(0, 0, 0, 0.04);
  color: #525252;
}

.drawer-tab.active {
  color: #0a0a0a;
  font-weight: 600;
}

.drawer-tab.running .tab-label {
  color: inherit;
}

.tab-label {
  font-size: 12px;
  line-height: 1;
}

/* Green blinking dot for running stages */
.tab-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
  animation: live-blink 1.4s ease-in-out infinite;
}

@keyframes live-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}

/* Tab bar actions (collapse / close) */
.drawer-tab-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.drawer-collapse-btn,
.drawer-close-btn {
  border: none;
  background: transparent;
  color: #a3a3a3;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.drawer-collapse-btn:hover,
.drawer-close-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #525252;
}

.collapse-chevron {
  font-size: 18px;
  font-weight: 300;
}

/* Collapsed expand trigger */
.drawer-expand-trigger {
  position: absolute;
  top: 50%;
  left: -24px;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-right: none;
  border-radius: 8px 0 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.04);
}

.drawer-expand-trigger:hover {
  background: #f3f1ec;
}

.expand-chevron {
  font-size: 16px;
  color: #737373;
  font-weight: 300;
}

/* ─── Body ──────────────────────────────────────── */
.drawer-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.continuation-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-top: 1px solid #e3e0db;
  background: rgba(250, 249, 244, 0.96);
}

.continuation-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid #e3e0db;
  background: #fff;
  color: #0a0a0a;
  font-size: 12px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.continuation-input:focus {
  border-color: #117dff;
  box-shadow: 0 0 0 3px rgba(17, 125, 255, 0.08);
}

.continuation-input:disabled {
  background: #f3f1ec;
  color: #a3a3a3;
  cursor: not-allowed;
}

.continuation-btn {
  height: 38px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #117dff;
  background: #117dff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  cursor: pointer;
  transition: opacity 0.15s ease, transform 0.15s ease, background 0.15s ease;
}

.continuation-btn:hover:not(:disabled) {
  background: #0f6ee0;
}

.continuation-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ─── Responsive ────────────────────────────────── */
@media (max-width: 1200px) {
  .workspace-drawer {
    max-width: 40vw;
  }
}

@media (max-width: 768px) {
  .workspace-drawer {
    left: 0;
    max-width: none;
    width: 100% !important;
  }

  .drawer-resize-handle {
    display: none;
  }
}
</style>
