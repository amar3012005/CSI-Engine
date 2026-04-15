<template>
  <div class="legacy-redirect-view">
    <div class="redirect-card">
      <div class="spinner"></div>
      <div class="copy">
        <h2>Opening workspace</h2>
        <p v-if="error">{{ error }}</p>
        <p v-else>Resolving the report and redirecting to the unified simulation workspace.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getReport } from '../api/report'

const route = useRoute()
const router = useRouter()
const error = ref('')

onMounted(async () => {
  const reportId = String(route.params.reportId || '')
  if (!reportId) {
    error.value = 'Missing report id.'
    return
  }

  try {
    const res = await getReport(reportId)
    const simulationId = res?.data?.simulation_id
    if (!simulationId) {
      error.value = 'Could not resolve simulation for this report.'
      return
    }

    await router.replace({
      name: 'Simulation',
      params: { simulationId },
      query: {
        stage: 'report',
        reportId
      }
    })
  } catch (err) {
    error.value = err.message || 'Failed to open workspace.'
  }
})
</script>

<style scoped>
.legacy-redirect-view {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f7f6f3;
}

.redirect-card {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 28px 32px;
  border-radius: 18px;
  background: #fff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
}

.spinner {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 2px solid #e5e7eb;
  border-top-color: #111827;
  animation: spin 1s linear infinite;
}

.copy h2 {
  font-size: 18px;
  color: #111827;
  margin-bottom: 6px;
}

.copy p {
  font-size: 14px;
  color: #6b7280;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
