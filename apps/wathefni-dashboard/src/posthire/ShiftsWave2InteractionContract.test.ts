import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const shiftsSrc = readFileSync(resolve(__dirname, './ShiftsWorkspace.tsx'), 'utf8')
const uxSrc = readFileSync(resolve(__dirname, './shiftsUx.ts'), 'utf8')

describe('Shifts Visual & UX Wave 2 — Interaction Quality (IQ-12)', () => {
  it('keeps content visible while refreshing and avoids layout-jump strips', () => {
    expect(shiftsSrc).toContain('data-shifts-iq-wave2')
    expect(shiftsSrc).toContain('data-shifts-updating')
    expect(shiftsSrc).toContain('pointer-events-none absolute')
    expect(shiftsSrc).toContain('c.updating')
    expect(uxSrc).toContain('updating:')
    // Soft-keep prior board commit (no wipe on range identity)
    expect(shiftsSrc).toContain('data-shifts-range-soft-keep')
    expect(shiftsSrc).toContain('data-shifts-committed-week')
    expect(shiftsSrc).toContain('data-shifts-target-week')
    expect(shiftsSrc).toContain('coldLoading: !committed')
    expect(shiftsSrc).toContain('commitIfLatest')
    expect(shiftsSrc).toContain('prefetchAdjacent')
    expect(shiftsSrc).not.toMatch(/setData\(null\)/)
    expect(shiftsSrc).not.toMatch(/setCommitted\(null\)/)
  })

  it('debounces employee filter and preserves applied filter keys', () => {
    expect(shiftsSrc).toContain('debouncedEmployee')
    expect(shiftsSrc).toContain('setTimeout(() => setDebouncedEmployee')
    expect(shiftsSrc).toContain('branch_key: filters.branch_key')
    expect(shiftsSrc).toContain('data-shifts-filters')
  })

  it('keeps drawers open with sticky selection rematch', () => {
    expect(shiftsSrc).toContain('selectedSnapshot')
    expect(shiftsSrc).toContain('selectShift')
    expect(shiftsSrc).toContain('clearSelection')
    expect(shiftsSrc).toContain('setSelectedSnapshot(selectedFromList)')
    // History soft-keep (do not null history before fetch)
    expect(shiftsSrc).toContain('Soft-keep prior history')
    expect(shiftsSrc).not.toMatch(/setHistoryLoading\(true\)\s*\n\s*setHistory\(null\)/)
  })

  it('completes needs_confirmation instead of idle info return', () => {
    expect(shiftsSrc).toContain('resultNeedsConfirmation')
    expect(shiftsSrc).toContain('ackArgsForConflict')
    expect(shiftsSrc).toContain('c.continueLabel')
    expect(shiftsSrc).toContain('c.cancelled')
    expect(shiftsSrc).not.toMatch(/if \(result\.result\?\.needs_confirmation\) \{\s*onNotice\([^)]*'info'\)\s*return/)
  })

  it('keeps governed dialogs open until mutation success via confirm.run', () => {
    expect(shiftsSrc).toContain('run: async ({ reason }) =>')
    expect(shiftsSrc).toContain('run: async () => {\n        await doCancel')
    expect(shiftsSrc).toContain('run: async () => {\n                                        setWave4Busy(`mat:')
    expect(shiftsSrc).toContain('if (actionBusy) return')
    expect(shiftsSrc).toContain('if (!shift.shift_id || rowBusy) return')
  })

  it('does not reopen scheduling authority contracts', () => {
    expect(shiftsSrc).toContain('expected_updated_at')
    expect(shiftsSrc).toContain('approve_shift_swap')
    expect(shiftsSrc).toContain('cancelShift')
    expect(shiftsSrc).toContain('rescheduleShift')
    expect(shiftsSrc).toContain('createShift')
    expect(shiftsSrc).not.toContain('window.confirm')
    expect(shiftsSrc).not.toContain('window.prompt')
  })
})
