/**
 * Research Artifact Persistence & Retrieval Utility
 * Workflow:
 * 1. Deep Research (Local/Cloud execution results) -> Final Artifacts
 * 2. Backend -> Compresses to ResearchBundle -> Saves to HIVEMIND DB
 * 3. Client (Unveiling Result) -> Requests Bundle -> Extract to Local Cache (IndexedDB or LocalStorage)
 */

import axios from 'axios';

export const simulationPersistence = {
  /**
   * 'Unveil' a past research report.
   * If local files are missing, it fetches the bundle from the HIVEMIND DB
   * and populates the local cache (IndexedDB or temp frontend store).
   * @param {string} simId - Simulation ID to unveil
   */
  async revealPastReport(simId) {
    try {
      // 1. Check if the report state exists locally first (for performance)
      const cached = localStorage.getItem(`csi_unveiled_${simId}`);
      if (cached) return JSON.parse(cached);

      // 2. Fetch the bundle from HIVEMIND DB
      const response = await axios.get(`/api/simulation/${simId}/csi/unveil`);
      if (response.data.status === 'success') {
        const bundle = response.data.content;
        
        // 3. Cache it (simulating the 'revealing' back to original state)
        localStorage.setItem(`csi_unveiled_${simId}`, JSON.stringify(bundle));
        return bundle;
      }
      throw new Error('Bundle retrieval failed');
    } catch (e) {
      console.error('[persistence] Unveiling failed:', error);
      throw error;
    }
  }
};
