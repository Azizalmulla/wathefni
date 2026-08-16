import { chromium } from 'playwright'
import { resolve } from 'path'
import { mkdirSync } from 'fs'

const EVID = process.env.EVID
const TOKEN = process.env.TOKEN
const BASE = process.env.BASE || 'http://127.0.0.1:18011'

mkdirSync(resolve(EVID, 'screenshots/en-desktop'), { recursive: true })
mkdirSync(resolve(EVID, 'screenshots/ar-desktop'), { recursive: true })
mkdirSync(resolve(EVID, 'screenshots/en-mobile'), { recursive: true })
mkdirSync(resolve(EVID, 'screenshots/ar-mobile'), { recursive: true })

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

async function shot({ locale, viewport, folder, file, pagePath }) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  await page.addInitScript(({ token, locale }) => {
    localStorage.setItem('wathefni_dashboard_token', token)
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_recruiting_locale', locale)
  }, { token: TOKEN, locale })
  await page.goto(`${BASE}/dashboard/?page=${pagePath}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(2500)
  // dismiss load blockers
  const loadNow = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if (await loadNow.count()) {
    await loadNow.first().click().catch(() => {})
    await page.waitForTimeout(2000)
  }
  await page.screenshot({ path: resolve(EVID, 'screenshots', folder, file), fullPage: false })
  const probe = await page.evaluate(() => ({
    dir: document.documentElement.getAttribute('dir'),
    lang: document.documentElement.getAttribute('lang'),
    hasWorkforce: /workforce|القوى العاملة|Organization|الهيكل|Employees 360|موظفون 360/i.test(document.body.innerText),
    hasDirectory: /Directory|الدليل|Employee|موظف/i.test(document.body.innerText),
    textSample: document.body.innerText.replace(/\s+/g, ' ').slice(0, 240),
  }))
  console.log(folder, file, JSON.stringify(probe))
  await context.close()
  return probe
}

const probes = []
probes.push(await shot({ locale: 'en', viewport: { width: 1440, height: 900 }, folder: 'en-desktop', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'en', viewport: { width: 1440, height: 900 }, folder: 'en-desktop', file: 'workforce-requests.png', pagePath: 'workforce&workforce=requests' }))
probes.push(await shot({ locale: 'en', viewport: { width: 1440, height: 900 }, folder: 'en-desktop', file: 'employees-directory.png', pagePath: 'employees' }))
probes.push(await shot({ locale: 'ar', viewport: { width: 1440, height: 900 }, folder: 'ar-desktop', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'ar', viewport: { width: 390, height: 844 }, folder: 'ar-mobile', file: 'workforce-organization.png', pagePath: 'workforce' }))
probes.push(await shot({ locale: 'en', viewport: { width: 390, height: 844 }, folder: 'en-mobile', file: 'employees-directory.png', pagePath: 'employees' }))
probes.push(await shot({ locale: 'en', viewport: { width: 1440, height: 900 }, folder: 'en-desktop', file: 'workforce-remediation.png', pagePath: 'workforce&workforce=remediation' }))
probes.push(await shot({ locale: 'en', viewport: { width: 1440, height: 900 }, folder: 'en-desktop', file: 'workforce-lifecycle.png', pagePath: 'workforce&workforce=lifecycle' }))

const rtlOk = probes.filter(p => p && p.lang === 'ar').every(p => p.dir === 'rtl')
const enOk = probes.filter(p => p && p.lang === 'en').every(p => p.dir === 'ltr' || !p.dir || p.dir === 'ltr')
console.log(JSON.stringify({ rtlOk, probeCount: probes.length }, null, 2))
await browser.close()
if (!rtlOk) process.exit(1)
