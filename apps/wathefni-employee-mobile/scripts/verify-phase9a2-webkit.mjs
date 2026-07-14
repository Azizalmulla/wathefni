import { webkit, devices } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const baseUrl = process.env.PREVIEW_BASE_URL || 'http://127.0.0.1:8091'
const outputDir = path.resolve('docs/phase9a2-preview')
mkdirSync(outputDir, { recursive: true })

const screens = [
  ['activation', 'default'],
  ['home', 'multi'],
  ['onboarding', 'multi'],
  ['inbox', 'default'],
  ['leave', 'default'],
  ['leave-request', 'default'],
  ['shifts', 'default'],
  ['attendance', 'default'],
  ['documents', 'default'],
  ['profile', 'default'],
  ['settings', 'default'],
  ['privacy-support', 'default'],
  ['not-found', 'default'],
  ['offline', 'default'],
  ['session-expired', 'default'],
  ['employee-inactive', 'default'],
  ['company-disabled', 'default'],
  ['company-archived', 'default'],
  ['module-removed', 'default'],
  ['app-unavailable', 'default'],
]

const results = []
const browser = await webkit.launch({ headless: true })
try {
  const context = await browser.newContext({
    ...devices['iPhone 13'],
    viewport: { width: 393, height: 852 },
    deviceScaleFactor: 1,
  })
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'standalone', { get: () => true })
  })
  const page = await context.newPage()
  const pageErrors = []
  const failedAssets = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    if (/\.(js|ttf|otf|woff2?)(\?|$)/.test(request.url())) {
      failedAssets.push(`${request.failure()?.errorText || 'failed'} ${request.url()}`)
    }
  })

  for (const [screen, scenario] of screens) {
    for (const locale of ['en', 'ar']) {
      pageErrors.length = 0
      failedAssets.length = 0
      const query = `screen=${screen}&locale=${locale}&scenario=${scenario}`
      await page.goto(`${baseUrl}/design-preview?${query}`, { waitUntil: 'networkidle' })
      await page.waitForTimeout(350)
      await page.reload({ waitUntil: 'networkidle' })
      await page.waitForTimeout(500)
      const label = await page.locator(`[aria-label="preview-${screen}-${locale}-${scenario}"]`).count()
      const boundary = await page.locator('[aria-label="preview-error-boundary"]').count()
      const textLength = (await page.locator('body').innerText()).trim().length
      const pass = label === 1 && boundary === 0 && textLength > 20 && pageErrors.length === 0 && failedAssets.length === 0
      results.push({ screen, locale, scenario, pass, label, boundary, textLength, pageErrors: [...pageErrors], failedAssets: [...failedAssets] })
      console.log(`${pass ? 'PASS' : 'FAIL'} ${screen}-${locale}`)
    }
  }

  pageErrors.length = 0
  await page.goto(`${baseUrl}/design-preview?screen=invalid&locale=invalid&scenario=invalid`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  const fallback = await page.locator('[aria-label="preview-activation-en-default"]').count()
  results.push({
    screen: 'invalid-params',
    locale: 'invalid',
    scenario: 'invalid',
    pass: fallback === 1 && pageErrors.length === 0,
    fallback,
    pageErrors: [...pageErrors],
  })

  await page.goto(`${baseUrl}/design-preview?screen=settings&locale=en&scenario=default`, { waitUntil: 'networkidle' })
  await page.getByLabel('AR', { exact: true }).click()
  await page.waitForTimeout(350)
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  const localePreserved = page.url().includes('locale=ar')
    && await page.locator('[aria-label="preview-settings-ar-default"]').count() === 1
  results.push({ screen: 'interactive-locale-refresh', pass: localePreserved, url: page.url() })

  const beforeOffline = page.url()
  await context.setOffline(true)
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 5_000 }).catch(() => undefined)
  await context.setOffline(false)
  await page.goto(beforeOffline, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  const reconnectPass = await page.locator('[aria-label="preview-settings-ar-default"]').count() === 1
  results.push({ screen: 'offline-reconnect', pass: reconnectPass, url: page.url() })

  await context.close()
} finally {
  await browser.close()
}

const report = {
  generated_at: new Date().toISOString(),
  engine: 'Playwright WebKit / iPhone 13 / standalone mode',
  passed: results.filter((result) => result.pass).length,
  total: results.length,
  results,
}
writeFileSync(path.join(outputDir, 'webkit-verification.json'), `${JSON.stringify(report, null, 2)}\n`)

const failures = results.filter((result) => !result.pass)
if (failures.length) {
  console.error(`\n${failures.length} WebKit verification failures`)
  process.exitCode = 1
} else {
  console.log(`\nWebKit matrix: GREEN (${report.passed}/${report.total})`)
}
