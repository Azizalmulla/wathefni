/**
 * Focused mobile PRE-HIRING nav verification.
 * Serve local dist, proxy APIs to production. No deploy. Token via env only.
 */
import { createServer } from 'node:http'
import { readFileSync, mkdirSync, writeFileSync, existsSync, statSync } from 'node:fs'
import { resolve, dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const EVID = __dirname
const DIST = resolve(__dirname, '../../../apps/wathefni-dashboard/dist')
const API_ORIGIN = process.env.API_ORIGIN || 'https://api.wathefni.ai'
const PORT = Number(process.env.VISUAL_QUAL_PORT || 4188)
const TOKEN = (process.env.DASHBOARD_TOKEN || '').trim()
const EMAIL = (process.env.DASHBOARD_EMAIL || '').trim()
const PHONE = (process.env.DASHBOARD_PHONE || '').trim()
const COMPANY = (process.env.DASHBOARD_COMPANY || 'WATHEFNI').trim()

if (!TOKEN) {
  console.error('DASHBOARD_TOKEN required')
  process.exit(2)
}
if (!existsSync(DIST)) {
  console.error('dist missing:', DIST)
  process.exit(2)
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
}

const API_PREFIXES = [
  '/dashboard/auth',
  '/dashboard/bootstrap',
  '/dashboard/prehire',
  '/dashboard/team',
  '/dashboard/activity',
  '/dashboard/setup',
  '/dashboard/posthire',
  '/dashboard/notifications',
  '/dashboard/calendar',
  '/dashboard/integrations',
  '/dashboard/settings',
  '/dashboard/mailbox',
  '/dashboard/email',
]

function isApi(pathname) {
  if (pathname === '/dashboard' || pathname === '/dashboard/') return false
  if (pathname.startsWith('/dashboard/assets/')) return false
  if (pathname.endsWith('.html')) return false
  return (
    API_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?')) ||
    (pathname.startsWith('/dashboard/') && !pathname.includes('.') && !pathname.startsWith('/dashboard/assets'))
  )
}

function serveStatic(req, res, pathname) {
  let rel = pathname
  if (rel === '/dashboard' || rel === '/dashboard/') rel = '/dashboard/index.html'
  if (rel.startsWith('/dashboard/')) rel = rel.slice('/dashboard'.length)
  const filePath = join(DIST, rel === '/' || rel === '' ? 'index.html' : rel)
  if (!filePath.startsWith(DIST) || !existsSync(filePath) || statSync(filePath).isDirectory()) {
    const index = join(DIST, 'index.html')
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
    res.end(readFileSync(index))
    return
  }
  res.writeHead(200, {
    'Content-Type': MIME[extname(filePath)] || 'application/octet-stream',
    'Cache-Control': 'no-store',
  })
  res.end(readFileSync(filePath))
}

async function proxyApi(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`)
  const target = `${API_ORIGIN}${url.pathname}${url.search}`
  const headers = { ...req.headers, host: new URL(API_ORIGIN).host }
  delete headers['accept-encoding']
  const chunks = []
  for await (const c of req) chunks.push(c)
  const body = Buffer.concat(chunks)
  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: ['GET', 'HEAD'].includes(req.method || 'GET') ? undefined : body,
    redirect: 'manual',
  })
  const buf = Buffer.from(await upstream.arrayBuffer())
  const outHeaders = {}
  upstream.headers.forEach((v, k) => {
    if (['content-encoding', 'transfer-encoding', 'content-length'].includes(k.toLowerCase())) return
    outHeaders[k] = v
  })
  outHeaders['content-length'] = String(buf.length)
  res.writeHead(upstream.status, outHeaders)
  res.end(buf)
}

const server = createServer((req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${PORT}`)
  const pathname = url.pathname
  if (isApi(pathname)) {
    proxyApi(req, res).catch((err) => {
      res.writeHead(502, { 'Content-Type': 'text/plain' })
      res.end(String(err))
    })
    return
  }
  serveStatic(req, res, pathname)
})

await new Promise((r) => server.listen(PORT, '127.0.0.1', r))
console.log('proxy_ready', `http://127.0.0.1:${PORT}/dashboard/`)

const shotsDir = resolve(EVID, 'screenshots')
mkdirSync(shotsDir, { recursive: true })
mkdirSync(resolve(EVID, 'verify'), { recursive: true })

const PAGES = [
  'overview',
  'jobs',
  'candidates',
  'interviews',
  'calendar',
  'assessments',
  'ranking',
  'reports',
  'ai',
]

const TITLE_EN = {
  overview: 'Overview',
  jobs: 'Jobs',
  candidates: 'Candidates',
  interviews: 'Interviews',
  calendar: 'Calendar',
  assessments: 'Assessments',
  ranking: 'Ranking',
  reports: 'Reports',
  ai: 'Wathefni Assistant',
}

const TITLE_AR = {
  overview: 'نظرة عامة',
  jobs: 'الوظائف',
  candidates: 'المرشحون',
  interviews: 'المقابلات',
  calendar: 'التقويم',
  assessments: 'التقييمات',
  ranking: 'الترتيب',
  reports: 'التقارير',
  ai: 'مساعد واثقني',
}

const viewports = {
  mobile: { width: 390, height: 844 },
  narrow: { width: 320, height: 720 },
}

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

const smoke = []
const navProofs = []

async function settle(page) {
  await page.waitForTimeout(800)
  await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})
  await page.waitForTimeout(350)
}

async function seedAuth(page, locale) {
  await page.addInitScript(
    ({ token, email, phone, company, locale }) => {
      localStorage.setItem('wathefni_dashboard_token', token)
      localStorage.setItem('wathefni_company_code', company)
      if (email) localStorage.setItem('wathefni_dashboard_email', email)
      if (phone) localStorage.setItem('wathefni_hr_phone', phone)
      localStorage.setItem('wathefni_recruiting_locale', locale)
    },
    { token: TOKEN, email: EMAIL, phone: PHONE, company: COMPANY, locale },
  )
}

async function openPage(context, pageId, locale, viewportName) {
  const page = await context.newPage()
  await page.setViewportSize(viewports[viewportName])
  await seedAuth(page, locale)
  const url = `http://127.0.0.1:${PORT}/dashboard/?page=${pageId}`
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await settle(page)
  const loginVisible = await page.locator('text=Sign in').first().isVisible().catch(() => false)
  const shell = await page.locator('aside').first().isVisible().catch(() => false)
  smoke.push({
    page: pageId,
    locale,
    viewport: viewportName,
    status: resp?.status() ?? null,
    login_wall: loginVisible,
    shell_visible: shell,
    title: await page.title(),
    url: page.url(),
  })
  return page
}

async function inspectNav(page, pageId, locale) {
  return page.evaluate(
    ({ pageId, expectedEn, expectedAr, locale }) => {
      const chip = document.querySelector('[data-testid="mobile-active-route-chip"]')
      const rail = document.querySelector('[data-testid="mobile-prehire-rail"]')
      const more = document.querySelector('[data-testid="mobile-nav-more"]')
      const desktop = document.querySelector('[data-testid="desktop-workspace-nav"]')
      const h1 = document.querySelector('h1')?.textContent?.trim() || null
      const chipText = chip?.textContent?.trim() || null
      const chipActive = chip?.getAttribute('data-active') === 'true'
      const railButtons = rail
        ? [...rail.querySelectorAll('button')].map((b) => ({
            text: (b.textContent || '').trim(),
            active: b.getAttribute('data-active') === 'true',
            ariaCurrent: b.getAttribute('aria-current'),
          }))
        : []
      const activeInRail = railButtons.filter((b) => b.active)
      const expected = locale === 'ar' ? expectedAr[pageId] : expectedEn[pageId]
      const settingsInRail = railButtons.some((b) => /settings|الإعدادات/i.test(b.text))
      const employeesInRail = railButtons.some((b) => /employees|الموظفون/i.test(b.text))
      const main = document.querySelector('main')
      const dir =
        main?.getAttribute('dir') ||
        document.documentElement.getAttribute('dir') ||
        document.body.getAttribute('dir') ||
        getComputedStyle(document.body).direction
      const chipBox = chip?.getBoundingClientRect()
      const firstRailBox = rail?.querySelector('button')?.getBoundingClientRect()
      const viewportW = window.innerWidth || document.documentElement.clientWidth
      const chipInViewport = !!(
        chipBox &&
        chipBox.width > 0 &&
        chipBox.height > 0 &&
        chipBox.right > 24 &&
        chipBox.left < viewportW - 24
      )
      const titleOk =
        pageId === 'overview'
          ? chipText === expected
          : !!(h1 && expected && h1.includes(expected))
      return {
        pageId,
        locale,
        h1,
        expected,
        chipText,
        chipActive,
        chipAriaCurrent: chip?.getAttribute('aria-current') || null,
        chipVisible: chipInViewport,
        chipLeft: chipBox ? Math.round(chipBox.left) : null,
        chipRight: chipBox ? Math.round(chipBox.right) : null,
        firstRailLeft: firstRailBox ? Math.round(firstRailBox.left) : null,
        railCount: railButtons.length,
        activeInRailCount: activeInRail.length,
        activeInRailTexts: activeInRail.map((b) => b.text),
        settingsInRail,
        employeesInRail,
        moreVisible: !!(more && more.getBoundingClientRect().width > 0),
        desktopPresent: !!desktop,
        dir,
        chipMatchesExpected: chipText === expected,
        h1IncludesExpected: !!(h1 && expected && h1.includes(expected)),
        titleOk,
        pass:
          !!chip &&
          chipActive &&
          chipText === expected &&
          titleOk &&
          chipInViewport &&
          activeInRail.length === 0 &&
          !settingsInRail &&
          !employeesInRail &&
          !desktop &&
          railButtons.length >= 7 &&
          (locale !== 'ar' || dir === 'rtl'),
      }
    },
    { pageId, expectedEn: TITLE_EN, expectedAr: TITLE_AR, locale },
  )
}

async function shot(page, name) {
  const path = resolve(shotsDir, name)
  await page.screenshot({ path, fullPage: false })
  console.log('wrote', name)
}

// Mobile EN + AR screenshots and smoke for all pre-hire pages
for (const locale of ['en', 'ar']) {
  for (const pageId of PAGES) {
    const context = await browser.newContext()
    const page = await openPage(context, pageId, locale, 'mobile')
    const proof = await inspectNav(page, pageId, locale)
    navProofs.push({ ...proof, viewport: 'mobile' })
    await shot(page, `${pageId}-${locale}-mobile.png`)
    await page.close()
    await context.close()
  }
}

// Narrow width EN for jobs + reports (overflow / chip dominance)
for (const pageId of ['jobs', 'reports', 'ai']) {
  const context = await browser.newContext()
  const page = await openPage(context, pageId, 'en', 'narrow')
  const proof = await inspectNav(page, pageId, 'en')
  navProofs.push({ ...proof, viewport: 'narrow' })
  await shot(page, `${pageId}-en-narrow.png`)
  await page.close()
  await context.close()
}

// Route-change proof: start overview, click Candidates then Reports in rail, chip must update
{
  const context = await browser.newContext()
  const page = await openPage(context, 'overview', 'en', 'mobile')
  const sequence = []
  sequence.push(await inspectNav(page, 'overview', 'en'))
  await page.locator('[data-testid="mobile-prehire-rail"] button', { hasText: 'Candidates' }).click()
  await settle(page)
  sequence.push(await inspectNav(page, 'candidates', 'en'))
  await page.locator('[data-testid="mobile-prehire-rail"] button', { hasText: 'Reports' }).click()
  await settle(page)
  sequence.push(await inspectNav(page, 'reports', 'en'))
  // open More and confirm Settings reachable
  await page.locator('[data-testid="mobile-nav-more"]').click()
  await page.waitForTimeout(200)
  const moreHasSettings = await page.locator('[data-testid="mobile-nav-more-menu"] >> text=Settings').isVisible()
  writeFileSync(
    resolve(EVID, 'verify', 'route-change-nav.json'),
    JSON.stringify({ sequence, moreHasSettings, pass: sequence.every((s) => s.pass) && moreHasSettings }, null, 2),
  )
  await shot(page, 'route-change-reports-en-mobile.png')
  await page.close()
  await context.close()
}

// AR route change + RTL chip placement
{
  const context = await browser.newContext()
  const page = await openPage(context, 'overview', 'ar', 'mobile')
  await page.locator('[data-testid="mobile-prehire-rail"] button', { hasText: 'الوظائف' }).click()
  await settle(page)
  const arProof = await inspectNav(page, 'jobs', 'ar')
  writeFileSync(resolve(EVID, 'verify', 'ar-route-change-nav.json'), JSON.stringify(arProof, null, 2))
  await shot(page, 'jobs-ar-mobile-after-nav.png')
  await page.close()
  await context.close()
}

const failed = navProofs.filter((p) => !p.pass)
writeFileSync(resolve(EVID, 'verify', 'route-smoke.json'), JSON.stringify(smoke, null, 2))
writeFileSync(
  resolve(EVID, 'verify', 'mobile-nav-proofs.json'),
  JSON.stringify(
    {
      total: navProofs.length,
      pass: navProofs.length - failed.length,
      fail: failed.length,
      failed,
      proofs: navProofs,
    },
    null,
    2,
  ),
)

await browser.close()
server.close()
console.log('capture_complete', { smoke: smoke.length, nav_pass: navProofs.length - failed.length, nav_fail: failed.length })
if (failed.length) process.exit(1)
