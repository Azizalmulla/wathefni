/**
 * Pre-hire E2E production UI qualification — pages, locale, viewport.
 * Read-only navigation + screenshots. Logs failures to failures/.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const EVID = process.env.PREHIRE_E2E_EVID
const SESSION = process.env.PREHIRE_E2E_SESSION || '/tmp/prehire-e2e.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

const PAGES = [
  'overview',
  'jobs',
  'candidates',
  'ranking',
  'assessments',
  'interviews',
  'calendar',
  'reports',
  'ai',
]

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
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
  await page.goto(`${BASE}?page=${pageId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2200)
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
    const fatal =
      /Access verification required|Could not load|Something went wrong|Unauthorized|Forbidden/i.test(body) &&
      body.length < 1200
    return {
      id,
      urlPage,
      title,
      active,
      dir,
      bodyLen: body.length,
      fatal,
      hasContent: body.length > 80,
    }
  }, pageId)
}

async function runViewport(browser, session, { locale, width, height, isMobile, shotDir, prefix }) {
  const ctx = await browser.newContext({
    viewport: { width, height },
    isMobile: !!isMobile,
    hasTouch: !!isMobile,
  })
  const page = await ctx.newPage()
  await inject(page, session, locale)
  const results = []
  for (const pageId of PAGES) {
    const gateId = `UI_${prefix}_${pageId}`
    try {
      await openPage(page, pageId)
      const snap = await probe(page, pageId)
      const shot = path.join(shotDir, `${prefix}-${pageId}.png`)
      await page.screenshot({ path: shot, fullPage: false })
      const pageOk = snap.urlPage === pageId || new RegExp(pageId, 'i').test(snap.title + snap.active)
      const ok = snap.hasContent && !snap.fatal && pageOk
      const row = {
        id: gateId,
        module: pageId === 'ai' ? 'assistant' : pageId,
        title: `UI ${prefix} ${pageId}`,
        result: ok ? 'PASS' : 'FAIL',
        severity: ok ? null : 'P1',
        detail: { ...snap, shot },
      }
      if (!ok) logFail(gateId, row.module, row.title, 'P1', row.detail)
      results.push(row)
      console.log(`${row.result} ${gateId}`)
    } catch (err) {
      const row = logFail(gateId, pageId, `UI ${prefix} ${pageId}`, 'P1', { error: String(err) })
      results.push({ ...row, result: 'FAIL' })
      console.log(`FAIL ${gateId}`)
    }
  }

  // Back/forward spot-check on desktop EN only
  if (prefix === 'en-desktop') {
    try {
      await openPage(page, 'candidates')
      await openPage(page, 'reports')
      await page.goBack()
      await page.waitForTimeout(900)
      const back = page.url()
      await page.goForward()
      await page.waitForTimeout(900)
      const fwd = page.url()
      const ok = /page=candidates/.test(back) && /page=reports/.test(fwd)
      const row = {
        id: 'UI_en-desktop_back_forward',
        module: 'cross',
        title: 'Back/forward candidates↔reports',
        result: ok ? 'PASS' : 'FAIL',
        detail: { back, fwd },
      }
      if (!ok) logFail(row.id, 'cross', row.title, 'P1', row.detail)
      results.push(row)
      console.log(`${row.result} ${row.id}`)
    } catch (err) {
      results.push(logFail('UI_en-desktop_back_forward', 'cross', 'Back/forward', 'P1', { error: String(err) }))
    }
  }

  // Assessments tab=reports contract on EN desktop
  if (prefix === 'en-desktop') {
    try {
      await page.goto(`${BASE}?page=assessments&tab=reports`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await page.waitForTimeout(2200)
      const loadNow = page.getByRole('button', { name: /Load now/i })
      if (await loadNow.count()) await loadNow.first().click().catch(() => {})
      await page.waitForTimeout(1500)
      const tab = new URL(page.url()).searchParams.get('tab')
      const ok = tab === 'reports'
      const row = {
        id: 'UI_AS04_tab_reports',
        module: 'assessments',
        title: 'Assessments URL tab=reports preserved',
        result: ok ? 'PASS' : 'FAIL',
        detail: { url: page.url(), tab },
      }
      if (!ok) logFail(row.id, 'assessments', row.title, 'P1', row.detail)
      results.push(row)
      await page.screenshot({ path: path.join(shotDir, `${prefix}-assessments-reports-tab.png`), fullPage: false })
      console.log(`${row.result} ${row.id}`)
    } catch (err) {
      results.push(logFail('UI_AS04_tab_reports', 'assessments', 'Assessments tab reports', 'P1', { error: String(err) }))
    }
  }

  // RTL check
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
  if (!EVID) throw new Error('PREHIRE_E2E_EVID required')
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
    passed: all.filter((r) => r.result === 'PASS').length,
    failed: all.filter((r) => r.result === 'FAIL').length,
    total: all.length,
    results: all,
  }
  fs.writeFileSync(path.join(EVID, 'verify', 'ui-results.json'), JSON.stringify(summary, null, 2) + '\n')
  console.log(JSON.stringify({ passed: summary.passed, failed: summary.failed, total: summary.total }, null, 2))
  if (summary.failed) process.exit(1)
}

run().catch((e) => {
  console.error(e)
  process.exit(1)
})
