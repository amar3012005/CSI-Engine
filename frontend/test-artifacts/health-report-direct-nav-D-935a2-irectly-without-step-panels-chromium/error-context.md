# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: health-report-direct-nav.spec.cjs >> Direct URL navigation to health report stage >> loads report stage directly without step panels
- Location: e2e/health-report-direct-nav.spec.cjs:44:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.paper-header, .ieee-paper') to be visible

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - img "Da'vinci" [ref=e6]
      - generic [ref=e8]: Deep Research
      - generic [ref=e9]: 45-year-old male with 2 weeks of persistent headache, photophobia, and neck stiffness
    - generic [ref=e10]:
      - generic [ref=e11]:
        - generic [ref=e12]: "Usage:"
        - generic [ref=e13]: 267.7K
      - generic [ref=e16]: Ready
  - generic [ref=e17]:
    - generic [ref=e18]:
      - generic [ref=e24]: Follow-up
      - textbox "Ask a follow-up question..." [ref=e26]
      - generic [ref=e27]:
        - generic [ref=e29]: Ready for follow-up
        - button "Send" [disabled] [ref=e31]
    - generic [ref=e32]:
      - complementary [ref=e33]:
        - generic [ref=e34]:
          - generic [ref=e36] [cursor=pointer]: ⬡
          - button "›" [ref=e37] [cursor=pointer]
        - navigation [ref=e38]:
          - button "+" [ref=e39] [cursor=pointer]
          - button "▢" [ref=e40] [cursor=pointer]
        - button "⬡" [ref=e42] [cursor=pointer]:
          - generic [ref=e43]: ⬡
      - generic [ref=e45]:
        - generic [ref=e47]:
          - generic [ref=e49]:
            - generic [ref=e50]:
              - generic [ref=e51]:
                - checkbox
              - generic [ref=e53]: Highlight Agents
            - generic [ref=e54]:
              - generic [ref=e55]:
                - checkbox [checked]
              - generic [ref=e57]: Edge Labels
            - generic [ref=e58]:
              - generic [ref=e59]:
                - checkbox [checked]
              - generic [ref=e61]: CSI Artifacts
              - generic [ref=e62]: "855"
          - generic [ref=e63]:
            - button "+" [ref=e64] [cursor=pointer]
            - button "−" [ref=e65] [cursor=pointer]
            - button "Fit to view" [ref=e66] [cursor=pointer]:
              - img [ref=e67]
        - generic [ref=e69]:
          - generic [ref=e70]: Entity Types
          - generic [ref=e71]:
            - generic [ref=e72]:
              - generic [ref=e74]: "CSI: Agent"
              - generic [ref=e75]: "18"
            - generic [ref=e76]:
              - generic [ref=e78]: "CSI: Source"
              - generic [ref=e79]: "50"
            - generic [ref=e80]:
              - generic [ref=e82]: "CSI: Claim"
              - generic [ref=e83]: "100"
            - generic [ref=e84]:
              - generic [ref=e86]: "CSI: Trial"
              - generic [ref=e87]: "85"
            - generic [ref=e88]:
              - generic [ref=e90]: "CSI: AgentAction"
              - generic [ref=e91]: "502"
            - generic [ref=e92]:
              - generic [ref=e94]: "CSI: Recall"
              - generic [ref=e95]: "109"
        - generic [ref=e96]:
          - generic [ref=e97] [cursor=pointer]:
            - generic [ref=e98]: CSI Artifacts Preview
            - button "↻" [ref=e99]
            - button [ref=e100]:
              - img [ref=e101]
          - generic [ref=e104]:
            - article [ref=e105] [cursor=pointer]:
              - generic [ref=e106]:
                - generic [ref=e108]: Claim
                - generic [ref=e109]: proposed
                - generic [ref=e110]: 95%
              - paragraph [ref=e111]: A 45‑year‑old male presenting with a two‑week history of persistent headache, photophobia, and neck stiffness has a high...
              - generic [ref=e112]:
                - generic [ref=e113]: Dr. Michael Patel
                - generic [ref=e114]: R2
            - article [ref=e115] [cursor=pointer]:
              - generic [ref=e116]:
                - generic [ref=e118]: Claim
                - generic [ref=e119]: proposed
                - generic [ref=e120]: 95%
              - paragraph [ref=e121]: In a 45‑year‑old male presenting with 2 weeks of persistent headache, photophobia, and neck stiffness—classic signs of m...
              - generic [ref=e122]:
                - generic [ref=e123]: Dr. Sarah Lee
                - generic [ref=e124]: R2
            - article [ref=e125] [cursor=pointer]:
              - generic [ref=e126]:
                - generic [ref=e128]: Claim
                - generic [ref=e129]: proposed
                - generic [ref=e130]: 95%
              - paragraph [ref=e131]: In a 45‑year‑old adult presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, the mos...
              - generic [ref=e132]:
                - generic [ref=e133]: Dr. Thomas Nguyen
                - generic [ref=e134]: R2
            - article [ref=e135] [cursor=pointer]:
              - generic [ref=e136]:
                - generic [ref=e138]: Claim
                - generic [ref=e139]: proposed
                - generic [ref=e140]: 95%
              - paragraph [ref=e141]: In a 45‑year‑old male presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, the find...
              - generic [ref=e142]:
                - generic [ref=e143]: Dr. James O'Connor
                - generic [ref=e144]: R2
            - article [ref=e145] [cursor=pointer]:
              - generic [ref=e146]:
                - generic [ref=e148]: Claim
                - generic [ref=e149]: proposed
                - generic [ref=e150]: 95%
              - paragraph [ref=e151]: In a 45‑year‑old male presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, the clin...
              - generic [ref=e152]:
                - generic [ref=e153]: Dr. Laura Bennett
                - generic [ref=e154]: R2
            - article [ref=e155] [cursor=pointer]:
              - generic [ref=e156]:
                - generic [ref=e158]: Claim
                - generic [ref=e159]: proposed
                - generic [ref=e160]: 95%
              - paragraph [ref=e161]: In a 45‑year‑old male presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, the NICE...
              - generic [ref=e162]:
                - generic [ref=e163]: Dr. Sophia Patel
                - generic [ref=e164]: R2
            - article [ref=e165] [cursor=pointer]:
              - generic [ref=e166]:
                - generic [ref=e168]: Claim
                - generic [ref=e169]: revised
                - generic [ref=e170]: 95%
              - paragraph [ref=e171]: In a 45‑year‑old man with a two‑week history of persistent headache, photophobia, and neck stiffness, the presentation i...
              - generic [ref=e172]:
                - generic [ref=e173]: Dr. Laura Bennett
                - generic [ref=e174]: R2
            - article [ref=e175] [cursor=pointer]:
              - generic [ref=e176]:
                - generic [ref=e178]: Claim
                - generic [ref=e179]: revised
                - generic [ref=e180]: 95%
              - paragraph [ref=e181]: For a 45‑year‑old man with a two‑week history of persistent headache, photophobia, and neck stiffness, both NICE NG240 a...
              - generic [ref=e182]:
                - generic [ref=e183]: Dr. Sophia Patel
                - generic [ref=e184]: R2
            - article [ref=e185] [cursor=pointer]:
              - generic [ref=e186]:
                - generic [ref=e188]: Claim
                - generic [ref=e189]: revised
                - generic [ref=e190]: 95%
              - paragraph [ref=e191]: In a 45‑year‑old male with a 2‑week history of persistent headache, photophobia, and neck stiffness but no fever or foca...
              - generic [ref=e192]:
                - generic [ref=e193]: Dr. James O'Connor
                - generic [ref=e194]: R2
            - article [ref=e195] [cursor=pointer]:
              - generic [ref=e196]:
                - generic [ref=e198]: Claim
                - generic [ref=e199]: revised
                - generic [ref=e200]: 95%
              - paragraph [ref=e201]: In a 45‑year‑old adult with a 2‑week history of persistent headache, photophobia, and neck stiffness, the presentation i...
              - generic [ref=e202]:
                - generic [ref=e203]: Dr. Thomas Nguyen
                - generic [ref=e204]: R2
            - article [ref=e205] [cursor=pointer]:
              - generic [ref=e206]:
                - generic [ref=e208]: Claim
                - generic [ref=e209]: revised
                - generic [ref=e210]: 95%
              - paragraph [ref=e211]: In a 45‑year‑old male with 2 weeks of headache, photophobia, and neck stiffness suggestive of bacterial meningitis, empi...
              - generic [ref=e212]:
                - generic [ref=e213]: Dr. Sarah Lee
                - generic [ref=e214]: R2
            - article [ref=e215] [cursor=pointer]:
              - generic [ref=e216]:
                - generic [ref=e218]: Claim
                - generic [ref=e219]: revised
                - generic [ref=e220]: 95%
              - paragraph [ref=e221]: In a 45‑year‑old with a two‑week history of headache, photophobia, and neck stiffness, bacterial meningitis is less like...
              - generic [ref=e222]:
                - generic [ref=e223]: Dr. Michael Patel
                - generic [ref=e224]: R2
            - article [ref=e225] [cursor=pointer]:
              - generic [ref=e226]:
                - generic [ref=e228]: Claim
                - generic [ref=e229]: revised
                - generic [ref=e230]: 95%
              - paragraph [ref=e231]: In a 45‑year‑old man with a two‑week history of headache, photophobia, and neck stiffness, the NICE NG240 and WHO mening...
              - generic [ref=e232]:
                - generic [ref=e233]: Dr. Sophia Patel
                - generic [ref=e234]: R2
            - article [ref=e235] [cursor=pointer]:
              - generic [ref=e236]:
                - generic [ref=e238]: Claim
                - generic [ref=e239]: proposed
                - generic [ref=e240]: 95%
              - paragraph [ref=e241]: In a 45‑year‑old male presenting with a two‑week history of persistent headache, photophobia, and neck stiffness, a lumb...
              - generic [ref=e242]:
                - generic [ref=e243]: Dr. Thomas Nguyen
                - generic [ref=e244]: R3
            - article [ref=e245] [cursor=pointer]:
              - generic [ref=e246]:
                - generic [ref=e248]: Claim
                - generic [ref=e249]: proposed
                - generic [ref=e250]: 95%
              - paragraph [ref=e251]: In a 45‑year‑old male presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, the clin...
              - generic [ref=e252]:
                - generic [ref=e253]: Dr. James O'Connor
                - generic [ref=e254]: R3
            - article [ref=e255] [cursor=pointer]:
              - generic [ref=e256]:
                - generic [ref=e258]: Claim
                - generic [ref=e259]: proposed
                - generic [ref=e260]: 95%
              - paragraph [ref=e261]: In a 45‑year‑old male presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness, bacteria...
              - generic [ref=e262]:
                - generic [ref=e263]: Dr. Robert Kim
                - generic [ref=e264]: R3
            - article [ref=e265] [cursor=pointer]:
              - generic [ref=e266]:
                - generic [ref=e268]: Claim
                - generic [ref=e269]: proposed
                - generic [ref=e270]: 95%
              - paragraph [ref=e271]: In a 45‑year‑old adult presenting with a 2‑week history of persistent headache, photophobia, and neck stiffness—clinical...
              - generic [ref=e272]:
                - generic [ref=e273]: Dr. Sarah Lee
                - generic [ref=e274]: R3
            - article [ref=e275] [cursor=pointer]:
              - generic [ref=e276]:
                - generic [ref=e278]: Claim
                - generic [ref=e279]: proposed
                - generic [ref=e280]: 95%
              - paragraph [ref=e281]: In a 45‑year‑old male presenting with a two‑week history of persistent headache, photophobia, and neck stiffness, bacter...
              - generic [ref=e282]:
                - generic [ref=e283]: Dr. Laura Bennett
                - generic [ref=e284]: R3
            - article [ref=e285] [cursor=pointer]:
              - generic [ref=e286]:
                - generic [ref=e288]: Claim
                - generic [ref=e289]: proposed
                - generic [ref=e290]: 95%
              - paragraph [ref=e291]: In a 45‑year‑old male with a 2‑week history of persistent headache, photophobia, and neck stiffness, the clinical pictur...
              - generic [ref=e292]:
                - generic [ref=e293]: Dr. Michael Patel
                - generic [ref=e294]: R3
            - article [ref=e295] [cursor=pointer]:
              - generic [ref=e296]:
                - generic [ref=e298]: Claim
                - generic [ref=e299]: revised
                - generic [ref=e300]: 95%
              - paragraph [ref=e301]: In a 45‑year‑old male with a 2‑week history of headache, photophobia, and neck stiffness, viral meningitis remains a lea...
              - generic [ref=e302]:
                - generic [ref=e303]: Dr. James O'Connor
                - generic [ref=e304]: R3
      - complementary [ref=e305]:
        - generic [ref=e307]:
          - generic [ref=e308]:
            - generic [ref=e309]:
              - button "Environment" [ref=e310] [cursor=pointer]:
                - generic [ref=e311]: Environment
              - button "Simulation" [ref=e312] [cursor=pointer]:
                - generic [ref=e313]: Simulation
              - button "Report" [ref=e314] [cursor=pointer]:
                - generic [ref=e316]: Report
            - generic [ref=e317]:
              - button "›" [ref=e318] [cursor=pointer]:
                - generic [ref=e319]: ›
              - button "×" [ref=e320] [cursor=pointer]
          - generic [ref=e325]:
            - generic [ref=e326]: 🩺 Medical Assessment
            - generic [ref=e327]: sim_8e971ff001cb
            - generic [ref=e328]: Generating
      - generic [ref=e340]:
        - button "View Dr. Emily Zhang" [ref=e341] [cursor=pointer]:
          - img "Dr. Emily Zhang" [ref=e342]
        - button "View Dr. Michael Patel" [ref=e343] [cursor=pointer]:
          - img "Dr. Michael Patel" [ref=e344]
        - button "View Dr. Sarah Lee" [ref=e345] [cursor=pointer]:
          - img "Dr. Sarah Lee" [ref=e346]
        - button "View Dr. Robert Kim" [ref=e347] [cursor=pointer]:
          - img "Dr. Robert Kim" [ref=e348]
        - button "View Dr. Anna Martinez" [ref=e349] [cursor=pointer]:
          - img "Dr. Anna Martinez" [ref=e350]
        - button "View Dr. James O'Connor" [ref=e351] [cursor=pointer]:
          - img "Dr. James O'Connor" [ref=e352]
        - button "View Dr. Laura Bennett" [ref=e353] [cursor=pointer]:
          - img "Dr. Laura Bennett" [ref=e354]
        - button "View Dr. Thomas Nguyen" [ref=e355] [cursor=pointer]:
          - img "Dr. Thomas Nguyen" [ref=e356]
        - button "View Dr. Sophia Patel" [ref=e357] [cursor=pointer]:
          - img "Dr. Sophia Patel" [ref=e358]
```

# Test source

```ts
  53  | 
  54  |     page.on('response', res => {
  55  |       if (res.status() >= 500) {
  56  |         responses500.push(`${res.status()} ${res.url()}`)
  57  |       }
  58  |     })
  59  | 
  60  |     // ── 1. Navigate directly to the report stage URL ──────────────────────
  61  |     console.log(`Navigating to: ${DIRECT_URL}`)
  62  |     await page.goto(DIRECT_URL, { waitUntil: 'domcontentloaded' })
  63  | 
  64  |     await screenshot(page, '01-initial-load')
  65  | 
  66  |     // ── 2. Verify step panels are NOT visible ─────────────────────────────
  67  |     // Step1/Step2/Step3 headers should not be present on the page
  68  |     const step1Heading = page.locator('text=Step 1').first()
  69  |     const step2Heading = page.locator('text=Step 2').first()
  70  |     const step3Heading = page.locator('text=Step 3').first()
  71  | 
  72  |     await expect(step1Heading).not.toBeVisible({ timeout: 5000 }).catch(() => {
  73  |       // acceptable if element doesn't exist
  74  |     })
  75  |     await expect(step2Heading).not.toBeVisible({ timeout: 5000 }).catch(() => {})
  76  |     await expect(step3Heading).not.toBeVisible({ timeout: 5000 }).catch(() => {})
  77  | 
  78  |     console.log('Step panels absent check: passed')
  79  | 
  80  |     // ── 3. Wait for the drawer to open and show Report tab as active ──────
  81  |     // The drawer starts collapsed and opens after 400ms per onMounted()
  82  |     await page.waitForTimeout(600)
  83  | 
  84  |     // The Report tab should be active (the URL stage=report triggers it)
  85  |     const reportTab = page.locator('.drawer-tab.active:has-text("Report"), .drawer-tab:has-text("Report")').first()
  86  |     await expect(reportTab).toBeVisible({ timeout: 10_000 })
  87  |     console.log('Report tab visible: passed')
  88  | 
  89  |     await screenshot(page, '02-report-tab-active')
  90  | 
  91  |     // ── 4. Verify HealthReportPanel is mounted (the medical assessment bar) ─
  92  |     const medAssessmentTag = page.locator('text=Medical Assessment').first()
  93  |     await expect(medAssessmentTag).toBeVisible({ timeout: 15_000 })
  94  |     console.log('Medical Assessment tag visible: passed')
  95  | 
  96  |     await screenshot(page, '03-health-report-panel-mounted')
  97  | 
  98  |     // ── 5. Wait for report content to load (no loading spinner after 30s) ─
  99  |     // Loading skeleton or in_progress state should resolve
  100 |     // The health-report API returns 'completed' data immediately
  101 |     const loadingCleared = await page.waitForFunction(() => {
  102 |       const progressEls = document.querySelectorAll('.in-progress, .loading-skeleton')
  103 |       return progressEls.length === 0
  104 |     }, null, { timeout: 30_000 }).then(() => true).catch(async () => {
  105 |       console.warn('Loading state still visible after 30s — capturing diagnostics')
  106 |       await screenshot(page, '04-still-loading')
  107 |       // Log what's in the DOM
  108 |       const domInfo = await page.evaluate(() => {
  109 |         const sk = document.querySelectorAll('.loading-skeleton')
  110 |         const ip = document.querySelectorAll('.in-progress')
  111 |         const rb = document.querySelectorAll('.report-bar')
  112 |         const ph = document.querySelectorAll('.paper-header')
  113 |         const hp = document.querySelectorAll('.health-paper-panel')
  114 |         return {
  115 |           loadingSkeleton: sk.length,
  116 |           inProgress: ip.length,
  117 |           reportBar: rb.length,
  118 |           paperHeader: ph.length,
  119 |           healthPaperPanel: hp.length
  120 |         }
  121 |       })
  122 |       console.warn('DOM state:', JSON.stringify(domInfo))
  123 |       return false
  124 |     })
  125 | 
  126 |     console.log(`Loading cleared: ${loadingCleared}`)
  127 |     await screenshot(page, '04-content-loaded')
  128 | 
  129 |     // ── 6. Verify IEEE paper structure ────────────────────────────────────
  130 |     // Paper header is inside an overflow-y:auto container — use DOM presence check
  131 |     // rather than Playwright's strict visibility (which can fail for clipped elements)
  132 |     const paperHeaderExists = await page.locator('.paper-header, .ieee-paper').count()
  133 |     const paperHeaderInDom = paperHeaderExists > 0
  134 |     console.log(`IEEE paper structure in DOM: ${paperHeaderInDom} (count: ${paperHeaderExists})`)
  135 | 
  136 |     if (!paperHeaderInDom) {
  137 |       // Check if it's present at all — capture DOM state
  138 |       const domDump = await page.evaluate(() => {
  139 |         const hrp = document.querySelector('.health-paper-panel')
  140 |         return hrp ? hrp.innerHTML.substring(0, 500) : 'health-paper-panel not found'
  141 |       })
  142 |       console.warn('HealthReportPanel innerHTML (first 500):', domDump)
  143 |     }
  144 | 
  145 |     // Scroll into view and verify
  146 |     if (paperHeaderInDom) {
  147 |       const paperHeader = page.locator('.paper-header').first()
  148 |       await paperHeader.scrollIntoViewIfNeeded()
  149 |       await expect(paperHeader).toBeVisible({ timeout: 5_000 })
  150 |       console.log('IEEE paper header visible after scroll: passed')
  151 |     } else {
  152 |       // Wait longer — maybe the API is still fetching
> 153 |       await page.waitForSelector('.paper-header, .ieee-paper', { timeout: 15_000 })
      |                  ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  154 |       console.log('IEEE paper structure appeared after extended wait: passed')
  155 |     }
  156 | 
  157 |     // ── 7. Verify Abstract / Case Presentation section ────────────────────
  158 |     const abstractSection = page.locator('.abstract-section, text=Abstract, text=Case Presentation').first()
  159 |     await expect(abstractSection).toBeVisible({ timeout: 10_000 })
  160 |     console.log('Abstract/Case Presentation section visible: passed')
  161 | 
  162 |     // ── 8. Verify Differential Diagnosis table ────────────────────────────
  163 |     const diffDxSection = page.locator('text=Differential Diagnos').first()
  164 |     await expect(diffDxSection).toBeVisible({ timeout: 10_000 })
  165 |     console.log('Differential Diagnosis section visible: passed')
  166 | 
  167 |     // Check for table or structured diagnosis list
  168 |     const diagnosisTable = page.locator('.diff-table, table, .diagnosis-row, .dd-table').first()
  169 |     const hasDiagnosisTable = await diagnosisTable.isVisible().catch(() => false)
  170 |     if (hasDiagnosisTable) {
  171 |       console.log('Differential diagnosis table visible: passed')
  172 |     } else {
  173 |       // May be rendered as a list — check for rank/diagnosis content
  174 |       const diagnosisContent = page.locator('.diagnosis-list, .dx-rank, [class*="diagnos"]').first()
  175 |       const hasContent = await diagnosisContent.isVisible().catch(() => false)
  176 |       console.log(`Differential diagnosis content ${hasContent ? 'visible' : 'structure may vary'}: checked`)
  177 |     }
  178 | 
  179 |     await screenshot(page, '05-differential-diagnosis')
  180 | 
  181 |     // ── 9. Verify Specialist Assessments section ──────────────────────────
  182 |     const specialistSection = page.locator('text=Specialist Assessment').first()
  183 |     await expect(specialistSection).toBeVisible({ timeout: 10_000 })
  184 |     console.log('Specialist Assessments section visible: passed')
  185 | 
  186 |     // Should have collapsible specialist cards
  187 |     const specialistCards = page.locator('.specialist-card, .sp-card, [class*="specialist"]')
  188 |     const cardCount = await specialistCards.count()
  189 |     console.log(`Specialist cards found: ${cardCount}`)
  190 | 
  191 |     await screenshot(page, '06-specialist-assessments')
  192 | 
  193 |     // ── 10. Verify Bibliography section ───────────────────────────────────
  194 |     const bibSection = page.locator('text=Bibliography, text=References').first()
  195 |     await expect(bibSection).toBeVisible({ timeout: 10_000 })
  196 |     console.log('Bibliography section visible: passed')
  197 | 
  198 |     // Check for numbered references
  199 |     const bibItems = page.locator('.bib-item, .ref-item, [class*="bib"]')
  200 |     const bibCount = await bibItems.count()
  201 |     console.log(`Bibliography items found: ${bibCount}`)
  202 | 
  203 |     await screenshot(page, '07-bibliography')
  204 | 
  205 |     // ── 11. Full page final screenshot ────────────────────────────────────
  206 |     await page.evaluate(() => window.scrollTo(0, 0))
  207 |     await screenshot(page, '08-final-full-page')
  208 | 
  209 |     // ── 12. Scroll through the entire report ─────────────────────────────
  210 |     await page.evaluate(() => {
  211 |       const body = document.querySelector('.paper-body, .health-paper-panel')
  212 |       if (body) body.scrollTop = body.scrollHeight
  213 |     })
  214 |     await page.waitForTimeout(500)
  215 |     await screenshot(page, '09-report-bottom')
  216 | 
  217 |     // ── 13. Console error check ───────────────────────────────────────────
  218 |     // Filter out known non-critical warnings
  219 |     const criticalErrors = consoleErrors.filter(e =>
  220 |       !e.includes('favicon') &&
  221 |       !e.includes('ResizeObserver') &&
  222 |       !e.includes('[Vue Router]') &&
  223 |       !e.includes('Download the Vue Devtools')
  224 |     )
  225 |     if (criticalErrors.length > 0) {
  226 |       console.warn(`Console errors detected (${criticalErrors.length}):`)
  227 |       criticalErrors.slice(0, 5).forEach(e => console.warn(`  - ${e}`))
  228 |     } else {
  229 |       console.log('Console errors: none (passed)')
  230 |     }
  231 | 
  232 |     // ── 14. Network 500 check ─────────────────────────────────────────────
  233 |     if (responses500.length > 0) {
  234 |       console.warn(`500 responses detected (${responses500.length}):`)
  235 |       responses500.forEach(r => console.warn(`  - ${r}`))
  236 |     } else {
  237 |       console.log('500 responses: none (passed)')
  238 |     }
  239 | 
  240 |     // Soft assertions — log but don't fail on warnings
  241 |     expect(responses500.length).toBe(0)
  242 | 
  243 |     console.log('\n=== Direct navigation test COMPLETE ===')
  244 |     console.log(`Simulation ID: ${SIM_ID}`)
  245 |     console.log(`URL: ${DIRECT_URL}`)
  246 |     console.log(`Artifacts saved to: ${ARTIFACTS_DIR}`)
  247 |   })
  248 | 
  249 |   test('URL contains correct query params after load', async ({ page }) => {
  250 |     await page.goto(DIRECT_URL, { waitUntil: 'domcontentloaded' })
  251 | 
  252 |     // Wait a moment for Vue router to settle
  253 |     await page.waitForTimeout(1000)
```