/**
 * Wave 3 production proofs — Candidates URL / filter-state authority.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const API = process.env.DASHBOARD_API || 'https://api.wathefni.ai'
const OUT = process.env.W3_PROBE_OUT || '/tmp/w3-prod-ui-probes.json'
const SESSION = process.env.W3_SESSION || '/tmp/w2-prod.session'
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

async function apiJson(session, path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { ...authHeaders(session), ...(opts.headers || {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`${path} ${res.status} ${JSON.stringify(body)}`)
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

async function setLocale(page, locale) {
  await page.evaluate((loc) => localStorage.setItem('wathefni_recruiting_locale', loc), locale)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await waitCandidates(page)
}

async function openFilters(page) {
  const panel = page.locator('button', { hasText: /Clear advanced filters|مسح المرشحات المتقدمة/ })
  if (await panel.count()) return
  const btn = page.getByRole('button', { name: /Filters|مرشحات/i }).first()
  await btn.click()
  await page.waitForTimeout(350)
}

async function clearFollowUpSelect(page) {
  const followSelect = page.locator('select').filter({ has: page.locator('option[value="needed"]') }).first()
  await followSelect.selectOption('')
  await page.waitForTimeout(900)
}

async function run() {
  const session = loadSession()
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const page = await (await browser.newContext()).newPage()
  await injectAuth(page, session)

  const checks = {}
  const detail = {}
  let viewId = null

  try {
    // Create a temp saved view without follow-up/cohort (position + status only)
    const created = await apiJson(session, '/dashboard/prehire/candidates/saved-views', {
      method: 'POST',
      body: JSON.stringify({
        name: `W3 URL probe ${Date.now()}`,
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
        },
      }),
    })
    viewId = created?.view?.view_id || created?.view_id || null
    detail.created_view_id = viewId
    if (!viewId) throw new Error(`saved view create missing id: ${JSON.stringify(created)}`)

    // 1) Shared URL reproduces durable keys
    const shared =
      `${BASE}?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&action=follow_up_failed_delivery&position=ACCOUNTING_EXCEL&status=new&view=talent_pool&assessment_status=completed`
    await page.goto(shared, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(1200)
    let params = urlParams(page.url())
    checks.shared_url_follow_up = params.get('follow_up') === 'needed'
    checks.shared_url_overview_cohort = params.get('overview_cohort') === 'follow_up_needed'
    checks.shared_url_cohort_key = params.get('cohort_key') === 'follow_up_needed'
    checks.shared_url_action = params.get('action') === 'follow_up_failed_delivery'
    checks.shared_url_position = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.shared_url_status = params.get('status') === 'new'
    checks.shared_url_view = params.get('view') === 'talent_pool'
    checks.shared_url_assessment = params.get('assessment_status') === 'completed'
    detail.shared_url = page.url()

    // 2) Clear Follow-up needed — drop quartet; keep unrelated
    await openFilters(page)
    await clearFollowUpSelect(page)
    params = urlParams(page.url())
    checks.clear_follow_up_gone = !params.get('follow_up')
    checks.clear_overview_cohort_gone = !params.get('overview_cohort')
    checks.clear_cohort_key_gone = !params.get('cohort_key')
    checks.clear_action_gone = !params.get('action')
    checks.unrelated_position_intact = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.unrelated_status_intact = params.get('status') === 'new'
    checks.unrelated_view_intact = params.get('view') === 'talent_pool'
    checks.unrelated_assessment_intact = params.get('assessment_status') === 'completed'
    detail.after_clear_follow_up = page.url()

    // 3) Reload preserves active filters
    await page.reload({ waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(1000)
    params = urlParams(page.url())
    checks.reload_no_follow_up =
      !params.get('follow_up') && !params.get('overview_cohort') && !params.get('cohort_key') && !params.get('action')
    checks.reload_keeps_position = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.reload_keeps_status = params.get('status') === 'new'
    checks.reload_keeps_view = params.get('view') === 'talent_pool'
    checks.reload_keeps_assessment = params.get('assessment_status') === 'completed'
    detail.after_reload = page.url()

    // 4) Back/forward restores filters via real history + popstate
    await page.goto(shared, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    await page.waitForTimeout(800)
    // Navigate to a different durable URL (push) then back
    const alt =
      `${BASE}?page=candidates&position=ACCOUNTING_EXCEL&status=new&view=talent_pool&assessment_status=completed`
    await page.evaluate((u) => {
      window.history.pushState({ page: 'candidates' }, '', u)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, alt)
    await page.waitForTimeout(1000)
    await waitCandidates(page)
    params = urlParams(page.url())
    const midOk =
      !params.get('follow_up') &&
      params.get('position') === 'ACCOUNTING_EXCEL' &&
      params.get('status') === 'new'
    detail.after_push_alt = page.url()
    checks.history_mid_cleared = midOk
    await page.goBack()
    await page.waitForTimeout(1100)
    await waitCandidates(page)
    params = urlParams(page.url())
    checks.back_restores_follow_up = params.get('follow_up') === 'needed'
    checks.back_restores_cohort =
      params.get('overview_cohort') === 'follow_up_needed' && params.get('cohort_key') === 'follow_up_needed'
    checks.back_restores_action = params.get('action') === 'follow_up_failed_delivery'
    detail.after_back = page.url()
    await page.goForward()
    await page.waitForTimeout(1100)
    await waitCandidates(page)
    params = urlParams(page.url())
    checks.forward_clears_follow_up = !params.get('follow_up') && !params.get('overview_cohort')
    checks.forward_keeps_unrelated =
      params.get('position') === 'ACCOUNTING_EXCEL' && params.get('status') === 'new'
    detail.after_forward = page.url()

    // 5) Saved-view selection replaces stale cohort state
    await page.goto(
      `${BASE}?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&action=follow_up_failed_delivery&q=stale`,
      { waitUntil: 'domcontentloaded' },
    )
    await waitCandidates(page)
    await page.waitForTimeout(1000)
    // Open saved views panel
    const savedToggle = page.getByRole('button', { name: /Saved views|العروض المحفوظة|Save this view|حفظ هذا العرض/i }).first()
    await savedToggle.click()
    await page.waitForTimeout(400)
    // Click the named view (not Save)
    const viewBtn = page.locator('[data-testid="candidates-save-view-panel"] button').filter({ hasText: /W3 URL probe/ }).first()
    await viewBtn.click()
    await page.waitForTimeout(1200)
    params = urlParams(page.url())
    checks.saved_view_clears_follow_up = !params.get('follow_up')
    checks.saved_view_clears_overview_cohort = !params.get('overview_cohort')
    checks.saved_view_clears_cohort_key = !params.get('cohort_key')
    checks.saved_view_clears_action = !params.get('action')
    checks.saved_view_applies_position = params.get('position') === 'ACCOUNTING_EXCEL'
    checks.saved_view_applies_status = params.get('status') === 'new'
    checks.saved_view_applies_view = params.get('view') === 'talent_pool'
    detail.after_saved_view = page.url()

    // 6) EN/AR — toggle via Language button (addInitScript must not force locale)
    await page.goto(`${BASE}?page=candidates&follow_up=needed`, { waitUntil: 'domcontentloaded' })
    await waitCandidates(page)
    // Ensure EN first
    const langBtn = page.getByRole('button', { name: /Language|اللغة|English|العربية/i }).first()
    const enDirBefore = await page.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    if (enDirBefore !== 'ltr') {
      await langBtn.click()
      await page.waitForTimeout(500)
    }
    const enDir = await page.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    const rootEn = await page.locator('[dir]').first().getAttribute('dir')
    checks.en_ltr = enDir === 'ltr' || rootEn === 'ltr'
    await openFilters(page)
    checks.en_follow_up_control = (await page.locator('option[value="needed"]').count()) > 0
    detail.en_dir = enDir
    detail.root_en_dir = rootEn

    await langBtn.click()
    await page.waitForTimeout(700)
    const arDir = await page.locator('[data-testid="unified-candidates-page"]').getAttribute('dir')
    const rootAr = await page.evaluate(() => {
      const el = document.querySelector('[dir="rtl"]')
      return el ? { tag: el.tagName, dir: el.getAttribute('dir') } : null
    })
    checks.ar_rtl = arDir === 'rtl' || Boolean(rootAr)
    // Force filters panel open after locale swap
    const clearBtn = page.getByRole('button', { name: /Clear advanced filters|مسح المرشحات المتقدمة/i })
    if (!(await clearBtn.count())) {
      await page.getByRole('button', { name: /Filters|مرشحات/i }).first().click()
      await page.waitForTimeout(400)
    }
    const neededOpt = page.locator('option[value="needed"]')
    const neededLabel = page.locator('option', { hasText: /Follow-up needed|يحتاج متابعة/ })
    checks.ar_follow_up_control = (await neededOpt.count()) > 0 || (await neededLabel.count()) > 0
    checks.ar_labels = (await page.getByText(/مرشحات|مسح المرشحات|أي متابعة|يحتاج متابعة/).count()) > 0
    detail.ar_dir = arDir
    detail.root_ar = rootAr
    detail.ar_needed_opt = await neededOpt.count()
    detail.ar_labels = checks.ar_labels
    detail.ar_clear_visible = (await clearBtn.count()) > 0

    const liveChunk = await page.evaluate(() => {
      return [...document.scripts].map((s) => s.src).find((s) => s.includes('dashboard-')) || null
    })
    checks.live_chunk_wave3 = !!(liveChunk && liveChunk.includes('dashboard-B_fWNxcn'))
    detail.live_chunk = liveChunk
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
    'shared_url_follow_up',
    'shared_url_overview_cohort',
    'shared_url_cohort_key',
    'shared_url_action',
    'shared_url_position',
    'shared_url_status',
    'shared_url_view',
    'shared_url_assessment',
    'clear_follow_up_gone',
    'clear_overview_cohort_gone',
    'clear_cohort_key_gone',
    'clear_action_gone',
    'unrelated_position_intact',
    'unrelated_status_intact',
    'unrelated_view_intact',
    'unrelated_assessment_intact',
    'reload_no_follow_up',
    'reload_keeps_position',
    'reload_keeps_status',
    'reload_keeps_view',
    'reload_keeps_assessment',
    'history_mid_cleared',
    'back_restores_follow_up',
    'back_restores_cohort',
    'back_restores_action',
    'forward_clears_follow_up',
    'forward_keeps_unrelated',
    'saved_view_clears_follow_up',
    'saved_view_clears_overview_cohort',
    'saved_view_clears_cohort_key',
    'saved_view_clears_action',
    'saved_view_applies_position',
    'saved_view_applies_status',
    'saved_view_applies_view',
    'en_ltr',
    'en_follow_up_control',
    'ar_rtl',
    'ar_follow_up_control',
    'ar_labels',
    'live_chunk_wave3',
  ]
  const failed = required.filter((k) => !checks[k])
  const verdict = failed.length === 0 ? 'PASS' : 'FAIL'
  const result = { verdict, failed, checks, detail }
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ verdict, failed, checks }, null, 2))
  process.exit(verdict === 'PASS' ? 0 : 1)
}

run().catch((err) => {
  console.error(err)
  fs.writeFileSync(OUT, JSON.stringify({ verdict: 'FAIL', error: String(err) }, null, 2))
  process.exit(1)
})
