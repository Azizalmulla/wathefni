import { mkdir } from 'node:fs/promises'
import { chromium, webkit } from '@playwright/test'

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4177/design-preview'
const cases = [
  ['home', 'en', 'multi-workspace', 'ready', 'What needs your attention'],
  ['home', 'ar', 'multi-workspace', 'ready', 'ما يحتاج إلى انتباهك'],
  ['home', 'en', 'hr-only', 'empty', 'all caught up'],
  ['home', 'en', 'restricted-manager', 'revoked', 'access changed'],
  ['home', 'en', 'hr-only', 'company-disabled', 'workspace unavailable'],
  ['leave', 'en', 'hr-only', 'ready', 'Review before you decide'],
  ['leave', 'ar', 'restricted-manager', 'ready', 'راجع الطلب'],
  ['leave', 'en', 'hr-only', 'loading', 'Loading'],
  ['leave', 'en', 'hr-only', 'stale', 'item changed'],
  ['leave', 'en', 'hr-only', 'success', 'Decision recorded'],
  ['candidate', 'en', 'recruiter-only', 'ready', 'Candidate review'],
  ['candidate', 'ar', 'recruiter-only', 'ready', 'مراجعة المرشح'],
  ['candidate', 'en', 'multi-workspace', 'error', 'couldn’t load'],
  ['candidate', 'en', 'multi-workspace', 'revoked', 'access changed'],
]

await mkdir(new URL('../docs/screenshots/', import.meta.url), { recursive: true })

async function assertPageScrollable(page, label) {
  // Wait a beat for RN-web layout after content paint.
  await page.waitForTimeout(200)
  const metrics = await page.evaluate(() => {
    const preview = document.querySelector('[aria-label="App preview"]')
    const scrollers = [...document.querySelectorAll('*')].filter((el) => {
      const style = window.getComputedStyle(el)
      const oy = style.overflowY
      return (oy === 'auto' || oy === 'scroll') && el.scrollHeight >= el.clientHeight
    })
    const primary =
      scrollers.sort((a, b) => b.clientHeight - a.clientHeight || b.scrollHeight - a.scrollHeight)[0] || null
    if (!preview || !primary) {
      return {
        found: false,
        hasPreview: Boolean(preview),
        scrollHeight: primary?.scrollHeight || 0,
        clientHeight: primary?.clientHeight || 0,
        canScroll: false,
        nestedTrapCount: 0,
        needsScroll: false,
      }
    }
    const needsScroll = primary.scrollHeight > primary.clientHeight + 40
    const before = primary.scrollTop
    primary.scrollTop = primary.scrollHeight
    const after = primary.scrollTop
    primary.scrollTop = before
    const nestedTraps = [...preview.querySelectorAll('*')].filter((el) => {
      const style = window.getComputedStyle(el)
      const oy = style.overflowY
      return (oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 40
    })
    return {
      found: true,
      hasPreview: true,
      scrollHeight: primary.scrollHeight,
      clientHeight: primary.clientHeight,
      previewHeight: preview.scrollHeight,
      needsScroll,
      canScroll: !needsScroll || after > before + 20,
      nestedTrapCount: nestedTraps.length,
    }
  })
  if (!metrics.found || !metrics.hasPreview) {
    throw new Error(`${label}: preview scroller missing (${JSON.stringify(metrics)})`)
  }
  if (metrics.nestedTrapCount > 0) {
    throw new Error(`${label}: nested scroll trap inside preview (${JSON.stringify(metrics)})`)
  }
  if (!metrics.canScroll) {
    throw new Error(`${label}: page scroller could not reach bottom (${JSON.stringify(metrics)})`)
  }
}

for (const [browserName, browserType] of [
  ['chromium', chromium],
  ['webkit', webkit],
]) {
  const browser = await browserType.launch()
  const page = await browser.newPage({ viewport: { width: 390, height: 700 }, reducedMotion: 'reduce' })
  for (const [screen, locale, operator, scenario, expected] of cases) {
    const url = `${base}?view=${screen}&locale=${locale}&operator=${operator}&scenario=${scenario}&controls=0&capture=1`
    const response = await page.goto(url, { waitUntil: 'networkidle' })
    const headers = response?.headers() || {}
    if (!headers['cache-control']?.includes('no-store')) {
      throw new Error(`${browserName}: preview response is cacheable for ${url}`)
    }
    const buildMarker = headers['x-preview-build']
    if (!buildMarker) {
      throw new Error(`${browserName}: preview build response header missing for ${url}`)
    }
    await page.getByLabel(`Preview build ${buildMarker}`, { exact: true }).waitFor()
    const expectedLocator =
      expected === 'Loading'
        ? page.getByLabel('Loading').first()
        : page.getByText(expected, { exact: false }).first()
    await expectedLocator.waitFor()
    if (await page.getByLabel('Preview controls', { exact: true }).count()) {
      throw new Error(`${browserName}: large controls visible with controls=0 for ${url}`)
    }
    const canonical = new URL(page.url())
    for (const [key, value] of Object.entries({ view: screen, locale, operator, scenario, controls: '0' })) {
      if (canonical.searchParams.get(key) !== value) {
        throw new Error(`${browserName}: URL state lost ${key}=${value} for ${url}`)
      }
    }
    await assertPageScrollable(page, `${browserName} ${screen}/${locale}/${scenario}`)
    await page.reload({ waitUntil: 'networkidle' })
    await (
      expected === 'Loading'
        ? page.getByLabel('Loading').first()
        : page.getByText(expected, { exact: false }).first()
    ).waitFor()
    await page.getByLabel(`Preview build ${buildMarker}`, { exact: true }).waitFor()
    const serviceWorkerCount = await page.evaluate(async () =>
      'serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).length : 0,
    )
    if (serviceWorkerCount !== 0) {
      throw new Error(`${browserName}: stale service worker remained registered for ${url}`)
    }
  }

  // Mobile controls UX: collapsed by default, FAB opens sheet, selection closes it.
  await page.setViewportSize({ width: 390, height: 700 })
  await page.goto(`${base}?view=home&locale=en&operator=multi-workspace&scenario=ready`, {
    waitUntil: 'networkidle',
  })
  if (await page.getByLabel('Preview controls', { exact: true }).count()) {
    throw new Error(`${browserName}: controls should start collapsed on mobile`)
  }
  await page.getByRole('button', { name: 'Open preview controls' }).click()
  const panel = page.getByLabel('Preview controls', { exact: true })
  await panel.waitFor()
  await panel.getByRole('button', { name: 'leave', exact: true }).click()
  await page.waitForURL(/view=leave/)
  await page.getByText('Review before you decide', { exact: false }).waitFor()
  if (await page.getByLabel('Preview controls', { exact: true }).count()) {
    throw new Error(`${browserName}: controls should close after selecting a screen`)
  }

  if (browserName === 'webkit') {
    for (const locale of ['en', 'ar']) {
      for (const screen of ['home', 'leave', 'candidate']) {
        await page.goto(
          `${base}?view=${screen}&locale=${locale}&operator=multi-workspace&scenario=ready&controls=0&capture=1`,
          { waitUntil: 'networkidle' },
        )
        await page.screenshot({
          path: new URL(`../docs/screenshots/${screen}-${locale}.png`, import.meta.url).pathname,
          fullPage: true,
        })
      }
    }
    for (const [screen, locale, action, confirmationTitle] of [
      ['leave', 'en', 'Approve leave', 'Confirm this decision'],
      ['leave', 'ar', 'الموافقة على الإجازة', 'تأكيد هذا القرار'],
      ['candidate', 'en', 'Hire', 'Confirm this decision'],
      ['candidate', 'ar', 'تعيين', 'تأكيد هذا القرار'],
    ]) {
      await page.setViewportSize({ width: 390, height: 1200 })
      await page.goto(
        `${base}?view=${screen}&locale=${locale}&operator=multi-workspace&scenario=ready&controls=0&capture=1`,
        { waitUntil: 'networkidle' },
      )
      await page.getByRole('button', { name: action, exact: true }).click()
      await page.getByText(confirmationTitle, { exact: true }).waitFor()
      await page.waitForTimeout(500)
      await page.screenshot({
        path: new URL(`../docs/screenshots/${screen}-confirmation-${locale}.png`, import.meta.url).pathname,
        fullPage: true,
      })
    }
  }
  await browser.close()
}

console.log(`PREVIEW_VERIFIED ${cases.length} scenarios x chromium+webkit`)
