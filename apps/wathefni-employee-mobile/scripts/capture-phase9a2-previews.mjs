import { chromium } from '@playwright/test'
import path from 'node:path'

const baseUrl = process.env.PREVIEW_BASE_URL || 'http://127.0.0.1:8091'
const outputDir = path.resolve('docs/phase9a2-preview')
const shots = [
  ['activation-en.png', 'screen=activation&locale=en'],
  ['home-en-multi.png', 'screen=home&locale=en&scenario=multi'],
  ['onboarding-en.png', 'screen=onboarding&locale=en&scenario=multi'],
  ['activation-ar.png', 'screen=activation&locale=ar'],
  ['home-ar-multi.png', 'screen=home&locale=ar&scenario=multi'],
  ['onboarding-ar.png', 'screen=onboarding&locale=ar&scenario=multi'],
  ['home-en-minimal.png', 'screen=home&locale=en&scenario=minimal'],
  ['onboarding-en-empty.png', 'screen=onboarding&locale=en&scenario=empty'],
  ['onboarding-en-loading.png', 'screen=onboarding&locale=en&scenario=loading'],
  ['activation-en-error.png', 'screen=activation&locale=en&scenario=error'],
]

const browser = await chromium.launch({ headless: true })
try {
  for (const [filename, query] of shots) {
    const page = await browser.newPage({ viewport: { width: 393, height: 852 }, deviceScaleFactor: 1 })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`${baseUrl}/design-preview?${query}&capture=1`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
    if (errors.length) throw new Error(`${filename}: ${errors.join('; ')}`)
    await page.screenshot({ path: path.join(outputDir, filename) })
    await page.close()
    console.log(`captured ${filename}`)
  }
} finally {
  await browser.close()
}
