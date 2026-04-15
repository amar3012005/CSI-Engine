<template>
  <Transition name="confirm-slide">
    <div v-if="visible" class="csi-confirm-card">
      <div class="cc-hero">
        <div class="cc-icon">{{ icon }}</div>
        <h3 class="cc-title">{{ title }}</h3>
        <p class="cc-subtitle">{{ query }}</p>
      </div>
      <div v-if="stats.length" class="cc-stats">
        <div v-for="stat in stats" :key="stat.label" class="cc-stat">
          <span class="cc-stat-value">{{ stat.value }}</span>
          <span class="cc-stat-label">{{ stat.label }}</span>
        </div>
      </div>
      <div class="cc-actions">
        <button class="cc-back" @click="$emit('back')">{{ backLabel }}</button>
        <button class="cc-continue" @click="$emit('continue')" :disabled="loading">
          <span v-if="loading" class="cc-spinner"></span>
          {{ loading ? loadingLabel : continueLabel }}
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  query: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    default: 'Cognitive Swarm Intelligence'
  },
  icon: {
    type: String,
    default: '\u2B21'
  },
  stats: {
    type: Array,
    default: () => [
      { value: '8', label: 'Agents' },
      { value: 'CSI', label: 'Mode' },
      { value: 'Deep', label: 'Research' }
    ]
  },
  backLabel: {
    type: String,
    default: 'Back'
  },
  continueLabel: {
    type: String,
    default: 'Continue'
  },
  loadingLabel: {
    type: String,
    default: 'Starting...'
  },
  loading: {
    type: Boolean,
    default: false
  }
})

defineEmits(['back', 'continue'])
</script>

<style scoped>
.csi-confirm-card {
  width: 100%;
  max-width: 380px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  padding: 28px 24px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.cc-hero {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.cc-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: rgba(17, 125, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: #117dff;
  margin-bottom: 4px;
}

.cc-title {
  font-size: 16px;
  font-weight: 700;
  color: #0a0a0a;
  margin: 0;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.cc-subtitle {
  font-size: 13px;
  color: #525252;
  margin: 0;
  line-height: 1.4;
  max-width: 300px;
  text-align: center;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.cc-stats {
  display: flex;
  gap: 0;
  width: 100%;
}

.cc-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 0;
}

.cc-stat + .cc-stat {
  border-left: 1px solid #f0efeb;
}

.cc-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.cc-stat-label {
  font-size: 10px;
  color: #a3a3a3;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.cc-actions {
  display: flex;
  gap: 10px;
  width: 100%;
}

.cc-back {
  flex: 1;
  padding: 10px;
  border: 1px solid #e3e0db;
  border-radius: 10px;
  background: #fff;
  color: #525252;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  transition: all 0.15s;
}

.cc-back:hover {
  background: #faf9f4;
  border-color: #d4d0ca;
}

.cc-continue {
  flex: 2;
  padding: 10px;
  border: none;
  border-radius: 10px;
  background: #0a0a0a;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.cc-continue:hover:not(:disabled) {
  background: #333;
}

.cc-continue:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cc-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: cc-spin 0.6s linear infinite;
}

@keyframes cc-spin {
  to { transform: rotate(360deg); }
}

/* Slide transition */
.confirm-slide-enter-active {
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
}

.confirm-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.2s ease;
}

.confirm-slide-enter-from {
  transform: translateY(40px);
  opacity: 0;
}

.confirm-slide-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
</style>
