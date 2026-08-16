#!/usr/bin/env node
/**
 * Behavioural tests for the Employee App composition contract.
 *
 * The static verifier proves the contract is wired; this proves it actually
 * derives the right shape for every entitlement combination the canary can hit
 * (zero, one, two, four, full suite, onboarding active, onboarding completed),
 * plus deep-link admission. It runs the real TypeScript module rather than a
 * re-implementation: the source is compiled to CommonJS in a temp dir and
 * required, so drift between test and product is impossible.
 */
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-composition-'))

let passed = 0
const failures = []

function check(name, ok, detail) {
  if (ok) {
    passed += 1
    console.log(`PASS  ${name}`)
  } else {
    failures.push(name)
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

function compileComposition() {
  const tsconfig = path.join(OUT, 'tsconfig.json')
  fs.writeFileSync(
    tsconfig,
    JSON.stringify(
      {
        compilerOptions: {
          target: 'es2019',
          module: 'commonjs',
          moduleResolution: 'node',
          baseUrl: ROOT,
          paths: { '@/*': ['src/*'] },
          rootDir: ROOT,
          outDir: OUT,
          esModuleInterop: true,
          skipLibCheck: true,
          strict: false,
          typeRoots: [path.join(ROOT, 'node_modules/@types')],
          types: ['node'],
        },
        files: [path.join(ROOT, 'src/composition/employeeAppComposition.ts')],
      },
      null,
      2,
    ),
  )
  execFileSync(path.join(ROOT, 'node_modules/.bin/tsc'), ['-p', tsconfig], { stdio: 'pipe' })
  // Emitted code keeps the `@/...` specifiers, so map them through node_modules.
  const shim = path.join(OUT, 'node_modules')
  fs.mkdirSync(shim, { recursive: true })
  const alias = path.join(shim, '@')
  if (!fs.existsSync(alias)) fs.symlinkSync(path.join(OUT, 'src'), alias, 'junction')
  return require(path.join(OUT, 'src/composition/employeeAppComposition.js'))
}

const ALL_FEATURES = [
  'home',
  'profile',
  'inbox',
  'settings',
  'onboarding',
  'documents',
  'attendance',
  'shifts',
  'leave',
  'payslips',
  'bank',
  'performance',
  'talent',
  'learning',
  'benefits',
  'engagement',
  'preboarding',
  'probation',
]

function me(enabled, extraActions = {}) {
  const features = {}
  for (const key of ALL_FEATURES) {
    const on = enabled.includes(key)
    features[key] = { enabled: on, actions: on ? ['view', ...(extraActions[key] || [])] : [] }
  }
  return { ok: true, features }
}

function main() {
  const composition = compileComposition()
  const {
    compositionFromMe,
    canOpenPath,
    openableHref,
    resolveRoute,
    homeTasksFromServer,
    APP_ROUTES,
    HOME_ROUTE,
    INBOX_ROUTE,
  } = composition

  // --- shape A: zero entitlements (core shell only)
  const zero = compositionFromMe(me([]))
  check('zero-module Home has no entitlement tiles', zero.homeTiles.length === 0)
  check('zero-module Home lays out wide', zero.wideHomeTiles === true)
  check('zero-module keeps core surfaces', zero.core.home && zero.core.inbox && zero.core.profile && zero.core.settings)
  check('zero-module hides optional tabs', zero.tabs.schedule === false && zero.tabs.leave === false)
  check('no separate compliance tab ever', zero.separateComplianceTab === false)
  check('zero-module has no Schedule surface', zero.schedule.available === false)

  // --- shape B: one module
  const one = compositionFromMe(me(['leave']))
  check('one-module Home shows exactly one tile', one.homeTiles.join(',') === 'leave')
  check('one-module Home stays wide', one.wideHomeTiles === true)
  check('one-module shows only its tab', one.tabs.leave === true && one.tabs.schedule === false)

  // --- shape C: two modules — Shifts and Attendance are one Schedule surface
  const two = compositionFromMe(me(['shifts', 'attendance']))
  check('shifts + attendance collapse into one Schedule tile', two.homeTiles.join(',') === 'schedule')
  check('a single Schedule tile lays out wide', two.wideHomeTiles === true)
  check(
    'Schedule reports both contributing authorities',
    two.schedule.available === true && two.schedule.shifts === true && two.schedule.attendance === true,
  )

  // --- Schedule appears with either authority alone, and never duplicates itself
  const shiftsOnly = compositionFromMe(me(['shifts']))
  const attendanceOnly = compositionFromMe(me(['attendance']))
  check(
    'shifts alone opens Schedule',
    shiftsOnly.homeTiles.join(',') === 'schedule' &&
      shiftsOnly.tabs.schedule === true &&
      shiftsOnly.schedule.attendance === false,
  )
  check(
    'attendance alone opens Schedule',
    attendanceOnly.homeTiles.join(',') === 'schedule' &&
      attendanceOnly.tabs.schedule === true &&
      attendanceOnly.schedule.shifts === false,
  )

  // --- shape D: four modules
  const four = compositionFromMe(me(['shifts', 'attendance', 'leave', 'documents']))
  check('four-module Home keeps canonical tile order', four.homeTiles.join(',') === 'schedule,leave,documents')
  check('four-module Home switches to the grid', four.wideHomeTiles === false)

  // --- shape E: full suite
  const fullMe = me(['onboarding', 'documents', 'attendance', 'shifts', 'leave', 'payslips', 'bank'])
  const full = compositionFromMe(fullMe)
  check(
    'full-suite Home shows one tile per destination',
    full.homeTiles.join(',') === 'schedule,leave,documents,payslips',
  )
  check('Inbox is never a Home module tile', !full.homeTiles.includes('inbox'))
  check('Bank is never a Home module tile', !full.homeTiles.includes('bank'))
  const perfOnly = compositionFromMe(me(['performance']))
  check('performance-only Home shows the Performance tile', perfOnly.homeTiles.join(',') === 'performance')
  check('performance is a Home destination, not a tab', perfOnly.homeDestinations.map((d) => d.id).join(',') === 'performance')
  const talentOnly = compositionFromMe(me(['talent']))
  check('talent-only Home shows the Talent tile', talentOnly.homeTiles.join(',') === 'talent')
  check('talent is a Home destination, not a tab', talentOnly.homeDestinations.map((d) => d.id).join(',') === 'talent')
  const learningOnly = compositionFromMe(me(['learning']))
  check('learning-only Home shows the Learning tile', learningOnly.homeTiles.join(',') === 'learning')
  check('learning is a Home destination, not a tab', learningOnly.homeDestinations.map((d) => d.id).join(',') === 'learning')
  const benefitsOnly = compositionFromMe(me(['benefits']))
  check('benefits-only Home shows the Benefits tile', benefitsOnly.homeTiles.join(',') === 'benefits')
  check('benefits is a Home destination, not a tab', benefitsOnly.homeDestinations.map((d) => d.id).join(',') === 'benefits')
  const engagementOnly = compositionFromMe(me(['engagement']))
  check('engagement-only Home shows the Engagement tile', engagementOnly.homeTiles.join(',') === 'engagement')
  check('engagement is a Home destination, not a tab', engagementOnly.homeDestinations.map((d) => d.id).join(',') === 'engagement')

  // --- shape F: onboarding journey lifecycle
  const active = compositionFromMe(me(['onboarding']), {
    featureEnabled: true,
    requiredPending: 2,
    pendingCount: 3,
    requiredTotal: 5,
  })
  check('onboarding in progress shows the journey', active.showOnboardingJourney === true)
  check('onboarding in progress is not demoted', active.onboardingDemoted === false)

  const done = compositionFromMe(me(['onboarding']), {
    featureEnabled: true,
    requiredPending: 0,
    pendingCount: 0,
    requiredTotal: 5,
  })
  check('completed onboarding hides the journey', done.showOnboardingJourney === false)
  check('completed onboarding is demoted', done.onboardingDemoted === true)

  const offOnboarding = compositionFromMe(me([]), {
    featureEnabled: false,
    requiredPending: 0,
    pendingCount: 0,
    requiredTotal: 0,
  })
  check('disabled onboarding is demoted, not shown', offOnboarding.onboardingDemoted === true)

  // Loading onboarding data must not claim completion.
  const loading = compositionFromMe(me(['onboarding']), {
    featureEnabled: true,
    requiredPending: 0,
    pendingCount: 0,
    requiredTotal: 0,
  })
  check('unloaded onboarding counts do not claim completion', loading.showOnboardingJourney === false)

  const journeys = compositionFromMe(me(['preboarding', 'probation']))
  check('preboarding/probation are journeys, not Home destinations', journeys.homeDestinations.length === 0)
  check('preboarding journey is entitled without becoming a tile', journeys.showPreboardingJourney === true && !journeys.homeTiles.includes('preboarding'))
  check('probation journey is entitled without becoming a tile', journeys.showProbationJourney === true && !journeys.homeTiles.includes('probation'))
  check('preboarding deep link opens when entitled', canOpenPath(me(['preboarding']), '/preboarding') === true)
  check('probation deep link is refused when unentitled', canOpenPath(me(['preboarding']), '/probation') === false)

  // --- Home renders one launcher, and never a second route to a tab
  check(
    'Home destinations are the entitled modules with no tab',
    full.homeDestinations.map((d) => d.id).join(',') === 'documents',
    JSON.stringify(full.homeDestinations.map((d) => d.id)),
  )
  check(
    'no destination duplicates a bottom tab',
    full.homeDestinations.every((d) => !(d.id in full.tabs) || full.tabs[d.id] !== true),
    JSON.stringify(full.homeDestinations.map((d) => d.id)),
  )
  check(
    'a tabbed module is still an entitlement tile, just not a Home route',
    full.homeTiles.includes('schedule') &&
      full.homeTiles.includes('leave') &&
      full.homeTiles.includes('payslips') &&
      full.homeDestinations.every((d) => full.homeTiles.includes(d.id)),
  )
  check(
    'every destination points at a registry route',
    full.homeDestinations.every((d) => d.href in APP_ROUTES),
    JSON.stringify(full.homeDestinations),
  )
  check('zero-module Home offers no destinations', zero.homeDestinations.length === 0)
  check(
    'a documents-only company still gets its one destination',
    compositionFromMe(me(['documents'])).homeDestinations.map((d) => d.id).join(',') === 'documents',
  )
  check(
    'a leave-only company has a tab and therefore no Home destination',
    compositionFromMe(me(['leave'])).homeDestinations.length === 0,
  )
  check(
    'leave request action is the only primary action, and only when granted',
    compositionFromMe(me(['leave'])).homePrimaryAction === null &&
      compositionFromMe(me(['leave'], { leave: ['request'] })).homePrimaryAction.href === '/leave/request',
  )

  // --- deep links admit only entitled destinations
  const leaveOnly = me(['leave'])
  check('entitled deep link opens', canOpenPath(leaveOnly, '/(tabs)/leave') === true)
  check('unentitled deep link is refused', canOpenPath(leaveOnly, '/payslips') === false)
  check('core deep link always opens', canOpenPath(me([]), INBOX_ROUTE) === true)
  // The bell replaced the tab, so every link already in flight carries the old
  // path. It must still land on the Inbox rather than fall back to Home.
  check(
    'the pre-bell Inbox path still opens the Inbox',
    openableHref(me([]), '/(tabs)/notifications') === INBOX_ROUTE,
  )
  check(
    'Inbox is reachable without any entitlement, from Home rather than a tab',
    zero.inboxEntry.href === INBOX_ROUTE &&
      zero.inboxEntry.surface === 'home_header' &&
      !('inbox' in zero.tabs),
  )
  check(
    'Payslips takes the freed tab slot only when entitled',
    full.tabs.payslips === true && compositionFromMe(me(['leave'])).tabs.payslips === false,
  )
  check('unknown deep link is refused', canOpenPath(fullMe, '/totally-unknown') === false)
  check('empty deep link is refused', canOpenPath(fullMe, '') === false)

  // --- Schedule is a combined read: either authority admits it, neither refuses it
  check(
    'Schedule opens on shifts alone and on attendance alone',
    canOpenPath(me(['shifts']), '/(tabs)/schedule') === true &&
      canOpenPath(me(['attendance']), '/(tabs)/schedule') === true,
  )
  check('Schedule is refused without either authority', canOpenPath(leaveOnly, '/(tabs)/schedule') === false)
  check(
    'the pre-Schedule paths still land on the combined surface',
    openableHref(me(['shifts']), '/shifts') === '/(tabs)/schedule' &&
      openableHref(me(['attendance']), '/attendance') === '/(tabs)/schedule' &&
      openableHref(me(['shifts']), '/(tabs)/shifts') === '/(tabs)/schedule',
  )
  check(
    'an old attendance link is refused when neither authority is entitled',
    openableHref(leaveOnly, '/attendance') === null,
  )
  check(
    'Schedule declares no query parameters',
    resolveRoute('/(tabs)/schedule?shift_id=abc') === null,
  )

  // --- strict route registry: no substring guessing, no stray parameters
  check('registry resolves an explicit alias', resolveRoute('/inbox').route === INBOX_ROUTE)
  check('registry canonicalizes the root path', resolveRoute('/').route === HOME_ROUTE)
  check('registry tolerates a trailing slash', resolveRoute('/documents/').route === '/documents')
  check(
    'a path that merely contains a known word is refused',
    resolveRoute('/evil-payslips-phish') === null && resolveRoute('/admin/documents/all') === null,
  )
  check(
    'absolute and scheme URLs are refused',
    resolveRoute('https://wathefni.ai/payslips') === null &&
      resolveRoute('wathefni://payslips') === null &&
      resolveRoute('//wathefni.ai/payslips') === null &&
      resolveRoute('payslips') === null,
  )
  check('traversal is refused', resolveRoute('/documents/../settings') === null)
  check(
    'declared parameters are accepted and re-encoded',
    resolveRoute('/payslips?payslip_id=abc-123').href === '/payslips?payslip_id=abc-123',
  )
  check(
    'undeclared or malformed parameters invalidate the link',
    resolveRoute('/payslips?other=1') === null &&
      resolveRoute('/documents?payslip_id=abc') === null &&
      resolveRoute('/payslips?payslip_id=a b') === null,
  )
  check(
    'openableHref returns null instead of a dead route',
    openableHref(leaveOnly, '/payslips?payslip_id=abc') === null &&
      openableHref(fullMe, '/payslips?payslip_id=abc') === '/payslips?payslip_id=abc' &&
      openableHref(fullMe, '/nope') === null,
  )

  // --- tasks come from the server projection; the client only maps and gates them
  const serverTasks = [
    { kind: 'onboarding_documents', module: 'onboarding', count: 2, severity: 'action_required' },
    { kind: 'document_renewal', module: 'documents', count: 1, severity: 'action_required' },
    { kind: 'leave_pending', module: 'leave', count: 1, severity: 'informational' },
    { kind: 'payslip_released', module: 'payslips', count: 1, severity: 'informational' },
  ]
  check('zero-entitlement client drops every server task', homeTasksFromServer(me([]), serverTasks).length === 0)
  check(
    'full-suite client keeps the server task order and counts',
    homeTasksFromServer(fullMe, serverTasks)
      .map((task) => `${task.kind}:${task.count}:${task.severity}`)
      .join(',') ===
      'onboarding_documents:2:action_required,document_renewal:1:action_required,leave_pending:1:informational,payslip_released:1:informational',
    JSON.stringify(homeTasksFromServer(fullMe, serverTasks)),
  )
  check(
    'a task kind the client does not know is ignored, not guessed',
    homeTasksFromServer(fullMe, [{ kind: 'future_module_thing', count: 9 }]).length === 0,
  )
  check(
    'a revoked entitlement drops its task before it can be tapped',
    homeTasksFromServer(me(['onboarding']), serverTasks).map((task) => task.kind).join(',') ===
      'onboarding_documents',
  )
  check(
    'every presented task points at a path the employee may open',
    homeTasksFromServer(fullMe, serverTasks).every((task) => canOpenPath(fullMe, task.href)),
  )
  check('missing server tasks yield no tasks', homeTasksFromServer(fullMe, null).length === 0)

  console.log('---')
  if (failures.length) {
    console.log(`FAIL count=${failures.length}: ${failures.join(', ')}`)
    return 1
  }
  console.log(`PASS employee app composition shapes (${passed} checks)`)
  return 0
}

let code = 1
try {
  code = main()
} finally {
  fs.rmSync(OUT, { recursive: true, force: true })
}
process.exit(code)
