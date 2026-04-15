<template>
  <div class="app-shell">
    <AppSidebar
      :collapsed="sidebarCollapsed"
      :sessions="recentSessions"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @go-home="handleNewChat"
      @select-session="(simId) => navigateToSession({ simulationId: simId })"
      @delete-session="handleDeleteSession"
    />

    <main class="main-area">
      <!-- Center content -->
      <div class="center-stage">
        <div class="hero-brand">
          <img :src="davinciLogo" alt="Da'vinci" class="hero-logo" />
          <h1 class="hero-title">Deep Research</h1>
        </div>

        <!-- Chat input card -->
        <Transition name="card-swap" mode="out-in">
          <div v-if="!showConfirmCard" key="input" class="chat-card-container">
            <div class="chat-card">
              <div class="card-chrome">
                <div class="traffic-lights">
                  <span class="dot red"></span>
                  <span class="dot yellow"></span>
                  <span class="dot green"></span>
                </div>
                <span class="card-label">AI Research</span>
              </div>
              <div class="card-body">
                <textarea
                  ref="queryInput"
                  v-model="formData.simulationRequirement"
                  @keydown="handleKeyDown"
                  placeholder="Ask anything..."
                  rows="1"
                  class="chat-input"
                  :disabled="loading"
                  @input="adjustTextareaHeight"
                ></textarea>
              </div>
              <div class="card-footer">
                <div class="footer-left">
                  <button class="attach-btn" @click="triggerFileInput" :disabled="loading">
                    <span class="attach-plus">+</span>
                  </button>
                  <button class="connector-btn">
                    <span class="connector-icon">@</span>
                    <span>Sources</span>
                  </button>
                  <input
                    ref="fileInput"
                    type="file"
                    multiple
                    accept=".pdf,.md,.txt"
                    @change="handleFileSelect"
                    style="display: none"
                    :disabled="loading"
                  />
                  <div v-if="files.length > 0" class="chips">
                    <span v-for="(file, index) in files" :key="index" class="chip">
                      {{ file.name }}
                      <button @click.stop="removeFile(index)" class="chip-x">&times;</button>
                    </span>
                  </div>
                </div>
                <div class="footer-right">
                  <div class="model-selector">
                    <span>Model</span>
                    <span class="selector-chevron">▾</span>
                  </div>
                  <button
                    class="submit-btn"
                    @click="handleSubmitQuery"
                    :disabled="!canSubmit || loading"
                  >
                    <svg class="submit-icon" viewBox="0 0 24 24" width="20" height="20">
                      <path d="M12 4l-1.41 1.41L15.17 10H4v2h11.17l-4.58 4.59L12 18l7-7-7-7z" fill="currentColor"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Suggestion Panel -->
            <div class="suggestion-panel">
              <div class="suggestion-header">
                <span class="header-icon">✨</span>
                <span class="header-text">Research ideas for you</span>
              </div>
              <div class="suggestion-grid">
                <button 
                  v-for="idea in researchIdeas" 
                  :key="idea.text"
                  class="suggestion-item"
                  @click="useIdea(idea.text)"
                >
                  <span v-if="idea.tag" class="suggestion-tag" :class="idea.tag.toLowerCase()">{{ idea.tag }}</span>
                  <span class="suggestion-text">{{ idea.text }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- CSI confirmation card (replaces input after submit) -->
          <CsiConfirmCard
            v-else
            key="confirm"
            :visible="true"
            :query="formData.simulationRequirement"
            :loading="loading"
            @back="showConfirmCard = false"
            @continue="startSimulation"
          />
        </Transition>
      </div>
    </main>

    <!-- HIVEMIND Auth Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showAuthModal" class="modal-overlay" @click.self="showAuthModal = false">
          <div class="auth-modal">
            <div class="modal-header">
              <div class="modal-title-row">
                <span class="modal-icon">&#9889;</span>
                <h3 class="modal-title">Connect to HIVEMIND</h3>
              </div>
              <button class="modal-close" @click="showAuthModal = false">&times;</button>
            </div>

            <div class="modal-body">
              <p class="modal-desc">
                Connect your HIVEMIND account to sync research sessions, access memory graph, and use advanced features.
              </p>

              <!-- Google OAuth -->
              <button class="auth-option google" @click="connectGoogle" :disabled="authLoading">
                <svg class="google-icon" viewBox="0 0 24 24" width="18" height="18">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                <span>Continue with Google</span>
              </button>

              <!-- Divider -->
              <div class="auth-divider">
                <span>or</span>
              </div>

              <!-- API Key -->
              <div class="apikey-section">
                <label class="apikey-label">HIVEMIND API Key</label>
                <div class="apikey-input-row">
                  <input
                    v-model="apiKeyInput"
                    type="password"
                    class="apikey-input"
                    placeholder="hmk_live_..."
                    :disabled="authLoading"
                    @keydown.enter="connectApiKey"
                  />
                  <button class="apikey-submit" @click="connectApiKey" :disabled="!apiKeyInput.trim() || authLoading">
                    Connect
                  </button>
                </div>
                <p class="apikey-hint">
                  Get your API key from <a :href="hivemindUrl + '/hivemind/settings'" target="_blank" class="apikey-link">HIVEMIND Settings</a>
                </p>
              </div>

              <!-- Status -->
              <div v-if="authError" class="auth-error">{{ authError }}</div>
              <div v-if="hivemindUser" class="auth-success">
                Connected as {{ hivemindUser.displayName || hivemindUser.email }}
                <button class="disconnect-btn" @click="disconnectHivemind">Disconnect</button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSidebar } from '../store/sidebar'
import AppSidebar from '../components/ui/AppSidebar.vue'
import CsiConfirmCard from '../components/ui/CsiConfirmCard.vue'
import davinciLogo from '../assets/davinci-logo.svg'

const router = useRouter()
const { sidebarCollapsed } = useSidebar()
const recentSessions = ref([])
const fileInput = ref(null)
const queryInput = ref(null)

const formData = ref({
  simulationRequirement: ''
})
const files = ref([])
const loading = ref(false)
const showConfirmCard = ref(false)

const researchIdeas = ref([
  { text: 'Analyze market competitors for generative AI platforms in 2026', tag: 'Market' },
  { text: 'Benchmark on-device LLM performance across different hardware configurations', tag: 'Technical' },
  { text: 'How do HIVE-MIND agents compare to traditional linear search workflows?', tag: 'Strategy' },
  { text: 'Map global silicon supply chain vulnerabilities and mitigation strategies', tag: 'Geopolitics' },
  { text: 'Synthesize the latest research on transformer-alternative architectures', tag: 'Research' }
])

const useIdea = (text) => {
  formData.value.simulationRequirement = text
  queryInput.value?.focus()
}

const adjustTextareaHeight = () => {
  const el = queryInput.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

const handleSubmitQuery = () => {
  if (!canSubmit.value || loading.value) return
  showConfirmCard.value = true
}
const error = ref('')

// HIVEMIND Auth
const hivemindUrl = ref(import.meta.env.VITE_HIVEMIND_CONTROL_PLANE_URL || 'https://api.hivemind.davinciai.eu:8040')
const showAuthModal = ref(false)
const authLoading = ref(false)
const authError = ref('')
const apiKeyInput = ref('')
const hivemindUser = ref(null)

// Load saved auth on mount
const loadSavedAuth = () => {
  try {
    const saved = localStorage.getItem('hivemind_auth')
    if (saved) {
      const parsed = JSON.parse(saved)
      hivemindUser.value = parsed.user || null
    }
  } catch { /* ignore */ }
}

const connectGoogle = () => {
  authError.value = ''
  // Open HIVEMIND Google OAuth in a popup
  // Use the same pattern as HIVEMIND's frontend: /auth/google with return_to
  const returnUrl = encodeURIComponent(window.location.origin + '/?hivemind_auth=callback')
  const authUrl = `${hivemindUrl.value}/auth/google?return_to=${returnUrl}`
  const popup = window.open(authUrl, 'hivemind_auth', 'width=500,height=600,popup=yes')

  // Listen for the popup to close and check for auth
  const timer = setInterval(async () => {
    if (popup?.closed) {
      clearInterval(timer)
      await checkHivemindSession()
    }
  }, 500)
}

const checkHivemindSession = async () => {
  authLoading.value = true
  authError.value = ''
  try {
    const res = await fetch(`${hivemindUrl.value}/v1/bootstrap`, {
      credentials: 'include',
    })
    if (res.ok) {
      const data = await res.json()
      if (data.user) {
        const u = data.user
        hivemindUser.value = {
          id: u.id,
          email: u.email,
          displayName: u.display_name || u.displayName || u.email,
          avatarUrl: u.avatar_url || u.avatarUrl || null,
          role: u.role,
          org: data.organization,
        }
        localStorage.setItem('hivemind_auth', JSON.stringify({ user: hivemindUser.value, method: 'google' }))
        showAuthModal.value = false
      }
    }
  } catch (err) {
    authError.value = 'Could not reach HIVEMIND. Is it running?'
  } finally {
    authLoading.value = false
  }
}

const connectApiKey = async () => {
  const key = apiKeyInput.value.trim()
  if (!key) return
  authLoading.value = true
  authError.value = ''
  try {
    // Validate the API key by calling bootstrap with it
    const res = await fetch(`${hivemindUrl.value}/v1/bootstrap`, {
      headers: { 'X-API-Key': key },
    })
    if (res.ok) {
      const data = await res.json()
      if (data.user) {
        const u = data.user
        hivemindUser.value = {
          id: u.id,
          email: u.email,
          displayName: u.display_name || u.displayName || u.email,
          avatarUrl: u.avatar_url || u.avatarUrl || null,
          role: u.role,
          org: data.organization,
        }
        localStorage.setItem('hivemind_auth', JSON.stringify({
          user: hivemindUser.value,
          method: 'api_key',
          apiKey: key,
        }))
        showAuthModal.value = false
        apiKeyInput.value = ''
      } else {
        authError.value = 'API key is valid but no user found'
      }
    } else if (res.status === 401) {
      authError.value = 'Invalid API key'
    } else {
      authError.value = `HIVEMIND returned ${res.status}`
    }
  } catch (err) {
    authError.value = 'Could not reach HIVEMIND. Is it running?'
  } finally {
    authLoading.value = false
  }
}

const disconnectHivemind = () => {
  hivemindUser.value = null
  localStorage.removeItem('hivemind_auth')
  apiKeyInput.value = ''
  authError.value = ''
}

const URL_PATTERN = /(https?:\/\/[^\s]+)/gi

const extractUrls = (text) => {
  const matches = text.match(URL_PATTERN) || []
  return [...new Set(matches.map((url) => url.replace(/[),.;!?]+$/, '')))]
}

const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim().length >= 5
})

// Load auth + history on mount
onMounted(async () => {
  loadSavedAuth()

  // Check for OAuth callback
  if (window.location.search.includes('hivemind_auth=callback')) {
    await checkHivemindSession()
    window.history.replaceState({}, '', window.location.pathname)
  }

  try {
    const { getSimulationHistory } = await import('../api/simulation')
    if (getSimulationHistory) {
      const res = await getSimulationHistory(15)
      if (res?.success && res?.data) {
        recentSessions.value = (res.data.simulations || res.data || []).map(s => ({
          id: s.simulation_id,
          label: (s.simulation_requirement || s.project_name || s.simulation_id || '').substring(0, 40),
          simulationId: s.simulation_id,
        }))
      }
    }
  } catch {
    // History load is best-effort
  }
})

// Handlers
const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    startSimulation()
  }
}

const handleNewChat = () => {
  formData.value.simulationRequirement = ''
  files.value = []
  error.value = ''
  loading.value = false
  queryInput.value?.focus()
}

const navigateToSession = (item) => {
  router.push({ name: 'Simulation', params: { simulationId: item.simulationId } })
}

const handleDeleteSession = async (simId) => {
  if (!confirm('Delete this session and all its data? This cannot be undone.')) return
  try {
    const { deleteSimulation } = await import('../api/simulation')
    const res = await deleteSimulation(simId)
    if (res?.success) {
      recentSessions.value = recentSessions.value.filter(s => s.simulationId !== simId)
    }
  } catch {
    // best-effort
  }
}

const triggerFileInput = () => {
  if (!loading.value) fileInput.value?.click()
}

const handleFileSelect = (event) => {
  const selected = Array.from(event.target.files)
  const valid = selected.filter(f => ['pdf', 'md', 'txt'].includes(f.name.split('.').pop().toLowerCase()))
  files.value.push(...valid)
}

const removeFile = (index) => {
  files.value.splice(index, 1)
}

const startSimulation = async () => {
  if (!canSubmit.value || loading.value) return

  loading.value = true
  const urls = extractUrls(formData.value.simulationRequirement)

  if (files.value.length > 0 || urls.length > 0) {
    const { setPendingUpload } = await import('../store/pendingUpload.js')
    setPendingUpload(files.value, formData.value.simulationRequirement, urls)

    router.push({
      name: 'Simulation',
      params: { simulationId: 'new' },
      query: { configMode: 'deepresearch', stage: 'environment', pendingUpload: '1' }
    })
  } else {
    try {
      const { createSimulation } = await import('../api/simulation')
      const res = await createSimulation({
        project_id: '',
        graph_id: '',
        simulation_requirement: formData.value.simulationRequirement,
        config_mode: 'web_research',
      })

      if (res.success && res.data?.simulation_id) {
        showConfirmCard.value = false
        router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
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
</script>

<style scoped>
* { box-sizing: border-box; }

.app-shell {
  width: 100%;
  height: 100%;
  display: flex;
  background-color: #faf9f4;
  /* Monochrome ASCII pattern background */
  background-image: url("data:image/svg+xml,%3Csvg width='200' height='200' viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cstyle%3E text %7B font-family: 'Courier New', monospace; font-size: 14px; font-weight: 900; fill: %23000000; opacity: 0.12; letter-spacing: 2px; %7D%3C/style%3E%3Ctext x='5' y='20'%3E0 1 1 0 1 0 1 0 1 1 %23 %26 *%3C/text%3E%3Ctext x='5' y='45'%3E%26 * _ - %2B %3D ! ~ %3F / %5C %7C %23 %5B %5D%3C/text%3E%3Ctext x='5' y='70'%3E%7B %7D %24 %3E %3C _ ( ) : ; ' %22 %2C .%3C/text%3E%3Ctext x='5' y='95'%3E0 1 1 0 1 0 1 0 1 1 %23 %26 *%3C/text%3E%3Ctext x='5' y='120'%3E%26 * _ - %2B %3D ! ~ %3F / %5C %7C %23 %5B %5D%3C/text%3E%3Ctext x='5' y='145'%3E%7B %7D %24 %3E %3C _ ( ) : ; ' %22 %2C .%3C/text%3E%3Ctext x='5' y='170'%3E0 1 1 0 1 0 1 0 1 1 %23 %26 *%3C/text%3E%3Ctext x='5' y='195'%3E%26 * _ - %2B %3D ! ~ %3F / %5C %7C %23 %5B %5D%3C/text%3E%3C/svg%3E");
  background-size: 200px 200px;
  background-repeat: repeat;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, -apple-system, sans-serif;
  color: #000000;
  overflow: hidden;
}

:deep(.app-sidebar) {
  flex-shrink: 0;
  height: 100%;
}

.main-area {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  background: transparent;
  min-width: 0;
}

/* Old sidebar styles removed — now using AppSidebar.vue */

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.brand-hex {
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

.brand-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.brand-name {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.brand-sub {
  font-size: 10px;
  color: #a3a3a3;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}

.collapse-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #a3a3a3;
  font-size: 16px;
  padding: 4px;
  border-radius: 6px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: #f3f1ec;
  color: #525252;
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 10px;
  overflow-y: auto;
  gap: 14px;
}

.sidebar-action {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #DDD9D3;
  border-radius: 10px;
  background: #FFF;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #0a0a0a;
  transition: all 0.15s;
  margin-bottom: 12px;
}

.sidebar-action:hover {
  background: #F0EEED;
  border-color: #CCC;
}

.action-icon {
  font-size: 16px;
  color: #737373;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-item {
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
}

.nav-item:hover {
  background: #f3f1ec;
  color: #0a0a0a;
}

.nav-item.active {
  background: #f3f1ec;
  color: #0a0a0a;
  font-weight: 500;
}

.nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  color: #a3a3a3;
  flex-shrink: 0;
}

.nav-item.active .nav-icon,
.nav-item:hover .nav-icon {
  color: #525252;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.section-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a3a3a3;
  padding: 0 10px;
  margin-bottom: 4px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.history-item {
  padding: 7px 10px;
  font-size: 12px;
  color: #525252;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: all 0.15s;
}

.history-item:hover {
  background: #f3f1ec;
  color: #0a0a0a;
}

.history-empty {
  padding: 12px;
  font-size: 12px;
  color: #a3a3a3;
}

/* (main-area defined above) */

/* navbar and sidebar are now in App.vue */

/* Card swap transition */
.card-swap-enter-active {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.25s ease;
}
.card-swap-leave-active {
  transition: transform 0.2s ease, opacity 0.15s ease;
}
.card-swap-enter-from {
  transform: translateY(30px);
  opacity: 0;
}
.card-swap-leave-to {
  transform: translateY(-15px);
  opacity: 0;
}

.main-area {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  background: white;
  min-width: 0;
}

.center-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 40px;
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}

.hero-brand {
  margin-bottom: 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.hero-logo {
  height: 64px;
  width: auto;
  filter: invert(1);
}

.hero-title {
  font-size: 32px;
  font-weight: 700;
  color: #000;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  letter-spacing: -0.02em;
}

.chat-card-container {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Updated Chat input card */
.chat-card {
  width: 100%;
  background: #FFF;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.chat-card:focus-within {
  border-color: #117dff;
  box-shadow: 0 4px 24px rgba(17, 125, 255, 0.1);
}

.card-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fdfdfc;
  border-bottom: 1px solid #f2f2f1;
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
  color: #999;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.card-body {
  padding: 12px 16px;
}

.chat-input {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 16px;
  font-weight: 400;
  color: #000;
  background: transparent;
  min-height: 24px;
  max-height: 200px;
}

.chat-input::placeholder {
  color: #a3a3a3;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid #f2f2f1;
}

.footer-left, .footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.attach-btn {
  width: 24px;
  height: 24px;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  background: #FFF;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #737373;
  font-size: 14px;
  cursor: pointer;
}

.connector-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  background: #fdfdfc;
  font-size: 13px;
  color: #4a4a4a;
  cursor: pointer;
}

.connector-icon {
  font-weight: 700;
  color: #117dff;
}

.model-selector {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #737373;
  cursor: pointer;
  font-weight: 500;
}

.submit-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 50%;
  transition: transform 0.2s, background 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #f3f3f3;
  transform: translateX(2px);
}

.submit-btn:disabled {
  color: #e5e5e5;
  cursor: not-allowed;
}

/* Suggestion Panel */
.suggestion-panel {
  background: #fdfdfc;
  border: 1px solid #f0f0ef;
  border-radius: 12px;
  padding: 16px;
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: #737373;
}

.header-text {
  font-size: 13px;
  font-weight: 600;
}

.suggestion-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.suggestion-item:hover {
  background: #f5f5f4;
}

.suggestion-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 4px;
}

.suggestion-tag.market { background: #E0E7FF; color: #4338CA; }
.suggestion-tag.technical { background: #ECFDF5; color: #047857; }
.suggestion-tag.strategy { background: #FEF3C7; color: #92400E; }
.suggestion-tag.geopolitics { background: #FCE7F3; color: #9D174D; }
.suggestion-tag.research { background: #F3E8FF; color: #6D28D9; }

.suggestion-text {
  font-size: 14px;
  color: #262626;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chip {
  background: #f3f3f3;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chip-x {
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
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
}

@keyframes spinning {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.submit-btn {
  padding: 8px 20px;
  border-radius: 10px;
  border: none;
  background: #0a0a0a;
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

/* ─── Responsive ──────────────────────────────────── */
/* ─── Sidebar Auth ────────────────────────────── */
.sidebar-auth {
  padding: 8px 0;
  border-top: 1px solid #E8E5E0;
}

.connect-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid #D4D1CC;
  border-radius: 10px;
  background: linear-gradient(135deg, #FFF 0%, #F7F6F3 100%);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: #525252;
  transition: all 0.2s;
}

.connect-btn:hover {
  border-color: #117dff;
  color: #117dff;
  background: rgba(17, 125, 255, 0.04);
}

.connect-icon {
  font-size: 14px;
}

.auth-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.auth-user:hover {
  background: #EDEBE8;
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
}

.user-avatar-fallback {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #117dff;
  color: #FFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-size: 12px;
  font-weight: 600;
  color: #0a0a0a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.user-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #16a34a;
  background: rgba(22, 163, 74, 0.1);
  padding: 1px 5px;
  border-radius: 4px;
}

.user-org {
  font-size: 9px;
  color: #737373;
}

.user-role {
  font-size: 9px;
  color: #a3a3a3;
  text-transform: capitalize;
}

/* ─── Auth Modal ──────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.auth-modal {
  width: 420px;
  background: #FFF;
  border-radius: 20px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #E8E5E0;
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-icon {
  font-size: 18px;
  color: #117dff;
}

.modal-title {
  font-size: 16px;
  font-weight: 700;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #a3a3a3;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: all 0.15s;
}

.modal-close:hover {
  background: #F0EEED;
  color: #333;
}

.modal-body {
  padding: 24px;
}

.modal-desc {
  font-size: 13px;
  color: #737373;
  line-height: 1.6;
  margin: 0 0 20px;
}

.auth-option {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 12px;
  border: 1px solid #D4D1CC;
  border-radius: 12px;
  background: #FFF;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #0a0a0a;
  transition: all 0.2s;
}

.auth-option:hover:not(:disabled) {
  border-color: #999;
  background: #FAFAFA;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.auth-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.google-icon {
  flex-shrink: 0;
}

.auth-divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #E8E5E0;
}

.auth-divider span {
  padding: 0 12px;
  font-size: 11px;
  color: #a3a3a3;
}

.apikey-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.apikey-label {
  font-size: 12px;
  font-weight: 600;
  color: #525252;
}

.apikey-input-row {
  display: flex;
  gap: 8px;
}

.apikey-input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #D4D1CC;
  border-radius: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  outline: none;
  transition: border-color 0.2s;
}

.apikey-input:focus {
  border-color: #117dff;
}

.apikey-submit {
  padding: 10px 16px;
  border: none;
  border-radius: 10px;
  background: #0a0a0a;
  color: #FFF;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.apikey-submit:hover:not(:disabled) {
  background: #333;
}

.apikey-submit:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.apikey-hint {
  font-size: 11px;
  color: #a3a3a3;
  margin: 0;
}

.apikey-link {
  color: #117dff;
  text-decoration: none;
}

.apikey-link:hover {
  text-decoration: underline;
}

.auth-error {
  margin-top: 16px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #FEF2F2;
  border: 1px solid #FECACA;
  color: #DC2626;
  font-size: 12px;
}

.auth-success {
  margin-top: 16px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #F0FDF4;
  border: 1px solid #BBF7D0;
  color: #16a34a;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.disconnect-btn {
  background: none;
  border: none;
  color: #DC2626;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}

.disconnect-btn:hover {
  background: #FEF2F2;
}

/* Modal transitions */
.modal-enter-active { transition: all 0.25s ease; }
.modal-leave-active { transition: all 0.2s ease; }
.modal-enter-from { opacity: 0; }
.modal-enter-from .auth-modal { transform: scale(0.95) translateY(10px); }
.modal-leave-to { opacity: 0; }
.modal-leave-to .auth-modal { transform: scale(0.95) translateY(10px); }

/* ─── Responsive ──────────────────────────────── */
@media (max-width: 768px) {
  .sidebar { width: 56px; }
  .sidebar-content { display: none; }
  .center-stage { padding: 0 16px 40px; }
  .chat-card { max-width: 100%; }
  .auth-modal { width: calc(100% - 32px); }
}
</style>
