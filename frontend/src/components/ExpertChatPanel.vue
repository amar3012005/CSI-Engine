<template>
  <Transition name="expert-slide">
    <div v-if="open" class="expert-chat-overlay">
      <!-- Picker: choose which expert to talk to -->
      <div v-if="!selectedAgent" class="expert-picker">
        <div class="picker-header">
          <span class="picker-title">Talk to Expert</span>
          <button class="picker-close" type="button" @click="$emit('close')">×</button>
        </div>
        <p class="picker-sub">Pick a specialist from the round table to ask them anything from their POV.</p>
        <div class="picker-grid">
          <button
            v-for="a in profiles"
            :key="a.id"
            class="picker-card"
            type="button"
            @click="selectAgent(a)"
          >
            <div class="picker-avatar">
              <img v-if="a.avatarPath" :src="a.avatarPath" :alt="a.name" />
              <span v-else>{{ a.initials }}</span>
            </div>
            <div class="picker-meta">
              <span class="picker-name">{{ a.name }}</span>
              <span class="picker-type">{{ a.entityType }}</span>
              <span v-if="a.affiliation" class="picker-affil">{{ a.affiliation }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- Chat interface -->
      <div v-else class="expert-chat">
        <header class="ec-header">
          <button class="ec-back" type="button" @click="reset" title="Pick a different expert">‹</button>
          <div class="ec-avatar">
            <img v-if="selectedAgent.avatarPath" :src="selectedAgent.avatarPath" :alt="selectedAgent.name" />
            <span v-else>{{ selectedAgent.initials }}</span>
          </div>
          <div class="ec-meta">
            <span class="ec-name">{{ selectedAgent.name }}</span>
            <span class="ec-sub">{{ selectedAgent.entityType }}<span v-if="selectedAgent.affiliation"> · {{ selectedAgent.affiliation }}</span></span>
            <span v-if="introStats" class="ec-stats">
              {{ introStats.claims }} claims · {{ introStats.reviews }} reviews · {{ introStats.sources }} sources
            </span>
          </div>
          <button class="ec-close" type="button" @click="$emit('close')">×</button>
        </header>

        <div ref="logRef" class="ec-log">
          <div v-if="loadingIntro" class="ec-intro-loading">
            <span class="dot" /><span class="dot" /><span class="dot" />
            <span>{{ selectedAgent.name }} is preparing a briefing…</span>
          </div>

          <div
            v-for="(m, i) in messages"
            :key="i"
            class="ec-msg"
            :class="m.role"
          >
            <div v-if="m.role === 'assistant'" class="ec-msg-avatar">
              <img v-if="selectedAgent.avatarPath" :src="selectedAgent.avatarPath" :alt="selectedAgent.name" />
              <span v-else>{{ selectedAgent.initials }}</span>
            </div>
            <div class="ec-bubble" v-html="renderMd(m.content)"></div>
          </div>

          <div v-if="sending" class="ec-msg assistant">
            <div class="ec-msg-avatar">
              <img v-if="selectedAgent.avatarPath" :src="selectedAgent.avatarPath" :alt="selectedAgent.name" />
              <span v-else>{{ selectedAgent.initials }}</span>
            </div>
            <div class="ec-bubble typing"><span class="dot" /><span class="dot" /><span class="dot" /></div>
          </div>
        </div>

        <form class="ec-input" @submit.prevent="send">
          <input
            v-model="draft"
            type="text"
            :placeholder="`Ask ${selectedAgent.name.split(' ')[0]} a question…`"
            :disabled="sending || loadingIntro"
          />
          <button type="submit" :disabled="!canSend">Send</button>
        </form>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { getExpertIntro, sendExpertMessage } from '../api/simulation'

const props = defineProps({
  open: { type: Boolean, default: false },
  simulationId: { type: String, required: true },
  profiles: { type: Array, default: () => [] },
})

defineEmits(['close'])

const selectedAgent = ref(null)
const messages = ref([]) // {role, content}
const draft = ref('')
const sending = ref(false)
const loadingIntro = ref(false)
const introStats = ref(null)
const logRef = ref(null)

const canSend = computed(() => !sending.value && !loadingIntro.value && draft.value.trim().length > 0)

const renderMd = (text) => DOMPurify.sanitize(marked(String(text || '')))

const scrollBottom = async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
}

const selectAgent = async (agent) => {
  selectedAgent.value = agent
  messages.value = []
  introStats.value = null
  loadingIntro.value = true
  try {
    const res = await getExpertIntro(props.simulationId, agent.id)
    const data = res?.data || res
    if (data?.intro) {
      messages.value.push({ role: 'assistant', content: data.intro })
    }
    if (data?.stats) introStats.value = data.stats
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `_(Could not load briefing: ${e?.message || 'unknown error'})_`,
    })
  } finally {
    loadingIntro.value = false
    scrollBottom()
  }
}

const send = async () => {
  if (!canSend.value) return
  const text = draft.value.trim()
  draft.value = ''
  messages.value.push({ role: 'user', content: text })
  scrollBottom()
  sending.value = true
  try {
    const history = messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }))
    const res = await sendExpertMessage(props.simulationId, selectedAgent.value.id, text, history)
    const data = res?.data || res
    messages.value.push({ role: 'assistant', content: data?.reply || '(no response)' })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: `_(Error: ${e?.message || 'unknown'})_` })
  } finally {
    sending.value = false
    scrollBottom()
  }
}

const reset = () => {
  selectedAgent.value = null
  messages.value = []
  introStats.value = null
}

watch(() => props.open, (v) => { if (!v) reset() })
</script>

<style scoped>
.expert-chat-overlay {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(560px, 100%);
  background: #ffffff;
  border-left: 1px solid #e5e7eb;
  box-shadow: -10px 0 30px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  z-index: 50;
}

.expert-slide-enter-from { transform: translateX(100%); }
.expert-slide-leave-to   { transform: translateX(100%); }
.expert-slide-enter-active, .expert-slide-leave-active { transition: transform 0.28s ease; }

/* Picker */
.expert-picker { padding: 20px; overflow-y: auto; height: 100%; }
.picker-header { display: flex; justify-content: space-between; align-items: center; }
.picker-title { font-size: 18px; font-weight: 600; }
.picker-close { background: none; border: 0; font-size: 24px; cursor: pointer; color: #555; }
.picker-sub { color: #666; font-size: 13px; margin: 6px 0 16px; }
.picker-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
.picker-card {
  display: flex; gap: 12px; align-items: center;
  padding: 12px; border: 1px solid #e5e7eb; border-radius: 10px;
  background: #fafafa; cursor: pointer; text-align: left;
  transition: all 0.15s;
}
.picker-card:hover { background: #f0f7ff; border-color: #93c5fd; }
.picker-avatar {
  width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #e5e7eb; color: #444; font-weight: 600; overflow: hidden; flex-shrink: 0;
}
.picker-avatar img { width: 100%; height: 100%; object-fit: cover; }
.picker-meta { display: flex; flex-direction: column; min-width: 0; }
.picker-name { font-weight: 600; font-size: 14px; color: #111; }
.picker-type { font-size: 12px; color: #666; }
.picker-affil { font-size: 11px; color: #999; font-style: italic; margin-top: 2px; }

/* Chat */
.expert-chat { display: flex; flex-direction: column; height: 100%; }
.ec-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid #eee; background: #fafafa;
}
.ec-back, .ec-close {
  background: none; border: 0; font-size: 22px; cursor: pointer; color: #555;
  width: 28px; height: 28px; border-radius: 6px;
}
.ec-back:hover, .ec-close:hover { background: #ececec; }
.ec-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #e5e7eb; font-weight: 600; overflow: hidden; flex-shrink: 0;
}
.ec-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ec-meta { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.ec-name { font-weight: 600; font-size: 14px; color: #111; }
.ec-sub { font-size: 11px; color: #666; }
.ec-stats { font-size: 10px; color: #888; margin-top: 2px; font-family: 'JetBrains Mono', monospace; }

.ec-log { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; background: #fff; }
.ec-intro-loading {
  display: flex; align-items: center; gap: 8px; color: #777; font-size: 13px;
  font-style: italic; padding: 12px;
}
.ec-msg { display: flex; gap: 10px; max-width: 100%; }
.ec-msg.user { flex-direction: row-reverse; }
.ec-msg-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: #e5e7eb; display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600; flex-shrink: 0; overflow: hidden;
}
.ec-msg-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ec-bubble {
  padding: 10px 14px; border-radius: 14px; max-width: 80%;
  font-size: 13px; line-height: 1.55; color: #1f2937;
  background: #f3f4f6;
  word-wrap: break-word;
}
.ec-msg.user .ec-bubble { background: #2563eb; color: #fff; }
.ec-bubble.typing { display: flex; gap: 4px; padding: 14px 16px; }
.ec-bubble :deep(p) { margin: 0 0 8px; }
.ec-bubble :deep(p:last-child) { margin-bottom: 0; }
.ec-bubble :deep(ul), .ec-bubble :deep(ol) { margin: 4px 0 4px 18px; }

.ec-input {
  display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #eee; background: #fafafa;
}
.ec-input input {
  flex: 1; padding: 10px 14px; border: 1px solid #d1d5db; border-radius: 999px;
  font-size: 13px; outline: none; background: #fff;
}
.ec-input input:focus { border-color: #2563eb; }
.ec-input button {
  padding: 10px 18px; border-radius: 999px; border: 0;
  background: #2563eb; color: #fff; font-weight: 500; cursor: pointer; font-size: 13px;
}
.ec-input button:disabled { background: #9ca3af; cursor: not-allowed; }

.dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; opacity: 0.6;
  animation: dot-bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-3px); opacity: 1; }
}
</style>
