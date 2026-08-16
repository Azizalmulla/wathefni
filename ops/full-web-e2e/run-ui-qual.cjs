/**
 * Wathefni Full Web E2E — production UI qualification (read-only).
 * Covers pre-hire + post-hire routes × EN/AR × desktop/mobile.
 *
 * Env:
 *   FULL_WEB_E2E_EVID   evidence root (required)
 *   FULL_WEB_E2E_SESSION session file: token\\nemail\\nphone (required)
 *   DASHBOARD_BASE      default https://api.wathefni.ai/dashboard/
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const EVID = process.env.FULL_WEB_E2E_EVID
const SESSION = process.env.FULL_WEB_E2E_SESSION || '/tmp/full-web-e2e.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

/** Route id → expected title/active heuristics (EN). */
const PAGES = [
  { id: 'overview', module: 'overview' },
  { id: 'jobs', module: 'jobs' },
  { id: 'candidates', module: 'candidates' },
  { id: 'interviews', module: 'interviews' },
  { id: 'assessments', module: 'assessments' },
  { id: 'ranking', module: 'ranking' },
  { id: 'calendar', module: 'calendar' },
  { id: 'employees', module: 'employees' },
  { id: 'workforce', module: 'organization' },
  { id: 'inbox', module: 'needs_attention' },
  { id: 'onboarding', module: 'onboarding' },
  { id: 'attendance', module: 'attendance' },
  { id: 'leave', module: 'leave' },
  { id: 'shifts', module: 'shifts' },
  { id: 'payroll', module: 'payroll' },
  { id: 'analytics', module: 'analytics' },
  { id: 'compliance', module: 'compliance' },
  { id: 'notifications', module: 'alerts_delivery' },
  { id: 'activity', module: 'activity' },
  { id: 'settings', module: 'settings' },
]

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  if (!lines[0]) throw new Error(`empty session token in ${SESSION}`)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

function logFail(id, module, title, severity, detail) {
  const row = { id, module, title, result: 'FAIL', severity, detail, ts: new Date().toISOString() }
  fs.mkdirSync(path.join(EVID, 'failures'), { recursive: true })
  fs.writeFileSync(path.join(EVID, 'failures', `${id}.json`), JSON.stringify(row, null, 2) + '\n')
  return row
}

async function inject(page, session, locale) {
  await page.addInitScript(
    ({ s, locale }) => {
      localStorage.setItem('wathefni_dashboard_token', s.token)
      localStorage.setItem('wathefni_dashboard_email', s.email)
      localStorage.setItem('wathefni_hr_phone', s.phone)
      localStorage.setItem('wathefni_company_code', 'WATHEFNI')
      localStorage.setItem('wathefni_recruiting_locale', locale)
    },
    { s: session, locale },
  )
}

async function openPage(page, pageId) {
  await page.goto(`${BASE}?page=${pageId}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForTimeout(2400)
  const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if (await loadNow.count()) {
    await loadNow.first().click().catch(() => {})
    await page.waitForTimeout(1800)
  }
}

async function probe(page, pageId) {
  return page.evaluate((id) => {
    const body = document.body?.innerText || ''
    const dir =
      document.documentElement.getAttribute('dir') ||
      document.querySelector('[dir="rtl"],[dir="ltr"]')?.getAttribute('dir') ||
      getComputedStyle(document.body).direction
    const title = (document.querySelector('h1,h2')?.textContent || '').trim()
    const urlPage = new URL(location.href).searchParams.get('page')
    const active = (document.querySelector('[aria-current="page"],[data-active="true"]')?.textContent || '').trim()
    const loginWall =
      /Access verification required|Unauthorized|Forbidden/i.test(body) && body.length < 1800
    const fatal =
      loginWall ||
      (/Something interrupted the dashboard|Something went wrong/i.test(body) &&
        body.length < 900 &&
        !/Retry|حاول/i.test(body))
    // Soft empty / permission walls are OK if shell rendered
    const shell = !!document.querySelector('[data-testid="app-main"], main, aside')
    return {
      id,
      urlPage,
      title,
      active,
      dir,
      bodyLen: body.length,
      fatal,
      loginWall,
      shell,
      hasContent: body.length > 60,
    }
  }, pageId)
}

async function runViewport(browser, session, { locale, width, height, isMobile, shotDir, prefix }) {
  fs.mkdirSync(shotDir, { recursive: true })
  const ctx = await browser.newContext({
    viewport: { width, height },
    isMobile: !!isMobile,
    hasTouch: !!isMobile,
  })
  const page = await ctx.newPage()
  await inject(page, session, locale)
  const results = []

  for (const route of PAGES) {
    const gateId = `UI_${prefix}_${route.id}`
    try {
      await openPage(page, route.id)
      const snap = await probe(page, route.id)
      const shot = path.join(shotDir, `${prefix}-${route.id}.png`)
      await page.screenshot({ path: shot, fullPage: false })
      const pageOk =
        snap.urlPage === route.id ||
        new RegExp(route.id, 'i').test(`${snap.title} ${snap.active}`) ||
        (route.id === 'workforce' && /organization|workforce|تنظيم|القوى/i.test(`${snap.title} ${snap.active}`)) ||
        (route.id === 'inbox' && /attention|inbox|يحتاج|الانتباه/i.test(`${snap.title} ${snap.active}`)) ||
        (route.id === 'notifications' && /alert|delivery|إشعار|تنبيه/i.test(`${snap.title} ${snap.active}`))
      const ok = snap.shell && snap.hasContent && !snap.fatal && !snap.loginWall && pageOk
      const row = {
        id: gateId,
        module: route.module,
        title: `UI ${prefix} ${route.id}`,
        result: ok ? 'PASS' : 'FAIL',
        severity: ok ? null : 'P1',
        detail: { ...snap, shot },
      }
      if (!ok) logFail(gateId, row.module, row.title, 'P1', row.detail)
      results.push(row)
      console.log(`${row.result} ${gateId}`)
    } catch (err) {
      const row = logFail(gateId, route.module, `UI ${prefix} ${route.id}`, 'P1', { error: String(err) })
      results.push({ ...row, result: 'FAIL' })
      console.log(`FAIL ${gateId}`)
    }
  }

  // Deep-link spot checks (desktop EN only)
  if (prefix === 'en-desktop') {
    const deepLinks = [
      { id: 'UI_deeplink_employee', url: '?page=employees&employee=WATHEFNI-96550252254', expectPage: 'employees', expectText: /Talal|Back to directory|العودة|employee-profile|Employee/i },
      { id: 'UI_deeplink_calendar', url: '?page=calendar', expectPage: 'calendar', expectText: /Calendar|تقويم/i },
      { id: 'UI_deeplink_onboarding', url: '?page=onboarding', expectPage: 'onboarding', expectText: /Onboarding|تهيئة/i },
    ]
    for (const dl of deepLinks) {
      try {
        await page.goto(`${BASE}${dl.url}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
        await page.waitForTimeout(2600)
        const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
        if (await loadNow.count()) await loadNow.first().click().catch(() => {})
        await page.waitForTimeout(1200)
        const urlPage = new URL(page.url()).searchParams.get('page')
        const body = await page.evaluate(() => document.body?.innerText || '')
        const ok = urlPage === dl.expectPage && dl.expectText.test(body)
        const row = {
          id: dl.id,
          module: 'cross',
          title: `Deep link ${dl.url}`,
          result: ok ? 'PASS' : 'FAIL',
          detail: { url: page.url(), urlPage, bodySample: body.slice(0, 240) },
        }
        if (!ok) logFail(dl.id, 'cross', row.title, 'P2', row.detail)
        results.push(row)
        console.log(`${row.result} ${dl.id}`)
      } catch (err) {
        results.push(logFail(dl.id, 'cross', dl.id, 'P2', { error: String(err) }))
      }
    }

    // Back/forward
    try {
      await openPage(page, 'employees')
      await openPage(page, 'calendar')
      await page.goBack()
      await page.waitForTimeout(900)
      const back = page.url()
      await page.goForward()
      await page.waitForTimeout(900)
      const fwd = page.url()
      const ok = /page=employees/.test(back) && /page=calendar/.test(fwd)
      const row = {
        id: 'UI_en-desktop_back_forward',
        module: 'cross',
        title: 'Back/forward employees↔calendar',
        result: ok ? 'PASS' : 'FAIL',
        detail: { back, fwd },
      }
      if (!ok) logFail(row.id, 'cross', row.title, 'P1', row.detail)
      results.push(row)
      console.log(`${row.result} ${row.id}`)
    } catch (err) {
      results.push(logFail('UI_en-desktop_back_forward', 'cross', 'Back/forward', 'P1', { error: String(err) }))
    }

    // Overlay scroll-lock smoke: open Add employee if manage available
    try {
      await openPage(page, 'employees')
      const addBtn = page.getByRole('button', { name: /Add employee|إضافة موظف/i })
      if (await addBtn.count()) {
        await addBtn.first().click()
        await page.waitForTimeout(600)
        const locked = await page.evaluate(() => {
          const overflow = getComputedStyle(document.body).overflow
          const position = getComputedStyle(document.body).position
          return overflow === 'hidden' || position === 'fixed'
        })
        const dialog = await page.getByRole('dialog').count()
        const row = {
          id: 'UI_overlay_scroll_lock_add_employee',
          module: 'employees',
          title: 'Add employee overlay scroll lock',
          result: locked && dialog > 0 ? 'PASS' : 'FAIL',
          detail: { locked, dialog },
        }
        if (row.result === 'FAIL') logFail(row.id, 'employees', row.title, 'P2', row.detail)
        results.push(row)
        console.log(`${row.result} ${row.id}`)
        await page.keyboard.press('Escape').catch(() => {})
      } else {
        results.push({
          id: 'UI_overlay_scroll_lock_add_employee',
          module: 'employees',
          title: 'Add employee overlay scroll lock',
          result: 'SKIP',
          detail: { reason: 'no_add_button' },
        })
        console.log('SKIP UI_overlay_scroll_lock_add_employee')
      }
    } catch (err) {
      results.push(logFail('UI_overlay_scroll_lock_add_employee', 'employees', 'scroll lock', 'P2', { error: String(err) }))
    }
  }

  if (locale === 'ar') {
    const rtl = await page.evaluate(() => {
      return (
        document.documentElement.getAttribute('dir') === 'rtl' ||
        !!document.querySelector('[dir="rtl"]') ||
        getComputedStyle(document.body).direction === 'rtl'
      )
    })
    const row = {
      id: `UI_${prefix}_rtl`,
      module: 'cross',
      title: `RTL active (${prefix})`,
      result: rtl ? 'PASS' : 'FAIL',
      detail: { rtl },
    }
    if (!rtl) logFail(row.id, 'cross', row.title, 'P1', row.detail)
    results.push(row)
    console.log(`${row.result} ${row.id}`)
  }

  await ctx.close()
  return results
}

async function run() {
  if (!EVID) throw new Error('FULL_WEB_E2E_EVID required')
  fs.mkdirSync(EVID, { recursive: true })
  const session = loadSession()
  const browser = await chromium.launch({
    headless: true,
    executablePath: fs.existsSync(CHROME) ? CHROME : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const all = []
  try {
    all.push(
      ...(await runViewport(browser, session, {
        locale: 'en',
        width: 1440,
        height: 900,
        isMobile: false,
        shotDir: path.join(EVID, 'screenshots', 'en-desktop'),
        prefix: 'en-desktop',
      })),
    )
    all.push(
      ...(await runViewport(browser, session, {
        locale: 'ar',
        width: 1440,
        height: 900,
        isMobile: false,
        shotDir: path.join(EVID, 'screenshots', 'ar-desktop'),
        prefix: 'ar-desktop',
      })),
    )
    all.push(
      ...(await runViewport(browser, session, {
        locale: 'en',
        width: 390,
        height: 844,
        isMobile: true,
        shotDir: path.join(EVID, 'screenshots', 'en-mobile'),
        prefix: 'en-mobile',
      })),
    )
    all.push(
      ...(await runViewport(browser, session, {
        locale: 'ar',
        width: 390,
        height: 844,
        isMobile: true,
        shotDir: path.join(EVID, 'screenshots', 'ar-mobile'),
        prefix: 'ar-mobile',
      })),
    )
  } finally {
    await browser.close()
  }

  const summary = {
    stamp: path.basename(EVID).replace(/^full-web-e2e-prod-qual-/, ''),
    total: all.length,
    pass: all.filter((r) => r.result === 'PASS').length,
    fail: all.filter((r) => r.result === 'FAIL').length,
    skip: all.filter((r) => r.result === 'SKIP').length,
    results: all,
  }
  fs.writeFileSync(path.join(EVID, 'verify', 'ui-results.json'), JSON.stringify(summary, null, 2) + '\n')
  console.log(`UI_SUMMARY pass=${summary.pass} fail=${summary.fail} skip=${summary.skip} total=${summary.total}`)
  if (summary.fail > 0) process.exitCode = 1
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
