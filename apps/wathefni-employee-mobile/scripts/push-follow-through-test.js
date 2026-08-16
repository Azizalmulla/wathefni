#!/usr/bin/env node
/**
 * Push tap follow-through: candidate paths + registry/entitlement gating.
 * Compiles the real TypeScript modules so product and test cannot drift.
 */
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-push-ft-'))

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

function compile() {
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
        files: [
          path.join(ROOT, 'src/composition/employeeAppComposition.ts'),
          path.join(ROOT, 'src/push/resolvePushDestination.ts'),
          path.join(ROOT, 'src/capabilities.ts'),
          path.join(ROOT, 'src/api/types.ts'),
          path.join(ROOT, 'src/api/client.ts'),
        ],
      },
      null,
      2,
    ),
  )
  execFileSync(path.join(ROOT, 'node_modules/.bin/tsc'), ['-p', tsconfig], { stdio: 'pipe' })
  const shim = path.join(OUT, 'node_modules')
  fs.mkdirSync(shim, { recursive: true })
  const alias = path.join(shim, '@')
  if (!fs.existsSync(alias)) fs.symlinkSync(path.join(OUT, 'src'), alias, 'junction')
  return require(path.join(OUT, 'src/push/resolvePushDestination.js'))
}

function me(enabled) {
  const ALL = [
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
  ]
  const features = {}
  for (const key of ALL) {
    features[key] = { enabled: enabled.includes(key), actions: [] }
  }
  return { ok: true, features }
}

function main() {
  const { candidatePathFromPushData, pushFollowThroughHref, FLOW_DEFAULT_PATHS } = compile()
  // Read the Inbox path from the contract rather than restating it: the tab-to-bell
  // move changed it once already, and a test with its own copy would have passed.
  const { INBOX_ROUTE } = require(path.join(OUT, 'src/composition/employeeAppComposition.js'))
  const full = me(['shifts', 'attendance', 'leave', 'documents', 'payslips', 'onboarding', 'bank'])
  const leaveOnly = me(['leave'])

  check('flow payroll maps to payslips', candidatePathFromPushData({ flow: 'payroll' }) === '/payslips')
  check('flow shift maps to schedule', candidatePathFromPushData({ flow: 'shift' }) === '/(tabs)/schedule')
  check(
    'explicit deep_link path wins',
    candidatePathFromPushData({ flow: 'leave', deep_link: { path: '/documents' } }) === '/documents',
  )
  check(
    'payslip_id is appended to payslips path',
    candidatePathFromPushData({
      flow: 'payroll',
      deep_link: { path: '/payslips', payslip_id: 'ps-1' },
    }) === '/payslips?payslip_id=ps-1',
  )
  check(
    'flat path is accepted',
    candidatePathFromPushData({ path: '/(tabs)/leave' }) === '/(tabs)/leave',
  )
  check('empty data yields null candidate', candidatePathFromPushData({}) === null)
  check('unknown flow yields null candidate', candidatePathFromPushData({ flow: 'calendar' }) === null)
  check('FLOW_DEFAULT_PATHS covers payroll and leave', Boolean(FLOW_DEFAULT_PATHS.payroll && FLOW_DEFAULT_PATHS.leave))
  check(
    'FLOW_DEFAULT_PATHS covers preboarding and probation',
    FLOW_DEFAULT_PATHS.preboarding === '/preboarding' && FLOW_DEFAULT_PATHS.probation === '/probation',
  )

  check(
    'entitled push follow-through opens the destination',
    pushFollowThroughHref(full, { deep_link: { path: '/payslips', payslip_id: 'abc' } }) ===
      '/payslips?payslip_id=abc',
  )
  check(
    'unentitled push destination falls back to Inbox',
    pushFollowThroughHref(leaveOnly, { path: '/payslips' }) === INBOX_ROUTE,
  )
  check(
    'malformed absolute URL falls back to Inbox',
    pushFollowThroughHref(full, { path: 'https://evil.example/payslips' }) === INBOX_ROUTE,
  )
  check(
    'unknown path falls back to Inbox',
    pushFollowThroughHref(full, { path: '/totally-unknown' }) === INBOX_ROUTE,
  )
  check(
    'flow-only entitled hint opens schedule',
    pushFollowThroughHref(full, { flow: 'shift' }) === '/(tabs)/schedule',
  )
  check(
    'flow-only unentitled hint falls back to Inbox',
    pushFollowThroughHref(leaveOnly, { flow: 'shift' }) === INBOX_ROUTE,
  )

  console.log('---')
  if (failures.length) {
    console.log(`FAIL count=${failures.length}: ${failures.join(', ')}`)
    return 1
  }
  console.log(`PASS push follow-through (${passed} checks)`)
  return 0
}

let code = 1
try {
  code = main()
} finally {
  fs.rmSync(OUT, { recursive: true, force: true })
}
process.exit(code)
