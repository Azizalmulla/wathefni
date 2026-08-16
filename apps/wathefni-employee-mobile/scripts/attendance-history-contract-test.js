/**
 * Lightweight contract checks for attendance history month bounds / filters.
 * Run: node scripts/attendance-history-contract-test.js
 */
const assert = require('assert')

// Mirror of monthDateBounds / buildMonthFilters from AttendanceHistoryView.
function pad2(n) {
  return n < 10 ? `0${n}` : String(n)
}

function monthDateBounds(year, month1to12) {
  const lastDay = new Date(Date.UTC(year, month1to12, 0)).getUTCDate()
  return {
    dateFrom: `${year}-${pad2(month1to12)}-01`,
    dateTo: `${year}-${pad2(month1to12)}-${pad2(lastDay)}`,
  }
}

function buildMonthFilters(todayISO, count = 6) {
  const [y, m] = todayISO.slice(0, 10).split('-').map(Number)
  const filters = [{ kind: 'all' }]
  let year = y
  let month = m
  for (let i = 0; i < count; i += 1) {
    const bounds = monthDateBounds(year, month)
    filters.push({ kind: 'month', year, month, ...bounds })
    month -= 1
    if (month < 1) {
      month = 12
      year -= 1
    }
  }
  return filters
}

const feb = monthDateBounds(2024, 2)
assert.strictEqual(feb.dateFrom, '2024-02-01')
assert.strictEqual(feb.dateTo, '2024-02-29')

const filters = buildMonthFilters('2026-08-09', 3)
assert.strictEqual(filters[0].kind, 'all')
assert.strictEqual(filters[1].kind, 'month')
assert.strictEqual(filters[1].dateFrom, '2026-08-01')
assert.strictEqual(filters[1].dateTo, '2026-08-31')
assert.strictEqual(filters[2].dateFrom, '2026-07-01')
assert.strictEqual(filters[3].dateFrom, '2026-06-01')

console.log('PASS attendance history month contract')
