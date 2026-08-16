import { chromium } from 'playwright-core'
import { writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const OUT_DIR = '/Users/azizalmulla/Desktop/claw/ops/evidence/shifts-ux-closure-screenshots'
mkdirSync(OUT_DIR, { recursive: true })

async function capture() {
  const browser = await chromium.launch({
    executablePath: '/opt/homebrew/bin/chromium',
    headless: true,
  })

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
  })

  const page = await context.newPage()

  // Intercept API calls to mock clean shifts data
  await page.route('**/dashboard/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/bootstrap')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { name: 'Admin', role: 'owner' },
          company: { company_code: 'WATHEFNI', name: 'Wathefni Kuwait' },
          available_modules: [{ key: 'shifts', label: 'Shifts' }],
          enabled_modules: ['shifts'],
          permissions: ['posthire:shifts:read', 'posthire:shifts:write', 'posthire:shifts:manage'],
        }),
      })
    }
    if (url.includes('/prehire/candidates/feature')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ enabled: true }),
      })
    }
    return route.continue()
  })

  // 1. Dense Week EN
  console.log('Navigating to dashboard...')
  await page.goto('http://localhost:5199/dashboard/?page=shifts&lang=en', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)

  await page.screenshot({ path: join(OUT_DIR, '01-dense-week-en.png'), fullPage: false })
  console.log('Saved 01-dense-week-en.png')

  await browser.close()
}

capture().catch((err) => {
  console.error(err)
  process.exit(1)
})
