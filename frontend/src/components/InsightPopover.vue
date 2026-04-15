<template>
  <span class="insight-wrapper">
    <span class="insight-trigger" @click.stop="togglePopover" :title="'View source reasoning'">
      💡
    </span>
    
    <div v-if="showPopover" class="insight-popover" v-click-outside="closePopover">
      <div v-if="loading" class="insight-loading">
        <i class="fas fa-spinner fa-spin"></i> Loading context...
      </div>
      <div v-else-if="error" class="insight-error">
        {{ error }}
      </div>
      <div v-else-if="insightData" class="insight-content">
        <div class="insight-header">
          <h5>Insight Context</h5>
          <button class="close-btn" @click="closePopover">&times;</button>
        </div>
        
        <div class="insight-body">
          <div class="info-group">
            <span class="label">Agent:</span>
            <span class="value agent-name">{{ insightData.agent_name || 'System' }}</span>
          </div>
          
          <div class="info-group" v-if="insightData.action">
            <span class="label">Action:</span>
            <span class="value action-name">{{ insightData.action }}</span>
          </div>
          
          <div class="info-group" v-if="insightData.reasoning">
            <span class="label">Reasoning:</span>
            <div class="value reasoning-text">{{ insightData.reasoning }}</div>
          </div>
          
          <div class="info-group" v-if="insightData.content">
            <span class="label">Source Content:</span>
            <div class="value content-text">{{ truncateText(insightData.content, 300) }}</div>
          </div>
          
          <div class="info-group small-meta">
            <span class="label">Artifact ID:</span>
            <span class="value">{{ claimId }}</span>
          </div>
        </div>
      </div>
    </div>
  </span>
</template>

<script>
import api from '../api';

// Simple click outside directive
const clickOutside = {
  beforeMount: (el, binding) => {
    el.clickOutsideEvent = event => {
      // Check if click was outside the el and its children
      if (!(el == event.target || el.contains(event.target))) {
        // If it is, call the method provided in the attribute value
        binding.value(event, el)
      }
    };
    document.addEventListener("click", el.clickOutsideEvent)
  },
  unmounted: el => {
    document.removeEventListener("click", el.clickOutsideEvent)
  },
}

export default {
  name: 'InsightPopover',
  directives: {
    clickOutside
  },
  props: {
    claimId: {
      type: String,
      required: true
    },
    simulationId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      showPopover: false,
      loading: false,
      error: null,
      insightData: null
    }
  },
  methods: {
    togglePopover() {
      this.showPopover = !this.showPopover;
      if (this.showPopover && !this.insightData) {
        this.fetchInsightData();
      }
    },
    closePopover() {
      this.showPopover = false;
    },
    async fetchInsightData() {
      this.loading = true;
      this.error = null;
      try {
        const response = await api.get(`/api/paper-report/insight/${this.claimId}?simulation_id=${this.simulationId}`);
        // Extract the claim data since backend returns { success: true, claim: {...}, stats: {...} }
        const resData = response;
        if (resData && resData.success && resData.claim) {
          const claim = resData.claim;
          this.insightData = {
            agent_name: claim.agent_name || claim.creator || 'CSI Swarm',
            action: 'Generate Claim',
            reasoning: 'Supporting verification trials: ' + resData.stats.supporting_count,
            content: claim.text || claim.content || claim.description || ''
          };
        } else {
          this.insightData = resData;
        }
      } catch (err) {
        console.error("Failed to fetch insight data:", err);
        // Fallback or error display
        this.error = "Could not load insight reasoning.";
        // Mock data for testing if API fails
        if (err.response && err.response.status === 404) {
           this.insightData = {
             agent_name: 'Unknown Agent',
             action: 'Unknown Action',
             reasoning: 'The original artifact containing the reasoning for this claim could not be found or has been purged.',
             content: 'No source content available.'
           };
           this.error = null;
        }
      } finally {
        this.loading = false;
      }
    },
    truncateText(text, length) {
      if (!text) return '';
      if (text.length <= length) return text;
      return text.substring(0, length) + '...';
    }
  }
}
</script>

<style scoped>
.insight-wrapper {
  position: relative;
  display: inline-block;
}

.insight-trigger {
  cursor: pointer;
  padding: 0 4px;
  font-size: 1.1em;
  opacity: 0.8;
  transition: opacity 0.2s, transform 0.2s;
  user-select: none;
}

.insight-trigger:hover {
  opacity: 1;
  transform: scale(1.1);
}

.insight-popover {
  position: absolute;
  bottom: 120%;
  left: 50%;
  transform: translateX(-50%);
  width: 350px;
  max-width: 90vw;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  border: 1px solid #e0e0e0;
  z-index: 1000;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  text-align: left;
  line-height: 1.5;
  color: #333;
}

/* Arrow */
.insight-popover::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  margin-left: -8px;
  border-width: 8px;
  border-style: solid;
  border-color: white transparent transparent transparent;
}
.insight-popover::before {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  margin-left: -9px;
  border-width: 9px;
  border-style: solid;
  border-color: #e0e0e0 transparent transparent transparent;
}

.insight-loading, .insight-error {
  padding: 20px;
  text-align: center;
  font-size: 0.9em;
  color: #666;
}

.insight-error {
  color: #d32f2f;
}

.insight-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #f8f9fa;
  border-bottom: 1px solid #eee;
  border-radius: 8px 8px 0 0;
}

.insight-header h5 {
  margin: 0;
  font-size: 0.95em;
  font-weight: 600;
  color: #2c3e50;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.2em;
  line-height: 1;
  cursor: pointer;
  color: #999;
  padding: 0;
}

.close-btn:hover {
  color: #333;
}

.insight-body {
  padding: 15px;
  max-height: 300px;
  overflow-y: auto;
}

.info-group {
  margin-bottom: 12px;
}

.info-group:last-child {
  margin-bottom: 0;
}

.label {
  font-size: 0.75em;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #7f8c8d;
  font-weight: 600;
  display: block;
  margin-bottom: 3px;
}

.value {
  font-size: 0.9em;
  color: #2c3e50;
  word-break: break-word;
}

.agent-name {
  font-weight: 600;
  color: #e67e22;
}

.action-name {
  font-family: monospace;
  background: #f1f2f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
}

.reasoning-text {
  font-style: italic;
  border-left: 3px solid #3498db;
  padding-left: 10px;
  color: #34495e;
}

.content-text {
  background: #f9f9f9;
  padding: 8px;
  border-radius: 4px;
  font-size: 0.85em;
  white-space: pre-wrap;
}

.small-meta .value {
  font-family: monospace;
  font-size: 0.7em;
  color: #bdc3c7;
}
</style>
