<template>
  <aside class="app-sidebar" :class="{ collapsed }">

    <!-- Top logo row -->
    <div class="sb-top">
      <div class="sb-logo" @click="$emit('go-home')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M12 2C8.5 2 5.5 4.5 5 8C4.5 11 6 13.5 9 15L8 22L12 20L16 22L15 15C18 13.5 19.5 11 19 8C18.5 4.5 15.5 2 12 2Z" fill="#1a1a1a"/>
        </svg>
      </div>
      <button class="sb-toggle" @click="$emit('toggle')" title="Toggle sidebar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <path d="M9 3v18"/>
        </svg>
      </button>
    </div>

    <!-- Nav items -->
    <nav class="sb-nav">
      <button class="sb-nav-item new-item" @click="$emit('go-home')">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
        <span v-if="!collapsed" class="sb-label">New</span>
      </button>

      <button class="sb-nav-item" @click="$emit('go-home')">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="2" y="4" width="20" height="16" rx="2"/>
          <path d="M8 20h8M12 16v4"/>
          <path d="M2 8h20"/>
        </svg>
        <span v-if="!collapsed" class="sb-label">Research</span>
      </button>

      <button class="sb-nav-item">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 6h18M3 12h18M3 18h18"/>
        </svg>
        <span v-if="!collapsed" class="sb-label">Spaces</span>
      </button>

      <button class="sb-nav-item">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
        <span v-if="!collapsed" class="sb-label">Customize</span>
      </button>

      <div v-if="!collapsed" class="sb-section-label">History</div>

      <button v-if="collapsed" class="sb-nav-item">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
      </button>

      <!-- History list -->
      <div v-if="!collapsed" class="sb-history">
        <button
          v-for="item in recentSessions"
          :key="item.id"
          class="sb-history-item"
          @click="$emit('navigate', item)"
        >
          {{ item.label }}
        </button>
        <div v-if="!recentSessions.length" class="sb-history-empty">No recent sessions</div>
      </div>
    </nav>

    <!-- Footer -->
    <div class="sb-footer">
      <!-- Key input when not connected -->
      <div v-if="!userProfile && !collapsed && showKeyInput" class="sb-key-form">
        <input
          v-model="apiKeyInput"
          type="password"
          class="sb-key-input"
          placeholder="Paste API key..."
          @keydown.enter="handleConnectWithKey"
          @keydown.esc="showKeyInput = false"
          autofocus
        />
        <div class="sb-key-row">
          <button class="sb-key-cancel" @click="showKeyInput = false; apiKeyInput = ''">Cancel</button>
          <button class="sb-key-submit" :disabled="!apiKeyInput.trim() || connecting" @click="handleConnectWithKey">
            {{ connecting ? '…' : 'Connect' }}
          </button>
        </div>
        <div v-if="error" class="sb-key-error">{{ error }}</div>
      </div>

      <!-- Add team / connect row -->
      <button v-if="!userProfile && !showKeyInput" class="sb-footer-item" @click="showKeyInput = true; if(collapsed) $emit('toggle')">
        <svg class="sb-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
        <span v-if="!collapsed" class="sb-label">Add your team</span>
      </button>

      <!-- User profile row -->
      <div v-if="userProfile" class="sb-user-row">
        <div class="sb-user-left">
          <div class="sb-avatar">
            <img v-if="userProfile.avatar_url" :src="userProfile.avatar_url" :alt="userProfile.display_name" />
            <span v-else class="sb-avatar-fallback">{{ (userProfile.display_name || 'U')[0].toUpperCase() }}</span>
          </div>
          <div v-if="!collapsed" class="sb-user-info">
            <span class="sb-user-name">{{ userProfile.display_name }}</span>
            <span class="sb-user-badge">Pro</span>
          </div>
        </div>
        <div v-if="!collapsed" class="sb-user-right">
          <button class="sb-icon-btn" title="Notifications">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </button>
          <button class="sb-icon-btn" title="Disconnect" @click="handleLogout">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { authService } from '../../utils/auth'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
  recentSessions: { type: Array, default: () => [] }
})

const emit = defineEmits(['toggle', 'go-home', 'navigate'])

const userProfile = ref(null)
const connecting = ref(false)
const error = ref('')
const showKeyInput = ref(false)
const apiKeyInput = ref('')

onMounted(() => {
  try { userProfile.value = authService.getProfile() } catch { userProfile.value = null }
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
  authService.logout()
  userProfile.value = null
}
</script>

<style scoped>
.app-sidebar {
  width: 220px;
  min-width: 220px;
  height: 100%;
  background: #f5f4f1;
  border-right: 1px solid #e8e6e1;
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 13.5px;
  color: #1a1a1a;
  transition: width 0.2s ease, min-width 0.2s ease;
  overflow: hidden;
  user-select: none;
}

.app-sidebar.collapsed {
  width: 52px;
  min-width: 52px;
}

/* Top bar */
.sb-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px 10px;
  flex-shrink: 0;
}

.sb-logo {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;
}
.sb-logo:hover { background: #ebe9e4; }

.sb-toggle {
  background: none;
  border: none;
  cursor: pointer;
  color: #8c8882;
  padding: 4px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  transition: color 0.15s, background 0.15s;
}
.sb-toggle:hover { background: #ebe9e4; color: #1a1a1a; }

.collapsed .sb-toggle { margin: 0 auto; }

/* Nav */
.sb-nav {
  flex: 1;
  padding: 4px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sb-nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  background: none;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  color: #3a3a3a;
  font-size: 13.5px;
  font-family: inherit;
  transition: background 0.12s;
}
.sb-nav-item:hover { background: #ebe9e4; }
.sb-nav-item.new-item { color: #1a1a1a; font-weight: 500; }

.sb-icon { flex-shrink: 0; color: #6b6862; }
.sb-nav-item.new-item .sb-icon { color: #1a1a1a; }

.sb-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Section label */
.sb-section-label {
  font-size: 11px;
  font-weight: 600;
  color: #9c9894;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 10px 8px 4px;
}

/* History */
.sb-history {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sb-history-item {
  display: block;
  width: 100%;
  padding: 5px 8px;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  font-size: 12.5px;
  color: #5c5a57;
  font-family: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.12s;
}
.sb-history-item:hover { background: #ebe9e4; color: #1a1a1a; }

.sb-history-empty {
  font-size: 12px;
  color: #b0aea9;
  padding: 6px 8px;
}

/* Footer */
.sb-footer {
  flex-shrink: 0;
  padding: 8px;
  border-top: 1px solid #e8e6e1;
}

.sb-footer-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  background: none;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  color: #5c5a57;
  font-size: 13.5px;
  font-family: inherit;
  transition: background 0.12s;
}
.sb-footer-item:hover { background: #ebe9e4; color: #1a1a1a; }

/* Key form */
.sb-key-form { display: flex; flex-direction: column; gap: 6px; padding: 4px 0; }
.sb-key-input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid #d4d2cd;
  border-radius: 7px;
  background: #fff;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  outline: none;
  box-sizing: border-box;
}
.sb-key-input:focus { border-color: #1a1a1a; }
.sb-key-row { display: flex; gap: 6px; }
.sb-key-cancel {
  flex: 1; padding: 6px; border: 1px solid #d4d2cd; border-radius: 6px;
  background: none; font-size: 12px; cursor: pointer; font-family: inherit; color: #5c5a57;
}
.sb-key-submit {
  flex: 1; padding: 6px; border: none; border-radius: 6px;
  background: #1a1a1a; color: #fff; font-size: 12px; cursor: pointer; font-family: inherit;
  font-weight: 500;
}
.sb-key-submit:disabled { opacity: 0.4; cursor: not-allowed; }
.sb-key-error { font-size: 11px; color: #ef4444; }

/* User row */
.sb-user-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}
.sb-user-row:hover { background: #ebe9e4; }

.sb-user-left { display: flex; align-items: center; gap: 8px; min-width: 0; }

.sb-avatar {
  width: 28px; height: 28px; border-radius: 50%; overflow: hidden;
  background: #d4d2cd; flex-shrink: 0; display: flex; align-items: center; justify-content: center;
}
.sb-avatar img { width: 100%; height: 100%; object-fit: cover; }
.sb-avatar-fallback { font-size: 12px; font-weight: 700; color: #5c5a57; }

.sb-user-info { display: flex; align-items: center; gap: 6px; min-width: 0; }
.sb-user-name { font-size: 12.5px; font-weight: 500; color: #1a1a1a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 90px; }
.sb-user-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 4px;
  background: #fef3c7; color: #92400e; flex-shrink: 0; letter-spacing: 0.03em;
}

.sb-user-right { display: flex; align-items: center; gap: 2px; }
.sb-icon-btn {
  width: 26px; height: 26px; border: none; background: none; border-radius: 5px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: #8c8882; transition: background 0.12s, color 0.12s;
}
.sb-icon-btn:hover { background: #dddbd6; color: #1a1a1a; }
</style>
