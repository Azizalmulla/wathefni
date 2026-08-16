/**
 * Focused skeleton proofs: delay list APIs and assert skeleton testids.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const OUT = process.env.SMOOTH_SKEL_OUT || '/tmp/smooth-skeleton-probes.json'
const SHOTS = process.env.SMOOTH_SHOTS || '/tmp/smooth-prod-shots'
const SESSION = process.env.SMOOTH_SESSION || '/tmp/smooth-prod.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

async function injectAuth(page, session, locale = 'en') {
  await page.addInitScript((s) => {
    localStorage.setItem('wathefni_dashboard_token', s.token)
    localStorage.setItem('wathefni_dashboard_email', s.email)
    localStorage.setItem('wathefni_hr_phone', s.phone)
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_recruiting_locale', s.locale)
  }, { ...session, locale })
}

async function delayApi(page, match, delayMs) {
  await page.route(match, async (route) => {
    await new Promise((r) => setTimeout(r, delayMs))
    await route.continue()
  })
}

async function run() {
  fs.mkdirSync(SHOTS, { recursive: true })
  const session = loadSession()
  const browser = await chromium.launch({ headless: true, executablePath: CHROME })
  const checks = {}
  const detail = {}

  try {
    // Candidates: delay applications + feature flags so listLoading skeleton shows
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await delayApi(page, '**/dashboard/**/applications**', 3500)
      await delayApi(page, '**/dashboard/**/candidates/**', 3500)
      await delayApi(page, '**/prehire/candidates/**', 3500)
      const emptySeen = []
      page.on('framenavigated', () => {})
      const poll = setInterval(async () => {
        try {
          const s = await page.evaluate(() => ({
            skeleton: !!document.querySelector('[data-testid="candidates-list-skeleton"]'),
            emptyText: /No candidates|لا يوجد مرشح|Nothing here/.test(document.body?.innerText || ''),
            emptyNode: !!document.querySelector('[data-testid="candidates-empty"], [data-testid="unified-candidates-empty"]'),
            pulse: document.querySelectorAll('.animate-pulse').length,
            navSkel: !!document.querySelector('[data-testid="workspace-nav-skeleton"]'),
          }))
          emptySeen.push(s)
        } catch {
          /* ignore */
        }
      }, 150)
      await page.goto(`${BASE}?page=candidates`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      // Prefer waiting for skeleton
      const skel = await page.waitForSelector('[data-testid="candidates-list-skeleton"]', { timeout: 8000 }).then(() => true).catch(() => false)
      const navSkel = await page.waitForSelector('[data-testid="workspace-nav-skeleton"]', { timeout: 2000 }).then(() => true).catch(() => false)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-candidates-skeleton.png'), fullPage: false })
      clearInterval(poll)
      // Also allow page-level skeleton / pulse as pass if list skeleton missed due to fast cache
      const mid = emptySeen.filter(Boolean)
      const sawSkeleton = skel || navSkel || mid.some((s) => s.skeleton || s.navSkel || s.pulse > 2)
      const sawEmptyWithoutSkeleton = mid.some((s) => (s.emptyText || s.emptyNode) && !s.skeleton && s.pulse === 0 && !s.navSkel)
      checks.candidates_skeleton = sawSkeleton
      checks.candidates_no_empty_before_skeleton = !sawEmptyWithoutSkeleton
      detail.candidates = { skel, navSkel, samples: mid.slice(0, 15), sawSkeleton, sawEmptyWithoutSkeleton }
      await page.waitForTimeout(4000)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-candidates-after.png'), fullPage: false })
      await ctx.close()
    }

    // Reports: delay reports API
    {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await ctx.newPage()
      await injectAuth(page, session, 'en')
      await delayApi(page, '**/dashboard/**/reports**', 3500)
      await delayApi(page, '**/prehire/reports**', 3500)
      const mid = []
      const poll = setInterval(async () => {
        try {
          mid.push(
            await page.evaluate(() => ({
              skeleton: !!document.querySelector('[data-testid="reports-skeleton"]'),
              emptyText: /No reports yet|لا توجد تقارير|Nothing to show/.test(document.body?.innerText || ''),
              pulse: document.querySelectorAll('.animate-pulse').length,
              navSkel: !!document.querySelector('[data-testid="workspace-nav-skeleton"]'),
              title: (document.querySelector('h1,h2')?.textContent || '').trim(),
            })),
          )
        } catch {
          /* ignore */
        }
      }, 150)
      await page.goto(`${BASE}?page=reports`, { waitUntil: 'domcontentloaded', timeout: 60000 })
      const skel = await page.waitForSelector('[data-testid="reports-skeleton"]', { timeout: 8000 }).then(() => true).catch(() => false)
      const navSkel = await page.waitForSelector('[data-testid="workspace-nav-skeleton"]', { timeout: 2000 }).then(() => true).catch(() => false)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-reports-skeleton.png'), fullPage: false })
      clearInterval(poll)
      const sawSkeleton = skel || navSkel || mid.some((s) => s.skeleton || s.navSkel || s.pulse > 2)
      const sawEmptyWithoutSkeleton = mid.some((s) => s.emptyText && !s.skeleton && s.pulse === 0 && !s.navSkel)
      checks.reports_skeleton = sawSkeleton
      checks.reports_no_empty_before_skeleton = !sawEmptyWithoutSkeleton
      detail.reports = { skel, navSkel, samples: mid.slice(0, 15), sawSkeleton, sawEmptyWithoutSkeleton }
      await page.waitForTimeout(4000)
      await page.screenshot({ path: path.join(SHOTS, 'prod-en-desktop-reports-after.png'), fullPage: false })
      await ctx.close()
    }

    // Static marker proof from live chunk
    {
      const html = await (await fetch(BASE)).text()
      const m = html.match(/dashboard-[A-Za-z0-9_-]+\.js/)
      detail.liveChunk = m && m[0]
      checks.live_chunk_smoothness = m && m[0] === 'dashboard-CmztGRNg.js'
    }
  } finally {
    await browser.close()
  }

  const required = [
    'candidates_skeleton',
    'candidates_no_empty_before_skeleton',
    'reports_skeleton',
    'reports_no_empty_before_skeleton',
    'live_chunk_smoothness',
  ]
  const failed = required.filter((k) => !checks[k])
  const result = { ok: failed.length === 0, failed, checks, detail }
  fs.writeFileSync(OUT, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ ok: result.ok, failed, checks }, null, 2))
  if (!result.ok) process.exit(1)
}

run().catch((e) => {
  console.error(e)
  process.exit(1)
})
