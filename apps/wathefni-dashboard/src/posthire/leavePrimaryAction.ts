/** Derive Leave queue primary action from existing row status / next_action. */

export type LeavePrimaryKind =
  | 'approve'
  | 'confirm_dual'
  | 'start_dual'
  | 'cancel'
  | 'view_details'

export type LeavePrimaryInput = {
  status?: string | null
  next_action?: string | null
  dual_control_pending?: boolean | null
  dual_pending?: boolean | null
  dual_control_status?: string | null
  canDecide?: boolean
}

/**
 * Primary row action for a leave request.
 * Secondary actions (decline, request info, withdraw, approve-on-stale) stay under More / detail.
 */
export function leavePrimaryAction(input: LeavePrimaryInput): LeavePrimaryKind {
  const status = String(input.status || '').toLowerCase()
  const next = String(input.next_action || '').toLowerCase()
  const dualPending =
    Boolean(input.dual_control_pending) ||
    Boolean(input.dual_pending) ||
    ['pending_second', 'awaiting_second', 'pending_confirmation'].includes(
      String(input.dual_control_status || '').toLowerCase(),
    )

  if (!input.canDecide) return 'view_details'
  if (dualPending) return 'confirm_dual'
  // Stale dual-control start outranks ordinary approve on the same status.
  if (status === 'needs_review' || status === 'expired_stale') return 'start_dual'
  if (status === 'requested' || next === 'decide') return 'approve'
  if (status === 'approved' && next === 'may_cancel') return 'cancel'
  return 'view_details'
}
