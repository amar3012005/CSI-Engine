<template>
  <Transition name="overlay">
    <div v-if="agent" class="agent-overlay-backdrop" @click.self="$emit('close')" @keydown.esc="$emit('close')">
      <div class="agent-overlay-card">
        <button class="overlay-close-btn" type="button" @click="$emit('close')">×</button>

        <div class="overlay-header">
          <div class="overlay-avatar-ring">
            <img v-if="agent.avatarPath" :src="agent.avatarPath" :alt="agent.name" class="overlay-avatar-img" />
            <span v-else class="overlay-avatar-fallback">{{ agent.initials }}</span>
          </div>
          <h2 class="overlay-name">{{ agent.name }}</h2>
          <span class="overlay-entity-type">{{ agent.entityType }}</span>
          <div class="overlay-score-bar">
            <div class="score-fill" :style="{ width: `${(agent.qualificationScore || 0) * 100}%`, background: scoreColor }"></div>
          </div>
          <span class="overlay-score-label">{{ ((agent.qualificationScore || 0) * 100).toFixed(0) }}% qualified</span>
        </div>

        <div class="overlay-section">
          <p class="overlay-persona">{{ agent.persona }}</p>
        </div>

        <div class="overlay-section">
          <span class="overlay-role-badge" :style="{ background: roleBadgeColor }">{{ agent.researchRole }}</span>
          <p class="overlay-responsibility">{{ agent.responsibility }}</p>
          <span v-if="agent.evidencePriority" class="overlay-evidence-tag">{{ agent.evidencePriority }}</span>
        </div>

        <div class="overlay-capabilities">
          <div class="cap-column">
            <span class="cap-header">Skills</span>
            <div class="cap-chips">
              <span v-for="skill in agent.skills" :key="skill" class="cap-chip skill-chip">{{ skill }}</span>
            </div>
          </div>
          <div class="cap-column">
            <span class="cap-header">Actions</span>
            <div class="cap-chips">
              <span v-for="action in allActions" :key="action" class="cap-chip action-chip">{{ action }}</span>
            </div>
          </div>
        </div>

        <div v-if="agent.challengeTargets && agent.challengeTargets.length > 0" class="overlay-section">
          <span class="cap-header">Challenges</span>
          <div class="cap-chips">
            <span v-for="target in agent.challengeTargets" :key="target" class="cap-chip challenge-chip">{{ target }}</span>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  agent: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close'])

const scoreColor = computed(() => {
  const score = props.agent?.qualificationScore || 0
  if (score > 0.8) return '#22c55e'
  if (score > 0.6) return '#f59e0b'
  return '#ef4444'
})

const roleBadgeColor = computed(() => {
  const role = String(props.agent?.researchRole || '').toLowerCase()
  if (role.includes('explorer')) return 'rgba(59, 130, 246, 0.3)'
  if (role.includes('domain') || role.includes('expert')) return 'rgba(139, 92, 246, 0.3)'
  if (role.includes('fact') || role.includes('check')) return 'rgba(34, 197, 94, 0.3)'
  if (role.includes('challeng')) return 'rgba(239, 68, 68, 0.3)'
  if (role.includes('synth')) return 'rgba(236, 72, 153, 0.3)'
  return 'rgba(255, 255, 255, 0.15)'
})

const allActions = computed(() => [
  ...(props.agent?.worldActions || []),
  ...(props.agent?.peerActions || [])
])

const handleKeydown = (e) => {
  if (e.key === 'Escape' && props.agent) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.agent-overlay-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(20px) saturate(1.2);
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-overlay-card {
  position: relative;
  max-width: 480px;
  width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  padding: 32px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.overlay-close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.overlay-close-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.overlay-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.overlay-avatar-ring {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}

.overlay-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.overlay-avatar-fallback {
  font-size: 32px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.5);
}

.overlay-name {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
}

.overlay-entity-type {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}

.overlay-score-bar {
  width: 120px;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  margin-top: 8px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.overlay-score-label {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
}

.overlay-section {
  margin-top: 20px;
}

.overlay-persona {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
  line-height: 1.6;
  margin: 0;
}

.overlay-role-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  text-transform: capitalize;
  margin-bottom: 8px;
}

.overlay-responsibility {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.5;
  margin: 0 0 8px;
}

.overlay-evidence-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.5);
  text-transform: lowercase;
}

.overlay-capabilities {
  margin-top: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.cap-column {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cap-header {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.4);
}

.cap-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cap-chip {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
}

.skill-chip {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.85);
}

.action-chip {
  background: rgba(99, 179, 237, 0.2);
  color: rgba(147, 197, 253, 0.9);
}

.challenge-chip {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.6);
}

/* Transitions */
.overlay-enter-active {
  transition: opacity 0.2s ease;
}

.overlay-enter-active .agent-overlay-card {
  transition: transform 0.25s ease-out, opacity 0.25s ease-out;
}

.overlay-leave-active {
  transition: opacity 0.15s ease;
}

.overlay-leave-active .agent-overlay-card {
  transition: transform 0.15s ease-in, opacity 0.15s ease-in;
}

.overlay-enter-from {
  opacity: 0;
}

.overlay-enter-from .agent-overlay-card {
  opacity: 0;
  transform: scale(0.95);
}

.overlay-leave-to {
  opacity: 0;
}

.overlay-leave-to .agent-overlay-card {
  opacity: 0;
  transform: scale(0.95);
}
</style>
