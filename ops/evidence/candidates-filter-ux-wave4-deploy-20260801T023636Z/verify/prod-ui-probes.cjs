/**
 * Wave 4 production proofs — Candidates filter UX.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const API = process.env.DASHBOARD_API || 'https://api.wathefni.ai'
const OUT = process.env.W4_PROBE_OUT || '/tmp/w4-prod-ui-probes.json'
const SHOTS = process.env.W4_SHOTS || '/tmp/w4-prod-shots'
const SESSION = process.env.W4_SESSION || '/tmp/w2-prod.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

function authHeaders(session) {
  return {
    Authorization: `Bearer ${session.token}`,
    'X-Company-Code': 'WATHEFNI',
    'X-HR-Phone': session.phone,
    'Content-Type': 'application/json',
  }
}

async function apiJson(session, pathName, opts = {}) {
  const res = await fetch(`${API}${pathName}`, {
    ...opts,
    headers: { ...authHeaders(session), ...(opts.headers || {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`${pathName} ${res.status} ${JSON.stringify(body)}`)
  return body
}

async function injectAuth(page, session) {
  await page.addInitScript((s) => {
    localStorage.setItem('wathefni_dashboard_token', s.token)
    localStorage.setItem('wathefni_dashboard_email', s.email)
    localStorage.setItem('wathefni_hr_phone', s.phone)
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    if (!localStorage.getItem('wathefni_recruiting_locale')) {
      localStorage.setItem('wathefni_recruiting_locale', 'en')
    }
  }, session)
}

async function waitCandidates(page) {
  await page.waitForSelector('[data-testid="unified-candidates-page"]', { timeout: 45000 })
}

function urlParams(url) {
  return new URL(url).searchParams
}

async function openFilters(page) {
  await page.getByTestId('candidates-open-filters').click()
  await page.waitForSelector('[data-testid="candidates-filter-overlay"]', { timeout: 10000 })
}

async function run() {
  fs.mkdirSync(SHOTS, { recursive: true })
  const session = loadSession()
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const checks = {}
  const detail = {}
  let viewId = null

  try {
    // Temp saved view for saved-views proof
    const created = await apiJson(session, '/dashboard/prehire/candidates/saved-views', {
      method: 'POST',
      body: JSON.stringify({
        name: `W4 UX probe ${Date.now()}`,
        filters: {
          query: '',
          status: 'new',
          position: 'ACCOUNTING_EXCEL',
          view: 'talent_pool',
          sort: 'newest',
          followUp: '',
          overviewCohort: '',
          cohortKey: '',
          action: '',
          assessmentStatus: '',
        },
      }),
    })
    viewId = created?.view?.view_id || null
    detail.created_view_id = viewId
    if (!viewId) throw new Error(`saved view create failed: ${JSON.stringify(created)}`)

    // Desktop context
    const desktop = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await desktop.newPage()
    await injectAuth(page, session)

    const shared =
      `${BASE}?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&action=follow_up_failed_delivery&position=ACCOUNTING_EXCEL&assessment_status=completed&source_channel=email`
    await page.goto(shared, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(1200)

    // Live chunk
    const liveChunk = await page.evaluate(() =>
      [...document.scripts].map((s) => s.src).find((s) => s.includes('dashboard-')) || null,
    )
    checks.live_chunk_wave4 = !!(liveChunk && liveChunk.includes('dashboard-Bt0QpWcY'))
    detail.live_chunk = liveChunk

    // Active count + chips
    const filtersBtn = page.getByTestId('candidates-open-filters')
    const filtersBtnText = (await filtersBtn.innerText()).trim()
    checks.active_count_filters_3 = /Filters \(3\)|مرشحات \(3\)/.test(filtersBtnText)
    detail.filters_btn_text = filtersBtnText
    checks.follow_up_chip_visible = (await page.getByTestId('candidate-filter-chip-followUp').count()) === 1
    checks.assessment_chip_visible = (await page.getByTestId('candidate-filter-chip-assessmentStatus').count()) === 1
    checks.source_chip_visible = (await page.getByTestId('candidate-filter-chip-sourceChannel').count()) === 1
    checks.clear_all_chips_visible = (await page.getByTestId('candidates-clear-all-chips').count()) === 1
    await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-chips.png'), fullPage: true })

    // Desktop drawer
    await openFilters(page)
    const overlayBox = await page.getByTestId('candidates-filter-panel').boundingBox()
    checks.desktop_drawer_open = !!(await page.getByTestId('candidates-filter-overlay').count())
    checks.desktop_drawer_narrower_than_viewport = !!overlayBox && overlayBox.width < 700
    detail.desktop_panel_box = overlayBox
    await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-drawer.png'), fullPage: true })

    // Close preserves chips/state
    await page.getByRole('button', { name: /Close|إغلاق|Done|تم/i }).first().click()
    await page.waitForTimeout(400)
    checks.close_preserves_follow_up_chip = (await page.getByTestId('candidate-filter-chip-followUp').count()) === 1
    checks.close_preserves_url_follow_up = urlParams(page.url()).get('follow_up') === 'needed'
    checks.close_overlay_gone = (await page.getByTestId('candidates-filter-overlay').count()) === 0

    // Chip removes only its own filter/context (assessment), keeps follow-up
    await page.getByTestId('candidate-filter-chip-assessmentStatus').click()
    await page.waitForTimeout(900)
    let params = urlParams(page.url())
    checks.chip_removed_assessment = !params.get('assessment_status')
    checks.chip_kept_follow_up = params.get('follow_up') === 'needed'
    checks.chip_kept_source = params.get('source_channel') === 'email'
    checks.chip_kept_position = params.get('position') === 'ACCOUNTING_EXCEL'
    detail.after_assessment_chip_remove = page.url()

    // Follow-up chip clears quartet only (not source/position)
    await page.getByTestId('candidate-filter-chip-followUp').click()
    await page.waitForTimeout(900)
    params = urlParams(page.url())
    checks.follow_up_chip_clears_follow_up = !params.get('follow_up')
    checks.follow_up_chip_clears_overview = !params.get('overview_cohort')
    checks.follow_up_chip_clears_cohort_key = !params.get('cohort_key')
    checks.follow_up_chip_clears_action = !params.get('action')
    checks.follow_up_chip_keeps_source = params.get('source_channel') === 'email'
    checks.follow_up_chip_keeps_position = params.get('position') === 'ACCOUNTING_EXCEL'
    detail.after_follow_up_chip_remove = page.url()

    // Restore multi-filter URL then Clear all
    await page.goto(shared, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(900)
    await page.getByTestId('candidates-clear-all-chips').click()
    await page.waitForTimeout(900)
    params = urlParams(page.url())
    checks.clear_all_drops_follow_up = !params.get('follow_up')
    checks.clear_all_drops_overview = !params.get('overview_cohort')
    checks.clear_all_drops_assessment = !params.get('assessment_status')
    checks.clear_all_drops_source = !params.get('source_channel')
    checks.clear_all_keeps_position = params.get('position') === 'ACCOUNTING_EXCEL'
    detail.after_clear_all = page.url()

    // Reload preserves remaining filters
    await page.reload({ waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(900)
    params = urlParams(page.url())
    checks.reload_keeps_position = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.reload_no_follow_up = !params.get('follow_up')
    detail.after_reload = page.url()

    // Back/forward
    await page.goto(shared, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(700)
    const alt = `${BASE}?page=candidates&position=ACCOUNTING_EXCEL&source_channel=email`
    await page.evaluate((u) => {
      window.history.pushState({ page: 'candidates' }, '', u)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, alt)
    await page.waitForTimeout(1000)
    await waitCandidates(page)
    params = urlParams(page.url())
    checks.history_mid_no_follow_up = !params.get('follow_up') && params.get('source_channel') === 'email'
    await page.goBack()
    await page.waitForTimeout(1100)
    await waitCandidates(page)
    params = urlParams(page.url())
    checks.back_restores_follow_up = params.get('follow_up') === 'needed'
    checks.back_restores_cohort = params.get('overview_cohort') === 'follow_up_needed'
    detail.after_back = page.url()
    await page.goForward()
    await page.waitForTimeout(1100)
    await waitCandidates(page)
    params = urlParams(page.url())
    checks.forward_clears_follow_up = !params.get('follow_up')
    checks.forward_keeps_source = params.get('source_channel') === 'email'
    detail.after_forward = page.url()

    // Saved views replace stale cohort
    await page.goto(
      `${BASE}?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&action=follow_up_failed_delivery`,
      { waitUntil: 'domcontentloaded' },
    )
    await waitCandidates(page)
    await page.waitForTimeout(900)
    await page.getByRole('button', { name: /Saved views|العروض المحفوظة|Save this view|حفظ هذا العرض/i }).first().click()
    await page.waitForTimeout(300)
    await page.locator('[data-testid="candidates-save-view-panel"] button').filter({ hasText: /W4 UX probe/ }).first().click()
    await page.waitForTimeout(1200)
    params = urlParams(page.url())
    checks.saved_view_clears_follow_up = !params.get('follow_up')
    checks.saved_view_clears_cohort = !params.get('overview_cohort') && !params.get('cohort_key') && !params.get('action')
    checks.saved_view_applies_position = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.saved_view_applies_status = params.get('status') === 'new'
    detail.after_saved_view = page.url()

    // EN/AR + RTL
    await page.goto(`${BASE}?page=candidates&follow_up=needed&source_channel=email`, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    const langBtn = page.getByRole('button', { name: /Language|اللغة|English|العربية/i }).first()
    const enDir = await page.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    checks.en_ltr = enDir === 'ltr'
    await langBtn.click()
    await page.waitForTimeout(700)
    const arDir = await page.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    const rootAr = await page.evaluate(() => {
      const el = document.querySelector('[dir="rtl"]')
      return el ? { tag: el.tagName, dir: el.getAttribute('dir') } : null
    })
    checks.ar_rtl = arDir === 'rtl' || Boolean(rootAr)
    checks.ar_follow_up_chip = (await page.getByTestId('candidate-filter-chip-followUp').count()) === 1
    checks.ar_clear_all = (await page.getByTestId('candidates-clear-all-chips').count()) === 1
    detail.en_dir = enDir
    detail.ar_dir = arDir
    detail.root_ar = rootAr
    await page.screenshot({ path: path.join(SHOTS, 'prod-ar-desktop-chips-rtl.png'), fullPage: true })

    // Drawer Clear all in AR
    await openFilters(page)
    await page.getByTestId('candidates-clear-all-filters').click()
    await page.waitForTimeout(800)
    params = urlParams(page.url())
    checks.drawer_clear_all_drops_follow_up = !params.get('follow_up')
    checks.drawer_clear_all_drops_source = !params.get('source_channel')
    await page.getByRole('button', { name: /Close|إغلاق|Done|تم/i }).first().click().catch(() => {})
    await desktop.close()

    // Mobile sheet
    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const mpage = await mobile.newPage()
    await injectAuth(mpage, session)
    await mpage.goto(
      `${BASE}?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&assessment_status=completed`,
      { waitUntil: 'domcontentloaded' },
    )
    await waitCandidates(mpage)
    await mpage.waitForTimeout(1000)
    await openFilters(mpage)
    const mbox = await mpage.getByTestId('candidates-filter-panel').boundingBox()
    checks.mobile_sheet_open = !!(await mpage.getByTestId('candidates-filter-overlay').count())
    checks.mobile_sheet_full_width = !!mbox && mbox.width >= 360
    detail.mobile_panel_box = mbox
    await mpage.screenshot({ path: path.join(SHOTS, 'prod-en-mobile-sheet.png'), fullPage: true })

    // Close sheet before locale toggle (overlay intercepts clicks)
    await mpage.getByRole('button', { name: /Close|إغلاق|Done|تم/i }).first().click()
    await mpage.waitForTimeout(400)
    const langBtnM = mpage.getByRole('button', { name: /Language|اللغة|English|العربية/i }).first()
    await langBtnM.click()
    await mpage.waitForTimeout(700)
    await openFilters(mpage)
    const arMobileDir = await mpage.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    checks.ar_mobile_rtl = arMobileDir === 'rtl' || !!(await mpage.locator('[dir="rtl"]').count())
    await mpage.screenshot({ path: path.join(SHOTS, 'prod-ar-mobile-sheet-rtl.png'), fullPage: true })
    await mobile.close()
  } finally {
    if (viewId) {
      try {
        await apiJson(session, `/dashboard/prehire/candidates/saved-views/${encodeURIComponent(viewId)}`, {
          method: 'DELETE',
        })
        detail.deleted_view_id = viewId
      } catch (e) {
        detail.delete_view_error = String(e)
      }
    }
    await browser.close().catch(() => {})
  }

  const required = [
    'live_chunk_wave4',
    'active_count_filters_3',
    'follow_up_chip_visible',
    'assessment_chip_visible',
    'source_chip_visible',
    'clear_all_chips_visible',
    'desktop_drawer_open',
    'desktop_drawer_narrower_than_viewport',
    'close_preserves_follow_up_chip',
    'close_preserves_url_follow_up',
    'close_overlay_gone',
    'chip_removed_assessment',
    'chip_kept_follow_up',
    'chip_kept_source',
    'chip_kept_position',
    'follow_up_chip_clears_follow_up',
    'follow_up_chip_clears_overview',
    'follow_up_chip_clears_cohort_key',
    'follow_up_chip_clears_action',
    'follow_up_chip_keeps_source',
    'follow_up_chip_keeps_position',
    'clear_all_drops_follow_up',
    'clear_all_drops_overview',
    'clear_all_drops_assessment',
    'clear_all_drops_source',
    'clear_all_keeps_position',
    'reload_keeps_position',
    'reload_no_follow_up',
    'history_mid_no_follow_up',
    'back_restores_follow_up',
    'back_restores_cohort',
    'forward_clears_follow_up',
    'forward_keeps_source',
    'saved_view_clears_follow_up',
    'saved_view_clears_cohort',
    'saved_view_applies_position',
    'saved_view_applies_status',
    'en_ltr',
    'ar_rtl',
    'ar_follow_up_chip',
    'ar_clear_all',
    'drawer_clear_all_drops_follow_up',
    'drawer_clear_all_drops_source',
    'mobile_sheet_open',
    'mobile_sheet_full_width',
    'ar_mobile_rtl',
  ]
  const failed = required.filter((k) => !checks[k])
  const verdict = failed.length === 0 ? 'PASS' : 'FAIL'
  const result = { verdict, failed, checks, detail, shots: fs.readdirSync(SHOTS) }
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ verdict, failed, checks }, null, 2))
  process.exit(verdict === 'PASS' ? 0 : 1)
}

run().catch((err) => {
  console.error(err)
  fs.writeFileSync(OUT, JSON.stringify({ verdict: 'FAIL', error: String(err) }, null, 2))
  process.exit(1)
})
