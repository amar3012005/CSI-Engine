<template>
  <Teleport to="body">
    <div class="agent-dock" v-if="visibleAgents.length > 0">
      <div class="dock-inner">
        <!-- Live pulse indicator -->
        <div class="dock-live">
          <span class="live-dot"></span>
          <span class="live-label">LIVE</span>
        </div>

        <div class="dock-divider"></div>

        <!-- Agent avatars appear one by one -->
        <TransitionGroup name="agent-spawn" tag="div" class="dock-agents">
          <div
            v-for="agent in visibleAgents"
            :key="agent.id"
            class="agent-slot"
            @mouseenter="hoveredId = agent.id"
            @mouseleave="handleLeave(agent.id)"
            @click="toggleDropdown(agent.id)"
          >
            <!-- Avatar bubble -->
            <button
              class="agent-avatar"
              :class="[
                agent.online ? 'is-online' : '',
                activeDropdown === agent.id ? 'is-active' : ''
              ]"
              :style="{ background: agent.gradientBg || '#e5e7eb' }"
              :aria-label="`${agent.name} – ${agent.role}`"
            >
              <span class="avatar-emoji">{{ agent.emoji }}</span>
              <span v-if="agent.online" class="online-dot"></span>
            </button>

            <!-- Hover tooltip -->
            <Transition name="tooltip-fade">
              <div
                v-if="hoveredId === agent.id && activeDropdown !== agent.id"
                class="agent-tooltip"
              >
                <span class="tooltip-name">{{ agent.name }}</span>
                <span class="tooltip-role">{{ agent.role }}</span>
              </div>
            </Transition>

            <!-- Click dropdown – current action -->
            <Transition name="dropdown-slide">
              <div
                v-if="activeDropdown === agent.id"
                class="agent-dropdown"
              >
                <div class="dropdown-header">
                  <span class="dh-emoji">{{ agent.emoji }}</span>
                  <div class="dh-info">
                    <span class="dh-name">{{ agent.name }}</span>
                    <span class="dh-role">{{ agent.role }}</span>
                  </div>
                  <button class="dh-close" @click.stop="activeDropdown = null">✕</button>
                </div>
                <div class="dropdown-action" v-if="agent.currentAction">
                  <span class="da-badge" :class="actionBadgeClass(agent.currentAction.type)">
                    {{ actionLabel(agent.currentAction.type) }}
                  </span>
                  <span class="da-text">{{ agent.currentAction.summary }}</span>
                  <span class="da-time">{{ agent.currentAction.time }}</span>
                </div>
                <div class="dropdown-action no-action" v-else>
                  <span class="da-text muted">No recent activity</span>
                </div>
              </div>
            </Transition>
          </div>
        </TransitionGroup>

        <!-- Agent count pill (when many agents) -->
        <div v-if="hiddenCount > 0" class="dock-overflow">
          +{{ hiddenCount }}
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  // Array of profile objects from the simulation API
  profiles: {
    type: Array,
    default: () => []
  },
  // Map of agent_id -> latest action object
  agentActions: {
    type: Object,
    default: () => ({})
  },
  // Max number of avatars shown before +N overflow pill
  maxVisible: {
    type: Number,
    default: 12
  }
})

// ─── palette for consistent agent coloring ──────────────────────────────────
const PALETTES = [
  { bg: 'linear-gradient(135deg,#86efac,#dcfce7)', emoji: '🔬' },
  { bg: 'linear-gradient(135deg,#c084fc,#f3e8ff)', emoji: '🧪' },
  { bg: 'linear-gradient(135deg,#fde047,#fefce8)', emoji: '📊' },
  { bg: 'linear-gradient(135deg,#fca5a5,#fef2f2)', emoji: '🌐' },
  { bg: 'linear-gradient(135deg,#67e8f9,#ecfeff)', emoji: '⚡' },
  { bg: 'linear-gradient(135deg,#fb923c,#fff7ed)', emoji: '🎯' },
  { bg: 'linear-gradient(135deg,#a3e635,#f7fee7)', emoji: '🔍' },
  { bg: 'linear-gradient(135deg,#f472b6,#fdf2f8)', emoji: '💡' },
  { bg: 'linear-gradient(135deg,#38bdf8,#f0f9ff)', emoji: '🧠' },
  { bg: 'linear-gradient(135deg,#4ade80,#f0fdf4)', emoji: '🤖' },
]

// ─── normalize incoming profiles into dock agents ────────────────────────────
const allAgents = computed(() => {
  return props.profiles.map((p, i) => {
    const palette = PALETTES[i % PALETTES.length]
    const agentId = p.agent_id ?? p.id ?? i

    // Determine role from research_role or profession fields
    const role =
      p.research_role ||
      p.role ||
      p.profession ||
      p.responsibility?.substring?.(0, 40) ||
      'Research Agent'

    // Pick emoji: prefer agent-specific role emoji, fall back to palette
    const roleEmoji =
      p.emoji ||
      (role?.toLowerCase().includes('challenge') ? '⚔️'  :
       role?.toLowerCase().includes('fact')      ? '✅'  :
       role?.toLowerCase().includes('domain')    ? '🔬'  :
       role?.toLowerCase().includes('synth')     ? '🧬'  :
       role?.toLowerCase().includes('method')    ? '📐'  :
       palette.emoji)

    return {
      id: agentId,
      name: p.username || p.name || p.agent_name || `Agent ${i + 1}`,
      role,
      emoji: roleEmoji,
      online: true,
      gradientBg: palette.bg,
    }
  })
})

// ─── stagger the appearance of agents ────────────────────────────────────────
const visibleAgentCount = ref(0)
let spawnTimer = null

const startSpawning = () => {
  if (spawnTimer) clearInterval(spawnTimer)
  visibleAgentCount.value = 0
  spawnTimer = setInterval(() => {
    if (visibleAgentCount.value < allAgents.value.length) {
      visibleAgentCount.value++
    } else {
      clearInterval(spawnTimer)
      spawnTimer = null
    }
  }, 180)
}

watch(
  () => props.profiles.length,
  (newLen, oldLen) => {
    if (newLen > oldLen) startSpawning()
  }
)

onMounted(() => {
  if (props.profiles.length > 0) startSpawning()
})

onBeforeUnmount(() => {
  if (spawnTimer) clearInterval(spawnTimer)
})

const visibleAgents = computed(() =>
  allAgents.value.slice(0, Math.min(visibleAgentCount.value, props.maxVisible))
)

const hiddenCount = computed(() =>
  Math.max(0, allAgents.value.length - props.maxVisible)
)

// ─── hover / dropdown state ───────────────────────────────────────────────────
const hoveredId = ref(null)
const activeDropdown = ref(null)

const handleLeave = (id) => {
  if (hoveredId.value === id) hoveredId.value = null
}

const toggleDropdown = (id) => {
  activeDropdown.value = activeDropdown.value === id ? null : id
  hoveredId.value = null
}

// Close dropdown on outside click
const handleOutsideClick = (e) => {
  if (!e.target.closest('.agent-slot')) {
    activeDropdown.value = null
  }
}
onMounted(() => document.addEventListener('mousedown', handleOutsideClick))
onBeforeUnmount(() => document.removeEventListener('mousedown', handleOutsideClick))

// ─── action helpers ───────────────────────────────────────────────────────────
const agentCurrentAction = (agentId) => {
  const action = props.agentActions[agentId]
  if (!action) return null

  const type = action.action_type || action.type || ''
  const detail = action.detail || action.action_args || {}

  let summary = ''
  if (type === 'SEARCH_WEB' || type === 'search_web') {
    summary = `Searching: "${detail.query?.substring(0, 60) || ''}"`
  } else if (type === 'READ_URL' || type === 'investigate_source') {
    summary = `Reading ${detail.urls?.length || 1} source(s)`
  } else if (type === 'PROPOSE_CLAIM' || type === 'propose_claim') {
    summary = `Proposing claim (confidence: ${detail.confidence || '?'})`
  } else if (type === 'CHALLENGE_CLAIM' || type === 'peer_review') {
    summary = `Challenging a claim`
  } else if (type === 'CREATE_POST') {
    const content = detail.content || detail.text || ''
    summary = content.substring(0, 80) + (content.length > 80 ? '…' : '')
  } else if (type === 'DO_NOTHING' || type === 'IDLE') {
    summary = 'Observing...'
  } else {
    summary = JSON.stringify(detail).substring(0, 80)
  }

  const ts = action.timestamp || action.created_at
  const time = ts
    ? new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : ''

  return { type, summary, time }
}

// Expose for template (use computed per-agent in template via helper)
const enrichedVisibleAgents = computed(() =>
  visibleAgents.value.map(a => ({
    ...a,
    currentAction: agentCurrentAction(a.id)
  }))
)

// Re-export as the actual list used by template
const visibleAgentsWithActions = computed(() => enrichedVisibleAgents.value)

// Override visibleAgents in template binding
// (we expose the enriched version under the same name via computed)
const agentSlots = computed(() => visibleAgentsWithActions.value)

const actionLabel = (type) => {
  const map = {
    'SEARCH_WEB': 'SEARCH', 'search_web': 'SEARCH',
    'READ_URL': 'READ', 'investigate_source': 'READ',
    'PROPOSE_CLAIM': 'CLAIM', 'propose_claim': 'CLAIM',
    'CHALLENGE_CLAIM': 'REVIEW', 'peer_review': 'REVIEW',
    'CREATE_POST': 'POST', 'REPOST': 'REPOST',
    'LIKE_POST': 'LIKE', 'CREATE_COMMENT': 'COMMENT',
    'DO_NOTHING': 'IDLE', 'IDLE': 'IDLE',
  }
  return map[type] || (type?.substring(0, 10) || 'ACT')
}

const actionBadgeClass = (type) => {
  if (!type) return 'badge-default'
  const t = type.toUpperCase()
  if (t.includes('SEARCH') || t.includes('READ')) return 'badge-blue'
  if (t.includes('CLAIM') || t.includes('PROPOSE')) return 'badge-green'
  if (t.includes('CHALLENGE') || t.includes('REVIEW')) return 'badge-orange'
  if (t.includes('POST') || t.includes('COMMENT')) return 'badge-purple'
  if (t.includes('IDLE') || t.includes('NOTHING')) return 'badge-gray'
  return 'badge-default'
}
</script>

<!-- Re-expose enriched agents under the original loop name via defineExpose trick -->
<!-- The template uses `agent` from agentSlots computed -->

<template>
  <!-- Teleport wrapper already defined above; this second <template> block
       is the real one. Vue SFCs allow only one <template>. The component
       above already defines the full template. Remove this duplicate. -->
</template>

<style scoped>
/* ─── Dock wrapper ─────────────────────────────────────────────────────────── */
.agent-dock {
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  pointer-events: none;
}

.dock-inner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(0,0,0,0.08);
  border-top: none;
  border-radius: 0 0 20px 20px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.12);
  pointer-events: all;
}

/* ─── Live indicator ───────────────────────────────────────────────────────── */
.dock-live {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  animation: live-pulse 1.4s ease-in-out infinite;
}

@keyframes live-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
  50% { box-shadow: 0 0 0 5px rgba(34,197,94,0); }
}

.live-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #22c55e;
  font-family: 'Space Grotesk', monospace, sans-serif;
}

.dock-divider {
  width: 1px;
  height: 22px;
  background: rgba(0,0,0,0.1);
  flex-shrink: 0;
  margin: 0 2px;
}

/* ─── Agent slots row ──────────────────────────────────────────────────────── */
.dock-agents {
  display: flex;
  align-items: center;
  gap: 4px;
}

.agent-slot {
  position: relative;
}

/* ─── Avatar button ──────────────────────────────────────────────────────────*/
.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.18s cubic-bezier(0.34,1.56,0.64,1),
              box-shadow 0.18s ease;
  position: relative;
  outline: none;
}

.agent-avatar:hover {
  transform: translateY(-4px) scale(1.1);
  box-shadow: 0 6px 18px rgba(0,0,0,0.16);
}

.agent-avatar.is-active {
  transform: translateY(-2px) scale(1.08);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.35);
}

.avatar-emoji {
  font-size: 18px;
  line-height: 1;
  pointer-events: none;
  user-select: none;
}

.online-dot {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #22c55e;
  border: 2px solid #fff;
}

/* ─── Hover tooltip ──────────────────────────────────────────────────────────*/
.agent-tooltip {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(10,10,10,0.85);
  color: #fff;
  border-radius: 10px;
  padding: 7px 10px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.22);
  z-index: 10;
}

.tooltip-name {
  font-weight: 700;
  font-size: 12px;
}

.tooltip-role {
  color: #a5b4fc;
  font-size: 10px;
  font-family: monospace;
}

/* caret */
.agent-tooltip::before {
  content: '';
  position: absolute;
  top: -5px;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-bottom-color: rgba(10,10,10,0.85);
  border-top: none;
}

/* ─── Click dropdown ─────────────────────────────────────────────────────────*/
.agent-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: 240px;
  background: #fff;
  border: 1px solid rgba(0,0,0,0.09);
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.16);
  overflow: hidden;
  z-index: 10;
}

.dropdown-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px 10px;
  border-bottom: 1px solid #f1f5f9;
}

.dh-emoji {
  font-size: 22px;
  flex-shrink: 0;
}

.dh-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.dh-name {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dh-role {
  font-size: 10px;
  color: #6366f1;
  font-family: 'Space Grotesk', monospace, sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.dh-close {
  margin-left: auto;
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 6px;
  flex-shrink: 0;
  transition: background 0.12s;
}
.dh-close:hover { background: #f1f5f9; color: #334155; }

.dropdown-action {
  padding: 10px 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.da-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.07em;
  width: fit-content;
}

.badge-blue   { background: #dbeafe; color: #1d4ed8; }
.badge-green  { background: #dcfce7; color: #15803d; }
.badge-orange { background: #ffedd5; color: #c2410c; }
.badge-purple { background: #ede9fe; color: #6d28d9; }
.badge-gray   { background: #f1f5f9; color: #64748b; }
.badge-default{ background: #f8fafc; color: #475569; }

.da-text {
  font-size: 11.5px;
  color: #334155;
  line-height: 1.5;
}

.da-text.muted { color: #94a3b8; }

.da-time {
  font-size: 10px;
  color: #94a3b8;
  font-family: monospace;
}

/* Overflow pill */
.dock-overflow {
  flex-shrink: 0;
  padding: 4px 9px;
  background: #f1f5f9;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  cursor: default;
}

/* ─── TransitionGroup: agent spawn from above ────────────────────────────────*/
.agent-spawn-enter-active {
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
              opacity 0.3s ease;
}
.agent-spawn-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.agent-spawn-enter-from {
  opacity: 0;
  transform: translateY(-16px) scale(0.7);
}
.agent-spawn-leave-to {
  opacity: 0;
  transform: scale(0.7);
}

/* ─── Tooltip fade ───────────────────────────────────────────────────────────*/
.tooltip-fade-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.tooltip-fade-leave-active { transition: opacity 0.1s ease; }
.tooltip-fade-enter-from   { opacity: 0; transform: translateX(-50%) translateY(-4px); }
.tooltip-fade-leave-to     { opacity: 0; }

/* ─── Dropdown slide-up ──────────────────────────────────────────────────────*/
.dropdown-slide-enter-active { transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.34,1.56,0.64,1); }
.dropdown-slide-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.dropdown-slide-enter-from   { opacity: 0; transform: translateX(-50%) translateY(-8px) scale(0.95); }
.dropdown-slide-leave-to     { opacity: 0; transform: translateX(-50%) translateY(-4px) scale(0.97); }
</style>
