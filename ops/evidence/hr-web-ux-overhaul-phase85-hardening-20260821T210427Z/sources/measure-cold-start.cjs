/**
 * Measure production cold restore:
 * page load → stored-session validation → shell first paint → first useful surface.
 * Read-only. Does not print tokens.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')

const BASE = process.env.DASHBOARD_BASE || 'https://app.octo-hr.com/dashboard/'
const SESSION = process.env.FULL_WEB_E2E_SESSION || '/tmp/full-web-e2e.session'
const PAGE_ID = process.env.COLD_START_PAGE || 'shifts'
const RUNS = Number(process.env.COLD_START_RUNS || 3)
const LABEL = process.env.COLD_START_LABEL || 'before'
const OUT = process.env.COLD_START_OUT || ''
const CHROME = process.env.PW_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  if (!lines[0]) throw new Error(`empty session token in ${SESSION}`)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

async function oneRun(browser, session) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  const marks = {
    resolvingMs: null,
    shellMs: null,
    usefulMs: null,
    loadingChipMs: null,
    loadingChipGoneMs: null,
    authWall: false,
    title: '',
    urlPage: '',
    usefulProbe: '',
  }
  await page.addInitScript(
    ({ s }) => {
      localStorage.setItem('wathefni_dashboard_token', s.token)
      localStorage.setItem('wathefni_dashboard_email', s.email)
      localStorage.setItem('wathefni_hr_phone', s.phone)
      localStorage.setItem('wathefni_company_code', 'WATHEFNI')
      localStorage.setItem('wathefni_recruiting_locale', 'en')
    },
    { s: session },
  )
  const t0 = Date.now()
  await page.goto(`${BASE}?page=${PAGE_ID}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  const resolving = page.getByTestId('octohr-auth-resolving')
  try {
    await resolving.waitFor({ state: 'visible', timeout: 4000 })
    marks.resolvingMs = Date.now() - t0
  } catch {
    marks.resolvingMs = null
  }
  await page.waitForFunction(
    () => !document.querySelector('[data-testid="octohr-auth-resolving"]'),
    null,
    { timeout: 30000 },
  )
  const resolvedMs = Date.now() - t0
  const authSurface = await page.getByTestId('octohr-auth-surface').count()
  if (authSurface) {
    marks.authWall = true
    marks.shellMs = resolvedMs
    marks.title = ((await page.locator('h1').first().textContent()) || '').trim()
    await context.close()
    return { ...marks, resolvedMs }
  }
  await page.waitForSelector('[data-testid="app-shell"]', { timeout: 30000 })
  marks.shellMs = Date.now() - t0
  const useful = await page.waitForFunction(
    (pageId) => {
      const text = document.body?.innerText || ''
      if (/Loading saved dashboard access/i.test(text)) return false
      if (document.querySelector('[data-testid="octohr-auth-resolving"]')) return false
      if (document.querySelector('[data-page-skeleton]')) return false
      const h1 = (document.querySelector('h1')?.textContent || '').trim()
      if (pageId === 'shifts') {
        return Boolean(document.querySelector('[data-testid="shifts-workspace"]') || document.querySelector('[data-testid="shifts-org-units-filter-state"]'))
      }
      return Boolean(h1) && !/checking your session/i.test(h1)
    },
    PAGE_ID,
    { timeout: 30000 },
  )
  marks.usefulMs = Date.now() - t0
  marks.usefulProbe = String(Boolean(useful))
  await page.waitForTimeout(3500)
  const settled = await page.evaluate(() => {
    const body = document.body?.innerText || ''
    return {
      authWall: Boolean(document.querySelector('[data-testid="octohr-auth-surface"]')),
      resolving: Boolean(document.querySelector('[data-testid="octohr-auth-resolving"]')),
      shell: Boolean(document.querySelector('[data-testid="app-shell"]')),
      shifts: Boolean(document.querySelector('[data-testid="shifts-workspace"]')),
      loadingChip: /Loading saved dashboard access/i.test(body),
      title: (document.querySelector('h1')?.textContent || '').trim(),
      urlPage: new URL(location.href).searchParams.get('page') || '',
    }
  })
  marks.authWall = Boolean(settled.authWall)
  marks.title = settled.title
  marks.urlPage = settled.urlPage
  marks.loadingChipMs = settled.loadingChip ? Date.now() - t0 : null
  marks.settledShifts = Boolean(settled.shifts)
  marks.settledShell = Boolean(settled.shell)
  await context.close()
  return { ...marks, resolvedMs }
}

function median(values) {
  const nums = values.filter((v) => typeof v === 'number').sort((a, b) => a - b)
  if (!nums.length) return null
  const mid = Math.floor(nums.length / 2)
  return nums.length % 2 ? nums[mid] : Math.round((nums[mid - 1] + nums[mid]) / 2)
}

async function main() {
  const session = loadSession()
  const browser = await chromium.launch({
    executablePath: fs.existsSync(CHROME) ? CHROME : undefined,
    headless: true,
  })
  const runs = []
  for (let i = 0; i < RUNS; i += 1) {
    runs.push(await oneRun(browser, session))
  }
  await browser.close()
  const summary = {
    label: LABEL,
    page: PAGE_ID,
    runs,
    median: {
      resolvingMs: median(runs.map((r) => r.resolvingMs)),
      resolvedMs: median(runs.map((r) => r.resolvedMs)),
      shellMs: median(runs.map((r) => r.shellMs)),
      usefulMs: median(runs.map((r) => r.usefulMs)),
    },
    authWall: runs.some((r) => r.authWall),
  }
  const text = JSON.stringify(summary, null, 2)
  if (OUT) {
    fs.mkdirSync(require('path').dirname(OUT), { recursive: true })
    fs.writeFileSync(OUT, text + '\n')
  }
  process.stdout.write(text + '\n')
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err))
  process.exit(1)
})
