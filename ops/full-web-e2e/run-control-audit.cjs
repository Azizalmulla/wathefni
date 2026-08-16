/**
 * Production-connected dashboard control inventory and safe interaction audit.
 *
 * It inventories every visible interactive DOM control across roles/locales/
 * viewports, then exercises non-mutating controls (navigation, tabs, menus,
 * search/filter, drawers, modals, pagination, back/close).
 *
 * Required env:
 *   INTERACTION_AUDIT_EVID
 *   INTERACTION_AUDIT_SESSIONS (directory with owner/hr_manager/viewer.json)
 */
const { chromium } = require('/Users/azizalmulla/Desktop/claw/apps/wathefni-hr-mobile/node_modules/playwright')
const crypto = require('crypto')
const fs = require('fs')
const path = require('path')

const BASE = process.env.DASHBOARD_BASE || 'https://api.wathefni.ai/dashboard/'
const EVID = process.env.INTERACTION_AUDIT_EVID
const SESSION_DIR = process.env.INTERACTION_AUDIT_SESSIONS
const CHROME =
  process.env.PW_CHROME ||
  '/Users/azizalmulla/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'

const DEFAULT_PAGES = [
  'overview', 'jobs', 'candidates', 'interviews', 'assessments', 'ranking',
  'calendar', 'employees', 'workforce', 'inbox', 'onboarding', 'attendance',
  'leave', 'shifts', 'payroll', 'analytics', 'compliance', 'notifications',
  'activity', 'settings',
]
const PAGES = (process.env.INTERACTION_AUDIT_PAGES || DEFAULT_PAGES.join(','))
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean)

const ROLES = (process.env.INTERACTION_AUDIT_ROLES || 'owner,hr_manager,viewer')
  .split(',')
  .map((role) => role.trim())
  .filter(Boolean)
const OUTPUT_SUFFIX = process.env.INTERACTION_AUDIT_OUTPUT_SUFFIX
  ? `-${process.env.INTERACTION_AUDIT_OUTPUT_SUFFIX.replace(/[^a-z0-9_-]/gi, '')}`
  : ''
const SURFACES = [
  { locale: 'en', viewport: 'desktop', width: 1440, height: 900, isMobile: false },
  { locale: 'ar', viewport: 'desktop', width: 1440, height: 900, isMobile: false },
  { locale: 'en', viewport: 'mobile', width: 390, height: 844, isMobile: true },
  { locale: 'ar', viewport: 'mobile', width: 390, height: 844, isMobile: true },
]

// Never invoke live mutations in the generic navigator. Mutation authority is
// qualified by dedicated canary smokes with synthetic/current governed rows.
const MUTATION_RE = new RegExp([
  'add', 'create', 'save', 'submit', 'send', 'invite', 'publish', 'close job',
  'delete', 'remove', 'archive', 'restore', 'approve', 'reject', 'decline',
  'hire', 'withdraw', 'cancel shift', 'confirm import', 'apply approved',
  'upload', 'import', 'export', 'download', 'mark done', 'deactivate',
  'undo', 'run payroll', 'record payment', 'correct dates', 'remind',
  'إضافة', 'إنشاء', 'حفظ', 'إرسال', 'دعوة', 'نشر', 'حذف', 'إزالة', 'أرشفة',
  'موافقة', 'رفض', 'تعيين', 'تأكيد', 'رفع', 'استيراد', 'تصدير', 'تنزيل',
  'إلغاء', 'تعطيل', 'تراجع',
].join('|'), 'i')

const SAFE_RE = new RegExp([
  'open', 'view', 'details', 'filter', 'search', 'menu', 'more', 'advanced',
  'back', 'close', 'next', 'previous', 'today', 'week', 'month', 'list',
  'board', 'timeline', 'summary', 'history', 'activity', 'settings', 'profile',
  'overview', 'jobs', 'candidates', 'interviews', 'assessments', 'ranking',
  'calendar', 'employees', 'organization', 'attention', 'onboarding',
  'attendance', 'leave', 'shifts', 'payroll', 'analytics', 'compliance',
  'alerts', 'load now', 'retry', 'refresh', 'clear',
  'فتح', 'عرض', 'تفاصيل', 'تصفية', 'بحث', 'قائمة', 'المزيد', 'متقدم',
  'عودة', 'إغلاق', 'التالي', 'السابق', 'اليوم', 'أسبوع', 'شهر', 'سجل',
  'نظرة', 'وظائف', 'مرشح', 'مقابلات', 'تقييم', 'تقويم', 'موظف', 'حضور',
  'إجاز', 'ورديات', 'رواتب', 'تحليلات', 'امتثال', 'تنبيهات', 'تحديث', 'مسح',
].join('|'), 'i')

function loadSession(role) {
  return JSON.parse(fs.readFileSync(path.join(SESSION_DIR, `${role}.json`), 'utf8'))
}

function hash(value) {
  return crypto.createHash('sha1').update(String(value || '')).digest('hex').slice(0, 12)
}

function slug(value) {
  return String(value || 'unnamed').toLowerCase().replace(/[^a-z0-9\u0600-\u06ff]+/g, '-').replace(/^-|-$/g, '').slice(0, 64)
}

async function inject(page, session, locale) {
  await page.addInitScript(({ session, locale }) => {
    localStorage.setItem('wathefni_dashboard_token', session.token)
    localStorage.setItem('wathefni_dashboard_email', session.email || '')
    localStorage.setItem('wathefni_hr_phone', session.phone || '')
    localStorage.setItem('wathefni_company_code', 'WATHEFNI')
    localStorage.setItem('wathefni_recruiting_locale', locale)
  }, { session, locale })
}

async function openScreen(page, pageId) {
  await page.goto(`${BASE}?page=${pageId}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.waitForTimeout(3000)
  const load = page.getByRole('button', { name: /Load now|تحميل الآن/i })
  if (await load.count()) {
    await load.first().click().catch(() => {})
    await page.waitForTimeout(1800)
  }
}

async function inventory(page) {
  return page.evaluate(() => {
    const selector = [
      'button', 'a[href]', 'input', 'select', 'textarea', 'summary',
      '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
      '[role="checkbox"]', '[role="radio"]', '[role="switch"]',
      '[role="combobox"]', '[role="option"]', '[tabindex]',
    ].join(',')
    const visible = (el) => {
      const style = getComputedStyle(el)
      const box = el.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' &&
        style.opacity !== '0' && box.width > 0 && box.height > 0
    }
    const name = (el) => {
      const labelled = el.getAttribute('aria-labelledby')
      if (labelled) {
        const text = labelled.split(/\s+/).map((id) => document.getElementById(id)?.textContent || '').join(' ').trim()
        if (text) return text
      }
      return (
        el.getAttribute('aria-label') ||
        el.getAttribute('title') ||
        el.getAttribute('placeholder') ||
        (el.tagName === 'INPUT' ? el.getAttribute('value') : '') ||
        el.textContent ||
        ''
      ).replace(/\s+/g, ' ').trim().slice(0, 180)
    }
    return [...document.querySelectorAll(selector)].filter(visible).map((el, index) => {
      const tag = el.tagName.toLowerCase()
      const role = el.getAttribute('role') || (
        tag === 'a' ? 'link' :
        tag === 'button' ? 'button' :
        tag === 'select' ? 'combobox' :
        ['input', 'textarea'].includes(tag) ? 'input' : ''
      )
      return {
        index,
        tag,
        role,
        name: name(el),
        type: el.getAttribute('type') || '',
        href: el.getAttribute('href') || '',
        disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
        expanded: el.getAttribute('aria-expanded'),
        pressed: el.getAttribute('aria-pressed'),
        selected: el.getAttribute('aria-selected'),
        current: el.getAttribute('aria-current'),
        controls: el.getAttribute('aria-controls') || '',
        testid: el.getAttribute('data-testid') || '',
        tabindex: el.getAttribute('tabindex'),
      }
    })
  })
}

async function snapshot(page) {
  return page.evaluate(() => {
    const body = document.body?.innerText || ''
    const dialogs = document.querySelectorAll('[role="dialog"],dialog,[aria-modal="true"]').length
    const expanded = [...document.querySelectorAll('[aria-expanded="true"]')].length
    const pressed = [...document.querySelectorAll('[aria-pressed="true"],[aria-selected="true"]')].length
    return {
      url: location.href,
      dialogs,
      expanded,
      pressed,
      bodyHash: body.slice(0, 16000),
      bodyLen: body.length,
    }
  })
}

async function locate(page, control) {
  const escaped = control.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const exact = control.name ? new RegExp(`^\\s*${escaped}\\s*$`, 'i') : null
  const ariaRoles = new Set([
    'button', 'link', 'tab', 'menuitem', 'checkbox', 'radio', 'switch',
    'combobox', 'option', 'textbox', 'searchbox',
  ])
  if (ariaRoles.has(control.role) && exact) {
    const byRole = page.getByRole(control.role, { name: exact })
    if (await byRole.count()) return byRole.first()
  }
  if (control.name) {
    const byText = page.getByText(control.name, { exact: true })
    if (await byText.count()) return byText.first()
  }
  return null
}

async function exercise(page, pageId, control, networkEvents) {
  const result = {
    expected: 'Safe interaction changes route, panel, form value, or sends a successful request.',
    actual: '',
    status: 'unproven',
    severity: 'P3',
  }
  if (control.disabled) {
    result.expected = 'Disabled control is visibly disabled or explained.'
    result.actual = 'Visible and disabled.'
    result.status = 'pass'
    return result
  }
  if (control.current === 'page') {
    result.expected = 'Current navigation control identifies the active screen.'
    result.actual = 'Visible active control exposes aria-current="page"; repeat activation is a safe no-op.'
    result.status = 'pass'
    result.severity = null
    return result
  }
  if (!control.name && !['input', 'select', 'textarea'].includes(control.tag)) {
    result.expected = 'Interactive control has an accessible name.'
    result.actual = 'Visible interactive control has no accessible name.'
    result.status = 'broken'
    result.severity = 'P2'
    return result
  }
  if (MUTATION_RE.test(control.name)) {
    result.expected = 'Mutation is backed by a handler/API, permission gate, pending lock and audit.'
    result.actual = 'Not clicked by generic production navigator; static/API mutation audit required.'
    result.status = 'unproven'
    result.severity = 'P1'
    return result
  }
  const shouldExercise =
    ['tab', 'menuitem', 'combobox', 'checkbox', 'radio', 'switch'].includes(control.role) ||
    ['input', 'select', 'textarea', 'summary'].includes(control.tag) ||
    Boolean(control.href) ||
    SAFE_RE.test(control.name)
  if (!shouldExercise) {
    result.actual = 'Inventoried; not safely classifiable for generic production click.'
    return result
  }

  await openScreen(page, pageId)
  const locator = await locate(page, control)
  if (!locator) {
    result.actual = 'Control disappeared after safe screen refresh; state-dependent.'
    return result
  }
  const before = await snapshot(page)
  const netStart = networkEvents.length
  try {
    if (control.tag === 'input' && !['button', 'submit', 'file', 'checkbox', 'radio'].includes(control.type)) {
      await locator.fill('__wathefni_control_audit_no_match__', { timeout: 5000 })
      await page.waitForTimeout(350)
      const value = await locator.inputValue()
      await locator.fill('')
      result.actual = value.includes('wathefni_control_audit') ? 'Input accepted and cleared safely.' : 'Input did not accept value.'
      result.status = value.includes('wathefni_control_audit') ? 'pass' : 'broken'
      result.severity = result.status === 'pass' ? null : 'P2'
      return result
    }
    if (control.tag === 'select') {
      const options = await locator.locator('option').count()
      if (options > 1) {
        const original = await locator.inputValue()
        const second = await locator.locator('option').nth(1).getAttribute('value')
        if (second !== null) await locator.selectOption(second)
        await page.waitForTimeout(250)
        if (original) await locator.selectOption(original).catch(() => {})
        result.actual = 'Select changed and restored.'
        result.status = 'pass'
        result.severity = null
      } else {
        result.actual = 'Select has fewer than two options.'
      }
      return result
    }
    await locator.click({ timeout: 6000 })
    await page.waitForTimeout(750)
    const after = await snapshot(page)
    const events = networkEvents.slice(netStart)
    const bad = events.filter((e) => e.status >= 400)
    const changed =
      before.url !== after.url ||
      before.dialogs !== after.dialogs ||
      before.expanded !== after.expanded ||
      before.pressed !== after.pressed ||
      hash(before.bodyHash) !== hash(after.bodyHash)
    const successfulRequest = events.some((e) => e.status >= 200 && e.status < 400)
    if (bad.length) {
      result.actual = `Interaction sent failing request(s): ${bad.map((e) => `${e.status} ${e.url}`).join(', ')}`
      result.status = 'broken'
      result.severity = bad.some((e) => e.status >= 500) ? 'P1' : 'P2'
    } else if (changed || successfulRequest) {
      result.actual = [
        changed ? 'Visible/navigation state changed.' : '',
        successfulRequest ? 'Request completed successfully.' : '',
      ].filter(Boolean).join(' ')
      result.status = 'pass'
      result.severity = null
    } else {
      result.actual = 'Click produced no observable state, route, dialog, or network change.'
      result.status = 'dead'
      result.severity = control.role === 'tab' || control.href ? 'P1' : 'P2'
    }
  } catch (error) {
    result.actual = `Interaction failed: ${String(error).slice(0, 240)}`
    result.status = 'broken'
    result.severity = 'P2'
  }
  return result
}

async function run() {
  if (!EVID || !SESSION_DIR) throw new Error('INTERACTION_AUDIT_EVID and INTERACTION_AUDIT_SESSIONS required')
  fs.mkdirSync(path.join(EVID, 'inventory'), { recursive: true })
  fs.mkdirSync(path.join(EVID, 'verify'), { recursive: true })
  fs.mkdirSync(path.join(EVID, 'screenshots'), { recursive: true })

  const browser = await chromium.launch({
    headless: true,
    executablePath: fs.existsSync(CHROME) ? CHROME : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  })
  const rows = []
  const pageSummaries = []
  const writeOutputs = () => {
    const summary = {
      generated_at: new Date().toISOString(),
      controls: rows.length,
      pages: pageSummaries.length,
      status_counts: rows.reduce((acc, row) => {
        acc[row.status] = (acc[row.status] || 0) + 1
        return acc
      }, {}),
      page_summaries: pageSummaries,
    }
    fs.writeFileSync(path.join(EVID, 'inventory', `dashboard-controls${OUTPUT_SUFFIX}.json`), JSON.stringify(rows, null, 2) + '\n')
    fs.writeFileSync(path.join(EVID, 'verify', `dashboard-control-summary${OUTPUT_SUFFIX}.json`), JSON.stringify(summary, null, 2) + '\n')
    return summary
  }
  try {
    for (const role of ROLES) {
      const session = loadSession(role)
      for (const surface of SURFACES) {
        const context = await browser.newContext({
          viewport: { width: surface.width, height: surface.height },
          isMobile: surface.isMobile,
          hasTouch: surface.isMobile,
        })
        const page = await context.newPage()
        await inject(page, session, surface.locale)
        const networkEvents = []
        const consoleErrors = []
        page.on('response', (res) => {
          const url = res.url()
          if (url.includes('/dashboard/')) networkEvents.push({ status: res.status(), url: url.replace(/^https?:\/\/[^/]+/, '') })
        })
        page.on('console', (msg) => {
          if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 400))
        })
        page.on('pageerror', (err) => consoleErrors.push(String(err).slice(0, 400)))

        for (const pageId of PAGES) {
          const key = `${role}-${surface.locale}-${surface.viewport}-${pageId}`
          try {
            await openScreen(page, pageId)
            const controls = await inventory(page)
            const dir = await page.evaluate(() => {
              const shell = document.querySelector('[data-testid="app-shell"]')
              return shell?.getAttribute('dir')
                || document.documentElement.getAttribute('dir')
                || getComputedStyle(document.body).direction
            })
            const body = await page.evaluate(() => document.body?.innerText || '')
            const authWall = /access verification required|unauthorized|forbidden/i.test(body) && body.length < 1800
            const startConsole = consoleErrors.length
            let exercised = 0
            const exerciseBudget =
              role === 'owner' && surface.locale === 'en' && surface.viewport === 'desktop'
                ? 4
                : surface.locale === 'en' && surface.viewport === 'desktop'
                  ? 4
                  : 0
            for (const control of controls) {
              const safeCandidate =
                !control.disabled &&
                !MUTATION_RE.test(control.name) &&
                (
                  ['tab', 'menuitem', 'combobox', 'checkbox', 'radio', 'switch'].includes(control.role) ||
                  ['input', 'select', 'textarea', 'summary'].includes(control.tag) ||
                  Boolean(control.href) ||
                  SAFE_RE.test(control.name)
                )
              const test =
                safeCandidate && exercised >= exerciseBudget
                  ? {
                      expected: 'Control is backed by handler/route and behaves consistently across roles/locales.',
                      actual: 'Inventoried on this surface; exercised on representative surface or statically verified.',
                      status: 'unproven',
                      severity: 'P3',
                    }
                  : await exercise(page, pageId, control, networkEvents)
              if (test.status !== 'unproven') exercised += 1
              rows.push({
                id: `${key}-${control.role || control.tag}-${slug(control.name)}-${control.index}`,
                screen: pageId,
                role,
                locale: surface.locale,
                layout: surface.locale === 'ar' ? 'RTL' : 'LTR',
                viewport: surface.viewport,
                control: control.name || '(unnamed)',
                control_type: control.role || control.tag,
                expected_behavior: test.expected,
                actual_result: test.actual,
                status: test.status,
                severity: test.severity,
                exact_fix_location: '',
                href: control.href,
                disabled: control.disabled,
                metadata: control,
              })
            }
            await openScreen(page, pageId)
            await page.keyboard.press('Tab').catch(() => {})
            const keyboardFocus = await page.evaluate(() => {
              const el = document.activeElement
              return Boolean(el && el !== document.body && (
                el.matches('button,a[href],input,select,textarea,[tabindex]') ||
                el.getAttribute('role')
              ))
            })
            const pageErrors = consoleErrors.slice(startConsole)
            pageSummaries.push({
              key,
              screen: pageId,
              role,
              locale: surface.locale,
              viewport: surface.viewport,
              dir,
              authWall,
              controls: controls.length,
              exercised,
              keyboardFocus,
              consoleErrors: pageErrors,
            })
            if (surface.viewport === 'mobile' && ['overview', 'employees', 'settings'].includes(pageId)) {
              const shotDir = path.join(EVID, 'screenshots', role, `${surface.locale}-${surface.viewport}`)
              fs.mkdirSync(shotDir, { recursive: true })
              await page.screenshot({ path: path.join(shotDir, `${pageId}.png`), fullPage: false })
            }
            console.log(`AUDITED ${key} controls=${controls.length} exercised=${exercised}`)
          } catch (error) {
            pageSummaries.push({
              key, screen: pageId, role, locale: surface.locale, viewport: surface.viewport,
              fatal: String(error), controls: 0, exercised: 0,
            })
            console.log(`FAILED ${key} ${String(error).slice(0, 160)}`)
          }
          writeOutputs()
        }
        await context.close()
      }
    }
  } finally {
    await browser.close()
  }

  const summary = writeOutputs()
  console.log(`CONTROL_AUDIT controls=${summary.controls} pages=${summary.pages} ${JSON.stringify(summary.status_counts)}`)
}

run().catch((error) => {
  console.error(error)
  process.exit(1)
})
