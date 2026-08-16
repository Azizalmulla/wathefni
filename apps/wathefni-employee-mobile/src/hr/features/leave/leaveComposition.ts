/** Leave decision presentation helpers — no invented business meaning. */

import type { StatusTone } from '@/components/ui'

export type LeaveBalanceRow = {
  leave_type?: string | null
  entitlement_days?: number | null
  accrued_to_date?: number | null
  consumed?: number | null
  current_balance?: number | null
  available?: number | null
  reserved?: number | null
  observe_only?: boolean | null
  enforced?: boolean | null
  balances_enforced?: boolean | null
}

export function leaveStatusTone(status: string | null | undefined): StatusTone {
  const value = String(status || '').toLowerCase()
  if (value === 'approved') return 'success'
  if (value === 'rejected' || value === 'cancelled' || value === 'canceled') return 'danger'
  if (value === 'requested' || value === 'pending') return 'warning'
  return 'neutral'
}

export function leaveStatusLabelKey(status: string | null | undefined): string {
  const value = String(status || '').toLowerCase()
  if (value === 'approved') return 'hrLeave.statusApproved'
  if (value === 'rejected') return 'hrLeave.statusRejected'
  if (value === 'cancelled' || value === 'canceled') return 'hrLeave.statusCancelled'
  if (value === 'requested') return 'hrLeave.statusRequested'
  return 'hrLeave.statusOther'
}

export function leaveTypeLabelKey(leaveType: string | null | undefined): string {
  const value = String(leaveType || '').toLowerCase()
  if (value === 'annual') return 'leave.typeAnnual'
  if (value === 'sick') return 'leave.typeSick'
  if (value === 'other') return 'leave.typeOther'
  return 'hrLeave.typeFallback'
}

export function parseLeaveBalances(balance: unknown): LeaveBalanceRow[] {
  if (!Array.isArray(balance)) return []
  return balance.filter((row) => row && typeof row === 'object') as LeaveBalanceRow[]
}

export function formatLeaveDays(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10)
}

/**
 * Map known English prepare consequences to mobile i18n templates.
 * Unknown server text is returned unchanged (no invented meaning).
 */
export function localizeLeaveConsequence(
  consequence: string | null | undefined,
  action: 'approve' | 'reject',
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(consequence || '').trim()
  if (!raw) {
    return action === 'approve' ? t('hrLeave.consequenceApproveGeneric') : t('hrLeave.consequenceRejectGeneric')
  }
  const approve = /^Approve (.+)'s leave and notify the employee\.?$/i.exec(raw)
  if (approve) return t('hrLeave.consequenceApprove', { name: approve[1] })
  const reject = /^Reject (.+)'s leave and notify the employee\.?$/i.exec(raw)
  if (reject) return t('hrLeave.consequenceReject', { name: reject[1] })
  return raw
}

export function localizeLeaveCurrentState(
  status: string | null | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const key = leaveStatusLabelKey(status)
  if (key === 'hrLeave.statusOther' && status) return String(status)
  return t(key)
}
