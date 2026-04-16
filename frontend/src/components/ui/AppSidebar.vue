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

      <!-- Sessions section removed - using API key auth instead -->
    </nav>

    <!-- Collapsed icons -->
    <nav v-else class="sb-nav-collapsed">
      <button class="sb-icon-btn" @click="$emit('go-home')" title="New Chat">+</button>
      <button class="sb-icon-btn" title="Agents">&#9634;</button>
    </nav>

    <!-- Connect to HIVEMIND Footer -->
    <div class="sb-profile-footer" :class="{ connected: !!userProfile }">
      <!-- Not connected: show key input -->
      <div v-if="!userProfile && !collapsed" class="sb-key-connect">
        <div v-if="!showKeyInput" class="sb-connect-row">
          <button class="sb-connect-btn" @click="showKeyInput = true">
            <span class="sb-connect-icon">&#x2B21;</span>
            <span class="sb-connect-label">Connect HIVEMIND</span>
          </button>
        </div>
        <div v-else class="sb-key-form">
          <input
            v-model="apiKeyInput"
            type="password"
            class="sb-key-input"
            placeholder="Paste API key..."
            @keydown.enter="handleConnectWithKey"
            @keydown.esc="showKeyInput = false"
          />
          <div class="sb-key-actions">
            <button class="sb-key-cancel" @click="showKeyInput = false; apiKeyInput = ''">Cancel</button>
            <button class="sb-key-submit" :disabled="!apiKeyInput.trim() || connecting" @click="handleConnectWithKey">
              {{ connecting ? '...' : 'Connect' }}
            </button>
          </div>
          <span class="sb-key-hint">Get your key from <a href="https://hivemind.davinciai.eu/hivemind/app/keys" target="_blank">HIVEMIND Dashboard</a></span>
        </div>
      </div>
      <!-- Collapsed: just icon -->
      <button v-if="!userProfile && collapsed" class="sb-connect-btn" @click="showKeyInput = true; $emit('toggle')">
        <span class="sb-connect-icon">&#x2B21;</span>
      </button>
      <!-- Connected: show profile -->
      <div v-if="userProfile" class="sb-profile-box" :title="userProfile.display_name">
        <img :src="userProfile.avatar_url" class="sb-avatar" :alt="userProfile.display_name" />
        <div v-if="!collapsed" class="sb-profile-meta">
          <div class="sb-meta-top">
            <span class="sb-user-name">{{ userProfile.display_name }}</span>
            <button class="sb-logout-icon" @click="handleLogout" title="Disconnect">&#x23FB;</button>
          </div>
          <span class="sb-user-role">{{ userProfile.organisation_id || 'Connected' }}</span>
        </div>
      </div>
      <div v-if="error && !collapsed" class="sb-error-text">{{ error }}</div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { authService } from '../../utils/auth';

const userProfile = ref(null);
const connecting = ref(false);
const error = ref('');
const showKeyInput = ref(false);
const apiKeyInput = ref('');

defineProps({
  collapsed: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['toggle', 'go-home'])

onMounted(() => {
  // Load existing profile from API key authentication
  try {
    userProfile.value = authService.getProfile()
  } catch {
    userProfile.value = null
  }
})

const handleConnectWithKey = async () => {
  const key = apiKeyInput.value.trim()
  if (!key) return
  connecting.value = true
  error.value = ''
  try {
    userProfile.value = await authService.connectWithKey(key)
    showKeyInput.value = false
    apiKeyInput.value = ''
  } catch (e) {
    error.value = e?.response?.data?.error || 'Invalid key'
  } finally {
    connecting.value = false
  }
}

const handleLogout = () => {
  authService.logout();
  userProfile.value = null;
};
</script>

<style scoped>
.sb-error-text {
  color: #ef4444;
  font-size: 11px;
  margin-top: 5px;
  padding: 0 5px;
}

/* Key input form */
.sb-key-connect {
  width: 100%;
}

.sb-connect-row {
  width: 100%;
}

.sb-key-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.sb-key-input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid #e3e0db;
  border-radius: 8px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  background: #fff;
  color: #0a0a0a;
  outline: none;
  transition: border-color 0.15s;
}

.sb-key-input:focus {
  border-color: #117dff;
}

.sb-key-input::placeholder {
  color: #a3a3a3;
}

.sb-key-actions {
  display: flex;
  gap: 6px;
}

.sb-key-cancel {
  flex: 1;
  padding: 5px;
  border: 1px solid #e3e0db;
  border-radius: 6px;
  background: #fff;
  color: #525252;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.sb-key-cancel:hover {
  background: #faf9f4;
}

.sb-key-submit {
  flex: 1;
  padding: 5px;
  border: none;
  border-radius: 6px;
  background: #117dff;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

.sb-key-submit:hover:not(:disabled) {
  background: #0d5fcc;
}

.sb-key-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sb-key-hint {
  font-size: 10px;
  color: #a3a3a3;
  text-align: center;
}

.sb-key-hint a {
  color: #117dff;
  text-decoration: none;
}

.sb-key-hint a:hover {
  text-decoration: underline;
}

.sb-spin {
  animation: sb-spin-keyframes 1s linear infinite;
}

@keyframes sb-spin-keyframes {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

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

.sb-logout-icon {
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
  color: #a3a3a3;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sb-logout-icon:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.sb-meta-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
</style>
