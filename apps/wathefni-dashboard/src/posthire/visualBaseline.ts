/**
 * Shared post-hiring visual baseline helpers.
 * Accents reuse pre-hire `wf-accent-*` tokens — same color, same meaning.
 * Do not introduce page-local hex palettes here.
 *
 * Healthy-tile rhythm uses governed `assignment_type` only.
 * Never infer category from free-text role / location / employee.
 * Exception ui_state always overrides category fill; labels also communicate state.
 */

import type { PosthireShiftRow } from '@/types'

export const SHIFT_ASSIGNMENT_TYPES = ['guest', 'operations', 'night', 'event', 'general'] as const
export type ShiftAssignmentType = (typeof SHIFT_ASSIGNMENT_TYPES)[number]

export function normalizeAssignmentType(value: unknown): ShiftAssignmentType {
  const raw = String(value || '')
    .trim()
    .toLowerCase()
  if ((SHIFT_ASSIGNMENT_TYPES as readonly string[]).includes(raw)) {
    return raw as ShiftAssignmentType
  }
  return 'general'
}

function exceptionalUi(shift: PosthireShiftRow): string | null {
  const ui = String(shift.ui_state || shift.status || 'scheduled').toLowerCase()
  if (ui === 'cancelled' || String(shift.status).toLowerCase() === 'cancelled') return 'cancelled'
  if (ui === 'reconciliation_required') return 'reconciliation_required'
  if (ui === 'conflicted') return 'conflicted'
  return null
}

/** Semantic surface for a shift block (Schedule hero). */
export function shiftStateSurfaceClass(shift: PosthireShiftRow): string {
  const exceptional = exceptionalUi(shift)
  if (exceptional === 'cancelled') {
    return 'border-transparent bg-wf-accent-paused-soft text-wf-accent-paused-ink'
  }
  if (exceptional === 'reconciliation_required') {
    return 'border-transparent bg-wf-accent-assess text-wf-accent-assess-ink'
  }
  if (exceptional === 'conflicted') {
    return 'border-transparent bg-wf-accent-review text-wf-accent-review-ink'
  }

  const type = normalizeAssignmentType(shift.assignment_type)
  if (type === 'guest') return 'border-transparent bg-wf-accent-review-soft text-wf-accent-review-ink'
  if (type === 'operations') return 'border-transparent bg-wf-accent-priority-soft text-wf-accent-priority-ink'
  if (type === 'night') return 'border-transparent bg-wf-accent-follow-soft text-wf-accent-follow-ink'
  if (type === 'event') return 'border-transparent bg-wf-accent-assess-soft text-wf-accent-assess-ink'
  // general / unknown / legacy — neutral frame cream (readable, not olive-default)
  return 'border-transparent bg-wf-frame text-wf-ink'
}

/** Inline-start rail carries category or exception without relying on color alone for risk. */
export function shiftStateRailClass(shift: PosthireShiftRow): string {
  const exceptional = exceptionalUi(shift)
  if (exceptional === 'cancelled') return 'bg-wf-accent-paused'
  if (exceptional === 'reconciliation_required') return 'bg-wf-accent-assess-ink'
  if (exceptional === 'conflicted') return 'bg-wf-accent-review-ink'

  const type = normalizeAssignmentType(shift.assignment_type)
  if (type === 'guest') return 'bg-wf-accent-review'
  if (type === 'operations') return 'bg-wf-accent-priority'
  if (type === 'night') return 'bg-wf-accent-follow'
  if (type === 'event') return 'bg-wf-accent-assess'
  return 'bg-wf-ink/35'
}

export function shiftStateTextClass(shift: PosthireShiftRow): string {
  const exceptional = exceptionalUi(shift)
  if (exceptional === 'cancelled') return 'text-wf-accent-paused-ink'
  if (exceptional === 'reconciliation_required') return 'text-wf-accent-assess-ink'
  if (exceptional === 'conflicted') return 'text-wf-accent-review-ink'

  const type = normalizeAssignmentType(shift.assignment_type)
  if (type === 'guest') return 'text-wf-accent-review-ink'
  if (type === 'operations') return 'text-wf-accent-priority-ink'
  if (type === 'night') return 'text-wf-accent-follow-ink'
  if (type === 'event') return 'text-wf-accent-assess-ink'
  return 'text-wf-ink'
}

export function shiftStateChipClass(shift: PosthireShiftRow): string {
  const exceptional = exceptionalUi(shift)
  if (exceptional === 'cancelled') return 'bg-white/50 text-wf-accent-paused-ink'
  if (exceptional === 'reconciliation_required') return 'bg-white/45 text-wf-accent-assess-ink'
  if (exceptional === 'conflicted') return 'bg-white/45 text-wf-accent-review-ink'

  const type = normalizeAssignmentType(shift.assignment_type)
  if (type === 'guest') return 'bg-white/50 text-wf-accent-review-ink'
  if (type === 'operations') return 'bg-white/50 text-wf-accent-priority-ink'
  if (type === 'night') return 'bg-white/45 text-wf-accent-follow-ink'
  if (type === 'event') return 'bg-white/45 text-wf-accent-assess-ink'
  return 'bg-white/50 text-wf-ink'
}
