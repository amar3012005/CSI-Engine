import { safeSessionGet, safeSessionSet, safeSessionRemove } from '../utils/safeStorage'

const STORAGE_KEY = 'mirofish_session_token_usage'

let state = {
  input: 0,
  output: 0,
}

const listeners = new Set()

const emit = () => {
  for (const listener of listeners) {
    try {
      listener({ ...state })
    } catch {
      // best-effort subscriber updates
    }
  }
}

const persist = () => {
  safeSessionSet(STORAGE_KEY, JSON.stringify(state))
}

const hydrate = () => {
  try {
    const raw = safeSessionGet(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    state = {
      input: Number(parsed?.input || 0),
      output: Number(parsed?.output || 0),
    }
  } catch {
    state = { input: 0, output: 0 }
  }
}

hydrate()

const normalizePayload = (payload) => {
  if (payload == null) return ''
  if (typeof payload === 'string') return payload
  try {
    return JSON.stringify(payload)
  } catch {
    return String(payload)
  }
}

const estimateTokens = (payload) => {
  const text = normalizePayload(payload)
  if (!text) return 0
  return Math.max(1, Math.ceil(text.length / 4))
}

export const recordSessionApiUsage = ({ direction, payload }) => {
  const tokens = estimateTokens(payload)
  if (!tokens) return 0

  if (direction === 'input') {
    state = { ...state, input: state.input + tokens }
  } else {
    state = { ...state, output: state.output + tokens }
  }

  persist()
  emit()
  return tokens
}

export const subscribeSessionTokenUsage = (listener) => {
  listeners.add(listener)
  listener({ ...state })
  return () => {
    listeners.delete(listener)
  }
}

export const getSessionTokenUsage = () => ({ ...state })

export const resetSessionTokenUsage = () => {
  state = { input: 0, output: 0 }
  safeSessionRemove(STORAGE_KEY)
  emit()
}
