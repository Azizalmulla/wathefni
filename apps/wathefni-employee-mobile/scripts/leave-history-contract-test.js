/**
 * Lightweight year-filter contract for Leave history UI.
 * Run: node scripts/leave-history-contract-test.js
 */
const assert = require('assert')

function buildYearFilters(todayISO, count = 5) {
  const year = Number(todayISO.slice(0, 4))
  const filters = [{ kind: 'all' }]
  for (let i = 0; i < count; i += 1) {
    filters.push({ kind: 'year', year: year - i })
  }
  return filters
}

function historyPath(locale, year, status, cursor) {
  const params = new URLSearchParams()
  params.set('locale', locale)
  params.set('limit', '30')
  if (year.kind === 'year') params.set('year', String(year.year))
  if (status) params.set('status', status)
  if (cursor) params.set('cursor', cursor)
  return `/app/leave/history?${params.toString()}`
}

const filters = buildYearFilters('2026-08-09', 3)
assert.strictEqual(filters[0].kind, 'all')
assert.strictEqual(filters[1].year, 2026)
assert.strictEqual(filters[2].year, 2025)
assert.strictEqual(filters[3].year, 2024)

const path = historyPath('en', { kind: 'year', year: 2025 }, 'cancelled', 'abc')
assert.ok(path.includes('year=2025'))
assert.ok(path.includes('status=cancelled'))
assert.ok(path.includes('cursor=abc'))
assert.ok(!historyPath('en', { kind: 'all' }, null).includes('year='))

console.log('PASS leave history year/status contract')
