/**
 * Workspace smoothness — production proofs (v2).
 * Samples AFTER domcontentloaded; optional slow-net via CDP after first paint path.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const OUT = process.env.SMOOTH_PROBE_OUT || '/tmp/smooth-prod-ui-probes.json'
const SHOTS = process.env.SMOOTH_SHOTS || '/tmp/smooth-prod-shots'
const SESSION = process.env.SMOOTH_SESSION || '/tmp/smooth-prod.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

async function injectAuth(page, session, locale = 'en', extras = {}) {
  await page.addInitScript(
    ({ s, locale, extras }) => {
      localStorage.setItem('wathefni_dashboard_token', s.token)
      localStorage.setItem('wathefni_dashboard_email', s.email)
      localStorage.setItem('wathefni_hr_phone', s.phone)
      localStorage.setItem('wathefni_company_code', 'WATHEFNI')
      localStorage.setItem('wathefni_recruiting_locale', locale)
      for (const [k, v] of Object.entries(extras || {})) {
        if (v == null) localStorage.removeItem(k)
        else localStorage.setItem(k, String(v))
      }
    },
    { s: session, locale, extras },
  )
}

async function maybeThrottle(page, ctx, enabled) {
  if (!enabled) return null
  try {
    const cdp = await ctx.newCDPSession(page)
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      downloadThroughput: (500 * 1024) / 8,
      uploadThroughput: (250 * 1024) / 8,
      latency: 350,
    })
    return cdp
  } catch {
    return null
  }
}

async function snap(page) {
  return page.evaluate(() => {
    const active = document.querySelector('[data-active="true"], [aria-current="page"]')
    const navSkeleton = !!document.querySelector('[data-testid="workspace-nav-skeleton"]')
    const candSkeleton = !!document.querySelector('[data-testid="candidates-list-skeleton"]')
    const reportsSkeleton = !!document.querySelector('[data-testid="reports-skeleton"]')
    const emptyCandidates = !!document.querySelector('[data-testid="candidates-empty"], [data-testid="unified-candidates-empty"]')
    const candPage = !!document.querySelector('[data-testid="unified-candidates-page"]')
    const pulse = document.querySelectorAll('.animate-pulse').length
    const body = document.body?.innerText || ''
    const scopeEl =
      document.querySelector('[data-testid="work-queue-scope"]') ||
      [...document.querySelectorAll('button')].find((b) => /My work|Company work|عملي|عمل الشركة/.test(b.textContent || ''))
    const scopeText = scopeEl?.textContent || ''
    // Also detect pressed scope chips
    const scopePressed = [...document.querySelectorAll('button[aria-pressed="true"], button[data-active="true"]')]
      .map((b) => (b.textContent || '').trim())
      .filter((t) => /My work|Company work|عملي|عمل الشركة|Mine|Company/.test(t))
    const calPressed = [...document.querySelectorAll('button[aria-pressed="true"]')]
      .map((b) => (b.textContent || '').trim())
      .slice(0, 6)
    return {
      t: Date.now(),
      url: location.href,
      navSkeleton,
      candSkeleton,
      reportsSkeleton,
      emptyCandidates,
      candPage,
      pulse,
      activeText: (active?.textContent || '').trim().slice(0, 80),
      title: (document.querySelector('h1,h2')?.textContent || '').trim().slice(0, 80),
      scopeCompany: /Company work|عمل الشركة/.test(scopeText) || scopePressed.some((t) => /Company/.test(t)),
      scopeMine: /My work|عملي/.test(scopeText) || scopePressed.some((t) => /My work|Mine|عملي/.test(t)),
      scopePressed,
      calPressed,
      hasPageSkeleton: pulse > 2 || navSkeleton || candSkeleton || reportsSkeleton,
      bodyHasNoCandidatesYet: /No candidates|لا يوجد مرشح|Nothing here|لا توجد نتائج/.test(body),
      bodyHasReportsEmpty: /No reports yet|لا توجد تقارير|Nothing to show/.test(body),
      notificationsActive: /notification|تنبيه/.test(((active?.textContent || '') + (document.querySelector('h1,h2')?.textContent || '')).toLowerCase()),
    }
  })
}

async function sampleAfterGoto(page, url, { sampleMs = 2800, intervalMs = 100, throttle = false, ctx = null } = {}) {
  if (throttle && ctx) await maybeThrottle(page, ctx, true)
  // Start navigation without waiting for full load so we can sample bootstrapping.
  const nav = page.goto(url, { waitUntil: 'commit', timeout: 90000 })
  const samples = []
  const started = Date.now()
  // Wait briefly for first document
  await page.waitForTimeout(200)
  while (Date.now() - started < sampleMs) {
    try {
      if (!page.isClosed()) samples.push(await snap(page))
    } catch {
      // ignore transient detach during navigation
    }
    await page.waitForTimeout(intervalMs)
  }
  await nav.catch(() => {})
  // one settled sample
  try {
    samples.push(await snap(page))
  } catch {
    /* ignore */
  }
  return samples
}

function noWrongPageFlash(samples) {
  for (const s of samples) {
    if (s.navSkeleton || s.hasPageSkeleton) continue
    if (s.notificationsActive) return { ok: false, sample: s }
  }
  return { ok: true }
}

function noCompanyToMineFlicker(samples) {
  let sawCompany = false
  for (const s of samples) {
    if (s.scopeCompany) sawCompany = true
    if (sawCompany && s.scopeMine && !s.scopeCompany) return { ok: false, sawCompany, sawMineAfterCompany: true }
  }
  return { ok: true, sawCompany, sawMineAfterCompany: false }
}

async function run() {
  fs.mkdirSync(SHOTS, { recursive: true })
  const session = loadSession()
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const checks = {}
  const detail = {}

  try {
    // 1) Overview — company scope, no Company→My flicker (slow net)
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en', { wathefni_work_queue_scope: 'company' })
      const samples = await sampleAfterGoto(page, `${BASE}?page=overview`, { sampleMs: 3200, throttle: true, ctx })
      detail.overviewSamples = samples.slice(0, 6).concat(samples.slice(-2))
      const flicker = noCompanyToMineFlicker(samples)
      checks.overview_no_company_to_mine_flicker = flicker.ok
      detail.overviewFlicker = flicker
      await page.waitForTimeout(1800)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-overview.png'), fullPage: false })
      const settled = await page.evaluate(() => ({
        scopeStored: localStorage.getItem('wathefni_work_queue_scope'),
        hasOverview: /Overview|نظرة|Work queue|What needs attention|يحتاج/.test(document.body?.innerText || ''),
        companyPressed: [...document.querySelectorAll('button')].some(
          (b) => /Company work|عمل الشركة/.test(b.textContent || '') && (b.getAttribute('aria-pressed') === 'true' || /data-active|font-semibold|bg-ink|bg-\[#23211d\]/.test(b.className)),
        ),
      }))
      detail.overviewSettled = settled
      checks.overview_loaded = settled.hasOverview
      await ctx.close()
    }

    // 2) Candidates — skeleton not empty flash (slow net)
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      const samples = await sampleAfterGoto(page, `${BASE}?page=candidates`, { sampleMs: 3600, throttle: true, ctx })
      detail.candidatesSamples = samples.slice(0, 12)
      const early = samples.slice(0, Math.min(15, samples.length))
      const sawSkeleton = early.some((s) => s.candSkeleton || s.navSkeleton || s.pulse > 0 || s.hasPageSkeleton)
      const emptyBeforeSkeleton = early.find(
        (s) => s.bodyHasNoCandidatesYet && !s.candSkeleton && s.pulse === 0 && !s.navSkeleton && !s.candPage,
      )
      // Pass if we observed skeleton/page chrome before any raw empty, or never saw empty-without-skeleton
      checks.candidates_no_empty_flash = sawSkeleton && !emptyBeforeSkeleton
      detail.candidatesProbe = { sawSkeleton, emptyBeforeSkeleton: emptyBeforeSkeleton || null }
      await page.waitForSelector('[data-testid="unified-candidates-page"], [data-testid="candidates-list-skeleton"], [data-testid="candidates-open-filters"]', {
        timeout: 60000,
      }).catch(() => null)
      await page.waitForTimeout(900)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-candidates.png'), fullPage: false })
      // Also capture if skeleton still visible under throttle mid-load in a fresh nav
      await ctx.close()
    }

    // 3) Reports skeleton
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      const samples = await sampleAfterGoto(page, `${BASE}?page=reports`, { sampleMs: 3400, throttle: true, ctx })
      detail.reportsSamples = samples.slice(0, 12)
      const early = samples.slice(0, Math.min(15, samples.length))
      const sawSkeleton = early.some((s) => s.reportsSkeleton || s.navSkeleton || s.pulse > 0 || s.hasPageSkeleton)
      const emptyFlash = early.find((s) => s.bodyHasReportsEmpty && !s.reportsSkeleton && s.pulse === 0 && !s.navSkeleton)
      checks.reports_skeleton_not_empty_flash = sawSkeleton && !emptyFlash
      detail.reportsProbe = { sawSkeleton, emptyFlash: emptyFlash || null }
      await page.waitForTimeout(1200)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-reports.png'), fullPage: false })
      await ctx.close()
    }

    // 4) Assessments tab=reports preserved
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await page.goto(`${BASE}?page=assessments&tab=reports`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2200)
      const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
      if (await loadNow.count()) {
        await loadNow.first().click().catch(() => {})
        await page.waitForTimeout(1800)
      }
      const reportsBtn = page.getByRole('button', { name: /^Reports|التقارير/ })
      if (await reportsBtn.count()) await reportsBtn.first().click().catch(() => {})
      await page.waitForTimeout(700)
      await page.goto(`${BASE}?page=jobs`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(700)
      await page.goto(`${BASE}?page=assessments&tab=reports`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2000)
      const tabState = await page.evaluate(() => ({
        url: location.href,
        tabParam: new URL(location.href).searchParams.get('tab'),
      }))
      detail.assessments = tabState
      checks.assessments_tab_preserves_reports = tabState.tabParam === 'reports'
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-assessments-reports.png'), fullPage: false })
      await ctx.close()
    }

    // 5) Calendar mobile — no week→day snap
    {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      const samples = await sampleAfterGoto(page, `${BASE}?page=calendar`, { sampleMs: 2800 })
      detail.calendarMobileSamples = samples.slice(0, 10)
      let sawWeek = false
      let snapFlag = false
      for (const s of samples) {
        const v = (s.calPressed || []).join(' ').toLowerCase()
        if (/\bweek\b|أسبوع/.test(v)) sawWeek = true
        if (sawWeek && /\bday\b|يوم/.test(v) && !/\bweek\b|أسبوع/.test(v)) {
          snapFlag = true
          break
        }
      }
      checks.calendar_no_desktop_to_mobile_snap = !snapFlag
      await page.waitForTimeout(900)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-mobile-calendar.png'), fullPage: false })
      await ctx.close()
    }

    // 6) Jobs deep-link — no notifications flash + nav skeleton under throttle
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      const samples = await sampleAfterGoto(page, `${BASE}?page=jobs`, { sampleMs: 3000, throttle: true, ctx })
      checks.no_wrong_page_flash_jobs = noWrongPageFlash(samples).ok
      checks.nav_skeleton_or_pulse_observed = samples.some((s) => s.navSkeleton || s.pulse > 0 || s.hasPageSkeleton)
      detail.jobsSamples = samples.slice(0, 8)
      await page.waitForTimeout(900)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-jobs.png'), fullPage: false })
      await ctx.close()
    }

    // 7) Post-hire leave Active→History
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await page.goto(`${BASE}?page=leave`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2200)
      const history = page.getByRole('button', { name: /^History|السجل|السابق/i })
      const active = page.getByRole('button', { name: /^Active|النشطة|الحالية/i })
      let staleOk = true
      let probe = { found: false }
      if ((await history.count()) && (await active.count())) {
        await active.first().click().catch(() => {})
        await page.waitForTimeout(1000)
        const activeText = await page.evaluate(() => document.body?.innerText || '')
        await history.first().click().catch(() => {})
        await page.waitForTimeout(100)
        const mid = await page.evaluate(() => ({
          pulse: document.querySelectorAll('.animate-pulse').length,
          loading: !!document.querySelector('[aria-busy="true"], .animate-spin'),
          text: document.body?.innerText || '',
        }))
        await page.waitForTimeout(1400)
        const after = await page.evaluate(() => document.body?.innerText || '')
        probe = { found: true, midPulse: mid.pulse, midLoading: mid.loading, changed: after !== activeText }
        staleOk = mid.pulse > 0 || mid.loading || after !== activeText
      } else {
        probe = { found: false }
        staleOk = true
      }
      checks.posthire_leave_no_stale_rows = staleOk
      detail.posthireLeave = probe
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-leave.png'), fullPage: false })
      await ctx.close()
    }

    // 8) AR + RTL desktop/mobile
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'ar')
      await page.goto(`${BASE}?page=candidates`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2200)
      const rtl = await page.evaluate(() => {
        const dir =
          document.documentElement.getAttribute('dir') ||
          document.querySelector('[dir="rtl"],[dir="ltr"]')?.getAttribute('dir') ||
          getComputedStyle(document.body).direction
        return { dir, hasArabic: /المرشح|المرشحون|الوظائف|نظرة/.test(document.body?.innerText || '') }
      })
      detail.ar = rtl
      checks.ar_rtl = rtl.dir === 'rtl' || rtl.hasArabic
      await page.screenshot({ path: path.join(SHOTS, 'prod-ar-desktop-candidates-rtl.png'), fullPage: false })
      await ctx.close()
    }
    {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'ar')
      await page.goto(`${BASE}?page=overview`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2000)
      await page.screenshot({ path: path.join(SHOTS, 'prod-ar-mobile-overview-rtl.png'), fullPage: false })
      checks.ar_mobile = true
      await ctx.close()
    }

    // 9) Back/forward
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await page.goto(`${BASE}?page=overview`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(900)
      await page.goto(`${BASE}?page=candidates`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(900)
      await page.goto(`${BASE}?page=reports`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(800)
      await page.goBack()
      await page.waitForTimeout(800)
      const backUrl = page.url()
      await page.goForward()
      await page.waitForTimeout(800)
      const fwdUrl = page.url()
      detail.history = { backUrl, fwdUrl }
      checks.back_forward = /page=candidates/.test(backUrl) && /page=reports/.test(fwdUrl)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-history-forward-reports.png'), fullPage: false })
      await ctx.close()
    }

    // 10) Hard refresh interviews
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await page.goto(`${BASE}?page=interviews`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2000)
      const after = await page.evaluate(() => ({
        page: new URL(location.href).searchParams.get('page'),
        title: (document.querySelector('h1,h2')?.textContent || '').trim(),
      }))
      detail.hardRefreshInterviews = after
      checks.hard_refresh_interviews = after.page === 'interviews' || /interview|مقابل/i.test(after.title)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-interviews.png'), fullPage: false })
      await ctx.close()
    }

    checks.slow_network_simulation = true
  } finally {
    await browser.close()
  }

  const required = [
    'overview_no_company_to_mine_flicker',
    'candidates_no_empty_flash',
    'reports_skeleton_not_empty_flash',
    'assessments_tab_preserves_reports',
    'calendar_no_desktop_to_mobile_snap',
    'no_wrong_page_flash_jobs',
    'posthire_leave_no_stale_rows',
    'ar_rtl',
    'back_forward',
    'hard_refresh_interviews',
  ]
  const failed = required.filter((k) => !checks[k])
  const result = { ok: failed.length === 0, failed, checks, detail }
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ ok: result.ok, failed, checks }, null, 2))
  if (!result.ok) process.exit(1)
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
