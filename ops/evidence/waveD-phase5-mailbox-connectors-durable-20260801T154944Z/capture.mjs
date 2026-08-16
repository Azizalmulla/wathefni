import { chromium } from 'playwright'
import { mkdirSync } from 'fs'
import { resolve } from 'path'
const root = process.cwd()
const fixture = resolve(root, 'artifacts/d5-fixture.html')
mkdirSync(resolve(root, 'screenshots'), { recursive: true })
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
async function shot(locale, mode, file) {
  const page = await browser.newPage({ viewport: mode==='mobile'?{width:390,height:844}:{width:1280,height:900} })
  await page.goto('file://'+fixture+`?locale=${locale}&mode=${mode}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(150)
  await page.screenshot({ path: resolve(root, 'screenshots', file), fullPage: true })
  await page.close()
}
await shot('en','desktop','connector-en-desktop.png')
await shot('ar','desktop','connector-ar-desktop.png')
await shot('en','mobile','connector-en-mobile.png')
await shot('ar','mobile','connector-ar-mobile.png')
await browser.close()
console.log('SHOTS_OK')
