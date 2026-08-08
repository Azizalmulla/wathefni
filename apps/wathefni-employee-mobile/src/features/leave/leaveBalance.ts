/**
 * What the app is allowed to say about a leave balance.
 *
 * Balances are observe-only on the server: they are tracked, but they never
 * block an approval. So the app may answer "how much do I have?" and must not
 * imply the number is an allowance being spent down, and must never fill a
 * missing number with a zero — "0 days" and "we don't know" look identical on a
 * screen and mean opposite things to someone about to request two weeks off.
 */
import type { LeaveBalance, LeaveResponse } from '@/api/types'

export type LeaveBalanceFact = {
  leaveType: string
  days: number
  /**
   * `available` already has pending requests deducted; `current_balance` does
   * not. The distinction is the server's and is carried through so the copy can
   * be accurate rather than averaged.
   */
  basis: 'available' | 'current'
  /** Set while the balance exists but cannot be taken until this date. */
  canTakeFrom: string | null
}

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * The balance for one leave type, or null when there is nothing truthful to say.
 *
 * Null covers every case that must render as silence: the company has balances
 * switched off, this leave type has no row, or the row arrived without a usable
 * number.
 */
export function balanceForLeaveType(
  data: Pick<LeaveResponse, 'balances_enabled' | 'balances'> | null | undefined,
  leaveType: string,
): LeaveBalanceFact | null {
  if (!data?.balances_enabled) return null
  const key = String(leaveType || '').trim().toLowerCase()
  if (!key) return null
  const row = (data.balances ?? []).find(
    (balance: LeaveBalance) => String(balance?.leave_type || '').trim().toLowerCase() === key,
  )
  if (!row) return null

  const available = finite(row.available)
  const current = finite(row.current_balance)
  if (available === null && current === null) return null

  return {
    leaveType: key,
    days: available ?? (current as number),
    basis: available !== null ? 'available' : 'current',
    canTakeFrom: String(row.can_take_from || '').trim() || null,
  }
}

/**
 * True while the server says balances are not binding, which is its permanent
 * posture today. Kept as a read of the response rather than a constant so the
 * app stops disclaiming the moment the server stops saying it.
 */
export function balancesAreInformational(
  data: Pick<LeaveResponse, 'balances_enforced' | 'balances_binding'> | null | undefined,
): boolean {
  if (!data) return false
  return data.balances_enforced !== true && data.balances_binding !== true
}
