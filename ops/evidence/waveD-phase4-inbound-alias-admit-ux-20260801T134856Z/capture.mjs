import { chromium } from 'playwright'
import { mkdirSync, copyFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
const root = resolve(dirname(fileURLToPath(import.meta.url)))
const fixture = resolve(root, 'artifacts/d4-fixture.html')
mkdirSync(resolve(root, 'screenshots'), { recursive: true })
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})
async function shot(locale, mode, file) {
  const page = await browser.newPage({
    viewport: mode === 'mobile' ? { width: 390, height: 844 } : { width: 1280, height: 900 },
  })
  await page.goto('file://' + fixture + `?locale=${locale}&mode=${mode}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(200)
  await page.screenshot({ path: resolve(root, 'screenshots', file), fullPage: true })
  await page.close()
}
await shot('en', 'desktop', 'settings-held-en-desktop.png')
await shot('ar', 'desktop', 'settings-held-ar-desktop.png')
await shot('en', 'mobile', 'settings-held-en-mobile.png')
await shot('ar', 'mobile', 'settings-held-ar-mobile.png')
await browser.close()
console.log('SHOTS_OK')
