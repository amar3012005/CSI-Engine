/**
 * Authentication and Profile Synchronization Utility
 * "Connect to HIVEMIND" — OAuth flow via api.hivemind.davinciai.eu
 *
 * Flow (matches the real HIVEMIND login at davinciai.eu/hivemind/login):
 *   1. login() — full page redirect to HIVEMIND OAuth login page
 *      with return_to=<current_url>?hivemind_auth=callback
 *   2. Control plane completes OIDC and redirects back to return_to,
 *      appending &token=<sessionId> (cross-origin support in control-plane-server.js)
 *   3. AppSidebar.vue onMounted detects ?hivemind_auth=callback&token=...
 *      and calls authService.syncProfile(token)
 *   4. syncProfile() POSTs to MiroFish Flask /api/auth/sync which validates
 *      the session token server-side via /v1/bootstrap (Bearer auth)
 *   5. Profile saved to localStorage
 */

import axios from 'axios';
import { safeGet, safeSet, safeRemove } from './safeStorage';

const API_BASE = '/api/auth';

const safeStore = {
  get(key) {
    return safeGet(key);
  },
  set(key, val) {
    safeSet(key, val);
  },
  remove(key) {
    safeRemove(key);
  }
};

export const authService = {
  /**
   * Redirect to the HIVEMIND Google OAuth login page.
   * Mirrors the exact flow used by davinciai.eu/hivemind/login.
   *
   * The control plane will:
   *   1. Authenticate via Google / Zitadel OIDC
   *   2. Create a session and append ?token=<sessionId> to the return_to URL
   *      (because return_to contains ?hivemind_auth=callback — see control-plane-server.js)
   *   3. Redirect the browser back here
   *
   * AppSidebar.vue onMounted then reads ?token= and calls syncProfile().
   */
  /**
   * Connect using a HIVEMIND API key (paste from dashboard).
   * Validates server-side via MiroFish backend → control plane /v1/bootstrap.
   * @param {string} apiKey - HIVEMIND API key or session token
   * @returns {Promise<Object>} user profile
   */
  async connectWithKey(apiKey) {
    const response = await axios.post(`${API_BASE}/sync`, { token: apiKey });
    if (response.data.status === 'success') {
      const profile = response.data.profile;
      safeStore.set('hm_user_profile', JSON.stringify(profile));
      safeStore.set('hm_api_key', apiKey);
      return profile;
    }
    throw new Error(response.data.error || 'Invalid API key');
  },

  /**
   * Get current synced profile from memory or storage
   */
  getProfile() {
    const stored = safeStore.get('hm_user_profile');
    return stored ? JSON.parse(stored) : null;
  },

  /**
   * Log out and clear presence
   */
  logout() {
    safeStore.remove('hm_user_profile');
    safeStore.remove('hm_api_key');
  },

  getApiKey() {
    return safeStore.get('hm_api_key');
  }
};
