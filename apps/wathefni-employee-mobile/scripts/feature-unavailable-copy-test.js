#!/usr/bin/env node
/**
 * FeatureUnavailable reason → customer copy keys (never echo raw enums).
 */
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-feature-copy-'))

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
          rootDir: ROOT,
          outDir: OUT,
          esModuleInterop: true,
          skipLibCheck: true,
          strict: false,
        },
        files: [path.join(ROOT, 'src/lib/featureUnavailableCopy.ts')],
      },
      null,
      2,
    ),
  )
  execFileSync(path.join(ROOT, 'node_modules/.bin/tsc'), ['-p', tsconfig], { stdio: 'pipe' })
  return require(path.join(OUT, 'src/lib/featureUnavailableCopy.js'))
}

function main() {
  const {
    featureUnavailableReasonKind,
    featureUnavailableMessageKey,
    featureUnavailableTitleKey,
  } = compile()

  check('module_disabled maps', featureUnavailableReasonKind('module_disabled') === 'module_disabled')
  check(
    'bank allowlist maps to no_access',
    featureUnavailableReasonKind('bank_ess_not_allowlisted') === 'no_access',
  )
  check(
    'feature_not_available maps to temporary',
    featureUnavailableReasonKind('feature_not_available') === 'temporarily_unavailable',
  )
  check(
    'unknown raw enum stays generic',
    featureUnavailableReasonKind('SOME_INTERNAL_ENUM_XYZ') === 'generic',
  )
  check('null reason is generic', featureUnavailableReasonKind(null) === 'generic')
  check(
    'message keys are customer i18n, not raw codes',
    featureUnavailableMessageKey('module_disabled') === 'feature.unavailable.moduleDisabled' &&
      featureUnavailableMessageKey('bank_ess_not_allowlisted') === 'feature.unavailable.noAccess' &&
      featureUnavailableMessageKey('feature_not_available') ===
        'feature.unavailable.temporarilyUnavailable' &&
      featureUnavailableMessageKey('weird') === 'feature.unavailable.message',
  )
  check(
    'temporary title variant',
    featureUnavailableTitleKey('ess_v5_disabled') ===
      'feature.unavailable.temporarilyUnavailableTitle',
  )

  const en = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/i18n/en.json'), 'utf8'))
  const ar = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/i18n/ar.json'), 'utf8'))
  const keys = [
    'feature.unavailable.moduleDisabled',
    'feature.unavailable.noAccess',
    'feature.unavailable.temporarilyUnavailable',
    'feature.unavailable.temporarilyUnavailableTitle',
  ]
  check(
    'EN+AR feature reason copy present and equal keysets for these keys',
    keys.every((k) => typeof en[k] === 'string' && typeof ar[k] === 'string'),
  )
  check(
    'customer copy does not echo backend reason tokens',
    keys.every(
      (k) =>
        !/module_disabled|bank_ess|feature_not_available|ess_v5/i.test(en[k]) &&
        !/module_disabled|bank_ess|feature_not_available|ess_v5/i.test(ar[k]),
    ),
  )

  console.log('---')
  if (failures.length) {
    console.log(`FAIL count=${failures.length}: ${failures.join(', ')}`)
    return 1
  }
  console.log(`PASS feature unavailable copy (${passed} checks)`)
  return 0
}

let code = 1
try {
  code = main()
} finally {
  fs.rmSync(OUT, { recursive: true, force: true })
}
process.exit(code)
