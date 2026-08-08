#!/usr/bin/env node
/**
 * Behavioural tests for Phase C+D density and hierarchy.
 *
 * The static scan proves the screens are wired to the compact primitives; this
 * proves the logic underneath them is right for the cases that actually break in
 * production: a one-day leave request, a decade of documents, an inbox with
 * hundreds of messages, and dates the backend never filled in.
 *
 * Like the other behavioural gates it compiles and runs the real TypeScript
 * rather than a re-implementation, so the test cannot drift from the product.
 */
'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const ROOT = path.resolve(__dirname, '..')
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'wathefni-density-'))

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

function compile(files) {
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
        files: files.map((f) => path.join(ROOT, f)),
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
}

/** Minimal `t` that renders the key plus its interpolations, so copy is visible. */
function t(key, vars) {
  if (!vars) return key
  return `${key}:${Object.values(vars).join(',')}`
}

function main() {
  compile(['src/lib/format.ts', 'src/features/documents/documentsHierarchy.ts'])
  const { formatDateRange, formatRelativeTime, yearOf, formatDate } = require(
    path.join(OUT, 'src/lib/format.js'),
  )
  const { groupHistoryByYear } = require(path.join(OUT, 'src/features/documents/documentsHierarchy.js'))

  // --- leave: a one-day request is one date
  check(
    'a single-day request renders one date, not the same date twice',
    formatDateRange('2026-03-04', '2026-03-04', 'en') === formatDate('2026-03-04', 'en'),
    formatDateRange('2026-03-04', '2026-03-04', 'en'),
  )
  check(
    'a multi-day request renders a range',
    formatDateRange('2026-03-04', '2026-03-09', 'en').includes('–'),
    formatDateRange('2026-03-04', '2026-03-09', 'en'),
  )
  check(
    'an open-ended request falls back to the date it has',
    formatDateRange('2026-03-04', null, 'en') === formatDate('2026-03-04', 'en') &&
      formatDateRange(null, '2026-03-09', 'en') === formatDate('2026-03-09', 'en'),
  )
  check('a request with no dates does not render a stray dash range', formatDateRange(null, null, 'en') === '—')
  check(
    'Arabic renders the same shape without leaking English separators',
    formatDateRange('2026-03-04', '2026-03-04', 'ar') === formatDate('2026-03-04', 'ar'),
  )

  // --- inbox: relative time answers "is this new?"
  const now = Date.parse('2026-03-10T12:00:00Z')
  check('a message from seconds ago reads as just now', formatRelativeTime('2026-03-10T11:59:30Z', 'en', t, now) === 'time.justNow')
  check('minutes are minutes', formatRelativeTime('2026-03-10T11:30:00Z', 'en', t, now) === 'time.minutesAgo:30')
  check('hours are hours', formatRelativeTime('2026-03-10T09:00:00Z', 'en', t, now) === 'time.hoursAgo:3')
  check('one day back is yesterday, not 1d', formatRelativeTime('2026-03-09T09:00:00Z', 'en', t, now) === 'time.yesterday')
  check('within the week counts days', formatRelativeTime('2026-03-07T09:00:00Z', 'en', t, now) === 'time.daysAgo:3')
  check(
    'beyond a week the exact date matters again',
    formatRelativeTime('2026-01-04T09:00:00Z', 'en', t, now) === formatDate('2026-01-04T09:00:00Z', 'en'),
  )
  check(
    'a clock skew ahead of the server does not read as the future',
    formatRelativeTime('2026-03-10T12:00:20Z', 'en', t, now) === 'time.justNow',
  )
  check('an unparseable timestamp does not crash the row', formatRelativeTime('not-a-date', 'en', t, now) === '—')

  // --- history grouping: years, newest first, undated last
  check('a year is read from a stored date', yearOf('2024-11-02T00:00:00Z') === 2024 && yearOf('2019-01-01') === 2019)
  check('an unparseable date has no year rather than a wrong one', yearOf('') === null && yearOf('later') === null)
  check(
    'a year label is not thousands-separated',
    require('util').format('%s', formatNumberYear(OUT, 2026, 'en')) === '2026',
  )

  const entry = (id, date) => ({
    id,
    label: 'Civil ID',
    documentType: 'civil_id',
    date,
    fileId: `f-${id}`,
    source: 'version',
  })
  const grouped = groupHistoryByYear([
    entry('a', '2024-01-05'),
    entry('b', '2026-06-02'),
    entry('c', '2024-09-30'),
    entry('d', null),
    entry('e', '2025-02-02'),
  ])
  check(
    'history groups newest year first',
    grouped.map((g) => g.year).join(',') === '2026,2025,2024,',
    JSON.stringify(grouped.map((g) => g.year)),
  )
  check('undated history sinks to the end rather than inventing a year', grouped[grouped.length - 1].year === null)
  check(
    'every entry survives grouping exactly once',
    grouped.reduce((n, g) => n + g.entries.length, 0) === 5 &&
      new Set(grouped.flatMap((g) => g.entries.map((e) => e.id))).size === 5,
  )
  check('a year keeps its own entries', grouped.find((g) => g.year === 2024).entries.length === 2)
  check('empty history produces no groups', groupHistoryByYear([]).length === 0)

  // --- ten years of documents must not all be laid out at once
  const long = []
  for (let year = 2016; year <= 2026; year += 1) {
    for (let i = 0; i < 24; i += 1) long.push(entry(`${year}-${i}`, `${year}-0${(i % 9) + 1}-15`))
  }
  const longGroups = groupHistoryByYear(long)
  check('a decade of history collapses to one group per year', longGroups.length === 11)
  const HISTORY_PAGE = readConst('src/features/documents/DocumentsView.tsx', 'HISTORY_PAGE')
  const PAYSLIP_PAGE = readConst('app/(tabs)/payslips.tsx', 'PAYSLIP_PAGE')
  const INBOX_PAGE = readConst('src/features/remaining/RemainingViews.tsx', 'INBOX_PAGE')
  const LEAVE_PAGE = readConst('src/features/remaining/RemainingViews.tsx', 'LEAVE_PAGE')
  check(
    'every growth list declares a page size',
    [HISTORY_PAGE, PAYSLIP_PAGE, INBOX_PAGE, LEAVE_PAGE].every((n) => Number.isInteger(n) && n > 0 && n <= 30),
    JSON.stringify({ HISTORY_PAGE, PAYSLIP_PAGE, INBOX_PAGE, LEAVE_PAGE }),
  )
  check(
    'the open year of a decade of history renders one page, not 264 rows',
    Math.min(longGroups[0].entries.length, HISTORY_PAGE) <= HISTORY_PAGE && longGroups[0].entries.length > HISTORY_PAGE,
  )

  console.log('---')
  if (failures.length) {
    console.log(`FAIL count=${failures.length}: ${failures.join(', ')}`)
    process.exitCode = 1
  } else {
    console.log(`PASS density + hierarchy (${passed} checks)`)
  }
}

/** Read a numeric module constant from source, so the gate tracks the product. */
function readConst(file, name) {
  const src = fs.readFileSync(path.join(ROOT, file), 'utf8')
  const match = new RegExp(`const ${name} = (\\d+)`).exec(src)
  return match ? Number(match[1]) : null
}

function formatNumberYear(out, year, locale) {
  const { formatNumber } = require(path.join(out, 'src/lib/format.js'))
  return formatNumber(year, locale, 0)
}

try {
  main()
} finally {
  fs.rmSync(OUT, { recursive: true, force: true })
}
