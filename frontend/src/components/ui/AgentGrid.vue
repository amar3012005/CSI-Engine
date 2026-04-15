<template>
  <div class="agent-grid-wrapper">
    <TransitionGroup name="agent-card" tag="div" class="agent-grid">
      <button
        v-for="(agent, idx) in visibleProfiles"
        :key="agent.id"
        class="agent-grid-card"
        type="button"
        :style="{ transitionDelay: `${idx * 100}ms` }"
        @click="$emit('agent-click', agent.id)"
      >
        <div class="grid-avatar">
          <img v-if="agent.avatarPath" :src="agent.avatarPath" :alt="agent.name" class="grid-avatar-img" />
          <span v-else class="grid-avatar-fallback">{{ agent.initials }}</span>
        </div>
        <span class="grid-agent-name">{{ agent.name }}</span>
        <span class="grid-agent-type">{{ agent.entityType }}</span>
        <div class="grid-score-bar">
          <div
            class="grid-score-fill"
            :style="{
              width: `${(agent.qualificationScore || 0) * 100}%`,
              background: scoreColor(agent.qualificationScore)
            }"
          ></div>
        </div>
      </button>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'

const props = defineProps({
  profiles: {
    type: Array,
    default: () => []
  }
})

defineEmits(['agent-click'])

// Progressive reveal — show cards one by one
const visibleCount = ref(0)
let spawnTimer = null

const visibleProfiles = computed(() => props.profiles.slice(0, visibleCount.value))

watch(() => props.profiles.length, (newLen, oldLen) => {
  if (newLen > (oldLen || 0)) {
    // New profiles arrived — spawn them one by one
    if (spawnTimer) clearInterval(spawnTimer)
    let current = visibleCount.value
    spawnTimer = setInterval(() => {
      current++
      visibleCount.value = current
      if (current >= props.profiles.length) {
        clearInterval(spawnTimer)
        spawnTimer = null
      }
    }, 200)
  } else {
    visibleCount.value = newLen
  }
}, { immediate: true })

const scoreColor = (score) => {
  if (score > 0.8) return '#22c55e'
  if (score > 0.6) return '#f59e0b'
  return '#ef4444'
}
</script>

<style scoped>
.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.agent-grid-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 8px 12px;
  border: 1px solid #e3e0db;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.15s ease;
}

.agent-grid-card:hover {
  transform: scale(1.03);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.grid-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  overflow: hidden;
  background: #f3f1ec;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.grid-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.grid-avatar-fallback {
  font-size: 16px;
  font-weight: 700;
  color: #737373;
}

.grid-agent-name {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.grid-agent-type {
  font-size: 11px;
  color: #737373;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.grid-score-bar {
  width: 80%;
  height: 4px;
  border-radius: 2px;
  background: #f3f1ec;
  overflow: hidden;
  margin-top: 4px;
}

.grid-score-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

/* TransitionGroup animations */
.agent-card-enter-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.agent-card-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.agent-card-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.agent-card-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.agent-card-move {
  transition: transform 0.3s ease;
}
</style>
