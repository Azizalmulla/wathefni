/**
 * Local Wave 4 screenshots against filter-ux-harness.html via Vite.
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const { spawn } = require('child_process')
const fs = require('fs')
const path = require('path')

const ROOT = '/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard'
const OUT = process.env.W4_SHOTS || '/tmp/w4-shots'
const PORT = process.env.W4_PORT || '5199'
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'
const BASE = `http://127.0.0.1:${PORT}/dashboard/filter-ux-harness.html`

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function waitForServer() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(BASE)
      if (res.ok || res.status === 200) return
    } catch {}
    await wait(500)
  }
  throw new Error('vite harness did not start')
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true })
  const vite = spawn(
    'npx',
    ['vite', '--host', '127.0.0.1', '--port', String(PORT), '--strictPort'],
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] },
  )
  let boot = ''
  vite.stdout.on('data', (d) => {
    boot += d.toString()
  })
  vite.stderr.on('data', (d) => {
    boot += d.toString()
  })

  try {
    await waitForServer()
    const browser = await chromium.launch({ headless: true, executablePath: CHROME })
    const shots = []

    async function shot(name, opts) {
      const context = await browser.newContext({
        viewport: opts.viewport,
        locale: opts.locale === 'ar' ? 'ar' : 'en',
      })
      const page = await context.newPage()
      const url = `${BASE}?locale=${opts.locale}${opts.open ? '&open=1' : ''}`
      await page.goto(url, { waitUntil: 'networkidle' })
      await page.waitForSelector('[data-testid="unified-candidates-page"]')
      if (opts.open) {
        await page.waitForSelector('[data-testid="candidates-filter-overlay"]', { timeout: 10000 })
      }
      await page.waitForTimeout(300)
      const file = path.join(OUT, `${name}.png`)
      await page.screenshot({ path: file, fullPage: true })
      shots.push({ name, file, url, viewport: opts.viewport, locale: opts.locale })
      await context.close()
    }

    await shot('en-desktop-chips', { locale: 'en', viewport: { width: 1280, height: 900 }, open: false })
    await shot('en-desktop-drawer', { locale: 'en', viewport: { width: 1280, height: 900 }, open: true })
    await shot('en-mobile-sheet', { locale: 'en', viewport: { width: 390, height: 844 }, open: true })
    await shot('ar-desktop-chips-rtl', { locale: 'ar', viewport: { width: 1280, height: 900 }, open: false })
    await shot('ar-mobile-sheet-rtl', { locale: 'ar', viewport: { width: 390, height: 844 }, open: true })

    await browser.close()
    fs.writeFileSync(path.join(OUT, 'shots.json'), JSON.stringify({ ok: true, shots }, null, 2))
    console.log(JSON.stringify({ ok: true, count: shots.length, out: OUT }, null, 2))
  } finally {
    vite.kill('SIGTERM')
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
