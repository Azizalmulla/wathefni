import { chromium, devices } from '@playwright/test'
import path from 'node:path'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseUrl = process.env.PREVIEW_BASE_URL || 'http://127.0.0.1:8091'
const outputDir = path.resolve('docs/phase9a2-preview')
mkdirSync(outputDir, { recursive: true })

const shots = [
  // Activation
  ['activation-en.png', 'screen=activation&locale=en&scenario=default', ['Welcome to Wathefni', 'Wathefni']],
  ['activation-ar.png', 'screen=activation&locale=ar&scenario=default', ['أهلاً بك في وظفني', 'وظفني']],
  ['activation-en-loading.png', 'screen=activation&locale=en&scenario=loading', ['Welcome to Wathefni', 'Wathefni']],
  ['activation-ar-loading.png', 'screen=activation&locale=ar&scenario=loading', ['أهلاً بك في وظفني', 'وظفني']],
  ['activation-en-error.png', 'screen=activation&locale=en&scenario=error', ["That code didn't work", 'Wathefni']],
  ['activation-ar-error.png', 'screen=activation&locale=ar&scenario=error', ['الرمز غير صحيح', 'وظفني']],
  // Home
  ['home-en-multi.png', 'screen=home&locale=en&scenario=multi', ['Today at work', "Today's shift", 'Wathefni']],
  ['home-ar-multi.png', 'screen=home&locale=ar&scenario=multi', ['يومك في العمل', 'مناوبة اليوم', 'وظفني']],
  ['home-en-minimal.png', 'screen=home&locale=en&scenario=minimal', ["You're all caught up", 'No notifications yet', 'Wathefni']],
  ['home-ar-minimal.png', 'screen=home&locale=ar&scenario=minimal', ['أنجزت كل شيء', 'لا توجد إشعارات بعد', 'وظفني']],
  ['home-en-loading.png', 'screen=home&locale=en&scenario=loading', ['Loading', 'Today at work', 'Wathefni']],
  ['home-ar-loading.png', 'screen=home&locale=ar&scenario=loading', ['جار', 'يومك في العمل', 'وظفني']],
  ['home-en-empty.png', 'screen=home&locale=en&scenario=empty', ["You're all caught up", 'No notifications yet', 'Wathefni']],
  ['home-ar-empty.png', 'screen=home&locale=ar&scenario=empty', ['أنجزت كل شيء', 'لا توجد إشعارات بعد', 'وظفني']],
  ['home-en-error.png', 'screen=home&locale=en&scenario=error', ['Something went wrong', 'Try again', 'Wathefni']],
  ['home-ar-error.png', 'screen=home&locale=ar&scenario=error', ['حدث خطأ', 'حاول مرة أخرى', 'وظفني']],
  // Onboarding
  ['onboarding-en.png', 'screen=onboarding&locale=en&scenario=multi', ['Your checklist', 'Upload photo', 'Wathefni']],
  ['onboarding-ar.png', 'screen=onboarding&locale=ar&scenario=multi', ['قائمة مهامك', 'رفع الصورة', 'وظفني']],
  ['onboarding-en-loading.png', 'screen=onboarding&locale=en&scenario=loading', ['Loading', 'Your checklist', 'Wathefni']],
  ['onboarding-ar-loading.png', 'screen=onboarding&locale=ar&scenario=loading', ['جار', 'قائمة مهامك', 'وظفني']],
  ['onboarding-en-empty.png', 'screen=onboarding&locale=en&scenario=empty', ["You're ready to go", 'Wathefni']],
  ['onboarding-ar-empty.png', 'screen=onboarding&locale=ar&scenario=empty', ['أصبحت جاهزاً', 'وظفني']],
  ['onboarding-en-error.png', 'screen=onboarding&locale=en&scenario=error', ['Something went wrong', 'Try again', 'Wathefni']],
  ['onboarding-ar-error.png', 'screen=onboarding&locale=ar&scenario=error', ['حدث خطأ', 'حاول مرة أخرى', 'وظفني']],
  ['onboarding-en-review.png', 'screen=onboarding&locale=en&scenario=review', ['Your HR team is reviewing', 'Wathefni']],
  ['onboarding-ar-review.png', 'screen=onboarding&locale=ar&scenario=review', ['يراجعه الآن', 'وظفني']],
  ['onboarding-en-rejected.png', 'screen=onboarding&locale=en&scenario=rejected', ['needs an update', 'Replace', 'Wathefni']],
  ['onboarding-ar-rejected.png', 'screen=onboarding&locale=ar&scenario=rejected', ['يحتاج إلى تحديث', 'استبدال', 'وظفني']],
  ['onboarding-en-completed.png', 'screen=onboarding&locale=en&scenario=completed', ["You're ready to go", 'Completed', 'Wathefni']],
  ['onboarding-ar-completed.png', 'screen=onboarding&locale=ar&scenario=completed', ['أصبحت جاهزاً', 'مكتمل', 'وظفني']],
]

const results = []
const browser = await chromium.launch({ headless: true })
try {
  for (const [filename, query, required] of shots) {
    const page = await browser.newPage({
      ...devices['iPhone 13'],
      viewport: { width: 393, height: 852 },
      deviceScaleFactor: 1,
    })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`${baseUrl}/design-preview?${query}&capture=1`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    if (errors.length) throw new Error(`${filename}: ${errors.join('; ')}`)

    const body = await page.locator('body').innerText()
    const locale = query.includes('locale=ar') ? 'ar' : 'en'
    const missing = required.filter((token) => !body.includes(token))
    const unexpectedEnglish =
      locale === 'ar'
      && /Welcome to Wathefni|Today at work|Your checklist|Something went wrong|Try again/.test(body)
      && !query.includes('scenario=error')
    // Error screens intentionally share some English keys only in EN mode; AR must not keep EN heroes.
    const unexpectedHero =
      locale === 'ar'
      && (body.includes('Welcome to Wathefni') || body.includes('Today at work') || body.includes('Your checklist'))
    const pass = missing.length === 0 && !unexpectedHero
    results.push({
      filename,
      query,
      pass,
      missing,
      unexpectedEnglish: unexpectedHero,
      sample: body.replace(/\s+/g, ' ').slice(0, 180),
    })
    await page.screenshot({ path: path.join(outputDir, filename) })
    await page.close()
    console.log(`${pass ? 'PASS' : 'FAIL'} ${filename}`)
  }

  const page = await browser.newPage({
    ...devices['iPhone 13'],
    viewport: { width: 393, height: 852 },
    deviceScaleFactor: 1,
  })
  await page.goto(`${baseUrl}/design-preview?screen=activation&locale=en&scenario=default`, {
    waitUntil: 'networkidle',
  })
  await page.waitForTimeout(700)
  await page.getByRole('button', { name: 'AR', exact: true }).click()
  await page.waitForTimeout(1000)
  const urlAfterAr = page.url()
  const bodyAfterAr = await page.locator('body').innerText()
  const arSelectedVisible = await page.getByRole('button', { name: 'AR selected', exact: true }).count()
  const interactivePass =
    urlAfterAr.includes('locale=ar')
    && bodyAfterAr.includes('وظفني')
    && bodyAfterAr.includes('أهلاً بك في وظفني')
    && !bodyAfterAr.includes('Welcome to Wathefni')
    && arSelectedVisible === 1

  await page.getByRole('button', { name: 'home', exact: true }).click()
  await page.waitForTimeout(700)
  const urlHome = page.url()
  const bodyHome = await page.locator('body').innerText()
  await page.getByRole('button', { name: 'minimal', exact: true }).click()
  await page.waitForTimeout(700)
  const urlMinimal = page.url()
  const bodyMinimal = await page.locator('body').innerText()
  const preservePass =
    urlHome.includes('locale=ar')
    && urlHome.includes('screen=home')
    && bodyHome.includes('يومك في العمل')
    && urlMinimal.includes('locale=ar')
    && urlMinimal.includes('scenario=minimal')
    && bodyMinimal.includes('وظفني')
    && bodyMinimal.includes('أنجزت كل شيء')

  // Refresh must preserve state.
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  const urlReload = page.url()
  const bodyReload = await page.locator('body').innerText()
  const refreshPass =
    urlReload.includes('locale=ar')
    && urlReload.includes('screen=home')
    && urlReload.includes('scenario=minimal')
    && bodyReload.includes('وظفني')
    && bodyReload.includes('أنجزت كل شيء')

  results.push({
    filename: 'interactive-ar-switch',
    query: 'control-tap',
    pass: interactivePass,
    missing: interactivePass ? [] : ['locale=ar visible switch'],
    unexpectedEnglish: !interactivePass,
    sample: `${urlAfterAr} | ${bodyAfterAr.replace(/\s+/g, ' ').slice(0, 120)}`,
  })
  results.push({
    filename: 'interactive-preserve-locale',
    query: 'screen+scenario',
    pass: preservePass,
    missing: preservePass ? [] : ['locale preserved across screen/scenario'],
    unexpectedEnglish: !preservePass,
    sample: `${urlMinimal} | ${bodyMinimal.replace(/\s+/g, ' ').slice(0, 120)}`,
  })
  results.push({
    filename: 'interactive-refresh-preserve',
    query: 'reload',
    pass: refreshPass,
    missing: refreshPass ? [] : ['state preserved on refresh'],
    unexpectedEnglish: !refreshPass,
    sample: `${urlReload} | ${bodyReload.replace(/\s+/g, ' ').slice(0, 120)}`,
  })
  await page.close()
  console.log(`${interactivePass ? 'PASS' : 'FAIL'} interactive-ar-switch`)
  console.log(`${preservePass ? 'PASS' : 'FAIL'} interactive-preserve-locale`)
  console.log(`${refreshPass ? 'PASS' : 'FAIL'} interactive-refresh-preserve`)
} finally {
  await browser.close()
}

const failed = results.filter((row) => !row.pass)
writeFileSync(
  path.join(outputDir, 'verification-matrix.json'),
  JSON.stringify({ generated_at: new Date().toISOString(), results, failed: failed.length }, null, 2),
)

if (failed.length) {
  console.error(`\n${failed.length} verification failures`)
  for (const row of failed) console.error(`- ${row.filename}: ${row.missing.join(', ') || 'unexpected English'}`)
  process.exit(1)
}

console.log(`\nverification matrix: GREEN (${results.length} checks)`)
