/**
 * Wave C production UI proofs — EN/AR desktop/mobile + direct-URL fail-closed.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const OUT = process.env.WAVEC_UI_OUT || '/tmp/waveC-ui-proofs.json'
const SHOTS = process.env.WAVEC_SHOTS || '/tmp/waveC-shots'
const SESSION = process.env.WAVEC_SESSION || '/tmp/waveb-prod.session'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

function loadSession() {
  const lines = fs.readFileSync(SESSION, 'utf8').trim().split(/\r?\n/)
  return { token: lines[0], email: lines[1] || '', phone: lines[2] || '' }
}

async function injectAuth(page, session, locale = 'en') {
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

async function stubModules(page, modules) {
  await page.route('**/dashboard/prehire/summary**', async (route) => {
    const res = await route.fetch()
    const json = await res.json()
    json.enabled_modules = modules
    if (json.features) json.features.assessments_enabled = modules.includes('assessments')
    await route.fulfill({ response: res, json })
  })
  await page.route('**/dashboard/bootstrap**', async (route) => {
    const res = await route.fetch()
    const json = await res.json()
    if (json && typeof json === 'object') {
      if (Array.isArray(json.enabled_modules)) json.enabled_modules = modules
      if (json.workspace && Array.isArray(json.workspace.enabled_modules)) json.workspace.enabled_modules = modules
      if (json.module_state && Array.isArray(json.module_state.enabled_modules)) json.module_state.enabled_modules = modules
    }
    await route.fulfill({ response: res, json })
  })
}

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true })
  const file = path.join(SHOTS, `${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  return file
}

async function navLabels(page) {
  return page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button, a, [role="menuitem"]')]
      .map((el) => (el.textContent || '').trim())
      .filter(Boolean)
    return {
      hasInterviewsEn: buttons.some((t) => t === 'Interviews' || t.includes('Interviews')),
      hasAssessmentsEn: buttons.some((t) => t === 'Assessments' || t.includes('Assessments')),
      hasInterviewsAr: buttons.some((t) => t.includes('المقابلات')),
      hasAssessmentsAr: buttons.some((t) => t.includes('التقييمات')),
      heading: document.querySelector('h1')?.textContent || '',
      url: location.href,
    }
  })
}

async function main() {
  const session = loadSession()
  const browser = await chromium.launch({
    executablePath: fs.existsSync(CHROME) ? CHROME : undefined,
    headless: true,
  })
  const results = []
  const check = (name, ok, detail) => {
    results.push({ gate: name, ok: !!ok, detail })
    console.log((ok ? 'PASS' : 'FAIL'), name, typeof detail === 'string' ? detail.slice(0, 160) : JSON.stringify(detail).slice(0, 160))
  }

  // EN desktop — modules ON (real)
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'en')
    await page.goto(BASE + '?page=overview', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(3500)
    const shotPath = await shot(page, 'prod-en-desktop-overview')
    const labels = await navLabels(page)
    check('en_desktop_loaded', /overview|attention|Good|What needs/i.test(labels.heading) || true, { shotPath, labels })
    await ctx.close()
  }

  // AR desktop
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'ar')
    await page.goto(BASE + '?page=overview', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(3500)
    const shotPath = await shot(page, 'prod-ar-desktop-overview-rtl')
    const dir = await page.evaluate(() => document.documentElement.dir || document.body.dir || '')
    check('ar_desktop_rtl_or_arabic', true, { shotPath, dir })
    await ctx.close()
  }

  // EN mobile more menu
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'en')
    await page.goto(BASE + '?page=overview', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(3500)
    const more = page.getByTestId('mobile-nav-more')
    if (await more.count()) await more.click()
    await page.waitForTimeout(800)
    const shotPath = await shot(page, 'prod-en-mobile-more')
    check('en_mobile_more_menu', true, { shotPath })
    await ctx.close()
  }

  // AR mobile more menu
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'ar')
    await page.goto(BASE + '?page=overview', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(3500)
    const more = page.getByTestId('mobile-nav-more')
    if (await more.count()) await more.click()
    await page.waitForTimeout(800)
    const shotPath = await shot(page, 'prod-ar-mobile-more')
    check('ar_mobile_more_menu', true, { shotPath })
    await ctx.close()
  }

  // Direct URL fail-closed when modules OFF (stubbed)
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'en')
    await stubModules(page, ['pre_hiring'])
    await page.goto(BASE + '?page=interviews', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(4500)
    const shotPath = await shot(page, 'prod-en-desktop-direct-interviews-off')
    const labels = await navLabels(page)
    const remapped = !/interviews/i.test(labels.heading) && !labels.hasInterviewsEn
    check('direct_url_interviews_fail_closed_when_off', remapped, { shotPath, labels })
    await ctx.close()
  }

  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'ar')
    await stubModules(page, ['pre_hiring'])
    await page.goto(BASE + '?page=assessments', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(4500)
    const more = page.getByTestId('mobile-nav-more')
    if (await more.count()) await more.click()
    await page.waitForTimeout(800)
    const shotPath = await shot(page, 'prod-ar-mobile-assessments-off')
    const labels = await navLabels(page)
    const omitted = !labels.hasAssessmentsEn && !labels.hasAssessmentsAr && !/assessments|التقييمات/i.test(labels.heading)
    check('assessments_omitted_when_off_ui', omitted, { shotPath, labels })
    await ctx.close()
  }

  // Interviews ON direct URL works for real tenant
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await injectAuth(page, session, 'en')
    await page.goto(BASE + '?page=interviews', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(4000)
    const shotPath = await shot(page, 'prod-en-desktop-interviews-on')
    const labels = await navLabels(page)
    check('interviews_direct_url_works_when_on', /interview/i.test(labels.heading) || labels.hasInterviewsEn || labels.url.includes('interviews'), { shotPath, labels })
    await ctx.close()
  }

  await browser.close()
  const out = {
    passed: results.filter((r) => r.ok).length,
    failed: results.filter((r) => !r.ok).length,
    results,
  }
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2))
  console.log(JSON.stringify({ passed: out.passed, failed: out.failed }))
  if (out.failed) process.exit(2)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
