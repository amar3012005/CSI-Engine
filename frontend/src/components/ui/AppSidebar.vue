<template>
  <aside class="app-sidebar" :class="{ collapsed }">
    <!-- Logo row -->
    <div class="sb-logo-row">
      <div class="sb-logo-left" @click="$emit('go-home')">
        <div class="sb-hex-icon">&#x2B21;</div>
        <div v-if="!collapsed" class="sb-logo-text">
          <span class="sb-brand-name">HIVEMIND</span>
          <span class="sb-brand-sub">Deep Research</span>
        </div>
      </div>
      <button class="sb-collapse-btn" @click="$emit('toggle')">
        <span v-if="collapsed">&#8250;</span>
        <span v-else>&#8249;</span>
      </button>
    </div>

    <!-- Expanded nav -->
    <nav v-if="!collapsed" class="sb-nav">
      <!-- New + Agents -->
      <div class="sb-nav-section">
        <a class="sb-nav-item" @click="$emit('go-home')">
          <span class="sb-nav-icon">+</span>
          <span class="sb-nav-label">New Chat</span>
        </a>
        <a class="sb-nav-item">
          <span class="sb-nav-icon">&#9634;</span>
          <span class="sb-nav-label">Agents</span>
        </a>
      </div>

      <!-- Current session (only when activeSession is provided) -->
      <div v-if="activeSession" class="sb-nav-section">
        <span class="sb-section-label">Current Session</span>
        <div class="sb-session-card active">
          <span class="sb-session-text">{{ activeSession.title }}</span>
          <span class="sb-session-id">{{ activeSession.id }}</span>
        </div>
        <div v-if="activeSession.checkpoints?.length" class="sb-checkpoint-list">
          <div
            v-for="checkpoint in activeSession.checkpoints"
            :key="checkpoint.id"
            class="sb-checkpoint-item"
          >
            <div class="sb-checkpoint-rail">
              <span class="sb-checkpoint-dot"></span>
              <span class="sb-checkpoint-line"></span>
            </div>
            <div class="sb-checkpoint-body">
              <span class="sb-checkpoint-id">{{ checkpoint.id }}</span>
              <span class="sb-checkpoint-query">{{ checkpoint.query || 'Untitled checkpoint' }}</span>
              <span class="sb-checkpoint-meta">
                {{ checkpoint.round_reached || 0 }} rounds · {{ checkpoint.artifact_summary?.claims || 0 }} claims
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Past sessions -->
      <div class="sb-nav-section">
        <span class="sb-section-label">Past Sessions</span>
        <div
          v-for="item in sessions"
          :key="item.id"
          class="sb-session-row"
          :class="{ active: item.simulationId === activeSession?.id }"
        >
          <a class="sb-nav-item history" @click="$emit('select-session', item.simulationId)">
            <span class="sb-nav-label">{{ item.label }}</span>
          </a>
          <button
            class="sb-delete-btn"
            title="Delete session"
            @click.stop="$emit('delete-session', item.simulationId)"
          >&times;</button>
        </div>
        <span v-if="sessions.length === 0" class="sb-empty">No past sessions</span>
      </div>
    </nav>

    <!-- Collapsed icons -->
    <nav v-else class="sb-nav-collapsed">
      <button class="sb-icon-btn" @click="$emit('go-home')" title="New Chat">+</button>
      <button class="sb-icon-btn" title="Agents">&#9634;</button>
    </nav>

    <!-- Connect to HIVEMIND Footer -->
    <div class="sb-profile-footer" :class="{ connected: !!userProfile }">
      <button v-if="!userProfile" class="sb-connect-btn" @click="handleConnectHIVEMIND">
        <span class="sb-connect-icon">&#x2B21;</span>
        <span v-if="!collapsed" class="sb-connect-label">Connect to HIVEMIND</span>
      </button>
      <div v-else class="sb-profile-box" :title="userProfile.display_name">
        <img :src="userProfile.avatar_url" class="sb-avatar" :alt="userProfile.display_name" />
        <div v-if="!collapsed" class="sb-profile-meta">
          <span class="sb-user-name">{{ userProfile.display_name }}</span>
          <span class="sb-user-role">{{ userProfile.role }} · {{ userProfile.organisation_id }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { authService } from '../../utils/auth';

const userProfile = ref(null);

defineProps({
  collapsed: {
    type: Boolean,
    default: false
  },
  activeSession: {
    type: Object,
    default: null
  },
  sessions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['toggle', 'go-home', 'select-session', 'delete-session'])

onMounted(() => {
  userProfile.value = authService.getProfile();
});

const handleConnectHIVEMIND = async () => {
    try {
        // Unified Identity & Profile Extraction Handshake
        const mockToken = "hm_jwt_test_token_8a7b6c";
        userProfile.value = await authService.syncProfile(mockToken);
    } catch (e) {
        console.error("Connect to HIVEMIND failed", e);
    }
};
</script>

<style scoped>
.sb-profile-footer {
  margin-top: auto;
  padding: 1rem;
  border-top: 1px solid #e3e0db;
  background: white;
}

.sb-connect-btn {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem;
  background: #117dff;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s;
  overflow: hidden;
  white-space: nowrap;
}

.sb-connect-btn:hover {
  transform: translateY(-2px);
  filter: brightness(1.1);
}

.sb-profile-box {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.sb-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f0f0;
  border: 1px solid #e3e0db;
}

.sb-profile-meta {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sb-user-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sb-user-role {
  font-size: 0.75rem;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-sidebar {
  width: 260px;
  background: #faf9f4;
  border-right: 1px solid #e3e0db;
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}

.app-sidebar.collapsed {
  width: 68px;
}

/* Logo row */
.sb-logo-row {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid #e3e0db;
  flex-shrink: 0;
}

.sb-logo-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  cursor: pointer;
}

.sb-hex-icon {
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

.sb-logo-text {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sb-brand-name {
  font-size: 13px;
  font-weight: 600;
  color: #0a0a0a;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.sb-brand-sub {
  font-size: 10px;
  color: #a3a3a3;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}

.sb-collapse-btn {
  padding: 4px;
  border: none;
  background: none;
  color: #a3a3a3;
  font-size: 16px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.sb-collapse-btn:hover {
  background: #f3f1ec;
  color: #525252;
}

/* Navigation */
.sb-nav {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scrollbar-width: thin;
  scrollbar-color: #d4d0ca transparent;
}

.sb-nav::-webkit-scrollbar { width: 3px; }
.sb-nav::-webkit-scrollbar-thumb { background: #d4d0ca; border-radius: 3px; }

.sb-nav-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sb-section-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a3a3a3;
  padding: 0 10px;
  margin-bottom: 4px;
}

.sb-nav-item {
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

.sb-nav-item:hover {
  background: #f3f1ec;
  color: #0a0a0a;
}

.sb-nav-item.active {
  background: #f3f1ec;
  color: #0a0a0a;
  font-weight: 500;
}

.sb-nav-item.history {
  padding: 6px 10px;
  font-size: 12px;
}

.sb-nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
  color: #a3a3a3;
}

.sb-nav-item.active .sb-nav-icon,
.sb-nav-item:hover .sb-nav-icon {
  color: #525252;
}

.sb-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Current session card */
.sb-session-card {
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sb-session-card.active {
  border-color: #117dff;
  background: rgba(17, 125, 255, 0.03);
}

.sb-session-text {
  font-size: 12px;
  font-weight: 500;
  color: #0a0a0a;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sb-session-id {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #a3a3a3;
}

.sb-checkpoint-list {
  margin-top: 8px;
  padding-left: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sb-checkpoint-item {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.sb-checkpoint-rail {
  width: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.sb-checkpoint-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #117dff;
  margin-top: 4px;
}

.sb-checkpoint-line {
  width: 1px;
  flex: 1;
  background: #e3e0db;
  margin-top: 4px;
}

.sb-checkpoint-item:last-child .sb-checkpoint-line {
  display: none;
}

.sb-checkpoint-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sb-checkpoint-id {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #737373;
  font-family: 'JetBrains Mono', monospace;
}

.sb-checkpoint-query {
  font-size: 11px;
  color: #262626;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sb-checkpoint-meta {
  font-size: 10px;
  color: #a3a3a3;
}

.sb-session-row {
  display: flex;
  align-items: center;
  border-radius: 8px;
  transition: background 0.12s;
}

.sb-session-row:hover {
  background: #f3f1ec;
}

.sb-session-row .sb-nav-item {
  flex: 1;
  min-width: 0;
}

.sb-delete-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  color: transparent;
  font-size: 14px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.12s;
}

.sb-session-row:hover .sb-delete-btn {
  color: #a3a3a3;
}

.sb-delete-btn:hover {
  color: #dc2626 !important;
  background: rgba(220, 38, 38, 0.08);
}

.sb-empty {
  font-size: 11px;
  color: #a3a3a3;
  padding: 4px 10px;
}

/* Collapsed nav */
.sb-nav-collapsed {
  flex: 1;
  padding: 10px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.sb-icon-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: none;
  border-radius: 8px;
  font-size: 18px;
  color: #a3a3a3;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.sb-icon-btn:hover {
  background: #f3f1ec;
  color: #525252;
}

.sb-icon-btn.active {
  background: #f3f1ec;
  color: #0a0a0a;
}
</style>
