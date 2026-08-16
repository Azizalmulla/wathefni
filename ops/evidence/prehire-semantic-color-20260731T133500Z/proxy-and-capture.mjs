/**
 * Local dist + API proxy — semantic color after captures. No deploy.
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
const PORT = Number(process.env.VISUAL_QUAL_PORT || 4191)
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
console.log('proxy_ready', PORT)

const shots = resolve(EVID, 'screenshots', 'after')
mkdirSync(shots, { recursive: true })
const PAGES = ['overview', 'jobs', 'candidates', 'interviews', 'calendar', 'assessments', 'ranking', 'reports', 'ai']
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
const probes = []

async function capture(pageId, locale, vpName, size) {
  const context = await browser.newContext({ viewport: size })
  const page = await context.newPage()
  await page.addInitScript(({ token, email, phone, company, locale }) => {
    localStorage.setItem('wathefni_dashboard_token', token)
    localStorage.setItem('wathefni_company_code', company)
    if (email) localStorage.setItem('wathefni_dashboard_email', email)
    if (phone) localStorage.setItem('wathefni_hr_phone', phone)
    localStorage.setItem('wathefni_recruiting_locale', locale)
  }, { token: TOKEN, email: EMAIL, phone: PHONE, company: COMPANY, locale })
  await page.goto(`http://127.0.0.1:${PORT}/dashboard/?page=${pageId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(1300)
  await page.screenshot({ path: resolve(shots, `${pageId}-${locale}-${vpName}.png`), fullPage: false })
  const probe = await page.evaluate(() => {
    const sample = [...document.querySelectorAll('[class*="accent-"], [class*="wf-accent"]')].slice(0, 8).map((el) => el.className.toString().slice(0, 120))
    return {
      dir: document.querySelector('main')?.getAttribute('dir') || document.documentElement.getAttribute('dir'),
      accentSamples: sample.length,
      h1: document.querySelector('h1')?.textContent?.trim() || null,
    }
  })
  probes.push({ page: pageId, locale, viewport: vpName, ...probe })
  console.log('after', pageId, locale, vpName)
  await page.close()
  await context.close()
}

for (const locale of ['en', 'ar']) {
  for (const pageId of PAGES) {
    await capture(pageId, locale, 'desktop', { width: 1440, height: 900 })
    if (['jobs', 'candidates', 'calendar', 'ai'].includes(pageId)) {
      await capture(pageId, locale, 'mobile', { width: 390, height: 844 })
    }
  }
}

writeFileSync(resolve(EVID, 'verify', 'after-probes.json'), JSON.stringify(probes, null, 2))
await browser.close()
server.close()
console.log('capture_complete', probes.length)
