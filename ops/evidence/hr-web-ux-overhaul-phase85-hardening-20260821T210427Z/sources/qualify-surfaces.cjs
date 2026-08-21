/**
 * Qualify previously unreviewed HR Web surfaces after the hardening fix.
 * Read-only. Does not print tokens. Does not fabricate PASS from a denied identity.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://app.octo-hr.com/dashboard/'
const SESSION = process.env.FULL_WEB_E2E_SESSION
const EVID = process.env.FULL_WEB_E2E_EVID
const LABEL = process.env.QUAL_LABEL || 'owner'
const CHROME = process.env.PW_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const EMPLOYEE = process.env.QUAL_EMPLOYEE || 'WATHEFNI-96550252254'

const SURFACES = [
  { id: 'employees', useful: /employees|directory|موظف/i, workspace: null },
  { id: 'workforce', useful: /organization|workforce|org unit|تنظيم|القوى/i, workspace: null },
  { id: 'preboarding', useful: /preboard|تهيئة مسبقة|ما قبل/i, workspace: null },
  { id: 'probation', useful: /probation|تجربة/i, workspace: null },
  { id: 'requisitions', useful: /requisition|طلب توظيف|احتياج/i, workspace: null },
  { id: 'shifts', useful: /shift|وردية|مناوبة/i, workspace: '[data-testid="shifts-workspace"]' },
]

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  if (!lines[0]) throw new Error(`empty session token in ${SESSION}`)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
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

async function shot(page, name) {
  const dir = path.join(EVID, 'screenshots', LABEL)
  fs.mkdirSync(dir, { recursive: true })
  const dest = path.join(dir, `${name}.png`)
  await page.screenshot({ path: dest, fullPage: false })
  return dest
}

async function readState(page) {
  return page.evaluate(() => {
    const body = document.body?.innerText || ''
    const dir =
      document.documentElement.getAttribute('dir') ||
      document.querySelector('[dir="rtl"],[dir="ltr"]')?.getAttribute('dir') ||
      getComputedStyle(document.body).direction
    return {
      title: (document.querySelector('h1')?.textContent || '').trim(),
      urlPage: new URL(location.href).searchParams.get('page') || '',
      urlEmployee: new URL(location.href).searchParams.get('employee') || '',
      dir,
      authWall: Boolean(document.querySelector('[data-testid="octohr-auth-surface"]')),
      resolving: Boolean(document.querySelector('[data-testid="octohr-auth-resolving"]')),
      shell: Boolean(document.querySelector('[data-testid="app-shell"]')),
      shifts: Boolean(document.querySelector('[data-testid="shifts-workspace"]')),
      orgUnitsError: Boolean(document.querySelector('[data-testid="shifts-org-units-filter-state"]')),
      resourceError: Boolean(document.querySelector('[data-testid*="state"][role="alert"], [data-resource-state="error"]')),
      loadingChip: /Loading saved dashboard access/i.test(body),
      signInCopy: /Sign in|تسجيل الدخول|does not include access to this workspace/i.test(body),
      bodyPreview: body.replace(/\s+/g, ' ').slice(0, 280),
    }
  })
}

function verdict(id, state, locale) {
  if (state.authWall || (state.signInCopy && !state.shell)) {
    return { result: 'FAIL', reason: 'dropped_to_global_auth_wall' }
  }
  if (!state.shell) return { result: 'FAIL', reason: 'no_shell' }
  if (state.urlPage && state.urlPage !== id && id !== 'employees') {
    return { result: 'UNVERIFIED', reason: `remapped_to_${state.urlPage}` }
  }
  if (id === 'shifts' && state.shifts && !state.authWall) {
    return { result: 'PASS', reason: state.orgUnitsError ? 'workspace_with_in_page_org_error' : 'workspace_kept' }
  }
  if (state.title && !/sign in/i.test(state.title)) return { result: 'PASS', reason: 'surface_kept' }
  return { result: 'UNVERIFIED', reason: 'no_clear_surface_title' }
}

async function openAndSettle(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForFunction(
    () => !document.querySelector('[data-testid="octohr-auth-resolving"]'),
    null,
    { timeout: 30000 },
  )
  await page.waitForTimeout(2800)
}

async function qualifySurface(browser, session, surface) {
  const rows = []
  for (const locale of ['en', 'ar']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await context.newPage()
    await inject(page, session, locale)
    const url = `${BASE}?page=${surface.id}`
    await openAndSettle(page, url)
    const deep = await readState(page)
    await shot(page, `${surface.id}-${locale}-deep`)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2400)
    const refresh = await readState(page)
    await shot(page, `${surface.id}-${locale}-refresh`)
    if (locale === 'en') {
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await page.waitForTimeout(800)
      await page.goForward({ waitUntil: 'domcontentloaded' }).catch(() => {})
      await page.waitForTimeout(1600)
    }
    const forward = await readState(page)
    const v = verdict(surface.id, deep, locale)
    rows.push({
      surface: surface.id,
      locale,
      dir: deep.dir,
      deep,
      refresh,
      forward,
      verdict: v,
    })
    await context.close()
  }
  return rows
}

async function qualifyEmployee360(browser, session) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await inject(page, session, 'en')
  await openAndSettle(page, `${BASE}?page=employees&employee=${encodeURIComponent(EMPLOYEE)}`)
  const state = await readState(page)
  await shot(page, 'employee-360-en-deep')
  await context.close()
  const ok = state.shell && !state.authWall && (state.urlEmployee === EMPLOYEE || /360|profile|employee/i.test(`${state.title} ${state.bodyPreview}`))
  return {
    surface: 'employee-360',
    locale: 'en',
    employee: EMPLOYEE,
    state,
    verdict: state.authWall
      ? { result: 'FAIL', reason: 'dropped_to_global_auth_wall' }
      : ok
        ? { result: 'PASS', reason: 'profile_kept' }
        : { result: 'UNVERIFIED', reason: 'profile_not_proven' },
  }
}

async function main() {
  if (!SESSION || !EVID) throw new Error('FULL_WEB_E2E_SESSION and FULL_WEB_E2E_EVID required')
  const session = loadSession()
  const browser = await chromium.launch({
    executablePath: fs.existsSync(CHROME) ? CHROME : undefined,
    headless: true,
  })
  const results = []
  for (const surface of SURFACES) {
    process.stderr.write(`qualify ${surface.id}\n`)
    results.push(...(await qualifySurface(browser, session, surface)))
  }
  results.push(await qualifyEmployee360(browser, session))
  await browser.close()
  const out = path.join(EVID, 'tests', `qualify-${LABEL}.json`)
  fs.mkdirSync(path.dirname(out), { recursive: true })
  fs.writeFileSync(out, JSON.stringify({ label: LABEL, results }, null, 2) + '\n')
  const summary = results.map((row) => ({
    surface: row.surface,
    locale: row.locale,
    result: row.verdict.result,
    reason: row.verdict.reason,
    title: row.deep?.title || row.state?.title,
    urlPage: row.deep?.urlPage || row.state?.urlPage,
    authWall: row.deep?.authWall || row.state?.authWall || false,
  }))
  process.stdout.write(JSON.stringify(summary, null, 2) + '\n')
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err))
  process.exit(1)
})
