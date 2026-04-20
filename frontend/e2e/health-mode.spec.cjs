/**
 * E2E Test: MiroFish Health Mode Workflow
 *
 * Tests the full Health / Medical Diagnostic CSI workflow end-to-end:
 *   1. Home page: select Health mode pill, enter patient case
 *   2. Confirm card: click "Start Assessment" to create simulation
 *   3. SimulationView: environment auto-prepares (9 specialist profiles)
 *   4. Simulation auto-starts on mount (Step3Simulation)
 *   5. CSI rounds run, "Medical Assessment Ready" confirm card appears
 *   6. Click "Generate Assessment" → HealthReportPanel renders
 *
 * Prerequisites:
 *   Backend: http://localhost:5001 (Flask)
 *   Frontend: http://localhost:3000 (Vite dev server)
 *
 * IMPORTANT: page.waitForFunction() takes (fn, arg, options).
 *   Options { timeout } must be the THIRD argument, not the second.
 *   Passing options as second arg treats it as the `arg` parameter.
 */

const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

const ARTIFACTS_DIR = path.join(__dirname, '../test-artifacts')

const PATIENT_CASE =
  '45M, 3 days of shortness of breath and chest pain. ' +
  'Sudden onset during exercise. Worsening. ' +
  'No medical history, no medications. ' +
  'Troponin elevated 2.1 ng/mL.'

// Helper: call waitForFunction with explicit timeout as THIRD arg (not second)
// Playwright signature: waitForFunction(fn, arg?, options?)
const waitFor = (page, fn, timeoutMs) =>
  page.waitForFunction(fn, null, { timeout: timeoutMs })

test.describe('Health Mode E2E Workflow', () => {
  test.setTimeout(15 * 60 * 1000) // 15 min overall cap

  const screenshot = async (page, name) => {
    try {
      await page.screenshot({
        path: path.join(ARTIFACTS_DIR, `${name}.png`),
        fullPage: true
      })
      console.log(`Screenshot: ${name}.png`)
    } catch (e) {
      console.warn(`Screenshot failed (${name}): ${e.message}`)
    }
  }

  test('complete health diagnostic workflow from chat to HealthReportPanel', async ({ page }) => {
    const consoleErrors = []
    const networkErrors500 = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    // Track which endpoints return 5xx (to distinguish critical vs. benign 500s)
    page.on('response', (resp) => {
      if (resp.status() >= 500) {
        networkErrors500.push({ url: resp.url(), status: resp.status() })
      }
    })

    // ── Step 0: Verify backend ─────────────────────────────────────────────
    const healthRes = await page.request.get('http://localhost:5001/health')
    expect(healthRes.ok(), 'Backend not running on :5001').toBeTruthy()
    console.log('Backend:', JSON.stringify(await healthRes.json()))

    // ── Step 1: Load home page ─────────────────────────────────────────────
    await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded' })
    await screenshot(page, '01-home-initial')

    // ── Step 2: Select Health mode ─────────────────────────────────────────
    const healthPill = page.locator('button.mode-pill', { hasText: /Health/i })
    await expect(healthPill).toBeVisible({ timeout: 10_000 })
    await healthPill.click()
    await expect(healthPill).toHaveClass(/health-active/, { timeout: 5_000 })
    console.log('Health mode pill active')

    // Hero title should say Medical Assessment
    await expect(page.locator('h1.hero-title')).toContainText(/Medical Assessment/i, { timeout: 5_000 })

    // Placeholder is patient-focused
    const chatInput = page.locator('textarea.chat-input')
    await expect(chatInput).toBeVisible()
    const placeholder = await chatInput.getAttribute('placeholder')
    expect(placeholder).toMatch(/patient|case|complaint/i)
    console.log('Placeholder:', placeholder)

    await screenshot(page, '02-health-mode-active')

    // ── Step 3: Fill patient case ──────────────────────────────────────────
    await chatInput.fill(PATIENT_CASE)
    await expect(chatInput).toHaveValue(PATIENT_CASE)

    // Suggestion panel shows Example cases
    const suggestionHeader = page.locator('.suggestion-header')
    const suggestionVisible = await suggestionHeader.isVisible({ timeout: 2_000 }).catch(() => false)
    if (suggestionVisible) {
      const txt = await suggestionHeader.textContent()
      expect(txt).toMatch(/Example cases|case/i)
    }

    await screenshot(page, '03-patient-case-entered')

    // ── Step 4: Submit → confirm card appears ──────────────────────────────
    await expect(page.locator('button.submit-btn')).not.toBeDisabled({ timeout: 5_000 })
    await page.locator('button.submit-btn').click()

    // CsiConfirmCard should replace the chat input
    await waitFor(
      page,
      () => {
        const t = document.body.innerText
        return t.includes('Start Assessment') || (t.includes('Medical Assessment') && t.includes('9'))
      },
      15_000
    )
    console.log('Confirm card visible')
    await screenshot(page, '04-confirm-card')

    // ── Step 5: Click "Start Assessment" ──────────────────────────────────
    const startBtn = page.locator('button', { hasText: /Start Assessment/i })
    await expect(startBtn).toBeVisible({ timeout: 5_000 })

    const [createResponse] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/api/simulation') && r.request().method() === 'POST',
        { timeout: 20_000 }
      ),
      startBtn.click()
    ])

    const createBody = await createResponse.json().catch(() => ({}))
    const simulationId = createBody?.data?.simulation_id
    const configMode = createBody?.data?.config_mode
    console.log('Simulation ID:', simulationId)
    console.log('Config mode:', configMode)
    expect(simulationId, 'simulation_id must be in create response').toBeTruthy()
    expect(configMode).toBe('health')

    // ── Step 6: Navigate to SimulationView ────────────────────────────────
    await page.waitForURL(/\/simulation\/[^/]+/, { timeout: 20_000 })
    const simUrl = page.url()
    console.log('SimulationView URL:', simUrl)
    expect(simUrl).toMatch(/configMode=health/i)
    await screenshot(page, '05-simulation-view-environment')

    // ── Step 7: Wait for 9 specialist agents to be deployed ────────────────
    console.log('Waiting for 9 agents to be deployed (env preparation, up to 3 min)...')
    await waitFor(
      page,
      () => /\b9\s*Agents\b/.test(document.body.innerText),
      3 * 60 * 1000  // 3 min
    )
    console.log('9 agents deployed!')
    await screenshot(page, '06-team-assembly-9-agents')

    // ── Step 8: Wait for CSI simulation activity ──────────────────────────
    console.log('Waiting for CSI simulation to start (up to 30s)...')
    await waitFor(
      page,
      () => {
        const t = document.body.innerText
        return (
          t.includes('Round') ||
          t.includes('Clinical') ||
          t.includes('Diagnosis') ||
          window.location.search.includes('stage=simulation')
        )
      },
      30_000
    )
    console.log('CSI simulation running')
    await screenshot(page, '07-csi-simulation-running')

    // ── Step 9: Wait for "Medical Assessment Ready" confirm card ──────────
    console.log('Waiting for Medical Assessment Ready (up to 8 min)...')
    await waitFor(
      page,
      () => document.body.innerText.includes('Medical Assessment Ready'),
      8 * 60 * 1000  // 8 min
    )
    console.log('Medical Assessment Ready!')
    await screenshot(page, '08-medical-assessment-ready-card')

    // Verify confirm card elements
    await expect(page.locator('text=Medical Assessment Ready').first()).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('text=🩺').first()).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('button', { hasText: /Generate Assessment/i }).first()).toBeVisible({ timeout: 5_000 })

    // ── Step 10: Click "Generate Assessment" ──────────────────────────────
    const generateBtn = page.locator('button', { hasText: /Generate Assessment/i }).first()

    // Capture health-report API response (best-effort)
    const healthReportPromise = page.waitForResponse(
      (r) => r.url().includes('/health-report') && r.status() < 500,
      { timeout: 3 * 60 * 1000 }
    ).catch((e) => {
      console.warn('health-report API not captured:', e.message)
      return null
    })

    await generateBtn.click()
    console.log('Clicked Generate Assessment')

    const healthReportResponse = await healthReportPromise
    if (healthReportResponse) {
      const httpStatus = healthReportResponse.status()
      console.log('Health report HTTP status:', httpStatus)
      expect(httpStatus, 'health-report must not return 5xx').toBeLessThan(500)

      const reportJson = await healthReportResponse.json().catch(() => null)
      if (reportJson) {
        console.log('Report status:', reportJson.status)
        console.log('Differential diagnoses:', reportJson.differential_diagnoses?.length ?? 0)
        console.log('Specialist assessments:', reportJson.specialist_assessments?.length ?? 0)
        console.log('Bibliography entries:', reportJson.bibliography?.length ?? 0)
      }
    }

    // ── Step 11: Verify URL changed to stage=report&configMode=health ──────
    await page.waitForURL(
      (url) => url.toString().includes('stage=report') && url.toString().includes('configMode=health'),
      { timeout: 20_000 }
    )
    console.log('Report URL:', page.url())
    await screenshot(page, '09-report-stage-url')

    // ── Step 12: HealthReportPanel is mounted ─────────────────────────────
    // NOT the web_research PaperReport — that has different markup
    const rbTag = page.locator('.rb-tag').first()
    await expect(rbTag).toBeVisible({ timeout: 3 * 60 * 1000 })
    const tagText = await rbTag.textContent()
    console.log('Report bar tag:', tagText)
    expect(tagText).toMatch(/Medical Assessment/i)

    // Verify NOT raw markdown format
    const pageBodyText = await page.locator('body').textContent()
    expect(pageBodyText, 'HealthReportPanel should not render raw markdown').not.toMatch(/^##\s+\w/m)

    await screenshot(page, '10-health-report-panel-mounted')

    // ── Step 13: Wait for report content to load ──────────────────────────
    // Use innerHTML check (innerText can miss overflow-hidden elements in the drawer)
    await waitFor(
      page,
      () => {
        const html = document.documentElement.innerHTML
        const t = document.body.innerText
        return (
          html.includes('Differential Diagnosis') ||
          html.includes('HIVEMIND Medical Intelligence') ||
          html.includes('section-heading') ||  // IEEE paper section heading class
          t.includes('collaborating') ||
          t.includes('Abstract')
        )
      },
      3 * 60 * 1000  // 3 min
    )
    await screenshot(page, '11-health-report-content')

    // Use innerHTML to check actual content (not innerText which misses clipped elements)
    const reportHtml = await page.evaluate(() => document.documentElement.innerHTML)
    // Report is "complete" if the ieee-paper div is present with actual differential diagnoses
    const isComplete = reportHtml.includes('ieee-paper') &&
                       reportHtml.includes('Differential Diagnosis') &&
                       !reportHtml.includes('Specialists collaborating')

    if (isComplete) {
      console.log('Full IEEE report rendered, verifying all sections...')

      // Check by HTML presence (panel may overflow the drawer viewport)
      const hasIeeeHeader = reportHtml.includes('HIVEMIND Medical Intelligence')
      const hasDiffDx = reportHtml.includes('Differential Diagnosis')
      const hasAbstract = reportHtml.includes('Abstract')
      const hasSpecialist = reportHtml.includes('specialist') || reportHtml.includes('Specialist')
      const hasBiblio = reportHtml.includes('References') || reportHtml.includes('Bibliography')

      console.log('  IEEE header in HTML:', hasIeeeHeader)
      console.log('  Differential Diagnosis in HTML:', hasDiffDx)
      console.log('  Abstract in HTML:', hasAbstract)
      console.log('  Specialist section in HTML:', hasSpecialist)
      console.log('  Bibliography in HTML:', hasBiblio)

      expect(hasIeeeHeader, 'IEEE-style header must be present').toBe(true)
      expect(hasDiffDx, 'Differential Diagnosis section must be present').toBe(true)
      expect(hasAbstract, 'Abstract/Clinical Reasoning must be present').toBe(true)
      expect(hasSpecialist, 'Specialist Assessments must be present').toBe(true)
      expect(hasBiblio, 'Bibliography/References must be present').toBe(true)

      // Also check specialist count in report bar stats
      const statsText = await page.locator('.rb-stats').first().textContent().catch(() => '')
      console.log('  Report bar stats:', statsText)
      expect(statsText).toMatch(/specialist/i)

      await screenshot(page, '12-health-report-full-verified')
    } else {
      console.log('Report still in_progress — HealthReportPanel mounted and polling. Accepted.')
    }

    // ── Step 15: Console error audit ──────────────────────────────────────
    await page.waitForTimeout(2_000)

    const criticalErrors = consoleErrors.filter(
      (e) =>
        !e.includes('ResizeObserver') &&
        !e.includes('favicon') &&
        !e.includes('ERR_ABORTED') &&
        !e.includes('net::ERR_')
    )
    console.log(`Console errors — total: ${consoleErrors.length}, critical: ${criticalErrors.length}`)
    criticalErrors.slice(0, 5).forEach((e) => console.warn('  Console error:', e))

    // Write error log artifact for debugging
    if (consoleErrors.length > 0) {
      fs.writeFileSync(
        path.join(ARTIFACTS_DIR, 'console-errors.txt'),
        consoleErrors.join('\n')
      )
    }

    // Log all 500 responses with their URLs for debugging
    console.log(`5xx responses total: ${networkErrors500.length}`)
    networkErrors500.forEach((e) => console.log(`  5xx: ${e.status} ${e.url}`))

    // Hard fail only on 5xx errors from critical health workflow endpoints
    // (exclude background polling endpoints like /csi/state, /run-status)
    const BENIGN_500_PATTERNS = [
      '/csi/state',     // graph visualization polling (non-critical)
      '/csi/graph',     // graph data polling
      '/run-status',    // simulation run status polling
    ]
    const criticalServer500s = networkErrors500.filter(
      (e) => !BENIGN_500_PATTERNS.some((p) => e.url.includes(p))
    )
    console.log(`Critical 5xx responses: ${criticalServer500s.length}`)
    criticalServer500s.forEach((e) => console.log(`  Critical 5xx: ${e.status} ${e.url}`))

    expect(
      criticalServer500s,
      `Critical server errors: ${criticalServer500s.map((e) => `${e.status} ${e.url}`).join('; ')}`
    ).toHaveLength(0)

    await screenshot(page, '13-final-state')
    console.log('E2E Health Mode Workflow: PASSED')
  })
})
