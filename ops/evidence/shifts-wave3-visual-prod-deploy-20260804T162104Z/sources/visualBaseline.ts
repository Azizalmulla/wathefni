/**
 * Shared post-hiring visual baseline helpers.
 * Accents reuse pre-hire `wf-accent-*` tokens — same color, same meaning.
 * Do not introduce page-local hex palettes here.
 */

import type { PosthireShiftRow } from '@/types'

/** Semantic surface for a shift block (Schedule hero). */
export function shiftStateSurfaceClass(shift: PosthireShiftRow): string {
  const ui = String(shift.ui_state || shift.status || 'scheduled').toLowerCase()
  if (ui === 'cancelled' || String(shift.status).toLowerCase() === 'cancelled') {
    return 'border-transparent bg-wf-accent-paused-soft text-wf-accent-paused-ink'
  }
  if (ui === 'reconciliation_required') {
    return 'border-transparent bg-wf-accent-assess text-wf-accent-assess-ink'
  }
  if (ui === 'conflicted') {
    return 'border-transparent bg-wf-accent-review text-wf-accent-review-ink'
  }
  if (shift.ends_next_day || shift.is_overnight) {
    return 'border-transparent bg-wf-accent-follow text-wf-accent-follow-ink'
  }
  // Healthy scheduled work — olive priority, readable on cream canvas
  return 'border-transparent bg-wf-accent-priority-soft text-wf-accent-priority-ink'
}

export function shiftStateChipClass(shift: PosthireShiftRow): string {
  const ui = String(shift.ui_state || shift.status || 'scheduled').toLowerCase()
  if (ui === 'cancelled' || String(shift.status).toLowerCase() === 'cancelled') {
    return 'bg-white/50 text-wf-accent-paused-ink'
  }
  if (ui === 'reconciliation_required') return 'bg-white/45 text-wf-accent-assess-ink'
  if (ui === 'conflicted') return 'bg-white/45 text-wf-accent-review-ink'
  if (shift.ends_next_day || shift.is_overnight) return 'bg-white/45 text-wf-accent-follow-ink'
  return 'bg-white/50 text-wf-accent-priority-ink'
}
