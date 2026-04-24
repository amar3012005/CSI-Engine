/**
 * Safe localStorage wrapper — falls back to in-memory when storage is blocked.
 * Handles: third-party cookie restrictions, iframe sandboxing, private browsing edge cases.
 */
const mem = {}

export function safeGet(key, fallback = null) {
  try {
    // Wrap access in try-catch to handle "Access to storage is not allowed" errors
    const storage = typeof localStorage !== 'undefined' ? localStorage : null
    if (storage !== null) {
      const val = storage.getItem(key)
      return val !== null ? val : fallback
    }
  } catch {
    // blocked or unavailable
  }
  return mem[key] ?? fallback
}

export function safeSet(key, val) {
  try {
    const storage = typeof localStorage !== 'undefined' ? localStorage : null
    if (storage !== null) {
      storage.setItem(key, String(val))
      return
    }
  } catch {
    // blocked or unavailable
  }
  mem[key] = String(val)
}

export function safeRemove(key) {
  try {
    const storage = typeof localStorage !== 'undefined' ? localStorage : null
    if (storage !== null) {
      storage.removeItem(key)
      return
    }
  } catch {
    // blocked or unavailable
  }
  delete mem[key]
}

/**
 * Session storage versions
 */

const sessionMem = {}

export function safeSessionGet(key, fallback = null) {
  try {
    const storage = typeof sessionStorage !== 'undefined' ? sessionStorage : null
    if (storage !== null) {
      const val = storage.getItem(key)
      return val !== null ? val : fallback
    }
  } catch {
    // blocked
  }
  return sessionMem[key] ?? fallback
}

export function safeSessionSet(key, val) {
  try {
    const storage = typeof sessionStorage !== 'undefined' ? sessionStorage : null
    if (storage !== null) {
      storage.setItem(key, String(val))
      return
    }
  } catch {
    // blocked
  }
  sessionMem[key] = String(val)
}

export function safeSessionRemove(key) {
  try {
    const storage = typeof sessionStorage !== 'undefined' ? sessionStorage : null
    if (storage !== null) {
      storage.removeItem(key)
      return
    }
  } catch {
    // blocked
  }
  delete sessionMem[key]
}

