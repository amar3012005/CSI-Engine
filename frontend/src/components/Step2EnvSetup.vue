<template>
  <div class="env-setup-panel">
    <div class="scroll-container">

      <!-- Status bar -->
      <div class="env-status-bar">
        <div class="env-status-indicator" :class="{ active: !feedComplete, done: feedComplete }">
          <span v-if="feedComplete" class="status-check">&#10003;</span>
          <span v-else class="status-pulse"></span>
        </div>
        <div class="env-status-info">
          <span class="env-status-title">{{ feedComplete ? 'Environment Ready' : phaseLabel }}</span>
          <span class="env-status-meta">{{ simulationId }}</span>
        </div>
        <span v-if="feedComplete" class="env-status-badge done">Ready</span>
        <span v-else class="env-status-badge active">Setting up</span>
      </div>

      <!-- Agent grid (always show when agents available) -->
      <div v-if="agentProfiles.length > 0" class="env-agents-section">
        <div class="agents-header">
          <span class="agents-count">{{ agentProfiles.length }} Agents</span>
          <span v-if="feedComplete" class="agents-badge">Deployed</span>
          <span v-else class="agents-badge spawning">Spawning</span>
        </div>
        <AgentGrid
          :profiles="agentProfiles"
          @agent-click="(id) => $emit('agent-click', id)"
        />
      </div>

      <!-- Compact log (collapsible, below agents) -->
      <details class="env-log-details" :open="!feedComplete">
        <summary class="env-log-summary">
          <span class="log-toggle-label">Activity Log</span>
          <span class="log-count">{{ activityLog.length }}</span>
        </summary>
        <div class="env-log-feed" ref="feedScrollRef">
          <div
            v-for="entry in activityLog"
            :key="entry.id"
            class="log-entry"
            :class="entry.type"
          >
            <span class="log-dot" :class="entry.type"></span>
            <span class="log-text">{{ entry.text }}</span>
            <span class="log-time">{{ entry.elapsed }}</span>
          </div>
        </div>
      </details>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { 
  prepareSimulation, 
  getPrepareStatus, 
  getSimulationProfilesRealtime,
  getSimulationConfig,
  getSimulationConfigRealtime 
} from '../api/simulation'
import CsiArtifactList from './CsiArtifactList.vue'
import AgentGrid from './ui/AgentGrid.vue'

const props = defineProps({
  simulationId: String,  // passed from parent component
  projectData: Object,
  graphData: Object,
  configMode: String,
  systemLogs: Array,
  autoStart: {
    type: Boolean,
    default: true
  },
  compactMode: {
    type: Boolean,
    default: false
  },
  agentProfiles: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'agent-click', 'profiles-updated'])

// Cinematic sandbox sequence
const sandboxSeqOverride = ref(null)
const sandboxPhase = computed(() => {
  if (sandboxSeqOverride.value) return sandboxSeqOverride.value
  if (!prepareStarted.value) return 'idle'
  if (profiles.value.length > 0 || props.agentProfiles.length > 0) return 'done'
  if (currentStage.value === 'generating_profiles') return 'generating'
  return 'creating'
})

// State
const phase = ref(0) // 0: init, 1: generating profiles, 2: generating config, 3: complete
const taskId = ref(null)
const prepareProgress = ref(0)
const currentStage = ref('')
const progressMessage = ref('')
const configMode = ref((props.configMode || 'social').toLowerCase())
const configModeLabel = ref('Dual-Platform Social Simulation')
const selectedConfigMode = ref((props.configMode || '').toLowerCase() || null)
const prepareStarted = ref(false)
const profiles = ref([])
const entityTypes = ref([])
const expectedTotal = ref(null)
const simulationConfig = ref(null)
const showProfilesDetail = ref(true)

// Log dedup: track last logged key info
let lastLoggedMessage = ''
let lastLoggedProfileCount = 0
let lastLoggedConfigStage = ''

// Simulation rounds config
const useCustomRounds = ref(false) // default: use auto-configured rounds
const customMaxRounds = ref(40)   // default recommended: 40 rounds


// Watch stage to update phase
watch(currentStage, (newStage) => {
  if (newStage === 'generating_profiles') {
    phase.value = isDeepResearchMode.value ? 1 : 1
  } else if (newStage === 'collecting_sources') {
    // For web_research / deepresearch mode, seed search is lightweight — advance to phase 3
    phase.value = isDeepResearchMode.value ? 3 : 2
  } else if (newStage === 'generating_config') {
    phase.value = isDeepResearchMode.value ? 1 : 2
    // Entering config generation stage, start polling
    if (!configTimer) {
      addLog(isDeepResearchMode.value ? 'Generating DeepResearch / CSI execution config...' : 'Generating dual-platform simulation config...')
      startConfigPolling()
    }
  } else if (newStage === 'copying_scripts') {
    phase.value = 2 // still in config stage
  }
})

// Calculate auto-generated rounds from config (no hardcoded defaults)
const autoGeneratedRounds = computed(() => {
  if (!simulationConfig.value?.time_config) {
    return null // return null when config not yet generated
  }
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) {
    return null // return null when config data is incomplete
  }
  const calculatedRounds = Math.floor((totalHours * 60) / minutesPerRound)
  // Ensure max rounds not less than 40 (recommended), avoid slider range issues
  return Math.max(calculatedRounds, 40)
})

// Polling timer
let pollTimer = null
let profilesTimer = null
let configTimer = null

// Computed
const displayProfiles = computed(() => {
  if (showProfilesDetail.value) {
    return profiles.value
  }
  return profiles.value.slice(0, 6)
})

const inferredConfigMode = computed(() => {
  const requirement = String(props.projectData?.simulation_requirement || '').toLowerCase()
  const deepResearchSignals = ['report', 'research', 'analysis', 'csi', 'deepresearch', 'web_research', 'websearch']
  return deepResearchSignals.some((token) => requirement.includes(token)) ? 'web_research' : 'social'
})
const requestedConfigMode = computed(() => selectedConfigMode.value || inferredConfigMode.value)

watch(
  () => props.configMode,
  (value) => {
    if (!value) return
    const normalized = String(value).toLowerCase()
    if (normalized === 'social' || normalized === 'deepresearch' || normalized === 'web_research' || normalized === 'health') {
      selectedConfigMode.value = normalized
      configMode.value = normalized
    }
  }
)

const isDeepResearchMode = computed(() => configMode.value === 'deepresearch' || configMode.value === 'web_research')
const isWebResearchMode = computed(() => configMode.value === 'web_research')
const isHealthMode = computed(() => configMode.value === 'health')
const isModeLocked = computed(() => Boolean(props.simulationId))
const stepOneTitle = computed(() => (
  isWebResearchMode.value ? 'Research Workspace Init' : 'Simulation Instance Init'
))
const stepOneStatusLabel = computed(() => (
  isWebResearchMode.value ? 'Bootstrapping' : 'Initializing'
))
const stepOneDescription = computed(() => (
  isWebResearchMode.value
    ? 'Create a query-scoped research workspace and persist the simulation session for the CSI workflow'
    : 'Create a new simulation instance and fetch world parameter templates'
))
const modeSelectorLabel = computed(() => (
  isModeLocked.value ? 'Workflow Mode (locked for this simulation)' : 'Workflow Mode (set before starting)'
))
const prepareButtonLabel = computed(() => (
  isWebResearchMode.value ? 'Start Web Research Environment' : 'Start Environment Setup'
))
const prepareButtonBusyLabel = computed(() => (
  isWebResearchMode.value ? 'Building research environment...' : 'Preparation in progress...'
))
const displayGraphId = computed(() => {
  if (props.projectData?.graph_id) return props.projectData.graph_id
  return isWebResearchMode.value ? 'Not required' : '-'
})
const profilesPreviewTitle = computed(() => (
  isWebResearchMode.value ? 'Research Agent Team' : 'Generated Agent Profiles'
))
const backButtonLabel = computed(() => (
  isWebResearchMode.value ? 'Back to Home' : 'Back'
))
const stepTwoTitle = computed(() => {
  if (configMode.value === 'web_research') return 'Generate Research Agent Team'
  return isDeepResearchMode.value ? 'Plan Research Agent Execution Config' : 'Generate Agent Profiles'
})
const stepTwoDescription = computed(() => (
  configMode.value === 'web_research'
    ? 'Auto-generate a research team (explorer / domain_expert / fact_checker / challenger, etc.) based on user query, as executors for subsequent source collection'
    : (isDeepResearchMode.value
      ? 'Based on entity types, source priorities, and research topics from the knowledge graph, plan a unified research agent roster with roles, skills, and qualification thresholds, then constrain subsequent profile generation'
      : 'Automatically invoke tools to extract entities and relationships from the knowledge graph, initialize simulated individuals, and give them unique behaviors and memories based on real-world seeds')
))
const stepTwoThirdStatLabel = computed(() => isDeepResearchMode.value ? 'Research Focus Count' : 'Seed Topic Count')
const stepThreeTitle = computed(() => {
  if (configMode.value === 'web_research') return 'Collect Sources & Evidence'
  return isDeepResearchMode.value ? 'Generate Research Config & Profile Output' : 'Generate Dual-Platform Simulation Config'
})
const stepThreeDescription = computed(() => (
  configMode.value === 'web_research'
    ? 'Execute web search and deep reading with the research team, collect sources and write to CSI source index'
    : (isDeepResearchMode.value
      ? 'LLM generates CSI / DeepResearch workflow parameters based on the planned research agent roster, constraining final profile output for twitter_profiles.csv and reddit_profiles.json'
      : 'LLM intelligently configures world time flow, recommendation algorithms, activity windows, posting frequency, and event triggers based on simulation requirements and real-world seeds')
))
const stepFourTitle = computed(() => {
  if (configMode.value === 'web_research') return 'Research Execution Orchestration'
  return isDeepResearchMode.value ? 'Research Execution Orchestration' : 'Initial Activation Orchestration'
})
const stepFourDescription = computed(() => (
  isDeepResearchMode.value
    ? 'Organize research rounds, evidence focus, and agent role assignments based on the research workflow config, preparing for Claim / Debate / Verdict execution'
    : 'Auto-generate initial activation events and hot topics based on narrative direction, guiding the simulation world initial state'
))
const stepFiveDescription = computed(() => (
  isDeepResearchMode.value
    ? 'Research execution environment is ready. You can now start the DeepResearch / CSI workflow.'
    : 'Simulation environment is ready. You can now start the simulation.'
))
const startActionLabel = computed(() => (
  isWebResearchMode.value
    ? 'Enter CSI Research Execution'
    : (isDeepResearchMode.value ? 'Start DeepResearch / CSI Execution' : 'Start Dual-World Parallel Simulation')
))

// Get username by agent_id
const getAgentUsername = (agentId) => {
  if (profiles.value && profiles.value.length > agentId && agentId >= 0) {
    const profile = profiles.value[agentId]
    return profile?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}

// Calculate total topic count across all profiles
const totalTopicsCount = computed(() => {
  return profiles.value.reduce((sum, p) => {
    return sum + (p.interested_topics?.length || 0)
  }, 0)
})

// Environment stage pipeline
const envStages = computed(() => {
  if (isHealthMode.value) {
    return [
      { key: 'patient', label: 'Patient Data' },
      { key: 'team', label: 'Team Assembly' },
      { key: 'evidence', label: 'Medical Evidence' },
      { key: 'ready', label: 'Ready' },
    ]
  }
  if (isWebResearchMode.value) {
    return [
      { key: 'bootstrap', label: 'Bootstrap Sandbox' },
      { key: 'agents', label: 'Spawn Agents' },
      { key: 'sources', label: 'Collect Sources' },
      { key: 'orchestrate', label: 'Orchestrate' },
      { key: 'ready', label: 'Ready' },
    ]
  }
  return [
    { key: 'bootstrap', label: 'Bootstrap Sandbox' },
    { key: 'agents', label: 'Generate Agents' },
    { key: 'config', label: 'Build Config' },
    { key: 'orchestrate', label: 'Orchestrate' },
    { key: 'ready', label: 'Ready' },
  ]
})

const currentEnvStageIndex = computed(() => {
  if (phase.value === 0) return 0
  if (phase.value === 1) {
    if (currentStage.value === 'collecting_sources') return 2
    return 1
  }
  if (phase.value === 2) return 2
  if (phase.value === 3) return 3
  if (phase.value >= 4) return 4
  return 0
})

const AVATAR_PALETTES = [
  'linear-gradient(135deg, #1a1a2e, #16213e)',
  'linear-gradient(135deg, #0f3460, #533483)',
  'linear-gradient(135deg, #2d2d2d, #535353)',
  'linear-gradient(135deg, #1b1b2f, #2c2f4a)',
  'linear-gradient(135deg, #141414, #2b2b2b)',
  'linear-gradient(135deg, #0a0a0a, #1c1c1c)',
]
const agentAvatarBg = (idx) => AVATAR_PALETTES[idx % AVATAR_PALETTES.length]



// Methods
const activityLog = ref([])
const feedScrollRef = ref(null)
let activityIdCounter = 0
const feedStartTime = Date.now()

const feedComplete = computed(() => phase.value >= 4)

const phaseLabel = computed(() => {
  if (phase.value === 0) return 'Initializing Environment'
  if (phase.value === 1) return 'Spawning Agents'
  if (phase.value === 2) return 'Configuring World'
  if (phase.value === 3) return 'Connecting Agents'
  return 'Ready'
})

const pushActivity = (text, type = 'info') => {
  const elapsed = Math.round((Date.now() - feedStartTime) / 1000)
  const mins = Math.floor(elapsed / 60)
  const secs = elapsed % 60
  activityLog.value.push({
    id: ++activityIdCounter,
    text,
    type,
    elapsed: mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
  })
  nextTick(() => {
    if (feedScrollRef.value) {
      feedScrollRef.value.scrollTop = feedScrollRef.value.scrollHeight
    }
  })
}

const addLog = (msg) => {
  emit('add-log', msg)
  // Classify log message for activity feed
  const lower = msg.toLowerCase()
  let type = 'info'
  if (lower.includes('agent profile') || lower.includes('generating agent')) type = 'agent'
  else if (lower.includes('complete') || lower.includes('ready') || lower.includes('loaded')) type = 'done'
  else if (lower.includes('config') || lower.includes('preparing') || lower.includes('polling') || lower.includes('task')) type = 'system'
  pushActivity(msg, type)
}

// Handle start simulation button click
const handleStartSimulation = () => {
  // Build params for parent component
  const params = {}

  if (useCustomRounds.value) {
    // Custom rounds: pass max_rounds param
    params.maxRounds = customMaxRounds.value
    addLog(`Starting simulation with custom rounds: ${customMaxRounds.value}`)
  } else {
    // Auto-configured rounds: no max_rounds param
    addLog(`Starting simulation with auto-configured rounds: ${autoGeneratedRounds.value}`)
  }
  
  emit('next-step', params)
}

const maybeAutoAdvanceToSimulation = () => {
  if (!props.autoStart) return
  setTimeout(() => {
    handleStartSimulation()
  }, 1200)
}

const truncateBio = (bio) => {
  if (bio.length > 80) {
    return bio.substring(0, 80) + '...'
  }
  return bio
}

// Auto-start simulation preparation
const startPrepareSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: missing simulationId')
    emit('update-status', 'error')
    return
  }

  if (prepareStarted.value) {
    return
  }
  
  // Mark step 1 complete, begin step 2
  prepareStarted.value = true
  phase.value = 1
  addLog(`Simulation instance created: ${props.simulationId}`)
  addLog('Preparing simulation environment...')
  emit('update-status', 'processing')

  // Cinematic sequence: creating → created → entering → (then computed takes over)
  sandboxSeqOverride.value = 'creating'
  setTimeout(() => { sandboxSeqOverride.value = 'created' }, 1500)
  setTimeout(() => { sandboxSeqOverride.value = 'entering' }, 2800)
  setTimeout(() => { sandboxSeqOverride.value = null }, 4200) // let computed decide
  
  try {
    const simulationRequirement = props.projectData?.simulation_requirement || ''
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5,
      config_mode: requestedConfigMode.value,
    })
    
    if (res.success && res.data) {
      if (res.data.already_prepared) {
        addLog('Detected existing prepared data, reusing')
        await loadPreparedData()
        return
      }
      
      taskId.value = res.data.task_id
      configMode.value = res.data.config_mode || configMode.value
      configModeLabel.value = res.data.config_mode_label || configModeLabel.value
      selectedConfigMode.value = configMode.value
      addLog(`Preparation task started`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)
      
      // Set expected agent total immediately (from prepare API response)
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
        addLog(`Found ${res.data.expected_entities_count} entities from Zep graph`)
        if (res.data.entity_types && res.data.entity_types.length > 0) {
          addLog(`  Entity types: ${res.data.entity_types.join(', ')}`)
        }
      }

      addLog('Polling preparation progress...')
      // Start polling progress
      startPolling()
      // Start realtime profile fetching
      startProfilesPolling()
    } else {
      addLog(`Preparation failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`Preparation error: ${err.message}`)
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  pollTimer = setInterval(pollPrepareStatus, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startProfilesPolling = () => {
  profilesTimer = setInterval(fetchProfilesRealtime, 3000)
}

const stopProfilesPolling = () => {
  if (profilesTimer) {
    clearInterval(profilesTimer)
    profilesTimer = null
  }
}

const pollPrepareStatus = async () => {
  if (!taskId.value && !props.simulationId) return
  
  try {
    const res = await getPrepareStatus({
      task_id: taskId.value,
      simulation_id: props.simulationId
    })
    
    if (res.success && res.data) {
      const data = res.data
      configMode.value = data.config_mode || configMode.value
      configModeLabel.value = data.config_mode_label || configModeLabel.value
      selectedConfigMode.value = configMode.value
      
      // Update progress
      prepareProgress.value = data.progress || 0
      progressMessage.value = data.message || ''
      
      // Parse stage info and output detailed logs
      if (data.progress_detail) {
        currentStage.value = data.progress_detail.current_stage_name || ''
        
        // Output detailed progress log (deduplicated)
        const detail = data.progress_detail
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (logKey !== lastLoggedMessage && detail.item_description) {
          lastLoggedMessage = logKey
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          if (detail.total_items > 0) {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`)
          } else {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`)
          }
        }
      } else if (data.message) {
        // Extract stage from message
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) {
          currentStage.value = match[3].trim()
        }
        // Output message log (deduplicated)
        if (data.message !== lastLoggedMessage) {
          lastLoggedMessage = data.message
          addLog(data.message)
        }
      }
      
      // Check if completed
      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog('Preparation completed')
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(`Preparation failed: ${data.error || 'Unknown error'}`)
        stopPolling()
        stopProfilesPolling()
      }
    }
  } catch (err) {
    console.warn('Poll status failed:', err)
  }
}

const fetchProfilesRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    
    if (res.success && res.data) {
      const prevCount = profiles.value.length
      profiles.value = res.data.profiles || []
      emit('profiles-updated', profiles.value)
      // Only update when API returns a valid value, avoid overwriting existing valid value
      if (res.data.total_expected) {
        expectedTotal.value = res.data.total_expected
      }
      
      // Extract entity types
      const types = new Set()
      profiles.value.forEach(p => {
        if (p.entity_type) types.add(p.entity_type)
      })
      entityTypes.value = Array.from(types)
      
      // Output profile generation progress log (only when count changes)
      const currentCount = profiles.value.length
      if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
        lastLoggedProfileCount = currentCount
        const total = expectedTotal.value || '?'
        const latestProfile = profiles.value[currentCount - 1]
        const profileName = latestProfile?.name || latestProfile?.username || `Agent_${currentCount}`
        if (currentCount === 1) {
          addLog(`Generating agent profiles...`)
        }
        addLog(`Agent profile ${currentCount}/${total}: ${profileName} (${latestProfile?.profession || 'Unknown'})`)

        // All profiles generated
        if (expectedTotal.value && currentCount >= expectedTotal.value) {
          addLog(`All ${currentCount} agent profiles generated`)
        }
      }
    }
  } catch (err) {
    console.warn('Fetch profiles failed:', err)
  }
}

// Config polling
const startConfigPolling = () => {
  configTimer = setInterval(fetchConfigRealtime, 2000)
}

const stopConfigPolling = () => {
  if (configTimer) {
    clearInterval(configTimer)
    configTimer = null
  }
}

const fetchConfigRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      // Output config generation stage log (deduplicated)
      if (data.generation_stage && data.generation_stage !== lastLoggedConfigStage) {
        lastLoggedConfigStage = data.generation_stage
        if (data.generation_stage === 'generating_profiles') {
          addLog(isDeepResearchMode.value ? 'Generating final profile output from unified agent config...' : 'Generating agent profile config...')
        } else if (data.generation_stage === 'generating_config') {
          addLog(isDeepResearchMode.value ? 'Calling LLM to generate research workflow and unified agent config...' : 'Calling LLM to generate simulation config parameters...')
        } else if (data.generation_stage === 'collecting_sources') {
          addLog(isDeepResearchMode.value
            ? '🔍 Running baseline seed search (agents will search reactively during debate)...'
            : 'Collecting sources and writing to CSI source index...')
        }
      }
      
      // If config is generated
      if (data.config_generated && data.config) {
        simulationConfig.value = data.config
        configMode.value = data.config.config_mode || configMode.value
        configModeLabel.value = data.config.mode_label || configModeLabel.value
        selectedConfigMode.value = configMode.value
        addLog(isDeepResearchMode.value ? 'Research execution config and profile output completed' : 'Simulation config generation completed')
        
        // Show detailed config summary
        if (data.summary) {
          addLog(`  Agents: ${data.summary.total_agents}`)
          addLog(`  Duration: ${data.summary.simulation_hours} hrs`)
          if (isDeepResearchMode.value) {
            addLog(`  Research rounds: ${data.summary.research_rounds_count || 0}`)
            addLog(`  Agent assignments: ${data.summary.agent_assignments_count || 0}`)
            addLog(`  Provenance gate: ${data.summary.has_research_workflow_config ? 'Yes' : 'No'}`)
          } else {
            addLog(`  Initial posts: ${data.summary.initial_posts_count}`)
            addLog(`  Hot topics: ${data.summary.hot_topics_count}`)
            addLog(`  Platforms: Twitter ${data.summary.has_twitter_config ? 'Yes' : 'No'}, Reddit ${data.summary.has_reddit_config ? 'Yes' : 'No'}`)
          }
        }

        // Show time config details
        if (data.config.time_config) {
          const tc = data.config.time_config
          addLog(`Time config: ${tc.minutes_per_round} min/round, ${Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)} rounds total`)
        }
        
        // Show event config
        if (data.config.event_config?.narrative_direction) {
          const narrative = data.config.event_config.narrative_direction
          addLog(`Narrative: ${narrative.length > 50 ? narrative.substring(0, 50) + '...' : narrative}`)
        }
        
        stopConfigPolling()
        phase.value = 4
        addLog('Environment setup complete, ready to start simulation')
        emit('update-status', 'completed')
        
        // Auto-transition to Step 3 only during the active setup flow.
        maybeAutoAdvanceToSimulation()
      }
    }
  } catch (err) {
    console.warn('Fetch config failed:', err)
  }
}

const loadPreparedData = async () => {
  phase.value = 2
  addLog('Loading existing configuration data...')

  // Fetch profiles
  await fetchProfilesRealtime()
  if (profiles.value.length > 0) {
    emit('profiles-updated', profiles.value)
  }
  addLog(`Loaded ${profiles.value.length} agent profiles`)

  // Fetch config (using realtime endpoint)
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      if (res.data.config_generated && res.data.config) {
        simulationConfig.value = res.data.config
        configMode.value = res.data.config.config_mode || configMode.value
        configModeLabel.value = res.data.config.mode_label || configModeLabel.value
        selectedConfigMode.value = configMode.value
        addLog(isDeepResearchMode.value ? 'Research execution config loaded' : 'Simulation config loaded')
        
        // Show detailed config summary
        if (res.data.summary) {
          addLog(`  Agents: ${res.data.summary.total_agents}`)
          addLog(`  Duration: ${res.data.summary.simulation_hours} hrs`)
          addLog(isDeepResearchMode.value
            ? `  Research rounds: ${res.data.summary.research_rounds_count || 0}`
            : `  Initial posts: ${res.data.summary.initial_posts_count}`
          )
        }
        
        addLog('Environment setup complete, ready to start simulation')
        phase.value = 4
        emit('update-status', 'completed')

        // Auto-transition to Step 3 only during the active setup flow.
        maybeAutoAdvanceToSimulation()

      } else {
        // Config not yet generated, start polling
        addLog('Config generating, starting poll...')
        startConfigPolling()
      }
    }
  } catch (err) {
    addLog(`Failed to load config: ${err.message}`)
    emit('update-status', 'error')
  }
}

onMounted(() => {
  addLog('Step 2 environment setup initialized')
  addLog(`Workflow mode selected: ${requestedConfigMode.value}`)
  nextTick(() => {
    if (props.autoStart) {
      startPrepareSimulation()
      return
    }
    if (props.simulationId) {
      loadPreparedData()
    }
  })
})

onUnmounted(() => {
  stopPolling()
  stopProfilesPolling()
  stopConfigPolling()
})
</script>

<style scoped>
/* ─── Root ─────────────────────────────────────── */
.env-setup-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  color: #0a0a0a;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scrollbar-width: thin;
  scrollbar-color: #d4d0ca transparent;
}
.scroll-container::-webkit-scrollbar { width: 3px; }
.scroll-container::-webkit-scrollbar-thumb { background: #d4d0ca; border-radius: 3px; }

/* ─── Status bar ──────────────────────────────── */
.env-status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 10px;
}

.env-status-indicator {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f1ec;
  flex-shrink: 0;
}

.env-status-indicator.active {
  background: rgba(17, 125, 255, 0.1);
}

.env-status-indicator.done {
  background: rgba(22, 163, 74, 0.1);
}

.status-check {
  font-size: 12px;
  color: #16a34a;
  font-weight: 700;
}

.status-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #117dff;
  animation: env-pulse 1.4s ease-in-out infinite;
}

@keyframes env-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

.env-status-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.env-status-title {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
}

.env-status-meta {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-status-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.env-status-badge.active {
  background: rgba(17, 125, 255, 0.1);
  color: #117dff;
}

.env-status-badge.done {
  background: rgba(22, 163, 74, 0.1);
  color: #16a34a;
}

/* ─── Agents Section ──────────────────────────── */
.env-agents-section {
  padding-top: 0;
}

.agents-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.agents-count {
  font-size: 12px;
  font-weight: 600;
  color: #0a0a0a;
}

.agents-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(22, 163, 74, 0.1);
  color: #16a34a;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.agents-badge.spawning {
  background: rgba(17, 125, 255, 0.1);
  color: #117dff;
  animation: env-pulse 1.4s ease-in-out infinite;
}

/* ─── Collapsible activity log ────────────────── */
.env-log-details {
  border-top: 1px solid #e3e0db;
  padding-top: 8px;
}

.env-log-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 0;
  list-style: none;
  user-select: none;
}

.env-log-summary::-webkit-details-marker { display: none; }

.log-toggle-label {
  font-size: 11px;
  font-weight: 600;
  color: #a3a3a3;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.log-count {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
  background: #f3f1ec;
  padding: 1px 5px;
  border-radius: 999px;
}

.env-log-feed {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 6px;
  scrollbar-width: thin;
  scrollbar-color: #e3e0db transparent;
}

.env-log-feed::-webkit-scrollbar { width: 2px; }
.env-log-feed::-webkit-scrollbar-thumb { background: #d4d0ca; border-radius: 2px; }

.log-entry {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 3px 0;
}

.log-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #d4d0ca;
  flex-shrink: 0;
  margin-top: 5px;
}

.log-dot.agent { background: #117dff; }
.log-dot.system { background: #8b5cf6; }
.log-dot.done { background: #16a34a; }

.log-text {
  flex: 1;
  font-size: 10px;
  color: #737373;
  line-height: 1.4;
  font-family: 'JetBrains Mono', monospace;
  word-break: break-word;
}

.log-time {
  font-size: 9px;
  color: #c4c0ba;
  flex-shrink: 0;
  font-family: 'JetBrains Mono', monospace;
}

/* ─── Health CSI Patient Form ─────────────────── */
.health-patient-form {
  background: #faf9f4;
  border: 1px solid #e3e0db;
  border-radius: 12px;
  padding: 1.5rem;
  margin-top: 1rem;
}
.health-form-header { margin-bottom: 1.5rem; }
.health-form-icon { font-size: 1.5rem; }
.health-form-header h3 { font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 600; margin: 0.25rem 0; }
.health-form-subtitle { font-size: 0.8rem; color: #666; }
.health-form-field { margin-bottom: 1rem; }
.health-form-field label { display: block; font-size: 0.85rem; font-weight: 500; margin-bottom: 0.4rem; }
.health-form-field textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  background: white;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 0.875rem;
  resize: vertical;
}
.health-form-field textarea:focus { outline: none; border-color: #999; }
.required { color: #e74c3c; }
.optional { color: #999; font-size: 0.8rem; }
.health-disclaimer {
  font-size: 0.8rem;
  color: #888;
  background: #fffdf0;
  border: 1px solid #e8e0c0;
  border-radius: 6px;
  padding: 0.75rem;
  margin-top: 1rem;
}
</style>
