<template>
  <div class="simulation-panel">
    <!-- Top Control Bar -->
    <div class="control-bar">
      <div class="status-group">
        <!-- Simulation progress summary -->
        <div class="sim-progress">
          <div class="progress-dot" :class="{ active: phase === 1, done: phase === 2 }"></div>
          <span class="progress-label">
            <template v-if="phase === 0">Ready</template>
            <template v-else-if="phase === 1">
              Round {{ Math.max(runStatus.twitter_current_round || 0, runStatus.reddit_current_round || 0) }}
              <span class="progress-dim">/ {{ runStatus.total_rounds || maxRounds || '—' }}</span>
            </template>
            <template v-else>Completed</template>
          </span>
          <span class="progress-separator">·</span>
          <span class="progress-events mono">{{ allActions.length }} events</span>
        </div>
      </div>

      <div class="action-controls">
        <button 
          class="action-btn primary"
          :disabled="phase !== 2 || isGeneratingReport || reportStarted"
          @click="handleNextStep"
        >
          <span v-if="isGeneratingReport" class="loading-spinner-small"></span>
          {{ reportActionLabel }}
          <span v-if="!isGeneratingReport && !reportStarted" class="arrow-icon">→</span>
        </button>
      </div>
    </div>

    <!-- Main Content: Action Feed -->
    <div class="main-content-area" ref="scrollContainer">
      <!-- Action Feed -->
      <div class="action-feed">
        <TransitionGroup name="action-item">
          <div 
            v-for="action in chronologicalActions" 
            :key="action._uniqueId || action.id || `${action.timestamp}-${action.agent_id}`" 
            class="action-card"
          >
            <div class="ac-left">
              <div class="ac-avatar">
                <img v-if="getAgentAvatar(action)" :src="getAgentAvatar(action)" :alt="action.agent_name" class="ac-avatar-img" />
                <span v-else class="ac-avatar-letter">{{ (action.agent_name || 'A')[0] }}</span>
              </div>
              <div class="ac-thread-line"></div>
            </div>
            <div class="ac-content">
              <div class="ac-header">
                <span class="ac-name">{{ action.agent_name }}</span>
                <span class="ac-badge" :class="getActionTypeClass(action.action_type)">{{ getActionTypeLabel(action.action_type) }}</span>
                <span class="ac-time">R{{ action.round_num }} · {{ formatActionTime(action.timestamp) }}</span>
              </div>
              
              <div class="ac-body">
                <!-- CREATE_POST -->
                <div v-if="action.action_type === 'CREATE_POST' && action.action_args?.content" class="ac-text">
                  {{ action.action_args.content }}
                </div>

                <!-- QUOTE_POST -->
                <template v-if="action.action_type === 'QUOTE_POST'">
                  <div v-if="action.action_args?.quote_content" class="ac-text">
                    {{ action.action_args.quote_content }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="ac-quote">
                    <span class="ac-quote-author">@{{ action.action_args.original_author_name || 'User' }}</span>
                    {{ truncateContent(action.action_args.original_content, 150) }}
                  </div>
                </template>

                <!-- REPOST -->
                <template v-if="action.action_type === 'REPOST'">
                  <div class="ac-meta-line">
                    ↻ Reposted from @{{ action.action_args?.original_author_name || 'User' }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="ac-quote">
                    {{ truncateContent(action.action_args.original_content, 200) }}
                  </div>
                </template>

                <!-- LIKE_POST -->
                <template v-if="action.action_type === 'LIKE_POST'">
                  <div class="ac-meta-line">
                    ♥ Liked @{{ action.action_args?.post_author_name || 'User' }}'s post
                  </div>
                  <div v-if="action.action_args?.post_content" class="ac-quote">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- SEARCH_POSTS -->
                <template v-if="action.action_type === 'SEARCH_POSTS'">
                  <div class="ac-meta-line">
                    ⌕ Search: <span class="ac-search-q">"{{ action.action_args?.query || '' }}"</span>
                  </div>
                </template>

                <!-- FOLLOW -->
                <template v-if="action.action_type === 'FOLLOW'">
                  <div class="ac-meta-line">
                    + Followed @{{ action.action_args?.target_user || action.action_args?.user_id || 'User' }}
                  </div>
                </template>

                <!-- UPVOTE / DOWNVOTE -->
                <template v-if="action.action_type === 'UPVOTE_POST' || action.action_type === 'DOWNVOTE_POST'">
                  <div class="ac-meta-line">
                    {{ action.action_type === 'UPVOTE_POST' ? '▲ Upvoted' : '▼ Downvoted' }} Post
                  </div>
                  <div v-if="action.action_args?.post_content" class="ac-quote">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- DO_NOTHING -->
                <template v-if="action.action_type === 'DO_NOTHING'">
                  <div class="ac-meta-line muted">— Idle</div>
                </template>

                <!-- CSI: PROPOSE_CLAIM / propose_claim / claim_propose -->
                <template v-if="['PROPOSE_CLAIM','propose_claim','claim_propose'].includes(action.action_type)">
                  <div class="ac-text">{{ action.action_args?.content || action.action_args?.claim_text || 'New clinical finding' }}</div>
                </template>

                <!-- CSI: CHALLENGE_CLAIM / VERIFY_CLAIM / peer_review -->
                <template v-if="['CHALLENGE_CLAIM','VERIFY_CLAIM','peer_review'].includes(action.action_type)">
                  <div class="ac-text">{{ action.action_args?.content || action.action_args?.review_text || 'Peer review' }}</div>
                  <div v-if="action.action_args?.verdict" class="ac-meta-line verdict-chip" :class="'verdict-' + action.action_args.verdict">
                    {{ action.action_args.verdict === 'needs_revision' ? '↻ Needs Revision' : action.action_args.verdict === 'supports' ? '✓ Supports' : action.action_args.verdict }}
                  </div>
                </template>

                <!-- CSI: REVISE_CLAIM -->
                <template v-if="['REVISE_CLAIM','revise_claim'].includes(action.action_type)">
                  <div class="ac-text">{{ action.action_args?.content || 'Revised claim based on peer challenge' }}</div>
                </template>

                <!-- CSI: SEARCH_WEB / search_web -->
                <template v-if="action.action_type === 'SEARCH_WEB' || action.action_type === 'search_web'">
                  <div class="ac-meta-line">
                    🔍 Searching
                    <span v-if="action.action_args?.query || action.detail?.query" class="ac-search-q">
                      "{{ action.action_args?.query || action.detail?.query }}"
                    </span>
                    <span v-else class="ac-search-q">medical literature</span>
                  </div>
                  <div v-if="action.action_args?.results_count || action.action_args?.extracted_count" class="ac-meta-line">Found {{ action.action_args?.results_count || action.action_args?.extracted_count || 0 }} results</div>
                </template>

                <!-- CSI: READ_URL / investigate_source -->
                <template v-if="action.action_type === 'READ_URL' || action.action_type === 'investigate_source'">
                  <div class="ac-meta-line">📖 Reading {{ action.action_args?.urls?.length || action.action_args?.extracted_count || 1 }} source{{ (action.action_args?.urls?.length || 1) > 1 ? 's' : '' }}</div>
                  <div v-if="action.action_args?.url" class="ac-meta-line mono-text">{{ truncateContent(action.action_args.url, 80) }}</div>
                </template>

                <!-- CSI: SYNTHESIZE -->
                <template v-if="action.action_type === 'SYNTHESIZE'">
                  <div class="ac-text">{{ action.action_args?.synthesis_text || action.action_summary || 'Synthesizing claims into a consolidated finding' }}</div>
                  <div v-if="action.action_args?.constituent_claim_ids?.length" class="ac-meta-line">Combined {{ action.action_args.constituent_claim_ids.length }} claims</div>
                </template>

                <!-- CSI: RECALL -->
                <template v-if="action.action_type === 'RECALL' || action.action_type === 'recall'">
                  <div class="ac-text">{{ action.action_args?.content || action.action_args?.query || 'Recalling prior research' }}</div>
                  <div v-if="action.action_args?.source_ids?.length" class="ac-meta-line">Retrieved {{ action.action_args.source_ids.length }} sources</div>
                </template>

                <!-- Generic fallback (only for truly unhandled types) -->
                <div v-if="!isHandledActionType(action.action_type)" class="ac-text">
                  {{ extractReadableText(action) }}
                </div>
              </div>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="allActions.length === 0 && phase <= 1" class="waiting-state">
          <div class="pulse-ring"></div>
          <span>Waiting for agent actions...</span>
        </div>
      </div>
    </div>

    <!-- System Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">Monitor</span>
        <span class="log-id mono">{{ simulationId || '—' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>

    <!-- Report confirmation overlay -->
    <div v-if="showReportConfirm" class="report-confirm-overlay">
      <CsiConfirmCard
        :visible="true"
        :title="isHealthMode ? 'Medical Assessment Ready' : 'Generate Report'"
        :icon="isHealthMode ? '🩺' : '📄'"
        :query="isHealthMode
          ? 'Synthesize all clinical findings, evidence, and specialist consultations into a structured diagnostic assessment.'
          : 'Compile all claims, trials, and evidence into a final CSI Deep Research report.'"
        :stats="isHealthMode ? [
          { value: allActions.length, label: 'Clinical Findings' },
          { value: Math.max(runStatus.twitter_current_round || 0, runStatus.reddit_current_round || 0), label: 'Review Rounds' },
          { value: 'Health', label: 'Mode' }
        ] : reportConfirmStats"
        backLabel="Later"
        :continueLabel="isHealthMode ? 'Generate Assessment' : 'Generate Report'"
        :loadingLabel="isHealthMode ? 'Generating Assessment...' : 'Generating...'"
        :loading="isGeneratingReport"
        @back="showReportConfirm = false"
        @continue="confirmReportGeneration"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { 
  startSimulation, 
  stopSimulation,
  getRunStatus, 
  getRunStatusDetail,
  getSimulationProfilesRealtime
} from '../api/simulation'
import { generatePaperReport } from '../api/report'
import CsiConfirmCard from './ui/CsiConfirmCard.vue'
import { getSimulationCsiState } from '../api/csi'
const props = defineProps({
  simulationId: String,
  maxRounds: Number, // Max rounds passed from Step2
  minutesPerRound: {
    type: Number,
    default: 30 // Default 30 minutes per round
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  embedded: {
    type: Boolean,
    default: false
  },
  reportStarted: {
    type: Boolean,
    default: false
  },
  autoGenerateReportOnComplete: {
    type: Boolean,
    default: false
  },
  agentProfiles: {
    type: Array,
    default: () => []
  },
  isHealthMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const router = useRouter()
const route = useRoute()

// Override prop with URL check — guards against prop chain timing failures
const isHealthMode = computed(() =>
  props.isHealthMode ||
  String(route.query.configMode || '').toLowerCase() === 'health'
)

// State
const isGeneratingReport = ref(false)
const showReportConfirm = ref(false)

const reportConfirmStats = computed(() => {
  const round = Math.max(runStatus.value.twitter_current_round || 0, runStatus.value.reddit_current_round || 0)
  return [
    { value: String(allActions.value.length), label: 'Actions' },
    { value: String(round || '—'), label: 'Rounds' },
    { value: 'CSI', label: 'Report' }
  ]
})

const confirmReportGeneration = () => {
  showReportConfirm.value = false
  handleNextStep()
}
const phase = ref(0) // 0: Not started, 1: Running, 2: Completed
const isStarting = ref(false)
const isStopping = ref(false)
const startError = ref(null)
const runStatus = ref({})
const allActions = ref([]) // All actions (incremental accumulation)
const actionIds = ref(new Set()) // Action ID set for deduplication
const scrollContainer = ref(null)
const profiles = ref([])
const isHydrating = ref(false)

const scrollActionsToBottom = (behavior = 'smooth') => {
  nextTick(() => {
    if (!scrollContainer.value) return
    scrollContainer.value.scrollTo({ top: scrollContainer.value.scrollHeight, behavior })
  })
}

// Computed
// Display actions in chronological order (newest at the bottom)
const chronologicalActions = computed(() => {
  return allActions.value
})

// Per-platform action counts
const twitterActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'twitter').length
})

const redditActionsCount = computed(() => {
  return allActions.value.filter(a => a.platform === 'reddit').length
})

// Format simulated elapsed time (calculated from rounds and minutes per round)
const formatElapsedTime = (currentRound) => {
  if (!currentRound || currentRound <= 0) return '0h 0m'
  const totalMinutes = currentRound * props.minutesPerRound
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${minutes}m`
}

// Twitter platform simulated elapsed time
const twitterElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.twitter_current_round || 0)
})

// Reddit platform simulated elapsed time
const redditElapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.reddit_current_round || 0)
})

const reportActionLabel = computed(() => {
  if (isGeneratingReport.value) return 'Starting...'
  if (props.reportStarted) return 'Report In Progress'
  return 'Generate IEEE Paper'
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// Reset all state (for restarting simulation)
const resetAllState = () => {
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  prevTwitterRound.value = 0
  prevRedditRound.value = 0
  startError.value = null
  isStarting.value = false
  isStopping.value = false
  stopPolling()  // Stop any existing polling
}

const resumeExistingSimulation = async () => {
  if (!props.simulationId || isHydrating.value) return false

  isHydrating.value = true
  try {
    const res = await getRunStatus(props.simulationId)
    if (!res.success || !res.data) return false

    const data = res.data
    runStatus.value = data

    const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped' || checkPlatformsCompleted(data)
    const isRunning = data.runner_status === 'running' || data.runner_status === 'processing'

    if (isCompleted) {
      phase.value = 2
      await fetchProfiles({ silent: true })
      await fetchRunStatusDetail()
      emit('update-status', 'completed')
      
      const autoReport = props.autoGenerateReportOnComplete || isHealthMode.value
      if (autoReport && !props.reportStarted) {
        addLog('Session restored. Auto-starting report generation...')
        await handleNextStep()
      } else if (!props.reportStarted) {
        // Show report confirmation if no report has been generated yet
        showReportConfirm.value = true
      }
      return true
    }

    if (isRunning) {
      phase.value = 1
      await fetchProfiles({ silent: true })
      startStatusPolling()
      startDetailPolling()
      startProfilesPolling()
      emit('update-status', 'processing')
      return true
    }

    return false
  } catch (err) {
    console.warn('Failed to hydrate simulation state:', err)
    return false
  } finally {
    isHydrating.value = false
  }
}

// Start simulation
const doStartSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: Missing simulationId')
    return
  }

  // Reset all state first to avoid interference from previous simulation
  resetAllState()

  isStarting.value = true
  startError.value = null
  addLog('Starting parallel simulation...')
  emit('update-status', 'processing')

  try {
    const params = {
      simulation_id: props.simulationId,
      platform: 'parallel',
      force: true,  // Force restart
      enable_graph_memory_update: true  // Enable dynamic graph memory update
    }

    if (props.maxRounds) {
      params.max_rounds = props.maxRounds
      addLog(`Setting max simulation rounds: ${props.maxRounds}`)
    }

    addLog('Dynamic graph memory update enabled')

    const res = await startSimulation(params)

    if (res.success && res.data) {
      if (res.data.force_restarted) {
        addLog('Old simulation logs cleaned, restarting simulation')
      }
      addLog('Simulation engine started successfully')
      addLog(`  PID: ${res.data.process_pid || '-'}`)

      phase.value = 1
      runStatus.value = res.data

      await fetchProfiles({ silent: false })
      startStatusPolling()
      startDetailPolling()
      startProfilesPolling()
    } else {
      startError.value = res.error || 'Start failed'
      addLog(`Start failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    startError.value = err.message
    addLog(`Start exception: ${err.message}`)
    emit('update-status', 'error')
  } finally {
    isStarting.value = false
  }
}

// Stop simulation
const handleStopSimulation = async () => {
  if (!props.simulationId) return

  isStopping.value = true
  addLog('Stopping simulation...')

  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })

    if (res.success) {
      addLog('Simulation stopped')
      phase.value = 2
      stopPolling()
      emit('update-status', 'completed')
    } else {
      addLog(`Stop failed: ${res.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Stop exception: ${err.message}`)
  } finally {
    isStopping.value = false
  }
}

// Poll status
let statusTimer = null
let detailTimer = null
let profilesTimer = null

const startStatusPolling = () => {
  statusTimer = setInterval(fetchRunStatus, 2000)
}

const startDetailPolling = () => {
  detailTimer = setInterval(fetchRunStatusDetail, 3000)
}

const startProfilesPolling = () => {
  profilesTimer = setInterval(() => {
    fetchProfiles({ silent: true })
  }, 3000)
}

const stopPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (detailTimer) {
    clearInterval(detailTimer)
    detailTimer = null
  }
  if (profilesTimer) {
    clearInterval(profilesTimer)
    profilesTimer = null
  }
}

// Track previous round per platform to detect changes and output logs
const prevTwitterRound = ref(0)
const prevRedditRound = ref(0)

const fetchRunStatus = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getRunStatus(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      runStatus.value = data
      
      // Detect round changes per platform and output logs
      if (data.twitter_current_round > prevTwitterRound.value) {
        addLog(`[Plaza] R${data.twitter_current_round}/${data.total_rounds} | T:${data.twitter_simulated_hours || 0}h | A:${data.twitter_actions_count}`)
        prevTwitterRound.value = data.twitter_current_round
      }
      
      if (data.reddit_current_round > prevRedditRound.value) {
        addLog(`[Community] R${data.reddit_current_round}/${data.total_rounds} | T:${data.reddit_simulated_hours || 0}h | A:${data.reddit_actions_count}`)
        prevRedditRound.value = data.reddit_current_round
      }
      
      // Detect whether simulation has completed or failed
      const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'
      const isFailed = data.runner_status === 'failed' || data.runner_status === 'error'
      
      // Extra check: if backend hasn't updated runner_status yet, but platforms report completion
      // Detect via twitter_completed and reddit_completed status
      const platformsCompleted = checkPlatformsCompleted(data)

      // CSI research phase completion check
      const researchCompleted = data.csi_research_completed === true
      
      // Effective completion requires platforms AND research (if applicable)
      // If runner_status is completed, we trust it. 
      // Otherwise, we wait for platforms + research if in health mode.
      let finalCompleted = isCompleted
      if (!isCompleted && platformsCompleted) {
        if (isHealthMode.value) {
          finalCompleted = researchCompleted
        } else {
          finalCompleted = true
        }
      }
      
      if (finalCompleted) {
        if (platformsCompleted && !isCompleted) {
          addLog('All platform simulations completed')
        }
        if (isHealthMode.value && researchCompleted) {
          addLog('Medical research phase completed')
        }
        addLog('Simulation completed')
        phase.value = 2
        stopPolling()
        await fetchRunStatusDetail() // Fetch final complete action logs
        emit('update-status', 'completed')
        
        const autoReport = props.autoGenerateReportOnComplete || isHealthMode.value
        if (autoReport && !props.reportStarted) {
          addLog('Transitioning to report generation sequence...')
          await handleNextStep()
        } else if (!props.reportStarted) {
          // Show confirmation card instead of auto-generating
          showReportConfirm.value = true
        }
      } else if (isFailed) {
        addLog('Simulation terminated due to error')
        phase.value = 2
        stopPolling()
        await fetchRunStatusDetail() // Fetch final complete action logs
        emit('update-status', 'error')
      }
    }
  } catch (err) {
    console.warn('Failed to get run status:', err)
  }
}

const fetchProfiles = async (options = {}) => {
  const { silent = false } = options
  if (!props.simulationId) return

  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    if (res.success && res.data) {
      profiles.value = res.data.profiles || []
      if (!silent && profiles.value.length > 0) {
        addLog(`Loaded ${profiles.value.length} active agents`)
      }
    }
  } catch (err) {
    if (!silent) {
      addLog(`Failed to load active agents: ${err.message}`)
    }
  }
}

// Check whether all enabled platforms have completed
const checkPlatformsCompleted = (data) => {
  // If no platform data, return false
  if (!data) return false

  // Check each platform's completion status
  const twitterCompleted = data.twitter_completed === true
  const redditCompleted = data.reddit_completed === true

  // Check if all enabled platforms have completed
  // A platform is considered enabled if actions_count > 0, running was true, or it completed
  const twitterEnabled = (data.twitter_actions_count > 0) || data.twitter_running || twitterCompleted
  const redditEnabled = (data.reddit_actions_count > 0) || data.reddit_running || redditCompleted

  // If no platforms are enabled, return false
  if (!twitterEnabled && !redditEnabled) return false

  // Check all enabled platforms are completed
  if (twitterEnabled && !twitterCompleted) return false
  if (redditEnabled && !redditCompleted) return false
  
  return true
}

const fetchRunStatusDetail = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getRunStatusDetail(props.simulationId)
    
    if (res.success && res.data) {
      // Use all_actions to get the complete action list
      let serverActions = res.data.all_actions || []

      // For CSI tasks, get locally graph-generated actions
      try {
        const csiRes = await getSimulationCsiState(props.simulationId)
        if (csiRes.success && csiRes.data && csiRes.data.agent_actions) {
          const csiActions = csiRes.data.agent_actions.map(action => {
            const detail = action.detail || {}
            let contentStr = ''
            
            // Format CSI details to readable content
            const isPropose = ['PROPOSE_CLAIM','propose_claim','claim_propose'].includes(action.action_type)
            const isReview  = ['CHALLENGE_CLAIM','peer_review','VERIFY_CLAIM'].includes(action.action_type)
            const isRevise  = ['REVISE_CLAIM','revise_claim'].includes(action.action_type)
            const isRecall  = action.action_type === 'recall'
            const isSynth   = action.action_type === 'SYNTHESIZE'

            if (action.action_type === 'SEARCH_WEB' || action.action_type === 'search_web') {
              const q = detail.query || ''
              const n = detail.results_count || detail.ingested_count || 0
              contentStr = q ? `"${q}"` : 'medical literature'
              if (n) contentStr += ` · ${n} sources found`
            } else if (action.action_type === 'READ_URL' || action.action_type === 'investigate_source') {
              const cnt = detail.urls?.length || detail.extracted_count || 1
              contentStr = `Read ${cnt} source${cnt > 1 ? 's' : ''}`
            } else if (isPropose) {
              const claimTxt = detail.claim_text || ''
              const conf = detail.confidence != null ? Math.round(detail.confidence * 100) + '%' : null
              const srcCnt = detail.source_ids?.length || detail.source_count || 1
              if (claimTxt) {
                contentStr = claimTxt.length > 180 ? claimTxt.substring(0, 180) + '…' : claimTxt
              } else {
                contentStr = `New clinical finding · ${srcCnt} source${srcCnt > 1 ? 's' : ''}`
              }
              if (conf) contentStr += ` (${conf})`
            } else if (isReview) {
              const verdict = detail.verdict || detail.trial_verdict || ''
              const reviewTxt = detail.review_text || detail.response || ''
              contentStr = reviewTxt ? (reviewTxt.length > 160 ? reviewTxt.substring(0, 160) + '…' : reviewTxt)
                         : verdict ? `Verdict: ${verdict}` : 'Reviewed peer claim'
            } else if (isRevise) {
              contentStr = 'Revised previous claim based on peer challenge'
            } else if (isRecall) {
              const q = detail.query || detail.recall_id || ''
              const srcCnt = detail.source_ids?.length || 0
              contentStr = q ? `Recalled: "${q.substring(0, 100)}"` : `Retrieved ${srcCnt} sources from memory`
            } else if (isSynth) {
              contentStr = 'Synthesizing all findings into consolidated assessment'
            } else {
              // fallback: only show non-empty keys
              const keys = Object.keys(detail).filter(k => detail[k] !== null && detail[k] !== '' && detail[k] !== undefined)
              contentStr = keys.length ? keys.map(k => `${k}: ${String(detail[k]).substring(0, 60)}`).join(' · ') : ''
            }

            return {
              ...action,
              _uniqueId: action.action_id,
              timestamp: action.created_at,
              platform: 'CSI',
              agent_name: action.agent_name || `Agent ${action.agent_id}`,
              action_type: action.action_type || 'observe',
              action_args: { ...detail, content: contentStr }
            }
          })
          serverActions = [...serverActions, ...csiActions]
        }
      } catch (err) {
        // Ignore if no CSI data available
      }
      
      // Sort by timestamp to ensure correct timeline after mixing social and CSI actions
      serverActions.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))

      // Incrementally add new actions (deduplicated)
      let newActionsAdded = 0
      serverActions.forEach(action => {
        // Generate unique ID
        const actionId = action.id || action.action_id || `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`
        
        if (!actionIds.value.has(actionId)) {
          actionIds.value.add(actionId)
          allActions.value.push({
            ...action,
            _uniqueId: actionId
          })
          newActionsAdded++
        }
      })
      
      // Re-sort all actions by time to ensure correct order after adding new ones
      if (newActionsAdded > 0) {
        allActions.value.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
      }
      
      // Auto-scroll to bottom when new actions arrive.
      if (newActionsAdded > 0 && scrollContainer.value) {
        scrollActionsToBottom('smooth')
      }
    }
  } catch (err) {
    console.warn('Failed to get detailed status:', err)
  }
}

// Helpers
const getActionTypeLabel = (type) => {
  if (!type) return 'UNKNOWN'
  if (type.length > 20) return type.substring(0, 20)

  if (isHealthMode.value) {
    const healthLabels = {
      'PROPOSE_CLAIM': 'Clinical Finding',
      'propose_claim': 'Clinical Finding',
      'claim_propose': 'Clinical Finding',
      'CHALLENGE_CLAIM': 'Specialist Review',
      'challenge_claim': 'Specialist Review',
      'peer_review': 'Specialist Review',
      'VERIFY_CLAIM': 'Evidence Verification',
      'REVISE_CLAIM': 'Revised Finding',
      'revise_claim': 'Revised Finding',
      'recall': 'Evidence Recall',
      'SYNTHESIZE': 'Diagnostic Synthesis',
      'synthesize': 'Diagnostic Synthesis',
      'SEARCH_WEB': 'Medical Literature Search',
      'search_web': 'Medical Literature Search',
      'READ_URL': 'Clinical Source Review',
    }
    if (healthLabels[type]) return healthLabels[type]
  }

  const labels = {
    'CREATE_POST': 'POST',
    'REPOST': 'REPOST',
    'LIKE_POST': 'LIKE',
    'CREATE_COMMENT': 'COMMENT',
    'LIKE_COMMENT': 'LIKE',
    'DO_NOTHING': 'IDLE',
    'FOLLOW': 'FOLLOW',
    'SEARCH_POSTS': 'SEARCH',
    'QUOTE_POST': 'QUOTE',
    'UPVOTE_POST': 'UPVOTE',
    'DOWNVOTE_POST': 'DOWNVOTE',
    // CSI Types
    'SEARCH_WEB': 'WEB_SEARCH',
    'READ_URL': 'READ_PAGE',
    'PROPOSE_CLAIM': 'PROPOSE',
    'CHALLENGE_CLAIM': 'CHALLENGE',
    'CROSS_REFERENCE': 'CROSS_REF',
    'investigate_source': 'INVESTIGATE',
    'peer_review': 'PEER_REVIEW',
    'propose_claim': 'PROPOSE_CLAIM',
    'revise_claim': 'REVISE_CLAIM',
    'synthesize': 'SYNTHESIZE'
  }
  return labels[type] || type.replace(/_/g, ' ').toUpperCase()
}

const getActionTypeClass = (type) => {
  const classes = {
    'CREATE_POST': 'badge-post',
    'REPOST': 'badge-action',
    'LIKE_POST': 'badge-action',
    'CREATE_COMMENT': 'badge-comment',
    'LIKE_COMMENT': 'badge-action',
    'QUOTE_POST': 'badge-post',
    'FOLLOW': 'badge-meta',
    'SEARCH_POSTS': 'badge-meta',
    'UPVOTE_POST': 'badge-action',
    'DOWNVOTE_POST': 'badge-action',
    'DO_NOTHING': 'badge-idle',
    // CSI action badges
    'SEARCH_WEB': 'badge-meta',
    'READ_URL': 'badge-meta',
    'PROPOSE_CLAIM': 'badge-post',
    'CHALLENGE_CLAIM': 'badge-action',
    'CROSS_REFERENCE': 'badge-comment',
    'investigate_source': 'badge-meta',
    'peer_review': 'badge-action',
    'propose_claim': 'badge-post',
    'revise_claim': 'badge-comment',
    'synthesize': 'badge-meta'
  }
  return classes[type] || 'badge-default'
}

const getAgentAvatar = (action) => {
  const id = action.agent_id
  if (id == null || !props.agentProfiles?.length) return null
  const profile = props.agentProfiles.find(p => p.id === id || p.id === Number(id))
  return profile?.avatarPath || null
}

const truncateContent = (content, maxLength = 100) => {
  if (!content) return ''
  if (content.length > maxLength) return content.substring(0, maxLength) + '...'
  return content
}

const HANDLED_ACTION_TYPES = new Set([
  'CREATE_POST', 'QUOTE_POST', 'REPOST', 'LIKE_POST', 'CREATE_COMMENT',
  'SEARCH_POSTS', 'FOLLOW', 'UPVOTE_POST', 'DOWNVOTE_POST', 'DO_NOTHING',
  'PROPOSE_CLAIM', 'propose_claim', 'CHALLENGE_CLAIM', 'peer_review',
  'SEARCH_WEB', 'search_web', 'READ_URL', 'investigate_source',
  'SYNTHESIZE', 'RECALL'
])

const isHandledActionType = (type) => HANDLED_ACTION_TYPES.has(type)

const extractReadableText = (action) => {
  const args = action.action_args || {}
  // Try common text fields first
  if (args.content) return truncateContent(String(args.content), 300)
  if (args.claim_text) return truncateContent(String(args.claim_text), 300)
  if (args.review_text) return truncateContent(String(args.review_text), 300)
  if (args.synthesis_text) return truncateContent(String(args.synthesis_text), 300)
  if (args.query) return `Query: ${args.query}`
  if (args.url) return `URL: ${truncateContent(args.url, 100)}`
  if (action.action_summary) return truncateContent(String(action.action_summary), 300)
  // Last resort — try to summarize the action type
  const type = action.action_type || 'Unknown'
  return `${type.replace(/_/g, ' ').toLowerCase()}`
}

const formatActionTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

const handleNextStep = async () => {
  if (!props.simulationId) {
    addLog('Error: Missing simulationId')
    return
  }

  if (isGeneratingReport.value) {
    addLog('Report generation request sent, please wait...')
    return
  }

  if (props.reportStarted) {
    addLog('Report generation already started')
    return
  }

  isGeneratingReport.value = true

  // Health mode: skip paper generation, navigate to report stage
  if (isHealthMode.value) {
    addLog('Generating medical assessment...')
    isGeneratingReport.value = false
    emit('next-step', { stage: 'report', reportId: null })
    return
  }

  addLog('Starting report generation...')

  try {
    const res = await generatePaperReport({
      simulation_id: props.simulationId,
      force_regenerate: true
    })

    const reportId = res?.data?.report_id || res?.report_id
    if (res?.success !== false && reportId) {
      addLog(`IEEE paper generation task started: ${reportId}`)
      emit('next-step', { stage: 'report', reportId })
      if (!props.embedded) {
        router.push({ name: 'Report', params: { reportId } })
      }
    } else {
      addLog(`Failed to start IEEE paper generation: ${res.error || 'Unknown error'}`)
      isGeneratingReport.value = false
    }
  } catch (err) {
    addLog(`IEEE paper generation exception: ${err.message}`)
    isGeneratingReport.value = false
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

onMounted(() => {
  addLog('Step 3 simulation initialized')
  if (props.simulationId) {
    resumeExistingSimulation().then((resumed) => {
      if (!resumed) {
        doStartSimulation()
      }
      // Scroll to bottom after loading existing actions
      nextTick(() => {
        scrollActionsToBottom('auto')
      })
    })
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.simulation-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #faf9f7;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  overflow: hidden;
}

/* ─── Control Bar ────────────────────────────────── */
.control-bar {
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e8e4df;
  background: #faf9f7;
  flex-shrink: 0;
}

.sim-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
  flex-shrink: 0;
}

.progress-dot.active {
  background: #3b82f6;
  box-shadow: 0 0 6px rgba(59, 130, 246, 0.35);
  animation: dot-pulse 1.5s ease-in-out infinite;
}

.progress-dot.done {
  background: #22c55e;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.progress-label {
  font-size: 13px;
  font-weight: 700;
  color: #1a1a1a;
}

.progress-dim {
  color: #999;
  font-weight: 400;
}

.progress-separator {
  color: #ccc;
}

.progress-events {
  font-size: 11px;
  color: #888;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  font-size: 12px;
  font-weight: 700;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
}

.action-btn.primary {
  background: #1a1a1a;
  color: #fff;
}

.action-btn.primary:hover:not(:disabled) {
  background: #333;
}

.action-btn:disabled {
  opacity: 0.25;
  cursor: not-allowed;
}

/* ─── Main Content ───────────────────────────────── */
.main-content-area {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #d4cfc8 transparent;
}

.main-content-area::-webkit-scrollbar { width: 4px; }
.main-content-area::-webkit-scrollbar-thumb { background: #d4cfc8; border-radius: 4px; }

/* ─── Action Feed — threaded conversation style ── */
.action-feed {
  padding: 16px 20px;
  min-height: 100%;
}

.action-card {
  display: flex;
  gap: 12px;
  padding-bottom: 4px;
}

.ac-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 32px;
  flex-shrink: 0;
}

.ac-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #e8e4df;
  color: #6e6257;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  text-transform: uppercase;
  flex-shrink: 0;
  overflow: hidden;
}

.ac-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

.ac-avatar-letter {
  line-height: 1;
}

.ac-thread-line {
  flex: 1;
  width: 1.5px;
  background: #e8e4df;
  margin-top: 4px;
  min-height: 8px;
}

.action-card:last-child .ac-thread-line {
  display: none;
}

.ac-content {
  flex: 1;
  min-width: 0;
  padding-bottom: 16px;
}

.ac-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.ac-name {
  font-size: 13px;
  font-weight: 700;
  color: #1a1a1a;
}

.ac-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.badge-post { background: #eef4ff; color: #3b82f6; }
.badge-comment { background: #f0fdf4; color: #22c55e; }
.badge-action { background: #fef3c7; color: #b45309; }
.badge-meta { background: #f3f4f6; color: #6b7280; }
.badge-idle { background: #f9fafb; color: #9ca3af; }
.badge-default { background: #f3f4f6; color: #6b7280; }

.ac-time {
  font-size: 10px;
  color: #b3a99d;
  font-family: 'JetBrains Mono', monospace;
  margin-left: auto;
}

.ac-body {
  margin-top: 2px;
}

.ac-text {
  font-size: 13px;
  line-height: 1.65;
  color: #333;
  margin-bottom: 6px;
}

.ac-quote {
  background: #f5f3ef;
  border-left: 2px solid #d4cfc8;
  padding: 8px 12px;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
  color: #6e6257;
  line-height: 1.55;
  margin-top: 6px;
}

.ac-quote-author {
  font-weight: 700;
  color: #999;
  display: block;
  font-size: 10px;
  margin-bottom: 2px;
}

.ac-meta-line {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
}

.ac-meta-line.muted {
  color: #bbb;
}

.verdict-chip {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 10px;
  margin-top: 3px;
}
.verdict-chip.verdict-supports { background: #dcfce7; color: #15803d; }
.verdict-chip.verdict-needs_revision { background: #fef9c3; color: #92400e; }
.verdict-chip.verdict-challenges,
.verdict-chip.verdict-disagrees { background: #fee2e2; color: #991b1b; }

.ac-search-q {
  font-family: 'JetBrains Mono', monospace;
  color: #3b82f6;
  background: #eef4ff;
  padding: 0 4px;
  border-radius: 3px;
}

.mono-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #737373;
  word-break: break-all;
}

/* ─── Report confirm overlay ─────────────────────── */
.report-confirm-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: rgba(250, 249, 244, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ─── Waiting State ──────────────────────────────── */
.waiting-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 80px 0;
  color: #b3a99d;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.pulse-ring {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1.5px solid #d4cfc8;
  animation: ripple 2s infinite;
}

@keyframes ripple {
  0% { transform: scale(0.8); opacity: 1; }
  100% { transform: scale(2.5); opacity: 0; }
}

/* ─── Transitions ────────────────────────────────── */
.action-item-enter-active {
  transition: all 0.35s cubic-bezier(0.32, 0.72, 0, 1);
}

.action-item-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

/* ─── CSI Review Section ─────────────────────────── */
.csi-review-section {
  padding: 14px 20px;
  border-top: 1px solid #e8e4df;
  background: #faf9f7;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.csi-review-header {
  margin-bottom: 10px;
}

.review-title {
  font-size: 13px;
  font-weight: 700;
  color: #1a1a1a;
  display: block;
}

.review-subtitle {
  font-size: 11px;
  color: #999;
  display: block;
  margin-top: 2px;
}

/* ─── System Logs ────────────────────────────────── */
.system-logs {
  background: #f5f3ef;
  border-top: 1px solid #e8e4df;
  padding: 10px 16px;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.log-title {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.1em;
  color: #b3a99d;
  text-transform: uppercase;
}

.log-id {
  font-size: 10px;
  color: #b3a99d;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 90px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #d4cfc8 transparent;
}

.log-content::-webkit-scrollbar { width: 3px; }
.log-content::-webkit-scrollbar-thumb { background: #d4cfc8; border-radius: 3px; }

.log-line {
  display: flex;
  gap: 10px;
  font-size: 10px;
  line-height: 1.7;
  font-family: 'JetBrains Mono', monospace;
}

.log-time { color: #c7beb2; min-width: 70px; }
.log-msg { color: #888; word-break: break-all; }

.mono { font-family: 'JetBrains Mono', monospace; }

/* Loading spinner */
.loading-spinner-small {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
