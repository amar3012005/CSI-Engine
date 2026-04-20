<template>
  <div class="health-paper-panel">
    <!-- Top bar -->
    <div class="report-bar">
      <div class="rb-left">
        <span class="rb-tag">🩺 Medical Assessment</span>
        <span class="rb-id">{{ simulationId }}</span>
        <span v-if="loading" class="rb-generating">
          <span class="rb-gen-dot" />Generating
        </span>
      </div>
      <div class="rb-right">
        <div v-if="report?.summary_stats" class="rb-stats">
          <span>{{ report.summary_stats.agents_count }} specialists</span>
          <span>{{ report.summary_stats.total_claims }} claims</span>
          <span class="tier1">{{ report.summary_stats.tier1_sources }} PubMed sources</span>
        </div>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="paper-body">
      <div class="loading-skeleton">
        <div class="sk-title" />
        <div class="sk-meta" />
        <div v-for="i in 3" :key="i" class="sk-block" />
      </div>
    </div>

    <!-- In-progress -->
    <div v-else-if="report?.status === 'in_progress'" class="paper-body">
      <div class="in-progress">
        <div class="pulse-dot" />
        <span>Specialists collaborating… checking every 5 seconds.</span>
      </div>
    </div>

    <!-- Full paper -->
    <div v-else-if="report" class="paper-body" ref="paperBodyRef">
      <div class="ieee-paper">

        <!-- ═══════ PAPER HEADER ═══════ -->
        <header class="paper-header">
          <div class="paper-journal">HIVEMIND Medical Intelligence · Evidence-Based Clinical Assessment</div>
          <h1 class="paper-title">
            {{ paperTitle }}
          </h1>
          <div class="paper-authors">
            <span v-for="(sp, i) in report.specialist_assessments" :key="sp.agent_id">
              {{ sp.agent_name }}<sup>{{ i + 1 }}</sup>{{ i < report.specialist_assessments.length - 1 ? ', ' : '' }}
            </span>
          </div>
          <div class="paper-affiliations">
            <span v-for="(sp, i) in report.specialist_assessments" :key="sp.agent_id" class="affil-line">
              <sup>{{ i + 1 }}</sup>{{ sp.specialty }}
            </span>
          </div>
          <div class="paper-meta-row">
            <span class="meta-chip">{{ report.summary_stats?.total_rounds }} Research Rounds</span>
            <span class="meta-chip">{{ report.summary_stats?.total_claims }} Clinical Claims</span>
            <span class="meta-chip">{{ report.summary_stats?.total_reviews }} Peer Reviews</span>
            <span class="meta-chip tier1-chip">{{ report.summary_stats?.tier1_sources }} PubMed/WHO Sources</span>
            <span class="meta-chip tier2-chip">{{ report.summary_stats?.tier2_sources }} Guideline Sources</span>
          </div>
        </header>

        <div class="paper-rule" />

        <!-- ═══════ ABSTRACT ═══════ -->
        <section class="paper-section abstract-section">
          <h2 class="section-heading">Abstract</h2>
          <div class="abstract-body">
            <p>{{ report.clinical_reasoning || 'Clinical reasoning summary not available.' }}</p>
          </div>
          <div class="abstract-keywords" v-if="report.differential_diagnoses?.length">
            <strong>Primary Diagnosis:</strong>
            <span v-for="d in report.differential_diagnoses.slice(0,2)" :key="d.rank" class="kw-chip">
              {{ d.diagnosis }} ({{ Math.round(d.confidence * 100) }}%)
            </span>
          </div>
        </section>

        <div class="paper-rule" />

        <!-- ═══════ CASE PRESENTATION ═══════ -->
        <section class="paper-section" v-if="report.case_query">
          <h2 class="section-heading">I. Case Presentation</h2>
          <div class="case-query-box">
            <pre class="case-text">{{ report.case_query }}</pre>
          </div>
        </section>

        <!-- ═══════ DIFFERENTIAL DIAGNOSIS ═══════ -->
        <section class="paper-section" v-if="report.differential_diagnoses?.length">
          <h2 class="section-heading">II. Differential Diagnosis</h2>
          <table class="ieee-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Diagnosis</th>
                <th>Confidence</th>
                <th>EBM Level</th>
                <th>Clinical Reasoning</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in report.differential_diagnoses" :key="d.rank" :class="d.rank === 1 ? 'primary-row' : ''">
                <td class="rank-cell">{{ d.rank }}</td>
                <td class="dx-cell">{{ d.diagnosis }}</td>
                <td class="conf-cell">
                  <div class="conf-bar-wrap">
                    <div class="conf-bar">
                      <div class="conf-fill" :style="{ width: (d.confidence * 100) + '%', background: confColor(d.confidence) }" />
                    </div>
                    <span class="conf-pct">{{ Math.round(d.confidence * 100) }}%</span>
                  </div>
                </td>
                <td class="level-cell">
                  <span class="ebm-badge" :class="'level-' + d.evidence_level">{{ d.evidence_level }}</span>
                </td>
                <td class="reason-cell">{{ d.reasoning }}</td>
              </tr>
            </tbody>
          </table>
          <p class="table-caption">Table I. Differential diagnoses ranked by confidence. EBM levels: A = RCT/meta-analysis, B = observational/cohort, C = expert consensus/case.</p>
        </section>

        <!-- ═══════ RECOMMENDED INVESTIGATIONS ═══════ -->
        <section class="paper-section" v-if="report.recommended_investigations?.length">
          <h2 class="section-heading">III. Recommended Investigations</h2>
          <ul class="ieee-list">
            <li v-for="inv in report.recommended_investigations" :key="inv">{{ inv }}</li>
          </ul>
        </section>

        <!-- ═══════ MANAGEMENT PLAN ═══════ -->
        <section class="paper-section" v-if="report.management_plan?.length">
          <h2 class="section-heading">IV. Management Plan</h2>
          <ol class="ieee-list ordered">
            <li v-for="(step, i) in report.management_plan" :key="i">{{ step }}</li>
          </ol>
        </section>

        <!-- ═══════ SAFETY ALERTS ═══════ -->
        <section class="paper-section safety-section" v-if="activeSafetyAlerts.length">
          <h2 class="section-heading">⚠ Clinical Safety Alerts</h2>
          <div class="safety-alerts-list">
            <div v-for="(alert, i) in activeSafetyAlerts" :key="i" class="safety-alert-item">
              <span class="alert-num">{{ i + 1 }}</span>
              <p>{{ alert }}</p>
            </div>
          </div>
        </section>

        <!-- ═══════ SPECIALIST ASSESSMENTS ═══════ -->
        <section class="paper-section">
          <h2 class="section-heading">V. Multi-Specialist Clinical Assessment</h2>
          <p class="section-intro">
            The following sections present independent evidence-based assessments from each specialist. Each contribution was subjected to peer review within the CSI framework over {{ report.summary_stats?.total_rounds }} rounds.
          </p>

          <div v-for="(sp, idx) in report.specialist_assessments" :key="sp.agent_id" class="specialist-block">
            <h3 class="spec-heading">
              <span class="spec-num">{{ idx + 1 }}.</span>
              {{ sp.agent_name }}
              <span class="spec-role">{{ sp.specialty }}</span>
              <span class="spec-stats">{{ sp.total_claims }} findings · {{ sp.total_reviews_received }} peer reviews received</span>
            </h3>

            <!-- Clinical contributions -->
            <div v-if="sp.contributions?.length" class="contrib-list">
              <div v-for="(c, ci) in sp.contributions" :key="c.claim_id" class="contrib-item">
                <div class="contrib-meta">
                  <span class="contrib-round">Round {{ c.round_num }}</span>
                  <span class="contrib-conf" :style="{ color: confColor(c.confidence) }">{{ Math.round(c.confidence * 100) }}% confidence</span>
                  <span v-if="c.revised" class="contrib-revised">↻ Revised</span>
                </div>
                <p class="contrib-text">{{ c.claim_text }}</p>
                <!-- Evidence chain -->
                <div v-if="c.evidence?.length" class="evidence-chain">
                  <span v-for="ev in c.evidence" :key="ev.source_id" class="ev-pill" :class="ev.tier">
                    <a :href="ev.url" target="_blank" rel="noopener noreferrer">
                      <span class="ev-tier-dot" :class="ev.tier" />
                      {{ ev.pmid ? ev.pmid : ev.label }}
                    </a>
                  </span>
                </div>
              </div>
            </div>

            <!-- Peer challenges received -->
            <div v-if="significantChallenges(sp).length" class="challenges-block">
              <h4 class="challenge-heading">Peer Challenges &amp; Reviews</h4>
              <div v-for="(rev, ri) in significantChallenges(sp)" :key="ri" class="challenge-item" :class="'verdict-' + rev.verdict">
                <div class="challenge-meta">
                  <strong>{{ rev.reviewer }}</strong>
                  <span class="ch-role">{{ rev.reviewer_role }}</span>
                  <span class="verdict-tag" :class="'v-' + rev.verdict">{{ verdictLabel(rev.verdict) }}</span>
                </div>
                <p class="challenge-text">{{ rev.review_text?.substring(0, 400) }}{{ rev.review_text?.length > 400 ? '…' : '' }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- ═══════ BIBLIOGRAPHY ═══════ -->
        <section class="paper-section" v-if="report.bibliography?.length">
          <h2 class="section-heading">References</h2>
          <div class="ieee-references">
            <div v-for="ref in report.bibliography" :key="ref.ref_num" class="ref-entry">
              <span class="ref-num">[{{ ref.ref_num }}]</span>
              <span class="ref-tier-badge" :class="ref.tier">{{ tierLabel(ref.tier) }}</span>
              <a :href="ref.url" target="_blank" rel="noopener noreferrer" class="ref-title">{{ ref.title }}</a>
              <span v-if="ref.pmid" class="ref-pmid">PMID: {{ ref.pmid }}</span>
            </div>
          </div>
        </section>

        <!-- ═══════ DISCLAIMER ═══════ -->
        <footer class="paper-footer">
          <p>{{ report.disclaimer }}</p>
        </footer>

      </div><!-- /ieee-paper -->
    </div><!-- /paper-body -->

    <div v-else-if="error" class="paper-body">
      <div class="error-state">⚠ {{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import service from '../api/index.js'

const props = defineProps({
  simulationId: { type: String, required: true }
})

const report = ref(null)
const loading = ref(true)
const error = ref(null)
const paperBodyRef = ref(null)
const expandedAgents = ref(new Set())
let pollTimer = null

const paperTitle = computed(() => {
  if (!report.value) return 'Medical Assessment Report'
  const diffs = report.value.differential_diagnoses || []
  if (diffs.length) return `Evidence-Based Assessment: ${diffs[0].diagnosis}`
  const cq = (report.value.case_query || '').replace(/Medical Scenario:.*\n/i, '').trim()
  const firstLine = cq.split('\n').find(l => l.trim().length > 10) || ''
  return firstLine.trim() || 'Evidence-Based Medical Assessment'
})

const activeSafetyAlerts = computed(() => {
  const alerts = report.value?.safety_alerts || []
  // Deduplicate by first 80 chars
  const seen = new Set()
  return alerts.filter(a => {
    const key = String(a).substring(0, 80)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 8)
})

async function fetchReport() {
  try {
    const res = await service.get(`/api/simulation/${props.simulationId}/health-report`)
    if (res.data) {
      report.value = res.data
      if (res.data.status === 'completed' || res.data.status === 'error') {
        stopPolling()
        loading.value = false
      } else {
        loading.value = false
      }
    }
  } catch (e) {
    error.value = e.message
    loading.value = false
    stopPolling()
  }
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function confColor(c) {
  if (c >= 0.7) return '#16a34a'
  if (c >= 0.4) return '#d97706'
  return '#dc2626'
}

function verdictLabel(v) {
  return { supports: '✓ Supports', needs_revision: '↻ Needs Revision', challenges: '✗ Challenges' }[v] || v
}

function tierLabel(t) {
  return { tier1: 'Tier 1', tier2: 'Tier 2', tier3: 'Web' }[t] || t
}

function significantChallenges(sp) {
  return (sp.reviews_received || []).filter(r => r.verdict !== 'supports').slice(0, 3)
}

onMounted(() => {
  fetchReport()
  pollTimer = setInterval(fetchReport, 5000)
})

onUnmounted(() => stopPolling())
</script>

<style scoped>
/* ─── Shell ───────────────────────────────── */
.health-paper-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

/* ─── Top bar (same as ReportWorkspacePanel) ── */
.report-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #e3e0db;
  background: #faf9f4;
  flex-shrink: 0;
}
.rb-left { display: flex; align-items: center; gap: 8px; }
.rb-tag {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: #065f46;
  background: rgba(6,95,70,0.08); padding: 2px 8px; border-radius: 4px;
}
.rb-id { font-size: 10px; font-family: monospace; color: #a3a3a3; }
.rb-generating { display: flex; align-items: center; gap: 5px; font-size: 10px; color: #888; }
.rb-gen-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #16a34a;
  animation: pulse 1.4s ease-in-out infinite;
}
.rb-stats { display: flex; gap: 8px; font-size: 10px; color: #888; }
.rb-stats .tier1 { color: #16a34a; font-weight: 600; }

/* ─── Scrollable body ─────────────────────── */
.paper-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  scrollbar-width: thin;
  scrollbar-color: #d4d0ca transparent;
}
.paper-body::-webkit-scrollbar { width: 3px; }
.paper-body::-webkit-scrollbar-thumb { background: #d4d0ca; border-radius: 3px; }

/* ─── IEEE paper layout ───────────────────── */
.ieee-paper {
  max-width: 820px;
  margin: 0 auto;
  color: #1a1a1a;
}

/* Header */
.paper-header { text-align: center; margin-bottom: 1rem; }
.paper-journal {
  font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em;
  color: #065f46; margin-bottom: 8px; font-weight: 700;
}
.paper-title {
  font-size: 17px; font-weight: 800; line-height: 1.3;
  color: #0a0a0a; margin: 0 0 10px;
}
.paper-authors {
  font-size: 11px; color: #404040; margin-bottom: 4px; line-height: 1.6;
}
.paper-authors sup { font-size: 8px; color: #065f46; }
.paper-affiliations {
  display: flex; flex-wrap: wrap; gap: 4px 12px;
  justify-content: center; font-size: 9px; color: #888;
  margin-bottom: 10px;
}
.affil-line sup { font-size: 7px; color: #065f46; margin-right: 1px; }
.paper-meta-row {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 4px;
  margin-top: 8px;
}
.meta-chip {
  font-size: 9px; padding: 2px 8px; border-radius: 10px;
  background: #f0f0ea; color: #555; border: 1px solid #e3e0db;
}
.meta-chip.tier1-chip { background: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
.meta-chip.tier2-chip { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }

.paper-rule { border: none; border-top: 2px solid #0a0a0a; margin: 12px 0; }

/* Sections */
.paper-section { margin-bottom: 1.5rem; }
.section-heading {
  font-size: 11px; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.08em; color: #0a0a0a;
  border-bottom: 1px solid #e3e0db; padding-bottom: 4px;
  margin: 0 0 10px;
}
.section-intro {
  font-size: 12px; line-height: 1.6; color: #525252; margin-bottom: 14px;
}

/* Abstract */
.abstract-section .abstract-body p {
  font-size: 12px; line-height: 1.65; color: #333;
  text-align: justify; margin: 0 0 6px;
}
.abstract-keywords { font-size: 11px; color: #555; margin-top: 6px; }
.kw-chip {
  display: inline-block; margin-left: 6px;
  background: #f0fdf4; color: #065f46;
  padding: 1px 7px; border-radius: 10px; font-size: 10px; font-weight: 600;
  border: 1px solid #bbf7d0;
}

/* Case presentation */
.case-query-box {
  background: #f8f7f2; border: 1px solid #e3e0db; border-radius: 6px;
  padding: 10px 14px;
}
.case-text {
  font-family: 'Space Grotesk', system-ui; font-size: 11px;
  line-height: 1.6; color: #333; margin: 0; white-space: pre-wrap; word-break: break-word;
}

/* IEEE table */
.ieee-table {
  width: 100%; border-collapse: collapse;
  font-size: 11px; margin-bottom: 6px;
}
.ieee-table th {
  background: #0a0a0a; color: #fff;
  padding: 5px 8px; text-align: left;
  font-size: 9px; text-transform: uppercase; letter-spacing: 0.05em;
}
.ieee-table td { padding: 6px 8px; border-bottom: 1px solid #e3e0db; vertical-align: top; }
.ieee-table tr:last-child td { border-bottom: 2px solid #0a0a0a; }
.ieee-table .primary-row td { background: #f0fdf4; font-weight: 600; }
.rank-cell { text-align: center; font-weight: 800; width: 40px; }
.dx-cell { font-weight: 600; width: 200px; }
.conf-cell { width: 110px; }
.conf-bar-wrap { display: flex; align-items: center; gap: 5px; }
.conf-bar { flex: 1; height: 5px; background: #e3e0db; border-radius: 3px; overflow: hidden; }
.conf-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.conf-pct { font-size: 10px; font-weight: 700; white-space: nowrap; }
.level-cell { width: 70px; text-align: center; }
.ebm-badge {
  font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;
  text-transform: uppercase;
}
.level-A { background: #dcfce7; color: #15803d; }
.level-B { background: #fef9c3; color: #92400e; }
.level-C { background: #fee2e2; color: #991b1b; }
.reason-cell { font-size: 10px; color: #555; line-height: 1.5; }
.table-caption { font-size: 9px; color: #888; text-align: center; margin-top: 4px; }

/* Lists */
.ieee-list { font-size: 12px; line-height: 1.65; color: #333; padding-left: 18px; margin: 0; }
.ieee-list li { margin-bottom: 4px; }
.ieee-list.ordered { list-style: decimal; }

/* Safety alerts */
.safety-section .section-heading { color: #b91c1c; }
.safety-alerts-list { display: flex; flex-direction: column; gap: 6px; }
.safety-alert-item {
  display: flex; align-items: flex-start; gap: 8px;
  background: #fff8f8; border: 1px solid #fecaca; border-radius: 6px;
  padding: 8px 10px;
}
.alert-num {
  font-size: 9px; font-weight: 800; color: #b91c1c;
  background: #fee2e2; border-radius: 50%;
  width: 18px; height: 18px; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 1px;
}
.safety-alert-item p { font-size: 11px; line-height: 1.5; color: #7f1d1d; margin: 0; }

/* Specialist blocks */
.specialist-block {
  border: 1px solid #e3e0db; border-radius: 8px;
  margin-bottom: 12px; overflow: hidden;
}
.spec-heading {
  font-size: 12px; font-weight: 700;
  background: #faf9f4; border-bottom: 1px solid #e3e0db;
  padding: 8px 12px; margin: 0;
  display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap;
}
.spec-num { color: #888; font-weight: 400; }
.spec-role { font-size: 10px; font-weight: 400; color: #888; }
.spec-stats { font-size: 9px; color: #aaa; margin-left: auto; }

.contrib-list { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.contrib-item {
  background: #faf9f4; border-radius: 6px;
  padding: 8px 10px; border: 1px solid #f0ede8;
}
.contrib-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.contrib-round {
  font-size: 9px; font-weight: 700; background: #e3e0db;
  color: #666; padding: 1px 6px; border-radius: 8px;
}
.contrib-conf { font-size: 10px; font-weight: 700; }
.contrib-revised { font-size: 9px; color: #d97706; }
.contrib-text { font-size: 11px; line-height: 1.55; color: #333; margin: 0 0 6px; }
.evidence-chain { display: flex; flex-wrap: wrap; gap: 4px; }
.ev-pill {
  font-size: 9px; padding: 1px 7px; border-radius: 10px;
  border: 1px solid; text-decoration: none;
}
.ev-pill a { text-decoration: none; color: inherit; }
.ev-pill a:hover { text-decoration: underline; }
.ev-pill.tier1 { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
.ev-pill.tier2 { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
.ev-pill.tier3 { background: #f9fafb; border-color: #e5e7eb; color: #6b7280; }
.ev-tier-dot {
  display: inline-block; width: 5px; height: 5px;
  border-radius: 50%; margin-right: 3px; vertical-align: middle;
}
.ev-tier-dot.tier1 { background: #16a34a; }
.ev-tier-dot.tier2 { background: #2563eb; }
.ev-tier-dot.tier3 { background: #9ca3af; }

/* Challenges */
.challenges-block {
  border-top: 1px solid #e3e0db;
  padding: 8px 12px; background: #fff;
}
.challenge-heading {
  font-size: 9px; text-transform: uppercase; letter-spacing: 0.07em;
  color: #888; font-weight: 700; margin: 0 0 6px;
}
.challenge-item {
  padding: 6px 8px; border-radius: 5px; margin-bottom: 5px;
  border-left: 3px solid #e3e0db;
}
.challenge-item.verdict-needs_revision { border-left-color: #f59e0b; background: #fffbeb; }
.challenge-item.verdict-challenges { border-left-color: #dc2626; background: #fef2f2; }
.challenge-meta {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; margin-bottom: 3px;
}
.challenge-meta strong { font-weight: 700; }
.ch-role { color: #888; }
.verdict-tag {
  font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 8px;
}
.v-supports { background: #dcfce7; color: #15803d; }
.v-needs_revision { background: #fef9c3; color: #92400e; }
.v-challenges { background: #fee2e2; color: #991b1b; }
.challenge-text { font-size: 10px; line-height: 1.5; color: #444; margin: 0; }

/* References */
.ieee-references { display: flex; flex-direction: column; gap: 4px; }
.ref-entry {
  display: flex; align-items: baseline; gap: 6px;
  font-size: 10px; line-height: 1.5;
}
.ref-num { font-weight: 700; color: #555; white-space: nowrap; min-width: 24px; }
.ref-tier-badge {
  font-size: 8px; font-weight: 700; padding: 1px 4px; border-radius: 3px;
  text-transform: uppercase; flex-shrink: 0;
}
.ref-tier-badge.tier1 { background: #dcfce7; color: #15803d; }
.ref-tier-badge.tier2 { background: #dbeafe; color: #1d4ed8; }
.ref-tier-badge.tier3 { background: #f3f4f6; color: #6b7280; }
.ref-title { color: #1d4ed8; text-decoration: none; flex: 1; }
.ref-title:hover { text-decoration: underline; }
.ref-pmid { font-family: monospace; font-size: 9px; color: #888; white-space: nowrap; }

/* Footer */
.paper-footer {
  border-top: 2px solid #0a0a0a; margin-top: 20px; padding-top: 10px;
}
.paper-footer p { font-size: 10px; color: #888; line-height: 1.5; margin: 0; }

/* Loading/states */
.loading-skeleton { display: flex; flex-direction: column; gap: 12px; }
.sk-title { height: 28px; background: #f0ede8; border-radius: 4px; width: 70%; margin: 0 auto; }
.sk-meta { height: 14px; background: #f0ede8; border-radius: 4px; width: 50%; margin: 0 auto; }
.sk-block {
  height: 80px; border-radius: 6px;
  background: linear-gradient(90deg, #f0ede8 25%, #faf9f4 50%, #f0ede8 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}
.in-progress { display: flex; align-items: center; gap: 10px; color: #888; font-size: 13px; padding: 40px; }
.pulse-dot { width: 10px; height: 10px; border-radius: 50%; background: #16a34a; animation: pulse 1.5s infinite; }
.error-state { color: #dc2626; padding: 40px; text-align: center; }
</style>
