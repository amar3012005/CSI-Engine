/**
 * Authentication and Profile Synchronization Utility
 * Achieves "Connect to HIVEMIND" by syncing user profiles from the Control Plane via Zitadel.
 */

import axios from 'axios';

const API_BASE = '/api/auth';

export const authService = {
  /**
   * Synchronize profile using JWT from Zitadel/Control Plane
   * @param {string} token - OIDC JWT from Control Plane
   * @returns {Promise<Object>} - User profile (user_id, organisation_id, display_name, avatar, role)
   */
  async syncProfile(token) {
    try {
      const response = await axios.post(`${API_BASE}/sync`, { token });
      if (response.data.status === 'success') {
        const profile = response.data.profile;
        // Persistence: Local storage for session consistency
        localStorage.setItem('hm_user_profile', JSON.stringify(profile));
        return profile;
      }
      throw new Error(response.data.error || 'Sync failed');
    } catch (error) {
      console.error('[auth] Profile sync error:', error);
      throw error;
    }
  },

  /**
   * Get current synced profile from memory or storage
   */
  getProfile() {
    const stored = localStorage.getItem('hm_user_profile');
    return stored ? JSON.parse(stored) : null;
  },

  /**
   * Log out and clear presence
   */
  logout() {
    localStorage.removeItem('hm_user_profile');
  }
};
