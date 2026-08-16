import { createServer } from 'node:http'
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import playwright from '/Users/azizalmulla/Desktop/claw/ops/evidence/interviews-ui-refine-20260730T133052Z/node_modules/playwright-core/index.js'

const { chromium } = playwright

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST = resolve(__dirname, '../../../apps/wathefni-dashboard/dist')
const PROD = 'https://api.wathefni.ai'
const PORT = 4197
const TOKEN = (process.env.DASHBOARD_TOKEN || '').trim()
const EMAIL = (process.env.DASHBOARD_EMAIL || '').trim()
const PHONE = (process.env.DASHBOARD_PHONE || '').trim()
const COMPANY = (process.env.DASHBOARD_COMPANY || 'WATHEFNI').trim()
const VARIANT = (process.env.CALENDAR_CAPTURE_VARIANT || '').trim()
if (!TOKEN || !existsSync(DIST)) process.exit(2)

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
}

function isApi(pathname) {
  if (pathname === '/dashboard' || pathname === '/dashboard/' || pathname.startsWith('/dashboard/assets/')) return false
  return pathname.startsWith('/dashboard/') && !pathname.includes('.')
}

function serveStatic(res, pathname) {
  let rel = pathname
  if (rel === '/dashboard' || rel === '/dashboard/') rel = '/dashboard/index.html'
  if (rel.startsWith('/dashboard/')) rel = rel.slice('/dashboard'.length)
  const path = join(DIST, rel === '/' || rel === '' ? 'index.html' : rel)
  if (!path.startsWith(DIST) || !existsSync(path) || statSync(path).isDirectory()) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
    res.end(readFileSync(join(DIST, 'index.html')))
    return
  }
  res.writeHead(200, { 'Content-Type': MIME[extname(path)] || 'application/octet-stream', 'Cache-Control': 'no-store' })
  res.end(readFileSync(path))
}

async function proxyApi(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`)
  const target = `${PROD}${url.pathname}${url.search}`
  const headers = { ...req.headers, host: new URL(PROD).host }
  delete headers['accept-encoding']
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const body = Buffer.concat(chunks)
  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: ['GET', 'HEAD'].includes(req.method || 'GET') ? undefined : body,
    redirect: 'manual',
  })
  const bytes = Buffer.from(await upstream.arrayBuffer())
  const out = {}
  upstream.headers.forEach((value, key) => {
    if (!['content-encoding', 'transfer-encoding', 'content-length'].includes(key.toLowerCase())) out[key] = value
  })
  out['content-length'] = String(bytes.length)
  res.writeHead(upstream.status, out)
  res.end(bytes)
}

const server = createServer((req, res) => {
  const pathname = new URL(req.url || '/', `http://127.0.0.1:${PORT}`).pathname
  if (isApi(pathname)) return proxyApi(req, res).catch((error) => {
    res.writeHead(502)
    res.end(String(error))
  })
  serveStatic(res, pathname)
})
await new Promise((done) => server.listen(PORT, '127.0.0.1', done))

const localOrigin = `http://127.0.0.1:${PORT}`
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

function at(dayOffset, hour, minute = 0) {
  const date = new Date()
  date.setDate(date.getDate() + dayOffset)
  date.setHours(hour, minute, 0, 0)
  return date.toISOString()
}

const fixtures = [
  {
    event_id: 'short-check-in',
    title: 'Candidate check-in',
    event_type: 'meeting',
    status: 'confirmed',
    start_at: at(0, 8),
    end_at: at(0, 8, 30),
    timezone: 'Asia/Kuwait',
    detail_level: 'full',
    attendees: [],
    guests: [],
  },
  {
    event_id: 'medium-review',
    title: 'Hiring review',
    event_type: 'deadline',
    status: 'tentative',
    start_at: at(0, 9),
    end_at: at(0, 10, 30),
    timezone: 'Asia/Kuwait',
    detail_level: 'full',
    attendees: [{ user_id: 'aziz' }],
    guests: [],
  },
  {
    event_id: 'long-teams',
    title: 'Interview · Sara · Product Designer',
    event_type: 'interview',
    status: 'confirmed',
    start_at: at(0, 11),
    end_at: at(0, 14),
    timezone: 'Asia/Kuwait',
    detail_level: 'full',
    meeting_url: 'https://teams.microsoft.com/l/meetup-join/calendar-visual-proof',
    metadata: { candidate_name: 'Sara', job_title: 'Product Designer' },
    attendees: [{ user_id: 'aziz' }, { user_id: 'recruiter' }],
    guests: [{ display_name: 'Sara', guest_kind: 'candidate' }],
  },
  {
    event_id: 'overlap-interview',
    title: 'Interview · Omar · Finance Lead',
    event_type: 'interview',
    status: 'confirmed',
    start_at: at(1, 9),
    end_at: at(1, 12),
    timezone: 'Asia/Kuwait',
    detail_level: 'full',
    location: 'Kuwait City office',
    metadata: { candidate_name: 'Omar', job_title: 'Finance Lead' },
    attendees: [{ user_id: 'aziz' }],
    guests: [{ display_name: 'Omar' }],
  },
  {
    event_id: 'overlap-screen',
    title: 'Portfolio review',
    event_type: 'meeting',
    status: 'confirmed',
    start_at: at(1, 9, 30),
    end_at: at(1, 11),
    timezone: 'Asia/Kuwait',
    detail_level: 'full',
    meeting_url: 'https://meet.google.com/abc-defg-hij',
    attendees: [{ user_id: 'recruiter' }],
    guests: [],
  },
]

const json = (body) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
})

async function preparePage(origin, locale, viewport, empty = false) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
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
  await page.route('**/dashboard/calendar/team-scopes', (route) =>
    route.fulfill(
      json({
        ok: true,
        show_team_switch: false,
        has_team_scope: false,
        has_company_oversight: true,
        no_team_guidance: true,
        scopes: [],
        primary_org_scope_id: null,
      }),
    ),
  )
  await page.route('**/dashboard/calendar/events?**', (route) => {
    const url = new URL(route.request().url())
    route.fulfill(
      json({
        ok: true,
        company_code: COMPANY,
        scope: url.searchParams.get('scope') || 'mine',
        start: url.searchParams.get('start'),
        end: url.searchParams.get('end'),
        events: empty ? [] : fixtures,
        count: empty ? 0 : fixtures.length,
        team: { show_team_switch: false, has_team_scope: false, scopes: [] },
      }),
    )
  })
  await page.route('**/dashboard/calendar/events/*', (route) => {
    const id = route.request().url().split('/').pop()?.split('?')[0]
    const event = fixtures.find((item) => item.event_id === id)
    route.fulfill(json({ ok: true, event }))
  })
  await page.goto(`${origin}/dashboard/?page=calendar`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForTimeout(1400)
  const load = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if ((await load.count()) && (await load.first().isVisible().catch(() => false))) {
    await load.first().click({ timeout: 5000 }).catch(() => {})
    await page.waitForTimeout(1000)
  }
  await page.waitForSelector(empty ? '[data-testid="calendar-scope-mine"]' : 'text=Candidate check-in', { timeout: 60000 })
  if (empty) await page.waitForTimeout(800)
  return { context, page }
}

const beforeDir = resolve(__dirname, 'screenshots', 'before')
const afterDir = resolve(__dirname, 'screenshots', VARIANT ? `${VARIANT}-after` : 'after')
mkdirSync(beforeDir, { recursive: true })
mkdirSync(afterDir, { recursive: true })

// Apples-to-apples: same fixtures against current production UI, then local redesign.
{
  const { context, page } = await preparePage(PROD, 'en', { width: 1440, height: 1000 })
  await page.screenshot({ path: resolve(beforeDir, 'calendar-before-same-fixtures.png'), fullPage: true })
  await context.close()
}

const probes = {}

{
  const { context, page } = await preparePage(localOrigin, 'en', { width: 1440, height: 1000 })
  await page.screenshot({ path: resolve(afterDir, 'calendar-after-en-desktop.png'), fullPage: true })
  const cards = await page.locator('[data-testid^="calendar-timed-event-"]').evaluateAll((nodes) =>
    nodes.map((node) => ({
      id: node.getAttribute('data-testid'),
      density: node.getAttribute('data-density'),
      lane: node.getAttribute('data-lane'),
      text: node.textContent,
      height: Math.round(node.getBoundingClientRect().height),
    })),
  )
  probes.desktop = {
    cards,
    hasJoin: (await page.getByRole('button', { name: 'Join' }).count()) > 0,
    scopeSwitcherPresent: (await page.getByTestId('calendar-scope-mine').count()) > 0,
  }
  await context.close()
}

{
  const { context, page } = await preparePage(localOrigin, 'ar', { width: 1440, height: 1000 })
  await page.screenshot({ path: resolve(afterDir, 'calendar-after-ar-rtl.png'), fullPage: true })
  probes.rtl = {
    dir: await page.locator('section[dir]').first().getAttribute('dir'),
    myCalendar: (await page.getByTestId('calendar-scope-mine').textContent() || '').trim(),
    hasArabicJoin: (await page.getByRole('button', { name: 'انضمام' }).count()) > 0,
  }
  await context.close()
}

{
  const { context, page } = await preparePage(localOrigin, 'en', { width: 390, height: 844 })
  await page.screenshot({ path: resolve(afterDir, 'calendar-after-mobile.png'), fullPage: true })
  probes.mobile = {
    dayMode: (await page.getByRole('button', { name: 'Day' }).count()) > 0,
    hasTeams: (await page.getByText('Teams', { exact: true }).count()) > 0,
    hasJoin: (await page.getByRole('button', { name: 'Join' }).count()) > 0,
  }
  await context.close()
}

{
  const { context, page } = await preparePage(localOrigin, 'en', { width: 1440, height: 1000 }, true)
  await page.screenshot({ path: resolve(afterDir, 'calendar-after-empty-week.png'), fullPage: true })
  probes.empty = { noTimedCards: (await page.locator('[data-testid^="calendar-timed-event-"]').count()) === 0 }
  await context.close()
}

const desktopCards = probes.desktop.cards
const pass =
  desktopCards.some((card) => card.density === 'short') &&
  desktopCards.some((card) => card.density === 'medium') &&
  desktopCards.some((card) => card.density === 'long') &&
  desktopCards.some((card) => card.lane === '1/2') &&
  desktopCards.some((card) => card.lane === '2/2') &&
  probes.desktop.hasJoin &&
  probes.desktop.scopeSwitcherPresent &&
  probes.rtl.dir === 'rtl' &&
  probes.rtl.hasArabicJoin &&
  probes.mobile.hasTeams &&
  probes.mobile.hasJoin &&
  probes.empty.noTimedCards

writeFileSync(
  resolve(__dirname, 'verify', VARIANT ? `visual-probes-${VARIANT}.json` : 'visual-probes.json'),
  JSON.stringify({ verdict: pass ? 'PASS' : 'FAIL', probes }, null, 2),
)

await browser.close()
await new Promise((done) => server.close(done))
console.log(JSON.stringify({ verdict: pass ? 'PASS' : 'FAIL', probes }, null, 2))
process.exit(pass ? 0 : 1)
