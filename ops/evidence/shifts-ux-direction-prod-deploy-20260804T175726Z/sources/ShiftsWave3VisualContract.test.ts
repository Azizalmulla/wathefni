import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { normalizeAssignmentType, shiftStateSurfaceClass } from './visualBaseline'
import type { PosthireShiftRow } from '@/types'

const shiftsSrc = readFileSync(resolve(__dirname, './ShiftsWorkspace.tsx'), 'utf8')
const rosterSrc = readFileSync(resolve(__dirname, './ShiftsRosterBoard.tsx'), 'utf8')
const baselineSrc = readFileSync(resolve(__dirname, './visualBaseline.ts'), 'utf8')
const cssSrc = readFileSync(resolve(__dirname, '../index.css'), 'utf8')

function shift(partial: Partial<PosthireShiftRow>): PosthireShiftRow {
  return {
    shift_id: 's1',
    employee_key: 'e1',
    shift_date: '2026-08-04',
    start_time: '09:00',
    end_time: '17:00',
    status: 'scheduled',
    ...partial,
  } as PosthireShiftRow
}

describe('Shifts Visual Design Wave 3 — Shared Post-Hiring Visual Baseline', () => {
  it('marks wave 3 and preserves IQ-12 interaction markers', () => {
    expect(shiftsSrc).toContain('data-shifts-visual-wave3')
    expect(shiftsSrc).toContain('data-shifts-board-hero')
    expect(shiftsSrc).toContain('data-shifts-iq-wave2')
    expect(shiftsSrc).toContain('data-shifts-updating')
    expect(shiftsSrc).toContain('selectedSnapshot')
    expect(shiftsSrc).toContain('resultNeedsConfirmation')
    expect(shiftsSrc).toContain('run: async ({ reason }) =>')
  })

  it('uses shared pre-hire accent tokens — no ad-hoc shift hex palette', () => {
    expect(baselineSrc).toContain('bg-wf-accent-priority-soft')
    expect(baselineSrc).toContain('bg-wf-accent-review')
    expect(baselineSrc).toContain('bg-wf-accent-assess')
    expect(baselineSrc).toContain('bg-wf-accent-follow')
    expect(baselineSrc).toContain('bg-wf-accent-paused-soft')
    expect(shiftsSrc).toContain('shiftStateSurfaceClass')
    expect(shiftsSrc).not.toContain('bg-[#e9e4d9]')
    expect(shiftsSrc).not.toContain('bg-[#f3d85f]')
    expect(shiftsSrc).not.toContain('bg-[#efbdd7]')
    expect(shiftsSrc).not.toContain('bg-[#b9cde8]')
    expect(cssSrc).toContain('--color-ph-state-scheduled')
    expect(cssSrc).toContain('--color-ph-state-conflict')
  })

  it('maps governed assignment_type and exception overrides — never free-text role', () => {
    expect(normalizeAssignmentType(undefined)).toBe('general')
    expect(normalizeAssignmentType('GUEST')).toBe('guest')
    expect(normalizeAssignmentType('Front desk')).toBe('general')
    expect(baselineSrc).toContain('normalizeAssignmentType')
    expect(baselineSrc).not.toContain('role.includes')
    expect(baselineSrc).not.toContain('role.toLowerCase')

    expect(shiftStateSurfaceClass(shift({}))).toContain('wf-frame')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'guest' }))).toContain('review-soft')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'operations' }))).toContain('priority-soft')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'night' }))).toContain('follow-soft')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'event' }))).toContain('assess-soft')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'guest', ui_state: 'conflicted' }))).toContain('review')
    expect(shiftStateSurfaceClass(shift({ assignment_type: 'operations', ui_state: 'reconciliation_required' }))).toContain(
      'assess',
    )
    expect(shiftStateSurfaceClass(shift({ status: 'cancelled', ui_state: 'cancelled' }))).toContain('paused')
    // Overnight span alone must not invent a category color
    expect(shiftStateSurfaceClass(shift({ is_overnight: true }))).toContain('wf-frame')
  })

  it('designs empty state and keeps Requests calmer than Schedule hero', () => {
    expect(rosterSrc).toContain('data-shifts-empty')
    expect(rosterSrc).toContain('data-shifts-roster-row')
    expect(shiftsSrc).toContain('data-shifts-queue-canvas')
    expect(shiftsSrc).toContain('bg-wf-surface/90')
    expect(shiftsSrc).toContain('bg-wf-ink text-white')
    expect(shiftsSrc).toContain('data-shifts-assignment-type')
    expect(shiftsSrc).toContain('data-shifts-visual-direction')
  })
})
