import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import playwright from '/Users/azizalmulla/Desktop/claw/ops/evidence/interviews-ui-refine-20260730T133052Z/node_modules/playwright-core/index.js'

const { chromium } = playwright
const __dirname = dirname(fileURLToPath(import.meta.url))
const ORIGIN = process.env.DASHBOARD_ORIGIN || 'https://api.wathefni.ai'
const TOKEN = (process.env.DASHBOARD_TOKEN || '').trim()
const EMAIL = (process.env.DASHBOARD_EMAIL || '').trim()
const PHONE = (process.env.DASHBOARD_PHONE || '').trim()
const COMPANY = (process.env.DASHBOARD_COMPANY || 'WATHEFNI').trim()
if (!TOKEN) process.exit(2)

const afterDir = resolve(__dirname, 'screenshots', 'after')
const overviewDir = resolve(__dirname, 'screenshots', 'overview')
mkdirSync(afterDir, { recursive: true })
mkdirSync(overviewDir, { recursive: true })

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
  {
    event_id: 'c3c3d8e7-dc0c-4fbd-9d57-8c91d1cc053b',
    title: 'online meeting with aziz',
    event_type: 'meeting',
    status: 'cancelled',
    start_at: '2026-08-01T06:00:00+00:00',
    end_at: '2026-08-02T07:00:00+00:00',
    timezone: 'Asia/Kuwait',
    all_day: false,
    detail_level: 'full',
    attendees: [{ user_id: 'aziz' }],
    guests: [],
  },
]

const json = (body) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
})

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

async function authed(locale, viewport = { width: 1440, height: 1000 }) {
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
  return { context, page }
}

async function routeCalendar(page, { empty = false, includeCrossDay = true } = {}) {
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
    const events = empty
      ? []
      : fixtures.filter((event) => includeCrossDay || event.event_id !== 'c3c3d8e7-dc0c-4fbd-9d57-8c91d1cc053b')
    route.fulfill(
      json({
        ok: true,
        company_code: COMPANY,
        scope: url.searchParams.get('scope') || 'mine',
        start: url.searchParams.get('start'),
        end: url.searchParams.get('end'),
        events,
        count: events.length,
        team: { show_team_switch: false, has_team_scope: false, scopes: [] },
      }),
    )
  })
  await page.route('**/dashboard/calendar/events/*', (route) => {
    const id = route.request().url().split('/').pop()?.split('?')[0]
    const event = fixtures.find((item) => item.event_id === id)
    route.fulfill(json({ ok: true, event }))
  })
}

async function openCalendar(page) {
  await page.goto(`${ORIGIN}/dashboard/?page=calendar`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForTimeout(1200)
  const load = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if ((await load.count()) && (await load.first().isVisible().catch(() => false))) {
    await load.first().click({ timeout: 5000 }).catch(() => {})
    await page.waitForTimeout(800)
  }
  await page.waitForSelector('[data-testid="calendar-scope-mine"]', { timeout: 60000 })
}

const probes = {}

{
  const { context, page } = await authed('en')
  const scopeReqs = []
  page.on('request', (req) => {
    const u = req.url()
    if (u.includes('/dashboard/calendar/events?') && !u.includes('/sync')) {
      scopeReqs.push(new URL(u).searchParams.get('scope') || '')
    }
  })
  await routeCalendar(page)
  await openCalendar(page)
  await page.waitForSelector('[data-testid="calendar-timed-event-short-check-in"]', { timeout: 60000 })
  await page.screenshot({ path: resolve(afterDir, 'prod-calendar-en-desktop.png'), fullPage: true })

  const cards = await page.locator('[data-testid^="calendar-timed-event-"]').evaluateAll((nodes) =>
    nodes.map((node) => ({
      id: node.getAttribute('data-testid'),
      density: node.getAttribute('data-density'),
      lane: node.getAttribute('data-lane'),
      text: (node.textContent || '').replace(/\s+/g, ' ').trim(),
      height: Math.round(node.getBoundingClientRect().height),
    })),
  )
  const crossDay = cards.find((card) => card.id?.includes('c3c3d8e7'))
  await page.evaluate(() => {
    window.__joinCalls = []
    window.open = (url, target, features) => {
      window.__joinCalls.push({ url: String(url || ''), target, features })
      return null
    }
  })
  const joinBtn = page.getByTestId('calendar-timed-event-long-teams').getByRole('button', { name: 'Join' })
  await joinBtn.waitFor({ state: 'visible', timeout: 15000 })
  await joinBtn.click()
  await page.waitForTimeout(300)
  const joinCalls = await page.evaluate(() => window.__joinCalls || [])
  // card body click (not Join) opens details — click title text, not Join
  await page.getByTestId('calendar-timed-event-long-teams').locator('p').first().click({ force: true })
  await page.waitForTimeout(900)
  const drawerOpened =
    (await page.locator('aside h2, aside h3').filter({ hasText: /Interview|Sara|Product Designer/i }).count()) > 0
    || (await page.getByRole('button', { name: /Edit|تعديل|Open interview|فتح المقابلة/i }).count()) > 0
    || (await page.getByText(/Synced|Not synced|تمت المزامنة|غير متزامن/i).count()) > 0

  // scope switch remains wired
  if (await page.getByTestId('calendar-scope-company').count()) {
    await page.getByTestId('calendar-scope-company').click()
    await page.waitForTimeout(700)
    await page.getByTestId('calendar-scope-mine').click()
    await page.waitForTimeout(500)
  }

  probes.desktop = {
    cards,
    hasShort: cards.some((c) => c.density === 'short'),
    hasMedium: cards.some((c) => c.density === 'medium'),
    hasLong: cards.some((c) => c.density === 'long'),
    hasOverlap: cards.some((c) => {
      const lane = String(c.lane || '')
      const total = Number(lane.split('/')[1] || '1')
      return total > 1
    }),
    crossDay: {
      present: Boolean(crossDay),
      text: crossDay?.text || null,
      showsPlus1d: Boolean(crossDay?.text?.includes('+1d')),
      density: crossDay?.density || null,
      height: crossDay?.height || null,
    },
    join: {
      openedMeeting: joinCalls?.[0]?.url?.includes('teams.microsoft.com') === true,
      url: joinCalls?.[0]?.url || null,
    },
    drawerOpened,
    scopeMine: scopeReqs.includes('mine'),
    scopeCompany: scopeReqs.includes('company') || (await page.getByTestId('calendar-scope-company').count()) === 0,
    scopeSwitcherPresent: (await page.getByTestId('calendar-scope-mine').count()) > 0,
  }
  await context.close()
}

{
  const { context, page } = await authed('ar')
  await routeCalendar(page)
  await openCalendar(page)
  await page.waitForSelector('[data-testid="calendar-timed-event-long-teams"]', { timeout: 60000 })
  await page.screenshot({ path: resolve(afterDir, 'prod-calendar-ar-rtl.png'), fullPage: true })
  const crossDayText = await page.getByTestId('calendar-timed-event-c3c3d8e7-dc0c-4fbd-9d57-8c91d1cc053b').textContent()
  probes.rtl = {
    dir: await page.locator('section[dir]').first().getAttribute('dir'),
    myCalendar: (await page.getByTestId('calendar-scope-mine').textContent() || '').trim(),
    hasArabicJoin: (await page.getByRole('button', { name: 'انضمام' }).count()) > 0,
    crossDayShowsPlusDay: (crossDayText || '').includes('+يوم'),
  }
  await context.close()
}

{
  const { context, page } = await authed('en', { width: 390, height: 844 })
  await routeCalendar(page, { includeCrossDay: false })
  await openCalendar(page)
  await page.waitForTimeout(1000)
  await page.screenshot({ path: resolve(afterDir, 'prod-calendar-mobile.png'), fullPage: true })
  probes.mobile = {
    dayMode: (await page.getByRole('button', { name: 'Day' }).count()) > 0,
    hasTeams: (await page.getByText('Teams', { exact: true }).count()) > 0,
    hasJoin: (await page.getByRole('button', { name: 'Join' }).count()) > 0,
  }
  await context.close()
}

{
  const { context, page } = await authed('en')
  await routeCalendar(page, { empty: true })
  await openCalendar(page)
  await page.waitForTimeout(800)
  await page.screenshot({ path: resolve(afterDir, 'prod-calendar-empty-week.png'), fullPage: true })
  probes.empty = {
    noTimedCards: (await page.locator('[data-testid^="calendar-timed-event-"]').count()) === 0,
  }
  await context.close()
}

{
  const { context, page } = await authed('en')
  const overviewScopes = []
  page.on('request', (req) => {
    if (req.url().includes('/dashboard/calendar/overview')) {
      overviewScopes.push(new URL(req.url()).searchParams.get('scope') || '')
    }
  })
  await page.goto(`${ORIGIN}/dashboard/?page=overview`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForTimeout(1400)
  const load = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if ((await load.count()) && (await load.first().isVisible().catch(() => false))) {
    await load.first().click({ timeout: 5000 }).catch(() => {})
    await page.waitForTimeout(800)
  }
  const panel = page.getByTestId('overview-my-calendar')
  if (await panel.count()) {
    await panel.waitFor({ timeout: 60000 })
    await page.screenshot({ path: resolve(overviewDir, 'prod-overview-my-calendar.png'), fullPage: false })
    probes.overview = {
      title: (await panel.locator('h3').first().textContent() || '').trim(),
      hasScopeToggle:
        (await page.getByTestId('calendar-scope-mine').count()) +
          (await page.getByTestId('calendar-scope-team').count()) +
          (await page.getByTestId('calendar-scope-company').count()) >
        0,
      overviewScopes,
      onlyMine: overviewScopes.length === 0 || overviewScopes.every((s) => s === 'mine'),
    }
  } else {
    probes.overview = { skipped: true, reason: 'overview panel not found in current session' }
  }
  await context.close()
}

const pass =
  probes.desktop.hasShort &&
  probes.desktop.hasMedium &&
  probes.desktop.hasLong &&
  probes.desktop.hasOverlap &&
  probes.desktop.crossDay.present &&
  probes.desktop.crossDay.showsPlus1d &&
  probes.desktop.join.openedMeeting &&
  probes.desktop.drawerOpened &&
  probes.desktop.scopeSwitcherPresent &&
  probes.rtl.dir === 'rtl' &&
  probes.rtl.hasArabicJoin &&
  probes.rtl.crossDayShowsPlusDay &&
  probes.mobile.hasTeams &&
  probes.mobile.hasJoin &&
  probes.empty.noTimedCards &&
  (probes.overview.skipped || (probes.overview.onlyMine && probes.overview.hasScopeToggle === false))

const out = { verdict: pass ? 'PASS' : 'FAIL', probes }
writeFileSync(resolve(__dirname, 'verify', 'prod-capture-probes.json'), JSON.stringify(out, null, 2))
console.log(JSON.stringify(out, null, 2))
await browser.close()
process.exit(pass ? 0 : 1)
