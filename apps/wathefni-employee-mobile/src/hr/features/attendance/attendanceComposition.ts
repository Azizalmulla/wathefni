import type { AttendanceException, AttendanceExceptionKind } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'

export type AttendanceQueueTab = 'today' | 'unresolved'

export function exceptionKindLabelKey(kind: AttendanceExceptionKind | null | undefined): string {
  switch (kind) {
    case 'absence':
      return 'hrAttendance.kindAbsence'
    case 'lateness':
      return 'hrAttendance.kindLateness'
    case 'early_leave':
      return 'hrAttendance.kindEarlyLeave'
    case 'missing_check_in':
      return 'hrAttendance.kindMissingCheckIn'
    case 'missing_check_out':
      return 'hrAttendance.kindMissingCheckOut'
    case 'incomplete_session':
      return 'hrAttendance.kindIncomplete'
    default:
      return 'hrAttendance.kindIncomplete'
  }
}

export function exceptionChipTone(kind: AttendanceExceptionKind | null | undefined): StatusTone {
  switch (kind) {
    case 'absence':
      return 'pink'
    case 'lateness':
    case 'early_leave':
      return 'yellow'
    case 'missing_check_in':
    case 'missing_check_out':
    case 'incomplete_session':
      return 'blue'
    default:
      return 'yellow'
  }
}

export function formatMinutes(minutes: number, t: (k: string, p?: Record<string, string | number>) => string): string | null {
  if (!minutes || minutes <= 0) return null
  return t('hrAttendance.minutes', { count: minutes })
}

export function queueSubtitle(item: AttendanceException, t: (k: string, p?: Record<string, string | number>) => string): string {
  const parts: string[] = []
  const late = formatMinutes(item.late_minutes, t)
  const early = formatMinutes(item.early_leave_minutes, t)
  if (late) parts.push(t('hrAttendance.lateBy', { count: item.late_minutes }))
  if (early) parts.push(t('hrAttendance.earlyBy', { count: item.early_leave_minutes }))
  if (!parts.length && item.employee.position_title) parts.push(item.employee.position_title)
  return parts.join(' · ')
}

/** Correction targets offered when request_correction is allowed. */
export const CORRECTION_STATUSES = ['present', 'late', 'absent', 'completed'] as const
export type CorrectionStatus = (typeof CORRECTION_STATUSES)[number]

export function correctionActionLabelKey(status: CorrectionStatus): string {
  return `hrAttendance.request.${status}`
}

/** Unresolved lookback uses API max window (92d) — unbounded history is a documented gap. */
export const UNRESOLVED_LOOKBACK_DAYS = 92
