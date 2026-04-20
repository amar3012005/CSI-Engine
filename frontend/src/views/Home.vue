<template>
  <div class="shell">
    <AppSidebar
      :collapsed="sidebarCollapsed"
      :recentSessions="recentSessions"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @go-home="handleNewChat"
      @navigate="navigateToSession"
    />

    <main class="main">
      <!-- Top bar -->
      <div class="topbar">
        <div class="topbar-spacer" />
        <div class="topbar-right">
          <button class="topbar-btn" title="Settings">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Center stage -->
      <div class="center">
        <Transition name="fade-up" mode="out-in">

          <!-- Input card -->
          <div v-if="!showConfirmCard" key="input" class="input-wrap">
            <div class="chat-card" :class="{ focused: isFocused, 'health-card': isHealthMode }">
              <!-- Mode pills row inside card top -->
              <div class="card-modes">
                <button
                  v-for="mode in MODES"
                  :key="mode.key"
                  class="mode-pill"
                  :class="{ active: selectedMode === mode.key, [`mode-${mode.key}`]: true }"
                  @click="selectedMode = mode.key"
                >
                  <span class="mode-icon">{{ mode.icon }}</span>
                  {{ mode.label }}
                </button>
              </div>

              <!-- Textarea -->
              <div class="card-body">
                <textarea
                  ref="queryInput"
                  v-model="formData.simulationRequirement"
                  @keydown="handleKeyDown"
                  @focus="isFocused = true"
                  @blur="isFocused = false"
                  :placeholder="chatPlaceholder"
                  rows="1"
                  class="chat-textarea"
                  :disabled="loading"
                  @input="adjustHeight"
                />
              </div>

              <!-- Footer toolbar -->
              <div class="card-toolbar">
                <div class="toolbar-left">
                  <button class="tool-btn" @click="triggerFileInput" :disabled="loading" title="Attach file">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                    </svg>
                  </button>
                  <input ref="fileInput" type="file" multiple accept=".pdf,.md,.txt" @change="handleFileSelect" style="display:none" />
                  <div v-if="files.length" class="chips">
                    <span v-for="(f, i) in files" :key="i" class="chip">
                      {{ f.name }}<button class="chip-x" @click.stop="files.splice(i,1)">×</button>
                    </span>
                  </div>
                </div>
                <div class="toolbar-right">
                  <button class="model-btn">
                    <span>Model</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                  </button>
                  <button class="tool-btn" title="Voice input">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/>
                    </svg>
                  </button>
                  <button
                    class="send-btn"
                    @click="handleSubmit"
                    :disabled="!canSubmit || loading"
                    :class="{ active: canSubmit && !loading }"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <line x1="22" y1="2" x2="11" y2="13"/>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Suggestion cards -->
            <div class="suggestions-wrap">
              <p class="suggestions-heading">{{ isHealthMode ? 'Example clinical cases' : 'Make the most out of HIVEMIND' }}</p>
              <div class="suggestion-cards">
                <div
                  v-for="(card, i) in currentCards"
                  :key="i"
                  class="scard"
                  @click="useCard(card.query)"
                >
                  <div class="scard-icon" :style="{ background: card.bg }">
                    <span class="scard-emoji">{{ card.icon }}</span>
                  </div>
                  <div class="scard-text">
                    <div class="scard-title">{{ card.title }}</div>
                    <div class="scard-desc">{{ card.desc }}</div>
                  </div>
                  <button class="scard-close" @click.stop="dismissCard(i)" title="Dismiss">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Confirm card -->
          <CsiConfirmCard
            v-else
            key="confirm"
            :visible="true"
            :query="formData.simulationRequirement"
            :loading="loading"
            :title="isHealthMode ? 'Medical Assessment' : 'Cognitive Swarm Intelligence'"
            :icon="isHealthMode ? '🩺' : '⊡'"
            :stats="isHealthMode
              ? [{ value: '9', label: 'Specialists' }, { value: 'Health', label: 'Mode' }, { value: 'EBM', label: 'Evidence' }]
              : [{ value: '8', label: 'Agents' }, { value: 'CSI', label: 'Mode' }, { value: 'Deep', label: 'Research' }]"
            :continueLabel="isHealthMode ? 'Start Assessment' : 'Continue'"
            @back="showConfirmCard = false"
            @continue="startSimulation"
          />
        </Transition>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSidebar } from '../store/sidebar'
import AppSidebar from '../components/ui/AppSidebar.vue'
import CsiConfirmCard from '../components/ui/CsiConfirmCard.vue'

const router = useRouter()
const { sidebarCollapsed } = useSidebar()

const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)
const showConfirmCard = ref(false)
const isFocused = ref(false)
const queryInput = ref(null)
const fileInput = ref(null)
const recentSessions = ref([])
const error = ref('')

// Mode selector
const selectedMode = ref('web_research')
const MODES = [
  { key: 'web_research', label: 'Research', icon: '🔬' },
  { key: 'health',       label: 'Health',   icon: '🩺' },
]
const isHealthMode = computed(() => selectedMode.value === 'health')

const chatPlaceholder = computed(() =>
  isHealthMode.value
    ? 'Describe the patient case — chief complaint, history, symptoms...'
    : 'Type / for search modes and shortcuts'
)

// Suggestion cards
const researchCards = ref([
  {
    icon: '🌐', bg: 'linear-gradient(135deg, #dbeafe, #bfdbfe)',
    title: 'Browse hands free',
    desc: 'Tell HIVEMIND what you need and watch it work for you.',
    query: 'Analyze the latest trends in large language model research and deployment'
  },
  {
    icon: '🖥️', bg: 'linear-gradient(135deg, #f3f4f6, #e5e7eb)',
    title: 'Start Deep Research',
    desc: 'Research works on any topic: market analysis, technical deep dives, competitive intelligence.',
    query: 'Synthesize the latest research on transformer-alternative architectures'
  },
])

const healthCards = ref([
  {
    icon: '🩺', bg: 'linear-gradient(135deg, #d1fae5, #a7f3d0)',
    title: 'Clinical Assessment',
    desc: 'Describe a patient case and get evidence-based differential diagnosis.',
    query: '45-year-old male, 2 weeks persistent headache, photophobia, neck stiffness'
  },
  {
    icon: '💊', bg: 'linear-gradient(135deg, #fce7f3, #fbcfe8)',
    title: 'Pharmacology Check',
    desc: 'Review drug interactions, contraindications, and dosing for complex cases.',
    query: 'Patient on Warfarin, Metformin, Lisinopril — starting new antibiotic therapy, check interactions'
  },
])

const dismissedCards = ref([])
const currentCards = computed(() => {
  const cards = isHealthMode.value ? healthCards.value : researchCards.value
  return cards.filter((_, i) => !dismissedCards.value.includes(`${selectedMode.value}-${i}`))
})

const dismissCard = (i) => dismissedCards.value.push(`${selectedMode.value}-${i}`)

const canSubmit = computed(() => formData.value.simulationRequirement.trim().length >= 5)

const useCard = (query) => {
  formData.value.simulationRequirement = query
  queryInput.value?.focus()
}

const adjustHeight = () => {
  const el = queryInput.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
}

const handleSubmit = () => {
  if (!canSubmit.value || loading.value) return
  showConfirmCard.value = true
}

const handleNewChat = () => {
  formData.value.simulationRequirement = ''
  files.value = []
  error.value = ''
  loading.value = false
  showConfirmCard.value = false
  queryInput.value?.focus()
}

const navigateToSession = (item) => {
  router.push({ name: 'Simulation', params: { simulationId: item.simulationId } })
}

const triggerFileInput = () => { if (!loading.value) fileInput.value?.click() }

const handleFileSelect = (e) => {
  const valid = Array.from(e.target.files).filter(f =>
    ['pdf','md','txt'].includes(f.name.split('.').pop().toLowerCase())
  )
  files.value.push(...valid)
}

const URL_PATTERN = /(https?:\/\/[^\s]+)/gi
const extractUrls = (text) => [...new Set((text.match(URL_PATTERN) || []).map(u => u.replace(/[),.;!?]+$/, '')))]

const startSimulation = async () => {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  const configMode = selectedMode.value
  const urls = extractUrls(formData.value.simulationRequirement)

  if (files.value.length > 0 || urls.length > 0) {
    const { setPendingUpload } = await import('../store/pendingUpload.js')
    setPendingUpload(files.value, formData.value.simulationRequirement, urls)
    router.push({ name: 'Simulation', params: { simulationId: 'new' }, query: { configMode: 'deepresearch', stage: 'environment', pendingUpload: '1' } })
  } else {
    try {
      const { createSimulation } = await import('../api/simulation')
      const res = await createSimulation({
        project_id: '', graph_id: '',
        simulation_requirement: formData.value.simulationRequirement,
        config_mode: configMode,
      })
      if (res.success && res.data?.simulation_id) {
        showConfirmCard.value = false
        router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id }, query: { configMode } })
      } else {
        error.value = res.error || 'Failed to create session'
        loading.value = false
      }
    } catch (err) {
      error.value = err.message
      loading.value = false
    }
  }
}

onMounted(async () => {
  if (window.location.search.includes('hivemind_auth=callback')) {
    window.history.replaceState({}, '', window.location.pathname)
  }
  try {
    const { getSimulationHistory } = await import('../api/simulation')
    if (getSimulationHistory) {
      const res = await getSimulationHistory(20)
      if (res?.success && res?.data) {
        recentSessions.value = (res.data.simulations || res.data || []).map(s => ({
          id: s.simulation_id,
          label: (s.simulation_requirement || s.project_name || s.simulation_id || '').substring(0, 45),
          simulationId: s.simulation_id,
        }))
      }
    }
  } catch { /* best-effort */ }
})
</script>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.shell {
  display: flex;
  width: 100%;
  height: 100%;
  background: #ffffff;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
  color: #1a1a1a;
}

/* Main area */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #ffffff;
}

/* Topbar */
.topbar {
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  flex-shrink: 0;
}
.topbar-spacer { flex: 1; }
.topbar-right { display: flex; align-items: center; gap: 4px; }
.topbar-btn {
  width: 32px; height: 32px; border: none; background: none; border-radius: 7px;
  cursor: pointer; color: #8c8882; display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
}
.topbar-btn:hover { background: #f0ede8; color: #1a1a1a; }

/* Center stage */
.center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 24px 40px;
}

.input-wrap {
  width: 100%;
  max-width: 660px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Chat card */
.chat-card {
  background: #ffffff;
  border: 1px solid #e5e3de;
  border-radius: 14px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chat-card.focused {
  border-color: #c8c5be;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04);
}
.chat-card.health-card.focused {
  border-color: #6ee7b7;
  box-shadow: 0 4px 20px rgba(16,185,129,0.1);
}

/* Mode pills row */
.card-modes {
  display: flex;
  gap: 6px;
  padding: 10px 12px 0;
}

.mode-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 11px 3px 8px;
  border: 1px solid #e0ddd8;
  border-radius: 20px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  color: #6b6862;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
  line-height: 1.5;
}
.mode-pill:hover { border-color: #b8b5af; color: #1a1a1a; background: #f5f4f1; }
.mode-pill.active { background: #1a1a1a; border-color: #1a1a1a; color: #fff; }
.mode-pill.mode-health.active { background: #064e3b; border-color: #064e3b; }
.mode-icon { font-size: 12px; line-height: 1; }

/* Textarea */
.card-body { padding: 10px 14px 8px; }
.chat-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-family: inherit;
  font-size: 15px;
  color: #1a1a1a;
  background: transparent;
  min-height: 28px;
  max-height: 200px;
  line-height: 1.5;
}
.chat-textarea::placeholder { color: #b0ada8; }

/* Toolbar */
.card-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 10px;
  border-top: 1px solid #f0ede8;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 4px; }

.tool-btn {
  width: 30px; height: 30px; border: none; background: none; border-radius: 7px;
  cursor: pointer; color: #8c8882; display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
}
.tool-btn:hover { background: #f0ede8; color: #1a1a1a; }
.tool-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.model-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 10px; border: 1px solid #e5e3de; border-radius: 8px;
  background: none; font-size: 12.5px; font-weight: 500; color: #4a4845;
  cursor: pointer; font-family: inherit; transition: background 0.12s;
}
.model-btn:hover { background: #f5f4f1; }

.send-btn {
  width: 32px; height: 32px; border: none; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; background: #e5e3de; color: #8c8882;
  transition: all 0.15s;
}
.send-btn.active { background: #1a1a1a; color: #fff; }
.send-btn.active:hover { background: #333; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  background: #f0ede8; padding: 2px 8px; border-radius: 5px;
  font-size: 11.5px; display: flex; align-items: center; gap: 4px;
}
.chip-x { background: none; border: none; font-size: 14px; cursor: pointer; color: #8c8882; padding: 0; }

/* Suggestions */
.suggestions-wrap { display: flex; flex-direction: column; gap: 10px; }

.suggestions-heading {
  font-size: 13px;
  font-weight: 500;
  color: #8c8882;
  margin: 0;
  padding: 0 2px;
}

.suggestion-cards { display: flex; flex-direction: column; gap: 8px; }

.scard {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 13px 14px;
  background: #fff;
  border: 1px solid #ebe9e4;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s, border-color 0.12s;
  position: relative;
  user-select: none;
}
.scard:hover { background: #faf9f7; border-color: #dddbd6; }

.scard-icon {
  width: 38px; height: 38px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.scard-emoji { font-size: 18px; line-height: 1; }

.scard-text { flex: 1; min-width: 0; }
.scard-title { font-size: 13.5px; font-weight: 600; color: #1a1a1a; margin-bottom: 2px; }
.scard-desc { font-size: 12.5px; color: #6b6862; line-height: 1.4; }

.scard-close {
  position: absolute; top: 10px; right: 10px;
  width: 22px; height: 22px; border: none; background: none; border-radius: 5px;
  cursor: pointer; color: #b0ada8; display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
  opacity: 0;
}
.scard:hover .scard-close { opacity: 1; }
.scard-close:hover { background: #f0ede8; color: #1a1a1a; }

/* Transitions */
.fade-up-enter-active { transition: opacity 0.25s ease, transform 0.3s cubic-bezier(0.16,1,0.3,1); }
.fade-up-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.fade-up-enter-from { opacity: 0; transform: translateY(16px); }
.fade-up-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
