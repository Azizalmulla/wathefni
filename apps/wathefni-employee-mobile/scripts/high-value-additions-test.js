#!/usr/bin/env node
/**
 * Phase E — behavioural gate for the high-value employee additions.
 *
 * Every addition in this phase states a number to an employee: how much leave
 * they have, how many days they are asking for, how long until a document
 * expires. The failure that matters is not a wrong layout, it is a confident
 * number that no system actually asserted. These tests are mostly about the
 * absent case: they assert silence at least as often as they assert output.
 */
const assert = require('node:assert/strict')
const path = require('node:path')
const ts = require('typescript')
const Module = require('node:module')

let pass = 0
const failures = []

function check(label, fn) {
  try {
    fn()
    pass += 1
    console.log(`      PASS  ${label}`)
  } catch (err) {
    failures.push(label)
    console.log(`      FAIL  ${label} :: ${err.message}`)
  }
}

const ROOT = path.resolve(__dirname, '..')

/** Load a TS source module by transpiling it, resolving the '@/' alias. */
function loadTs(relPath) {
  const filename = path.join(ROOT, relPath)
  const source = require('node:fs').readFileSync(filename, 'utf8')
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText
  const mod = new Module(filename, null)
  mod.filename = filename
  mod.paths = Module._nodeModulePaths(path.dirname(filename))
  const origResolve = Module._resolveFilename
  Module._resolveFilename = function (request, ...rest) {
    if (request.startsWith('@/')) return path.join(ROOT, 'src', request.slice(2))
    return origResolve.call(this, request, ...rest)
  }
  try {
    mod._compile(js, filename)
  } finally {
    Module._resolveFilename = origResolve
  }
  return mod.exports
}

const { balanceForLeaveType, balancesAreInformational } = loadTs('src/features/leave/leaveBalance.ts')
const { telHref, displayPhone } = loadTs('src/lib/contact.ts')
const { daysUntil, kuwaitToday, kuwaitDayPart, formatDateTime } = loadTs('src/lib/format.ts')

console.log('    employee app phase E — high-value additions (balance, duration, contact, expiry)')

// --- 1. Leave balance: only ever the server's number ------------------------

check('balance is silent when the company has balances switched off', () => {
  const data = { balances_enabled: false, balances: [{ leave_type: 'annual', current_balance: 21 }] }
  assert.equal(balanceForLeaveType(data, 'annual'), null)
})

check('balance is silent for a leave type with no row', () => {
  const data = { balances_enabled: true, balances: [{ leave_type: 'annual', current_balance: 21 }] }
  assert.equal(balanceForLeaveType(data, 'sick'), null)
})

check('the regression that started this: absent number never becomes 0', () => {
  // The API emits `current_balance`; the app used to read `balance_days`, which
  // is not a field the server has ever sent, and rendered `?? 0`.
  const data = { balances_enabled: true, balances: [{ leave_type: 'annual', balance_days: 14 }] }
  assert.equal(balanceForLeaveType(data, 'annual'), null, 'a non-canonical field must not be trusted')
})

check('real balance reads current_balance', () => {
  const data = { balances_enabled: true, balances: [{ leave_type: 'annual', current_balance: 21.5 }] }
  const fact = balanceForLeaveType(data, 'annual')
  assert.equal(fact.days, 21.5)
  assert.equal(fact.basis, 'current')
})

check('available wins over current_balance when the server sends it', () => {
  const data = {
    balances_enabled: true,
    balances: [{ leave_type: 'annual', current_balance: 21, reserved: 5, available: 16 }],
  }
  const fact = balanceForLeaveType(data, 'annual')
  assert.equal(fact.days, 16, 'pending requests are already deducted from available')
  assert.equal(fact.basis, 'available')
})

check('a genuine zero balance is still shown', () => {
  const data = { balances_enabled: true, balances: [{ leave_type: 'annual', current_balance: 0 }] }
  assert.equal(balanceForLeaveType(data, 'annual').days, 0)
})

check('null available falls back to current rather than reading as zero', () => {
  const data = {
    balances_enabled: true,
    balances: [{ leave_type: 'annual', current_balance: 12, reserved: null, available: null }],
  }
  assert.equal(balanceForLeaveType(data, 'annual').days, 12)
})

check('non-numeric balances are refused', () => {
  for (const value of ['21', NaN, undefined, null, {}]) {
    const data = { balances_enabled: true, balances: [{ leave_type: 'annual', current_balance: value }] }
    assert.equal(balanceForLeaveType(data, 'annual'), null, `refused: ${String(value)}`)
  }
})

check('leave type matching ignores case and padding', () => {
  const data = { balances_enabled: true, balances: [{ leave_type: 'Annual ', current_balance: 3 }] }
  assert.equal(balanceForLeaveType(data, 'annual').days, 3)
})

check('can_take_from is carried so eligibility is not implied away', () => {
  const data = {
    balances_enabled: true,
    balances: [{ leave_type: 'annual', current_balance: 21, can_take_from: '2026-09-01' }],
  }
  assert.equal(balanceForLeaveType(data, 'annual').canTakeFrom, '2026-09-01')
})

check('balances are informational while the server says not enforced', () => {
  assert.equal(balancesAreInformational({ balances_enforced: false, balances_binding: false }), true)
  assert.equal(balancesAreInformational({ balances_enforced: true }), false)
  assert.equal(balancesAreInformational(null), false)
})

// --- 2. Manager contact -----------------------------------------------------

check('kuwait 8-digit number dials internationally', () => {
  assert.equal(telHref('55667788'), 'tel:+96555667788')
})

check('number already carrying 965 is not double-prefixed', () => {
  assert.equal(telHref('96555667788'), 'tel:+96555667788')
  assert.equal(telHref('+965 5566 7788'), 'tel:+96555667788')
})

check('no contact action for a number that is not dialable', () => {
  for (const value of ['', null, undefined, '12', 'n/a', '1234567', '1'.repeat(16)]) {
    assert.equal(telHref(value), null, `refused: ${String(value)}`)
  }
})

check('manager phone is displayed grouped, never invented', () => {
  assert.equal(displayPhone('96555667788'), '5566 7788')
  assert.equal(displayPhone('55667788'), '5566 7788')
  assert.equal(displayPhone(''), '')
  assert.equal(displayPhone(null), '')
})

// --- 3. Document expiry: canonical date, Kuwait days ------------------------

check('days until expiry counts calendar days from a canonical date', () => {
  assert.equal(daysUntil('2026-08-26', '2026-08-08'), 18)
  assert.equal(daysUntil('2026-08-08', '2026-08-08'), 0)
  assert.equal(daysUntil('2026-08-01', '2026-08-08'), -7)
})

check('expiry counting crosses months and years correctly', () => {
  assert.equal(daysUntil('2027-01-01', '2026-12-31'), 1)
  assert.equal(daysUntil('2026-03-01', '2026-02-27'), 2, '2026 is not a leap year')
  assert.equal(daysUntil('2028-03-01', '2028-02-27'), 3, '2028 is a leap year')
})

check('a missing or malformed expiry yields no day count at all', () => {
  for (const value of ['', null, undefined, 'soon', '2026-13-45x', '08/26/2026']) {
    assert.equal(daysUntil(value, '2026-08-08'), null, `refused: ${String(value)}`)
  }
})

check('a timestamped expiry is read as its calendar date', () => {
  assert.equal(daysUntil('2026-08-26T00:00:00Z', '2026-08-08'), 18)
})

check('today is a Kuwait date, not the device date', () => {
  // 22:00 UTC is already the next day in Kuwait (UTC+3).
  assert.equal(kuwaitToday(new Date('2026-08-08T22:00:00Z')), '2026-08-09')
  assert.equal(kuwaitToday(new Date('2026-08-08T10:00:00Z')), '2026-08-08')

  assert.equal(kuwaitDayPart(new Date('2026-08-08T05:00:00Z')), 'morning') // 08:00 KW
  assert.equal(kuwaitDayPart(new Date('2026-08-08T10:00:00Z')), 'afternoon') // 13:00 KW
  assert.equal(kuwaitDayPart(new Date('2026-08-08T15:00:00Z')), 'evening') // 18:00 KW
  assert.equal(kuwaitDayPart(new Date('2026-08-08T20:59:00Z')), 'evening') // 23:59 KW
  assert.equal(kuwaitDayPart(new Date('2026-08-08T21:00:00Z')), 'morning') // 00:00 KW next day
})

check('expiry day count does not drift across the Kuwait day boundary', () => {
  const late = kuwaitToday(new Date('2026-08-08T21:30:00Z'))
  assert.equal(daysUntil('2026-08-26', late), 17, 'it is already the 9th in Kuwait')
})

// --- 4. Inbox exact timestamp preserved -------------------------------------

check('exact timestamp is available in both locales', () => {
  const iso = '2026-08-08T09:05:00Z'
  const en = formatDateTime(iso, 'en')
  const ar = formatDateTime(iso, 'ar')
  assert.match(en, /12:05/, `Kuwait is UTC+3, got ${en}`)
  assert.ok(en.includes('2026'), en)
  assert.ok(ar.length > 0 && ar !== en, 'arabic timestamp must be localized')
})

check('exact timestamp is empty rather than wrong when absent', () => {
  assert.equal(formatDateTime(null, 'en'), '')
  assert.equal(formatDateTime('not-a-date', 'en'), '')
})

console.log(`\n    ${pass} passed, ${failures.length} failed`)
if (failures.length) {
  console.log(`    failing: ${failures.join(', ')}`)
  process.exit(1)
}
