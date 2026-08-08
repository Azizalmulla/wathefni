#!/usr/bin/env node
/**
 * Documents hierarchy presentation contract.
 * Attention / current / history must not double-render the current file.
 */
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-docs-hierarchy-'))
const failures = []
let passed = 0

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
        files: [path.join(ROOT, 'src/features/documents/documentsHierarchy.ts')],
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
  return require(path.join(OUT, 'src/features/documents/documentsHierarchy.js'))
}

try {
  const { documentsHierarchy } = compile()
  const currentFile = 'file-current'
  const oldFile = 'file-old'
  const orphan = 'file-orphan'
  const compliance = [
    {
      document_type: 'civil_id',
      label: 'Civil ID',
      review_status: 'expired',
      review_status_label: 'Expired',
      renewal_required: true,
      current_file_id: currentFile,
      versions: [
        { version_id: 'v2', version_no: 2, review_status: 'expired', is_current: true, file_id: currentFile },
        { version_id: 'v1', version_no: 1, review_status: 'hr_reviewed', is_current: false, file_id: oldFile },
      ],
    },
    {
      document_type: 'passport',
      label: 'Passport',
      review_status: 'hr_reviewed',
      review_status_label: 'HR reviewed',
      current_file_id: 'passport-current',
      versions: [
        { version_id: 'p1', version_no: 1, review_status: 'hr_reviewed', is_current: true, file_id: 'passport-current' },
      ],
    },
  ]
  const documents = [
    { file_id: currentFile, label: 'Civil ID scan', has_file: true, stored_at: '2026-01-01' },
    { file_id: oldFile, label: 'Old Civil ID', has_file: true, stored_at: '2025-01-01' },
    { file_id: orphan, label: 'Extra upload', has_file: true, stored_at: '2024-01-01' },
    { file_id: 'passport-current', label: 'Passport', has_file: true, stored_at: '2026-02-01' },
  ]

  const h = documentsHierarchy(compliance, documents)
  check('expired civil id goes to attention', h.attention.map((i) => i.document_type).join(',') === 'civil_id')
  check('reviewed passport stays current', h.current.map((i) => i.document_type).join(',') === 'passport')
  check(
    'current files are not duplicated in history',
    !h.history.some((e) => e.fileId === currentFile || e.fileId === 'passport-current'),
    JSON.stringify(h.history),
  )
  check(
    'previous version and orphan registry files appear once in history',
    h.history.map((e) => e.fileId).sort().join(',') === [oldFile, orphan].sort().join(','),
    JSON.stringify(h.history),
  )
  check('complianceUnavailable is false when journey rows exist', h.complianceUnavailable === false)
  check(
    'registry-only payload marks compliance partial',
    documentsHierarchy([], documents).complianceUnavailable === true,
  )
  check('empty payload is genuinely empty', documentsHierarchy([], []).attention.length === 0)

  console.log('---')
  if (failures.length) {
    console.log(`FAIL count=${failures.length}: ${failures.join(', ')}`)
    process.exit(1)
  }
  console.log(`PASS documents hierarchy (${passed} checks)`)
} finally {
  fs.rmSync(OUT, { recursive: true, force: true })
}
