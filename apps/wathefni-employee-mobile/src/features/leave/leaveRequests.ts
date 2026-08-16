/**
 * Partition `/app/leave` requests for the Leave root.
 *
 * The API returns at most ~50 rows (server LIMIT). Current vs history is a
 * presentation split over that window — not a multi-year archive, and not a
 * new filter authority.
 */

import type { LeaveRequestRow } from '@/api/types'

/** Statuses the cancel endpoint still accepts (must stay aligned with backend). */
export const LEAVE_CANCELLABLE_STATUSES = ['requested', 'approved'] as const

const HISTORY_STATUSES = new Set([
  'cancelled',
  'canceled',
  'rejected',
  'completed',
  'denied',
  'withdrawn',
  'expired',
])

export function leaveStatusKey(status: string | null | undefined): string {
  return String(status || '')
    .trim()
    .toLowerCase()
}

export function isLeaveCancellableStatus(status: string | null | undefined): boolean {
  const key = leaveStatusKey(status)
  return (LEAVE_CANCELLABLE_STATUSES as readonly string[]).includes(key)
}

export function isLeaveHistoryStatus(status: string | null | undefined): boolean {
  return HISTORY_STATUSES.has(leaveStatusKey(status))
}

/**
 * Needs-attention first (`requested`), then other live rows (`approved`, …),
 * then by start date ascending so the next absence reads first.
 */
function compareCurrent(a: LeaveRequestRow, b: LeaveRequestRow): number {
  const aNeed = leaveStatusKey(a.status) === 'requested' ? 0 : 1
  const bNeed = leaveStatusKey(b.status) === 'requested' ? 0 : 1
  if (aNeed !== bNeed) return aNeed - bNeed
  return String(a.start_date || '').localeCompare(String(b.start_date || ''))
}

function compareHistory(a: LeaveRequestRow, b: LeaveRequestRow): number {
  // Newest first within the fetched window.
  const byStart = String(b.start_date || '').localeCompare(String(a.start_date || ''))
  if (byStart !== 0) return byStart
  return String(b.requested_at || '').localeCompare(String(a.requested_at || ''))
}

export type PartitionedLeaveRequests = {
  current: LeaveRequestRow[]
  history: LeaveRequestRow[]
}

/**
 * Current = actionable / live (requested, approved, and any non-terminal status).
 * History = cancelled / rejected / completed (and known terminal aliases).
 * Unknown statuses stay in Current so an actionable row is never buried.
 */
export function partitionLeaveRequests(requests: LeaveRequestRow[] | null | undefined): PartitionedLeaveRequests {
  const current: LeaveRequestRow[] = []
  const history: LeaveRequestRow[] = []
  for (const row of requests ?? []) {
    if (isLeaveHistoryStatus(row.status)) history.push(row)
    else current.push(row)
  }
  current.sort(compareCurrent)
  history.sort(compareHistory)
  return { current, history }
}
