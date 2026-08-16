import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const out = resolve(root, 'screenshots')
await mkdir(out, { recursive: true })
const fixture = resolve(root, 'fixture.html')
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
})
const shots = [
  { locale: 'en', width: 1440, height: 900, name: 'en-desktop.png' },
  { locale: 'en', width: 390, height: 844, name: 'en-mobile.png' },
  { locale: 'ar', width: 1440, height: 900, name: 'ar-desktop.png' },
  { locale: 'ar', width: 390, height: 844, name: 'ar-mobile.png' },
]
for (const shot of shots) {
  const page = await browser.newPage({ viewport: { width: shot.width, height: shot.height } })
  await page.goto(`file://${fixture}?locale=${shot.locale}`)
  await page.waitForTimeout(150)
  await page.screenshot({ path: resolve(out, shot.name), fullPage: true })
  await page.close()
  console.log('wrote', shot.name)
}
await browser.close()
