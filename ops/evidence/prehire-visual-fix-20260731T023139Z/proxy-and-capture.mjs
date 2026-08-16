/**
 * Serve local dashboard dist, proxy /dashboard API to production, capture visual matrix.
 * No deploy. Short-lived session token via env.
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
const PORT = Number(process.env.VISUAL_QUAL_PORT || 4177)
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
  return API_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?'))
    || (pathname.startsWith('/dashboard/') && !pathname.includes('.') && !pathname.startsWith('/dashboard/assets'))
}

function serveStatic(req, res, pathname) {
  let rel = pathname
  if (rel === '/dashboard' || rel === '/dashboard/') rel = '/dashboard/index.html'
  if (rel.startsWith('/dashboard/')) rel = rel.slice('/dashboard'.length)
  const filePath = join(DIST, rel === '/' || rel === '' ? 'index.html' : rel)
  if (!filePath.startsWith(DIST) || !existsSync(filePath) || statSync(filePath).isDirectory()) {
    // SPA fallback
    const index = join(DIST, 'index.html')
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
    res.end(readFileSync(index))
    return
  }
  res.writeHead(200, { 'Content-Type': MIME[extname(filePath)] || 'application/octet-stream', 'Cache-Control': 'no-store' })
  res.end(readFileSync(filePath))
}

async function proxyApi(req, res, pathname) {
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
    proxyApi(req, res, pathname).catch((err) => {
      res.writeHead(502, { 'Content-Type': 'text/plain' })
      res.end(String(err))
    })
    return
  }
  serveStatic(req, res, pathname)
})

await new Promise((r) => server.listen(PORT, '127.0.0.1', r))
console.log('proxy_ready', `http://127.0.0.1:${PORT}/dashboard/`)

const shotsDir = resolve(EVID, 'screenshots', 'after')
mkdirSync(shotsDir, { recursive: true })

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

const viewports = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
}

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

const smoke = []
const a11yNotes = []

async function settle(page) {
  await page.waitForTimeout(900)
  await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})
  await page.waitForTimeout(400)
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
  const vp = viewports[viewportName]
  await page.setViewportSize(vp)
  await seedAuth(page, locale)
  const url = `http://127.0.0.1:${PORT}/dashboard/?page=${pageId}`
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await settle(page)
  // dismiss obvious dialogs if any
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

async function shot(page, name) {
  const path = resolve(shotsDir, name)
  await page.screenshot({ path, fullPage: true })
  console.log('wrote', name)
  return path
}

async function auditPage(page, pageId, locale) {
  const metrics = await page.evaluate(() => {
    const cream = [...document.querySelectorAll('*')].filter((el) => {
      const s = getComputedStyle(el)
      const bg = s.backgroundColor
      return bg.includes('255, 250, 240') || bg.includes('238, 232, 218') || bg.includes('247, 242, 233')
    }).length
    const blackPills = [...document.querySelectorAll('button, a, span, div')].filter((el) => {
      const s = getComputedStyle(el)
      const r = parseFloat(s.borderRadius)
      const bg = s.backgroundColor
      const dark = bg.startsWith('rgb(0') || bg.startsWith('rgb(23') || bg.startsWith('rgb(35') || bg.includes('23, 33, 29') || bg.includes('24, 24, 27')
      return r >= 999 || (r >= 20 && dark && el.getBoundingClientRect().height < 48 && el.getBoundingClientRect().width < 280)
    }).length
    const overflowX = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
    const dir = document.documentElement.dir || document.body.dir || getComputedStyle(document.body).direction
    const focusables = [...document.querySelectorAll('a,button,input,select,textarea,[tabindex]')].filter((el) => {
      const r = el.getBoundingClientRect()
      return r.width > 0 && r.height > 0
    }).length
    const aside = document.querySelector('aside')
    const main = document.querySelector('main') || document.body
    return {
      creamish_nodes: cream,
      blackish_pillish: blackPills,
      overflow_x: overflowX,
      dir,
      focusables,
      aside_w: aside ? Math.round(aside.getBoundingClientRect().width) : 0,
      main_w: main ? Math.round(main.getBoundingClientRect().width) : 0,
      h1: document.querySelector('h1')?.textContent?.trim() || null,
      rounded_nested: [...document.querySelectorAll('*')].filter((el) => {
        const r = parseFloat(getComputedStyle(el).borderRadius)
        if (r < 16) return false
        const p = el.parentElement
        if (!p) return false
        const pr = parseFloat(getComputedStyle(p).borderRadius)
        return pr >= 16 && el.children.length > 0
      }).length,
    }
  })
  a11yNotes.push({ page: pageId, locale, ...metrics })
}

// Primary matrix
for (const pageId of PAGES) {
  for (const locale of ['en', 'ar']) {
    const context = await browser.newContext()
    const page = await openPage(context, pageId, locale, 'desktop')
    await auditPage(page, pageId, locale)
    await shot(page, `${pageId}-${locale}-desktop.png`)
    await page.close()
    await context.close()
  }
  // mobile EN only (requested mobile screenshot; AR mobile optional bonus for overview/jobs)
  const context = await browser.newContext()
  const page = await openPage(context, pageId, 'en', 'mobile')
  await shot(page, `${pageId}-en-mobile.png`)
  await page.close()
  await context.close()
}

// Extra AR mobile for overview + candidates (RTL spacing)
for (const pageId of ['overview', 'candidates']) {
  const context = await browser.newContext()
  const page = await openPage(context, pageId, 'ar', 'mobile')
  await shot(page, `${pageId}-ar-mobile.png`)
  await page.close()
  await context.close()
}

// Empty / loading / error probes on representative pages
{
  const context = await browser.newContext()
  const page = await openPage(context, 'ranking', 'en', 'desktop')
  // ranking often empty without position — capture empty personality
  await shot(page, 'ranking-en-desktop-empty-or-loaded.png')
  await page.close()
  await context.close()
}

{
  // Force loading skeleton by aborting API briefly then capture early frame via route delay
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.setViewportSize(viewports.desktop)
  await seedAuth(page, 'en')
  await page.route('**/dashboard/prehire/**', async (route) => {
    await new Promise((r) => setTimeout(r, 2500))
    await route.continue()
  })
  const nav = page.goto(`http://127.0.0.1:${PORT}/dashboard/?page=jobs`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(700)
  await shot(page, 'jobs-en-desktop-loading.png')
  await nav
  await settle(page)
  await page.close()
  await context.close()
}

{
  // Error state: abort applications list
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.setViewportSize(viewports.desktop)
  await seedAuth(page, 'en')
  await page.route('**/dashboard/prehire/applications**', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'forced_visual_qual_error' }) }),
  )
  await page.goto(`http://127.0.0.1:${PORT}/dashboard/?page=candidates`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await settle(page)
  await shot(page, 'candidates-en-desktop-error.png')
  await page.close()
  await context.close()
}

{
  // Assistant empty-ish (no conversation)
  const context = await browser.newContext()
  const page = await openPage(context, 'ai', 'en', 'desktop')
  await shot(page, 'ai-en-desktop-empty.png')
  await page.close()
  await context.close()
}

// Keyboard focus smoke on Overview
{
  const context = await browser.newContext()
  const page = await openPage(context, 'overview', 'en', 'desktop')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  const focus = await page.evaluate(() => {
    const el = document.activeElement
    if (!el) return null
    const s = getComputedStyle(el)
    return {
      tag: el.tagName,
      text: (el.textContent || '').trim().slice(0, 80),
      outline: s.outlineStyle,
      outlineWidth: s.outlineWidth,
      boxShadow: s.boxShadow,
    }
  })
  writeFileSync(resolve(EVID, 'verify', 'focus-smoke.json'), JSON.stringify(focus, null, 2))
  await shot(page, 'overview-en-desktop-focus.png')
  await page.close()
  await context.close()
}

writeFileSync(resolve(EVID, 'verify', 'route-smoke.json'), JSON.stringify(smoke, null, 2))
writeFileSync(resolve(EVID, 'verify', 'layout-metrics.json'), JSON.stringify(a11yNotes, null, 2))

await browser.close()
server.close()
console.log('capture_complete')
