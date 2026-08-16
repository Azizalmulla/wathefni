/**
 * Wave 7 production UI qualification — Employees + Workforce against live dashboard.
 * Injects a short-lived owner session; does not mutate employee data.
 */
import { chromium } from 'playwright'
import { resolve } from 'path'
import { mkdirSync, writeFileSync } from 'fs'

const EVID = process.env.EVID
const TOKEN = process.env.TOKEN
const BASE = (process.env.BASE || 'https://api.wathefni.ai/dashboard').replace(/\/?$/, '/')
const EMAIL = process.env.EMAIL || ''

if (!EVID || !TOKEN) {
  console.error('EVID and TOKEN required')
  process.exit(2)
}

for (const folder of ['en-desktop', 'ar-desktop', 'en-mobile', 'ar-mobile']) {
  mkdirSync(resolve(EVID, 'screenshots', folder), { recursive: true })
}

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

async function openPage({ locale, viewport }) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  await page.addInitScript(({ token, locale, email }) => {
    localStorage.setItem('wathefni_dashboard_token', token)
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_recruiting_locale', locale)
    if (email) localStorage.setItem('wathefni_dashboard_email', email)
  }, { token: TOKEN, locale, email: EMAIL })
  return { context, page }
}

async function dismissLoad(page) {
  const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if (await loadNow.count()) {
    await loadNow.first().click().catch(() => {})
    await page.waitForTimeout(1800)
  }
}

async function probeShell(page) {
  return page.evaluate(() => {
    const main = document.querySelector('main')
    const body = document.body.innerText.replace(/\s+/g, ' ')
    return {
      url: location.href,
      mainDir: main?.getAttribute('dir') || null,
      htmlLang: document.documentElement.getAttribute('lang'),
      htmlDir: document.documentElement.getAttribute('dir'),
      hasWorkforceNav: /Workforce|القوى العاملة/i.test(body),
      hasEmployeesNav: /Employees|الموظفون/i.test(body),
      hasOrg: /Organization|الهيكل|Departments|الأقسام/i.test(body),
      hasLifecycle: /Lifecycle|دورة الحياة/i.test(body),
      hasRemediation: /Remediation|المعالجة|unclassified|غير مصنف/i.test(body),
      hasMigration: /Migration|الترحيل|batches|دفعات/i.test(body),
      hasRequests: /Requests|الطلبات|self-service|الخدمة الذاتية/i.test(body),
      hasDirectory: /Directory|الدليل|Employee|موظف/i.test(body),
      hasPermissionDenied: /permission|صلاحية|not allowed|غير مسموح|403|denied/i.test(body),
      hasEmpty: /No |empty|لا يوجد|لا توجد|nothing yet|لا شيء/i.test(body),
      hasError: /Something went wrong|خطأ|failed to load|تعذر/i.test(body),
      textSample: body.slice(0, 280),
      title: document.title,
    }
  })
}

async function shot({ locale, viewport, folder, file, pagePath }) {
  const { context, page } = await openPage({ locale, viewport })
  const t0 = Date.now()
  await page.goto(`${BASE}?page=${pagePath}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2200)
  await dismissLoad(page)
  const loadMs = Date.now() - t0
  await page.screenshot({ path: resolve(EVID, 'screenshots', folder, file), fullPage: false })
  const shell = await probeShell(page)
  const result = { folder, file, pagePath, loadMs, ...shell }
  console.log(folder, file, JSON.stringify({ loadMs, mainDir: shell.mainDir, hasWorkforceNav: shell.hasWorkforceNav, hasDirectory: shell.hasDirectory }))
  await context.close()
  return result
}

const desktop = { width: 1440, height: 900 }
const mobile = { width: 390, height: 844 }
const probes = []

probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'employees-directory.png', pagePath: 'employees' }))
probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'workforce-lifecycle.png', pagePath: 'workforce&workforce=lifecycle' }))
probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'workforce-remediation.png', pagePath: 'workforce&workforce=remediation' }))
probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'workforce-migration.png', pagePath: 'workforce&workforce=migration' }))
probes.push(await shot({ locale: 'en', viewport: desktop, folder: 'en-desktop', file: 'workforce-requests.png', pagePath: 'workforce&workforce=requests' }))
probes.push(await shot({ locale: 'ar', viewport: desktop, folder: 'ar-desktop', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'ar', viewport: desktop, folder: 'ar-desktop', file: 'employees-directory.png', pagePath: 'employees' }))
probes.push(await shot({ locale: 'en', viewport: mobile, folder: 'en-mobile', file: 'employees-directory.png', pagePath: 'employees' }))
probes.push(await shot({ locale: 'en', viewport: mobile, folder: 'en-mobile', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'ar', viewport: mobile, folder: 'ar-mobile', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'ar', viewport: mobile, folder: 'ar-mobile', file: 'workforce-remediation.png', pagePath: 'workforce&workforce=remediation' }))

// Deep link + browser refresh (employee query + workforce section)
{
  const { context, page } = await openPage({ locale: 'en', viewport: desktop })
  const deep = `${BASE}?page=workforce&workforce=remediation`
  await page.goto(deep, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2200)
  await dismissLoad(page)
  const before = await probeShell(page)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2200)
  await dismissLoad(page)
  const after = await probeShell(page)
  await page.screenshot({ path: resolve(EVID, 'screenshots/en-desktop/workforce-remediation-refresh.png'), fullPage: false })
  probes.push({
    folder: 'en-desktop',
    file: 'workforce-remediation-refresh.png',
    kind: 'deep_link_refresh',
    beforeUrl: before.url,
    afterUrl: after.url,
    beforeHasRemediation: before.hasRemediation,
    afterHasRemediation: after.hasRemediation,
    refreshPreserved: /workforce=remediation/.test(after.url) && after.hasRemediation,
  })
  console.log('deep_link_refresh', JSON.stringify(probes[probes.length - 1]))
  await context.close()
}

// Employees deep link with employee= param survives refresh
{
  const { context, page } = await openPage({ locale: 'en', viewport: desktop })
  await page.goto(`${BASE}?page=employees`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2500)
  await dismissLoad(page)
  // pick first employee key from row click / data attribute if present
  const empKey = await page.evaluate(() => {
    const el = document.querySelector('[data-employee-key], [data-testid*="employee"]')
    return el?.getAttribute('data-employee-key') || el?.getAttribute('data-testid') || null
  })
  // Navigate via known real key is forbidden for mutation; use URL shape only if we found a key
  if (empKey && /^WATHEFNI-/.test(empKey)) {
    await page.goto(`${BASE}?page=employees&employee=${encodeURIComponent(empKey)}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(2200)
    await dismissLoad(page)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    await dismissLoad(page)
    const url = page.url()
    probes.push({
      kind: 'employee_deep_link_refresh',
      empKey,
      url,
      preserved: url.includes(`employee=${encodeURIComponent(empKey)}`) || url.includes(empKey),
    })
    await page.screenshot({ path: resolve(EVID, 'screenshots/en-desktop/employee-profile-deeplink.png'), fullPage: false })
  } else {
    probes.push({ kind: 'employee_deep_link_refresh', empKey, skipped: true, note: 'no data-employee-key in DOM; directory screenshot still captured' })
  }
  console.log('employee_deep_link', JSON.stringify(probes[probes.length - 1]))
  await context.close()
}

// Light a11y: landmark + heading presence on workforce
{
  const { context, page } = await openPage({ locale: 'en', viewport: desktop })
  await page.goto(`${BASE}?page=workforce`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2200)
  await dismissLoad(page)
  const a11y = await page.evaluate(() => {
    const mains = document.querySelectorAll('main').length
    const navs = document.querySelectorAll('nav').length
    const h1 = document.querySelectorAll('h1').length
    const buttons = [...document.querySelectorAll('button')].slice(0, 40).map((b) => ({
      text: (b.innerText || '').trim().slice(0, 40),
      aria: b.getAttribute('aria-label'),
      disabled: b.disabled,
    }))
    return { mains, navs, h1, buttonSample: buttons.filter((b) => b.text || b.aria).slice(0, 12) }
  })
  probes.push({ kind: 'a11y_light', ...a11y })
  console.log('a11y_light', JSON.stringify(a11y))
  await context.close()
}

const arProbes = probes.filter((p) => p.folder?.startsWith('ar-'))
const rtlOk = arProbes.length === 0 || arProbes.every((p) => p.mainDir === 'rtl')
const workforceOk = probes.filter((p) => String(p.pagePath || '').startsWith('workforce')).every((p) => p.hasWorkforceNav)
const refresh = probes.find((p) => p.kind === 'deep_link_refresh')
const perf = {
  maxLoadMs: Math.max(...probes.filter((p) => p.loadMs).map((p) => p.loadMs)),
  medianLoadMs: (() => {
    const xs = probes.filter((p) => p.loadMs).map((p) => p.loadMs).sort((a, b) => a - b)
    return xs[Math.floor(xs.length / 2)] || null
  })(),
}

const summary = {
  probeCount: probes.length,
  rtlOk,
  workforceOk,
  refreshPreserved: Boolean(refresh?.refreshPreserved),
  perf,
  screenshots: probes.filter((p) => p.file).map((p) => `${p.folder}/${p.file}`),
}

writeFileSync(resolve(EVID, 'screenshots/prod-ui-probes.json'), JSON.stringify({ summary, probes }, null, 2))
console.log(JSON.stringify(summary, null, 2))
await browser.close()

if (!rtlOk || !workforceOk || !refresh?.refreshPreserved) process.exit(1)
