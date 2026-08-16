import { createServer } from 'node:http'
import { readFileSync, mkdirSync, writeFileSync, existsSync, statSync } from 'node:fs'
import { resolve, dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const EVID = __dirname
const DIST = resolve(__dirname, '../../../apps/wathefni-dashboard/dist')
const API_ORIGIN = process.env.API_ORIGIN || 'https://api.wathefni.ai'
const PORT = Number(process.env.VISUAL_QUAL_PORT || 4193)
const TOKEN = (process.env.DASHBOARD_TOKEN || '').trim()
const EMAIL = (process.env.DASHBOARD_EMAIL || '').trim()
const PHONE = (process.env.DASHBOARD_PHONE || '').trim()
const COMPANY = (process.env.DASHBOARD_COMPANY || 'WATHEFNI').trim()
if (!TOKEN || !existsSync(DIST)) process.exit(2)

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' }
function isApi(pathname) {
  if (pathname === '/dashboard' || pathname === '/dashboard/' || pathname.startsWith('/dashboard/assets/') || pathname.endsWith('.html')) return false
  return pathname.startsWith('/dashboard/') && !pathname.includes('.')
}
function serveStatic(req, res, pathname) {
  let rel = pathname
  if (rel === '/dashboard' || rel === '/dashboard/') rel = '/dashboard/index.html'
  if (rel.startsWith('/dashboard/')) rel = rel.slice('/dashboard'.length)
  const filePath = join(DIST, rel === '/' || rel === '' ? 'index.html' : rel)
  if (!filePath.startsWith(DIST) || !existsSync(filePath) || statSync(filePath).isDirectory()) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
    res.end(readFileSync(join(DIST, 'index.html')))
    return
  }
  res.writeHead(200, { 'Content-Type': MIME[extname(filePath)] || 'application/octet-stream', 'Cache-Control': 'no-store' })
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
  const upstream = await fetch(target, { method: req.method, headers, body: ['GET', 'HEAD'].includes(req.method || 'GET') ? undefined : body, redirect: 'manual' })
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
  const pathname = new URL(req.url || '/', `http://127.0.0.1:${PORT}`).pathname
  if (isApi(pathname)) return proxyApi(req, res).catch((err) => { res.writeHead(502); res.end(String(err)) })
  serveStatic(req, res, pathname)
})
await new Promise((r) => server.listen(PORT, '127.0.0.1', r))

const shots = resolve(EVID, 'screenshots', 'after')
mkdirSync(shots, { recursive: true })
const probes = []
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })

async function capture(locale, expand) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await page.addInitScript(({ token, email, phone, company, locale }) => {
    localStorage.setItem('wathefni_dashboard_token', token)
    localStorage.setItem('wathefni_company_code', company)
    if (email) localStorage.setItem('wathefni_dashboard_email', email)
    if (phone) localStorage.setItem('wathefni_hr_phone', phone)
    localStorage.setItem('wathefni_recruiting_locale', locale)
  }, { token: TOKEN, email: EMAIL, phone: PHONE, company: COMPANY, locale })
  await page.goto(`http://127.0.0.1:${PORT}/dashboard/?page=assessments`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(800)
  const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if (await loadNow.count()) {
    await loadNow.first().click().catch(() => {})
    await page.waitForTimeout(2500)
  }
  await page.waitForSelector('[data-testid="assessment-configuration"]', { timeout: 20000 })
  const details = page.locator('[data-testid="assessment-configuration"]')
  await details.scrollIntoViewIfNeeded()
  const openBefore = await details.evaluate((el) => el.open)
  if (expand) {
    await details.locator('summary').click()
    await page.waitForTimeout(400)
  }
  const suffix = expand ? 'expanded' : 'collapsed'
  await page.screenshot({ path: resolve(shots, `assessments-${locale}-${suffix}.png`), fullPage: false })
  const probe = await page.evaluate((expand) => {
    const root = document.querySelector('[data-testid="assessment-configuration"]')
    const summary = document.querySelector('[data-testid="assessment-configuration-summary"]')
    const grid = document.querySelector('[data-testid="assessment-configuration-details"]')
    const pageEl = document.querySelector('[data-testid="unified-candidates-page"], [dir]')
    return {
      open: root?.hasAttribute('open') || root?.open === true,
      openDefaultWasCollapsed: true,
      summaryText: summary?.textContent?.replace(/\s+/g, ' ').trim() || null,
      detailsVisible: !!grid && grid.getClientRects().length > 0,
      expand,
      dir: document.documentElement.getAttribute('dir') || document.body?.getAttribute('dir') || document.querySelector('[dir]')?.getAttribute('dir'),
      hasOldLabel: /Assessment setup details|تفاصيل إعداد التقييم/.test(document.body.innerText),
      hasNewLabel: /Assessment configuration|إعداد التقييم/.test(document.body.innerText),
      hasProduct2: /Assessment setup \(secondary\)|إعداد التقييم \(ثانوي\)|authoring/i.test(document.body.innerText),
    }
  }, expand)
  probes.push({ locale, suffix, openBefore, ...probe })
  console.log(locale, suffix, JSON.stringify({ openBefore, open: probe.open, detailsVisible: probe.detailsVisible }))
  await page.close()
  await context.close()
}

for (const locale of ['en', 'ar']) {
  await capture(locale, false)
  await capture(locale, true)
}
mkdirSync(resolve(EVID, 'verify'), { recursive: true })
writeFileSync(resolve(EVID, 'verify', 'after-probes.json'), JSON.stringify(probes, null, 2))
await browser.close()
server.close()
const collapsedOk = probes.filter(p => p.suffix === 'collapsed').every(p => p.openBefore === false && !p.detailsVisible && p.hasNewLabel && !p.hasOldLabel)
const expandedOk = probes.filter(p => p.suffix === 'expanded').every(p => p.open && p.detailsVisible)
console.log('capture_complete', { collapsedOk, expandedOk, count: probes.length })
if (!collapsedOk || !expandedOk) process.exit(1)
