/**
 * CSI Bundle Persistence & Retrieval Utility
 * Workflow:
 * 1. After report completes — bundle CSI artifacts and push to cloud
 * 2. Past sessions are fetched from cloud (HIVEMIND) or local IndexedDB cache
 * 3. Session list merges cloud + local, deduped by simulation_id
 */

import service from '../api/index'
import { sessionCache } from './sessionCache'

export const persistence = {
  /**
   * Bundle and persist a completed session to cloud.
   * POSTs to backend which compresses artifacts and pushes to HIVEMIND.
   * Also saves the returned bundle to IndexedDB for fast local access.
   * @param {string} simId - Simulation ID to persist
   */
  async persistSession(simId) {
    const res = await service.post(`/api/simulation/${simId}/bundle`)
    if (res.data?.success && res.data?.bundle) {
      await sessionCache.save(simId, res.data.bundle)
    }
    return res.data
  },

  /**
   * Fetch and unveil a past session bundle.
   * Checks IndexedDB first, then falls back to backend (which checks local then HIVEMIND).
   * @param {string} simId - Simulation ID to unveil
   * @returns {Promise<Object>} The session bundle
   */
  async unveilSession(simId) {
    // 1. Check IndexedDB first for fast local access
    const cached = await sessionCache.get(simId)
    if (cached) return cached

    // 2. Fetch from backend (which checks local file then HIVEMIND)
    const res = await service.get(`/api/simulation/${simId}/bundle`)
    if (res.data?.success && res.data?.bundle) {
      await sessionCache.save(simId, res.data.bundle)
      return res.data.bundle
    }
    throw new Error('Session not found')
  },

  /**
   * List all sessions merged from cloud (HIVEMIND) and local IndexedDB cache.
   * Cloud entries take precedence for the same simulation_id.
   * Results are sorted by timestamp descending.
   * @returns {Promise<Array>} Merged and deduped session list
   */
  async listSessions() {
    const [cloudRes, localList] = await Promise.all([
      service.get('/api/simulation/sessions/cloud').catch(() => ({ data: { sessions: [] } })),
      sessionCache.list().catch(() => [])
    ])
    // Merge and dedupe by simulation_id — cloud entries win on conflict
    const map = new Map()
    for (const s of localList) map.set(s.simulation_id, { ...s, source: 'local' })
    for (const s of (cloudRes.data?.sessions || [])) map.set(s.simulation_id, { ...s, source: 'cloud' })
    return [...map.values()].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
  }
}
