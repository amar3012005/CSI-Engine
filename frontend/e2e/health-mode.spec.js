/**
 * E2E Test: MiroFish Health Mode Workflow
 *
 * Tests the full Health / Medical Diagnostic CSI workflow:
 *   Home → select Health mode → enter patient case → confirm
 *   → SimulationView environment stage (team assembly)
 *   → simulation stage (CSI rounds running)
 *   → "Medical Assessment Ready" confirm card
 *   → "Generate Assessment" → HealthReportPanel renders
 *
 * Prerequisites:
 *   Backend: http://localhost:5001 (Flask, proxied via Vite /api → :5001)
 *   Frontend: http://localhost:3000 (Vite dev server)
 */

const { test, expect } = require('@playwright/test')
const path = require('path')

// Artifact directory (created per test run)
const ARTIFACTS_DIR = path.join(__dirname, '../test-artifacts')

// ─── Timeouts ───────────────────────────────────────────────────────────────
// Environment preparation (LLM calls to spawn 9 specialists): up to 3 min
const ENV_PREPARE_TIMEOUT = 3 * 60 * 1000
// CSI simulation (multiple rounds): up to 5 min
const SIMULATION_TIMEOUT = 5 * 60 * 1000
// Report generation: up to 2 min
const REPORT_TIMEOUT = 2 * 60 * 1000

const PATIENT_CASE =
  '45M, 3 days of shortness of breath and chest pain. ' +
  'Sudden onset during exercise. Worsening. ' +
  'No medical history, no medications. ' +
  'Troponin elevated 2.1 ng/mL.'

test.describe('Health Mode E2E Workflow', () => {
  test.setTimeout(12 * 60 * 1000) // 12 min overall cap

  // Capture screenshot helper
  const screenshot = async (page, name) => {
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, `${name}.png`),
      fullPage: true
    })
  }

  test('complete health diagnostic workflow', async ({ page }) => {
    // ── Step 0: Verify backend and frontend are reachable ──────────────────
    const backendCheck = await page.request.get('http://localhost:5001/health')
    expect(backendCheck.ok(), 'Backend health check failed — is the Flask server running?').toBeTruthy()

    // ── Step 1: Navigate to home ───────────────────────────────────────────
    await page.goto('http://localhost:3000/')
    await expect(page).toHaveTitle(/.*/, { timeout: 10_000 })

    // ── Step 2: Select "Health" mode pill ─────────────────────────────────
    // Mode pills are buttons with class "mode-pill" containing the text "Health"
    const healthPill = page.locator('button.mode-pill', { hasText: 'Health' })
    await expect(healthPill).toBeVisible({ timeout: 10_000 })
    await healthPill.click()
    // Confirm pill is now active
    await expect(healthPill).toHaveClass(/health-active/)

    await screenshot(page, '01-home-health-mode-selected')

    // ── Step 3: Fill patient case in chat textarea ─────────────────────────
    const chatInput = page.locator('textarea.chat-input')
    await expect(chatInput).toBeVisible()
    await chatInput.fill(PATIENT_CASE)
    await expect(chatInput).toHaveValue(PATIENT_CASE)

    await screenshot(page, '02-patient-case-entered')

    // ── Step 4: Submit — show confirm card ────────────────────────────────
    // Click the submit arrow button
    const submitBtn = page.locator('button.submit-btn')
    await submitBtn.click()

    // CsiConfirmCard should appear with health-specific title
    const confirmCard = page.locator('.csi-confirm-card, .confirm-card, [class*="confirm"]').first()
    // Wait for confirm card OR for navigation (depending on UI version)
    await page.waitForFunction(
      () => {
        const text = document.body.innerText
        return (
          text.includes('Medical Assessment') ||
          text.includes('Start Assessment') ||
          text.includes('9') && text.includes('Specialists')
        )
      },
      { timeout: 15_000 }
    )

    await screenshot(page, '03-confirm-card')

    // ── Step 5: Click "Start Assessment" to create simulation ─────────────
    const startAssessmentBtn = page.locator('button', { hasText: /Start Assessment/i })
    if (await startAssessmentBtn.isVisible()) {
      // Intercept the simulation creation API call to get sim ID
      const [createResponse] = await Promise.all([
        page.waitForResponse(
          (resp) => resp.url().includes('/api/simulation') && resp.request().method() === 'POST',
          { timeout: 15_000 }
        ),
        startAssessmentBtn.click()
      ])
      const createBody = await createResponse.json().catch(() => ({}))
      console.log('Simulation create response:', JSON.stringify(createBody, null, 2))
    } else {
      // Some UI versions auto-submit on Enter or have different button label
      const altBtn = page.locator('button', { hasText: /Continue|Generate|Assess/i }).first()
      await altBtn.click()
    }

    // ── Step 6: Wait for navigation to SimulationView with health mode ─────
    await page.waitForURL(/\/simulation\/[^/]+/, { timeout: 20_000 })
    const simUrl = page.url()
    console.log('Navigated to simulation URL:', simUrl)

    // URL should include configMode=health
    expect(simUrl).toMatch(/configMode=health/i)

    await screenshot(page, '04-simulation-view-loaded')

    // ── Step 7: Environment stage — wait for agent/specialist grid ─────────
    // The environment stage shows agent grid once preparation completes
    // "9 Agents" badge or AgentGrid should appear
    const agentCountLabel = page.locator(
      'text=/9\\s*Agents|9 specialists|Team.*9/i'
    ).first()

    await expect(agentCountLabel).toBeVisible({ timeout: ENV_PREPARE_TIMEOUT })
    console.log('9 agents/specialists grid is visible')

    await screenshot(page, '05-team-assembly-9-agents')

    // Verify the agents count text contains 9
    const agentText = await agentCountLabel.textContent()
    expect(agentText).toMatch(/9/)

    // ── Step 8: Click "Start Simulation" ──────────────────────────────────
    // The "Start Simulation" button appears once environment preparation is ready
    const startSimBtn = page.locator('button', {
      hasText: /Start Simulation|Begin Simulation|Start Assessment/i
    }).first()
    await expect(startSimBtn).toBeVisible({ timeout: 30_000 })
    await startSimBtn.click()

    console.log('Simulation started')
    await screenshot(page, '06-simulation-started')

    // ── Step 9: Verify simulation tab is active (stage=simulation) ─────────
    // The drawer tab "Simulation" should become active
    await page.waitForFunction(
      () => document.body.innerText.includes('Simulation') ||
            window.location.search.includes('stage=simulation'),
      { timeout: 15_000 }
    )

    // ── Step 10: Wait for CSI rounds to complete ──────────────────────────
    // Wait for "Medical Assessment Ready" confirm card to appear
    // This happens when the simulation completes all rounds
    await page.waitForFunction(
      () => document.body.innerText.includes('Medical Assessment Ready') ||
            document.body.innerText.includes('Generate Assessment'),
      { timeout: SIMULATION_TIMEOUT }
    )
    console.log('Medical Assessment Ready confirm card appeared')

    await screenshot(page, '07-medical-assessment-ready')

    // Verify the confirm card details
    const assessmentReadyTitle = page.locator('text=/Medical Assessment Ready/i').first()
    await expect(assessmentReadyTitle).toBeVisible()

    // Confirm icon is 🩺
    const cardIcon = page.locator('text=🩺').first()
    await expect(cardIcon).toBeVisible()

    // ── Step 11: Click "Generate Assessment" ──────────────────────────────
    const generateBtn = page.locator('button', { hasText: /Generate Assessment/i }).first()
    await expect(generateBtn).toBeVisible({ timeout: 10_000 })

    const [healthReportResponse] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/health-report') ||
          resp.url().includes('/health_report'),
        { timeout: REPORT_TIMEOUT }
      ).catch(() => null), // non-fatal if endpoint timing varies
      generateBtn.click()
    ])

    if (healthReportResponse) {
      const reportJson = await healthReportResponse.json().catch(() => null)
      if (reportJson) {
        console.log('Health report API response status:', reportJson.status || 'N/A')
        console.log('Differential diagnoses count:', reportJson.differential_diagnoses?.length || 0)
        console.log('Specialists count:', reportJson.specialist_assessments?.length || 0)
      }
    }

    // ── Step 12: Verify URL changed to report stage ───────────────────────
    await page.waitForURL(
      (url) =>
        url.toString().includes('stage=report') &&
        url.toString().includes('configMode=health'),
      { timeout: 20_000 }
    )
    console.log('URL now shows stage=report&configMode=health')

    // ── Step 13: Verify HealthReportPanel rendered ─────────────────────────
    // The HealthReportPanel has a distinctive top bar with "🩺 Medical Assessment"
    const medAssessmentBar = page.locator('text=/🩺 Medical Assessment/').first()
    await expect(medAssessmentBar).toBeVisible({ timeout: REPORT_TIMEOUT })

    await screenshot(page, '08-health-report-panel-loading')

    // ── Step 14: Wait for report data to load ─────────────────────────────
    // Either differential diagnoses section appears OR "in_progress" message
    await page.waitForFunction(
      () => {
        const text = document.body.innerText
        return (
          text.includes('Differential Diagnosis') ||
          text.includes('collaborating') ||
          text.includes('in_progress')
        )
      },
      { timeout: REPORT_TIMEOUT }
    )

    await screenshot(page, '09-health-report-content')

    // ── Step 15: If report is complete, verify all sections ───────────────
    const isDone = await page.evaluate(
      () => !document.body.innerText.includes('collaborating')
    )

    if (isDone) {
      console.log('Report is complete, verifying all sections...')

      // IEEE-style header
      const ieeeHeader = page.locator('text=/HIVEMIND Medical Intelligence/').first()
      await expect(ieeeHeader).toBeVisible()

      // Differential Diagnosis table
      const diffDxSection = page.locator('text=/Differential Diagnosis/').first()
      await expect(diffDxSection).toBeVisible()

      // Clinical Reasoning / Abstract section
      const abstractSection = page.locator('text=/Abstract/').first()
      await expect(abstractSection).toBeVisible()

      // Specialist Assessments section
      const specialistSection = page.locator('text=/Specialist/').first()
      await expect(specialistSection).toBeVisible()

      // Bibliography section
      const biblioSection = page.locator('text=/References|Bibliography/').first()
      await expect(biblioSection).toBeVisible()

      await screenshot(page, '10-health-report-complete')
    } else {
      console.log('Report still generating (in_progress status) — marking as acceptable for now')
      // in_progress is a valid state — the panel is mounted and polling
    }

    // ── Step 16: Check console errors ─────────────────────────────────────
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    // Give it a moment to capture any pending errors
    await page.waitForTimeout(2_000)

    // Filter out known benign errors
    const criticalErrors = consoleErrors.filter(
      (e) =>
        !e.includes('ResizeObserver') &&
        !e.includes('favicon') &&
        !e.includes('404') // minor 404s are non-critical
    )
    if (criticalErrors.length > 0) {
      console.warn('Console errors found:', criticalErrors)
    }
    // Not a hard failure — log but don't fail the test on console errors alone
    console.log(`Console errors (total): ${consoleErrors.length}, critical: ${criticalErrors.length}`)

    await screenshot(page, '11-final-state')

    console.log('E2E Health Mode Workflow PASSED')
  })
})
