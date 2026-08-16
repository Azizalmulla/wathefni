import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, readFileSync } from 'fs'
import { resolve } from 'path'

const root = '/Users/azizalmulla/Desktop/claw/ops/evidence/waveD-phase4-inbound-alias-admit-ux-deploy-20260801T152150Z'
const shots = resolve(root, 'screenshots')
mkdirSync(shots, { recursive: true })
const token = readFileSync('/tmp/d4-session.token', 'utf8').trim()
const base = 'https://api.wathefni.ai/dashboard/'

const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})

const cases = []
async function run(name, locale, viewport) {
  const context = await browser.newContext({ viewport })
  const page = await context.newPage()
  await page.addInitScript(({ token, locale }) => {
    localStorage.setItem('wathefni_dashboard_token', token)
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_dashboard_email', 'azizalmulla16@gmail.com')
    localStorage.setItem('wathefni_recruiting_locale', locale)
  }, { token, locale })
  await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 120000 })
  await page.waitForTimeout(3500)
  // Settings
  await page.getByText(/Settings|الإعدادات/i).first().click({ timeout: 15000 }).catch(()=>{})
  await page.waitForTimeout(2500)
  await page.getByText(/Email & document intake|استقبال البريد/i).first().scrollIntoViewIfNeeded().catch(()=>{})
  await page.waitForTimeout(500)
  await page.screenshot({ path: resolve(shots, name + '-settings.png'), fullPage: true })
  const settingsBody = await page.locator('body').innerText()

  // Candidates
  await page.getByText(/Candidates|المرشح/i).first().click({ timeout: 15000 }).catch(()=>{})
  await page.waitForTimeout(3000)
  await page.getByText(/Held CVs waiting|السير|بانتظار وظيفة|معلّق/i).first().scrollIntoViewIfNeeded().catch(()=>{})
  await page.waitForTimeout(500)
  await page.screenshot({ path: resolve(shots, name + '-candidates.png'), fullPage: true })
  const candBody = await page.locator('body').innerText()
  const htmlLang = await page.locator('html').getAttribute('lang')
  const dir = await page.locator('html').getAttribute('dir')
  const signals = {
    htmlLang, dir,
    rtl: dir === 'rtl' || /[\u0600-\u06FF]/.test(settingsBody.slice(0,200)),
    hasIntakeCard: /Email & document intake|استقبال البريد/.test(settingsBody),
    hasGeneral: /General address|عنوان عام/.test(settingsBody),
    hasJobAlias: /Job-specific alias|اسم مستعار لوظيفة/.test(settingsBody),
    hasNeedsJob: /Needs a job|تحتاج وظيفة/.test(settingsBody + candBody),
    hasBound: /Bound to a job|مربوطة بوظيفة/.test(settingsBody),
    hasHeld: /Held CVs waiting|بانتظار|معلّق/.test(candBody),
    hasIdentity: /Identity review|مراجعة الهوية/.test(candBody + settingsBody),
    hasQuarantine: /Quarantined|محجور/.test(candBody + settingsBody),
    noIntakeOps: !/Intake Operations|IntakeOperations/.test(settingsBody + candBody),
    settingsSnippet: settingsBody.replace(/\s+/g,' ').slice(0,350),
    candSnippet: candBody.replace(/\s+/g,' ').slice(0,350),
  }
  signals.ok = Boolean(signals.hasIntakeCard && signals.noIntakeOps && (signals.hasGeneral || signals.hasJobAlias))
  cases.push({ name, locale, viewport, ok: signals.ok, signals })
  console.log(signals.ok ? 'PASS' : 'FAIL', name, JSON.stringify({hasIntakeCard:signals.hasIntakeCard,hasGeneral:signals.hasGeneral,hasJobAlias:signals.hasJobAlias,hasHeld:signals.hasHeld,noIntakeOps:signals.noIntakeOps,rtl:signals.rtl}))
  await context.close()
}

await run('prod-en-desktop', 'en', { width: 1440, height: 900 })
await run('prod-ar-desktop', 'ar', { width: 1440, height: 900 })
await run('prod-en-mobile', 'en', { width: 390, height: 844 })
await run('prod-ar-mobile', 'ar', { width: 390, height: 844 })
await browser.close()
const passed = cases.filter(c => c.ok).length
const failed = cases.length - passed
writeFileSync(resolve(root, 'verify/prod-ui-proofs.json'), JSON.stringify({ passed, failed, cases }, null, 2) + '\n')
console.log(JSON.stringify({ passed, failed }))
