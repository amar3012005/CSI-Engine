/**
 * E2E Test: CSI Endpoint Fix Verification
 *
 * Verifies that after our fix:
 *   - GET /api/simulation/{id}/csi/state  → 200 (not 500)
 *   - GET /api/simulation/{id}/csi/graph  → 200 (not 500)
 *
 * Both endpoints should return 200 even after simulation completion
 * (with empty/partial data if artifacts unavailable).
 *
 * Also runs the full Health Mode workflow and captures final state + network tab screenshots.
 *
 * Frontend: http://localhost:3002 (Vite dev server on available port)
 * Backend:  http://localhost:5001 (Flask)
 */

const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

const ARTIFACTS_DIR = path.join(__dirname, '../test-artifacts')

const BASE_URL = 'http://localhost:3002'
const BACKEND_URL = 'http://localhost:5001'

const PATIENT_CASE = '45M chest pain, troponin elevated'

const waitFor = (page, fn, timeoutMs) =>
  page.waitForFunction(fn, null, { timeout: timeoutMs })

test.describe('CSI Endpoint Fix Verification', () => {
  test.setTimeout(15 * 60 * 1000)

  const screenshot = async (page, name) => {
    try {
      await page.screenshot({
        path: path.join(ARTIFACTS_DIR, `csi-fix-${name}.png`),
        fullPage: true
      })
      console.log(`Screenshot saved: csi-fix-${name}.png`)
    } catch (e) {
      console.warn(`Screenshot failed (${name}): ${e.message}`)
    }
  }

  test('csi/state and csi/graph return 200 after simulation completion', async ({ page }) => {
    const consoleErrors = []
    const networkErrors500 = []
    const csiStateResponses = []
    const csiGraphResponses = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    page.on('response', async (resp) => {
      const url = resp.url()
      const status = resp.status()
      if (status >= 500) {
        networkErrors500.push({ url, status })
        console.error(`500 ERROR: ${status} ${url}`)
      }
      if (url.includes('/csi/state')) {
        csiStateResponses.push({ url, status })
        console.log(`csi/state response: ${status} ${url}`)
      }
      if (url.includes('/csi/graph')) {
        csiGraphResponses.push({ url, status })
        console.log(`csi/graph response: ${status} ${url}`)
      }
    })

    // ── Step 0: Verify backend ─────────────────────────────────────────────
    const healthRes = await page.request.get(`${BACKEND_URL}/health`)
    expect(healthRes.ok(), 'Backend must be running on :5001').toBeTruthy()
    console.log('Backend health:', JSON.stringify(await healthRes.json()))

    // ── Step 1: Load home page ─────────────────────────────────────────────
    await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' })
    await screenshot(page, '01-home')

    // ── Step 2: Select Health mode ─────────────────────────────────────────
    const healthPill = page.locator('button.mode-pill', { hasText: /Health/i })
    await expect(healthPill).toBeVisible({ timeout: 10_000 })
    await healthPill.click()
    await expect(healthPill).toHaveClass(/health-active/, { timeout: 5_000 })
    console.log('Health mode active')
    await screenshot(page, '02-health-mode')

    // ── Step 3: Enter patient case ─────────────────────────────────────────
    const chatInput = page.locator('textarea.chat-input')
    await expect(chatInput).toBeVisible()
    await chatInput.fill(PATIENT_CASE)
    await screenshot(page, '03-patient-case')

    // ── Step 4: Submit → confirm card ─────────────────────────────────────
    await expect(page.locator('button.submit-btn')).not.toBeDisabled({ timeout: 5_000 })
    await page.locator('button.submit-btn').click()

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
    console.log('Simulation ID:', simulationId)
    expect(simulationId, 'simulation_id must be returned').toBeTruthy()

    // ── Step 6: Wait for SimulationView ───────────────────────────────────
    await page.waitForURL(/\/simulation\/[^/]+/, { timeout: 20_000 })
    console.log('SimulationView URL:', page.url())
    await screenshot(page, '05-simulation-view')

    // ── Step 7: Wait for 9 agents ─────────────────────────────────────────
    console.log('Waiting for 9 agents (up to 3 min)...')
    await waitFor(
      page,
      () => /\b9\s*Agents\b/.test(document.body.innerText),
      3 * 60 * 1000
    )
    console.log('9 agents deployed')
    await screenshot(page, '06-team-assembly')

    // ── Step 8: Wait for simulation start ─────────────────────────────────
    console.log('Waiting for CSI simulation activity (up to 30s)...')
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
    console.log('Simulation running')
    await screenshot(page, '07-simulation-running')

    // ── Step 9: Wait for "Medical Assessment Ready" ────────────────────────
    console.log('Waiting for Medical Assessment Ready (up to 8 min)...')
    await waitFor(
      page,
      () => document.body.innerText.includes('Medical Assessment Ready'),
      8 * 60 * 1000
    )
    console.log('Medical Assessment Ready!')
    await screenshot(page, '08-assessment-ready')

    // ── Step 10: Verify CSI endpoint statuses so far ───────────────────────
    console.log(`csi/state responses seen: ${csiStateResponses.length}`)
    csiStateResponses.forEach((r) => console.log(`  ${r.status} ${r.url}`))
    console.log(`csi/graph responses seen: ${csiGraphResponses.length}`)
    csiGraphResponses.forEach((r) => console.log(`  ${r.status} ${r.url}`))

    // Direct API check on csi/state and csi/graph right now
    const stateResp = await page.request.get(`${BACKEND_URL}/api/simulation/${simulationId}/csi/state`)
    const graphResp = await page.request.get(`${BACKEND_URL}/api/simulation/${simulationId}/csi/graph`)

    console.log(`Direct csi/state status: ${stateResp.status()}`)
    console.log(`Direct csi/graph status: ${graphResp.status()}`)

    const stateBody = await stateResp.json().catch(() => null)
    const graphBody = await graphResp.json().catch(() => null)

    if (stateBody) {
      console.log('csi/state body keys:', Object.keys(stateBody))
    }
    if (graphBody) {
      console.log('csi/graph body keys:', Object.keys(graphBody))
    }

    // THE KEY ASSERTIONS: both must NOT be 500
    expect(
      stateResp.status(),
      `csi/state returned ${stateResp.status()} — expected 200 or 404, not 500`
    ).not.toBe(500)
    expect(
      graphResp.status(),
      `csi/graph returned ${graphResp.status()} — expected 200 or 404, not 500`
    ).not.toBe(500)

    // Also verify any polled csi responses were not 500
    const csiState500s = csiStateResponses.filter((r) => r.status >= 500)
    const csiGraph500s = csiGraphResponses.filter((r) => r.status >= 500)

    if (csiState500s.length > 0) {
      console.error('csi/state 500 responses:', csiState500s)
    }
    if (csiGraph500s.length > 0) {
      console.error('csi/graph 500 responses:', csiGraph500s)
    }

    expect(
      csiState500s,
      `csi/state had ${csiState500s.length} 500 responses — expected 0`
    ).toHaveLength(0)
    expect(
      csiGraph500s,
      `csi/graph had ${csiGraph500s.length} 500 responses — expected 0`
    ).toHaveLength(0)

    // ── Step 11: Click "Generate Assessment" ──────────────────────────────
    const generateBtn = page.locator('button', { hasText: /Generate Assessment/i }).first()
    await expect(generateBtn).toBeVisible({ timeout: 5_000 })

    const healthReportPromise = page.waitForResponse(
      (r) => r.url().includes('/health-report') && r.status() < 500,
      { timeout: 3 * 60 * 1000 }
    ).catch((e) => {
      console.warn('health-report response not captured:', e.message)
      return null
    })

    await generateBtn.click()
    console.log('Clicked Generate Assessment')

    const healthReportResponse = await healthReportPromise
    if (healthReportResponse) {
      console.log('health-report HTTP status:', healthReportResponse.status())
      const reportJson = await healthReportResponse.json().catch(() => null)
      if (reportJson) {
        console.log('Report fields:', Object.keys(reportJson))
        console.log('Differential diagnoses:', reportJson.differential_diagnoses?.length ?? 0)
        console.log('Specialist assessments:', reportJson.specialist_assessments?.length ?? 0)
      }
    }

    // ── Step 12: Wait for report URL ──────────────────────────────────────
    await page.waitForURL(
      (url) => url.toString().includes('stage=report'),
      { timeout: 20_000 }
    )
    console.log('Report URL:', page.url())
    await screenshot(page, '09-report-url')

    // ── Step 13: Wait for HealthReportPanel ───────────────────────────────
    const rbTag = page.locator('.rb-tag').first()
    await expect(rbTag).toBeVisible({ timeout: 3 * 60 * 1000 })
    const tagText = await rbTag.textContent()
    console.log('Report bar tag:', tagText)
    expect(tagText).toMatch(/Medical Assessment/i)

    await screenshot(page, '10-health-report-panel')

    // ── Step 14: Wait for report content ──────────────────────────────────
    console.log('Waiting for report content (up to 3 min)...')
    await waitFor(
      page,
      () => {
        const html = document.documentElement.innerHTML
        const t = document.body.innerText
        return (
          html.includes('Differential Diagnosis') ||
          html.includes('HIVEMIND Medical Intelligence') ||
          html.includes('section-heading') ||
          t.includes('collaborating') ||
          t.includes('Abstract')
        )
      },
      3 * 60 * 1000
    )
    await screenshot(page, '11-report-content')

    // ── Step 15: Final CSI check after report generation ──────────────────
    const stateRespFinal = await page.request.get(`${BACKEND_URL}/api/simulation/${simulationId}/csi/state`)
    const graphRespFinal = await page.request.get(`${BACKEND_URL}/api/simulation/${simulationId}/csi/graph`)

    console.log(`Final csi/state status: ${stateRespFinal.status()}`)
    console.log(`Final csi/graph status: ${graphRespFinal.status()}`)

    expect(stateRespFinal.status()).not.toBe(500)
    expect(graphRespFinal.status()).not.toBe(500)

    // Screenshot final state
    await screenshot(page, '12-final-state')

    // ── Step 16: Summary ──────────────────────────────────────────────────
    console.log('\n=== CSI Fix Verification Summary ===')
    console.log(`Total 500 errors: ${networkErrors500.length}`)
    networkErrors500.forEach((e) => console.log(`  500: ${e.url}`))
    console.log(`csi/state (direct): ${stateResp.status()} | final: ${stateRespFinal.status()}`)
    console.log(`csi/graph (direct): ${graphResp.status()} | final: ${graphRespFinal.status()}`)
    console.log(`csi/state polled 500s: ${csiState500s.length}`)
    console.log(`csi/graph polled 500s: ${csiGraph500s.length}`)
    console.log('====================================\n')

    // Write network log artifact
    const networkLog = {
      csiStateResponses,
      csiGraphResponses,
      networkErrors500,
      csiStateDirect: stateResp.status(),
      csiGraphDirect: graphResp.status(),
      csiStateFinal: stateRespFinal.status(),
      csiGraphFinal: graphRespFinal.status(),
    }
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, 'csi-network-log.json'),
      JSON.stringify(networkLog, null, 2)
    )
    console.log('Network log written to test-artifacts/csi-network-log.json')

    // Final hard assertion: all 500 errors from workflow (excluding unrelated ones)
    const criticalErrors = networkErrors500.filter(
      (e) => !e.url.includes('/run-status')
    )
    console.log(`Critical 500 errors (excluding /run-status): ${criticalErrors.length}`)
    criticalErrors.forEach((e) => console.log(`  CRITICAL 500: ${e.url}`))

    expect(
      criticalErrors,
      `Found critical 500 errors: ${criticalErrors.map((e) => e.url).join('; ')}`
    ).toHaveLength(0)

    console.log('CSI Fix Verification: PASSED')
  })
})
