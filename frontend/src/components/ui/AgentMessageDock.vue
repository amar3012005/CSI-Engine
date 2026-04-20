<template>
  <Transition name="notch">
    <div v-if="profiles.length > 0" class="agent-notch">
      <div
        class="notch-hover-zone"
        @mouseenter="expanded = true"
        @mouseleave="expanded = false"
      >
        <!-- Notch pill -->
        <div class="notch-pill" :class="{ expanded }">
          <span class="notch-indicator" :class="{ active: hasAnyActivity }"></span>

          <TransitionGroup name="notch-avatar" tag="div" class="notch-avatars" :class="{ expanded }">
            <button
              v-for="(agent, idx) in profiles"
              :key="agent.id"
              class="notch-avatar-btn"
              :class="{ 'has-activity': hasRecentAction(agent.id) }"
              type="button"
              :style="{ transitionDelay: `${idx * 30}ms` }"
              :aria-label="`View ${agent.name}`"
              @mouseenter="hoveredAgent = agent"
              @mouseleave="hoveredAgent = null"
              @click="$emit('agent-click', agent.id)"
            >
              <img v-if="agent.avatarPath" :src="agent.avatarPath" :alt="agent.name" class="notch-avatar-img" />
              <span v-else class="notch-avatar-initials">{{ agent.initials }}</span>
            </button>
          </TransitionGroup>

          <span class="notch-indicator right" :class="{ active: hasAnyActivity }"></span>
        </div>

        <!-- Tooltip: only the hovered agent -->
        <Transition name="tooltip">
          <div v-if="hoveredAgent" class="agent-tooltip">
            <span class="at-name">{{ hoveredAgent.name }}</span>
            <span class="at-role">{{ hoveredAgent.entityType || hoveredAgent.researchRole || 'Agent' }}</span>
            <span v-if="hasRecentAction(hoveredAgent.id)" class="at-live"></span>
          </div>
        </Transition>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { getSimulationActions } from '../../api/simulation'

const props = defineProps({
  profiles: {
    type: Array,
    default: () => []
  },
  simulationId: {
    type: String,
    default: ''
  },
  maxVisible: {
    type: Number,
    default: 6
  }
})

defineEmits(['agent-click'])

const expanded = ref(false)
const hoveredAgent = ref(null)
const loadedActions = ref([])
let refreshTimer = null

const latestActionsByAgent = computed(() => {
  const map = {}
  for (let i = 0; i < loadedActions.value.length; i++) {
    const action = loadedActions.value[i]
    if (!action) continue
    const agentId = action.agent_id
    if (agentId === undefined || agentId === null) continue
    if (!map[agentId]) {
      map[agentId] = action
    }
  }
  return map
})

const hasRecentAction = (agentId) => {
  const action = latestActionsByAgent.value[agentId]
  if (!action) return false
  const ts = action.timestamp || action.created_at
  if (!ts) return false
  return (Date.now() - new Date(ts).getTime()) < 30000
}

const hasAnyActivity = computed(() => {
  return props.profiles.some((p) => hasRecentAction(p.id))
})

const loadActions = async () => {
  if (!props.simulationId) return
  try {
    const res = await getSimulationActions(props.simulationId, { limit: 80 })
    if (res?.success) {
      loadedActions.value = Array.isArray(res.data?.actions) ? res.data.actions : []
    }
  } catch {
    // silently fail
  }
}

const startRefresh = () => {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = setInterval(loadActions, 3000)
}

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  if (props.simulationId) {
    loadActions()
    startRefresh()
  }
})

onBeforeUnmount(() => {
  stopRefresh()
})
</script>

<style scoped>
/* ─── Notch Container ─────────────────────────── */
.agent-notch {
  position: absolute;
  top: 0px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 55;
  pointer-events: none;
}

.notch-hover-zone {
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ─── Pill — Da-vinci warm theme ─────────────── */
.notch-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 5px 12px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-top: none;
  border-radius: 0 0 16px 16px;
  transition: all 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.notch-pill.expanded {
  padding: 6px 14px;
  gap: 6px;
  border-radius: 0;
  box-shadow: none;
  border-bottom-color: transparent;
}

/* ─── Indicator dots ─────────────────────────── */
.notch-indicator {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #d4d0ca;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.notch-indicator.active {
  background: #16a34a;
}

/* ─── Avatar row ─────────────────────────────── */
.notch-avatars {
  display: flex;
  align-items: center;
}

.notch-avatar-btn {
  position: relative;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1.5px solid #e3e0db;
  overflow: hidden;
  background: #f3f1ec;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: -6px;
  flex-shrink: 0;
  transition: all 0.3s cubic-bezier(0.32, 0.72, 0, 1);
}

.notch-avatar-btn:first-child {
  margin-left: 0;
}

.notch-avatars.expanded .notch-avatar-btn {
  width: 28px;
  height: 28px;
  margin-left: 2px;
}


.notch-avatars.expanded .notch-avatar-btn:first-child {
  margin-left: 0;
}

.notch-avatar-btn:hover {
  transform: scale(1.12);
  z-index: 3;
  border-color: #117dff;
}

.notch-avatar-btn.has-activity {
  border-color: #16a34a;
}

.notch-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.notch-avatar-initials {
  font-size: 9px;
  font-weight: 700;
  color: #737373;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

/* ─── Tooltip — single hovered agent ─────────── */
.agent-tooltip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 5px 12px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  white-space: nowrap;
}

.at-name {
  font-size: 12px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.at-role {
  font-size: 10px;
  color: #a3a3a3;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.at-live {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
  flex-shrink: 0;
}

/* ─── Tooltip transition ─────────────────────── */
.tooltip-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.tooltip-leave-active {
  transition: opacity 0.1s ease;
}

.tooltip-enter-from {
  opacity: 0;
  transform: translateY(-3px);
}

.tooltip-leave-to {
  opacity: 0;
}

/* ─── Notch enter/leave ──────────────────────── */
.notch-enter-active {
  transition: opacity 0.4s ease, transform 0.5s cubic-bezier(0.32, 0.72, 0, 1);
}

.notch-leave-active {
  transition: opacity 0.2s ease, transform 0.3s ease;
}

.notch-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-100%);
}

.notch-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-100%);
}

/* ─── Avatar spawn ───────────────────────────── */
.notch-avatar-enter-active {
  transition: opacity 0.2s ease, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.notch-avatar-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.notch-avatar-enter-from {
  opacity: 0;
  transform: scale(0.4);
}

.notch-avatar-leave-to {
  opacity: 0;
  transform: scale(0.4);
}

.notch-avatar-move {
  transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1);
}

/* ─── Mobile ─────────────────────────────────── */
@media (max-width: 900px) {
  .notch-pill {
    min-height: 30px;
    padding: 4px 10px;
    gap: 4px;
  }

  .notch-avatar-btn {
    width: 20px;
    height: 20px;
    margin-left: -5px;
  }

  .agent-dropdown {
    width: 200px;
  }
}
</style>
