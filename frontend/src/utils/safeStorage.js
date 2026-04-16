/**
 * Safe localStorage wrapper — falls back to in-memory when storage is blocked.
 * Handles: third-party cookie restrictions, iframe sandboxing, private browsing edge cases.
 */
const mem = {}

export function safeGet(key, fallback = null) {
  try {
    const val = localStorage.getItem(key)
    return val !== null ? val : fallback
  } catch {
    return mem[key] ?? fallback
  }
}

export function safeSet(key, val) {
  try {
    localStorage.setItem(key, String(val))
  } catch {
    mem[key] = String(val)
  }
}

export function safeRemove(key) {
  try {
    localStorage.removeItem(key)
  } catch {
    delete mem[key]
  }
}
