import type { AttendanceException, AttendanceExceptionKind } from '@hr/api/types'
import { ATTENDANCE_DEMO_ID_PREFIX, ATTENDANCE_DEMO_SOURCE } from './attendanceDemoGate'

const id = (suffix: string) => `${ATTENDANCE_DEMO_ID_PREFIX}${suffix}`

function row(
  partial: Omit<AttendanceException, 'exception_id' | 'is_exception' | 'action_mode' | 'allowed_actions'> & {
    attendance_id: string
  },
): AttendanceException {
  return {
    ...partial,
    exception_id: partial.attendance_id,
    is_exception: true,
    action_mode: 'request_correction',
    allowed_actions: ['resolve'],
  }
}

/** Realistic exception states for canary UX inspection — not live company truth. */
export function buildAttendanceDemoQueue(todayIso: string): {
  source: typeof ATTENDANCE_DEMO_SOURCE
  today: AttendanceException[]
  unresolved: AttendanceException[]
} {
  const yesterday = shiftDay(todayIso, -1)
  const threeAgo = shiftDay(todayIso, -3)
  const weekAgo = shiftDay(todayIso, -8)

  const today: AttendanceException[] = [
    row({
      attendance_id: id('late-1'),
      employee: { name: 'Sara Al-Mutairi', employee_key: 'demo-sara', position_title: 'Store Manager', department: 'Retail' },
      exception_kind: 'lateness',
      status: 'late',
      attendance_date: todayIso,
      scheduled_start: `${todayIso}T09:00:00+03:00`,
      scheduled_end: `${todayIso}T17:00:00+03:00`,
      check_in_at: `${todayIso}T09:22:00+03:00`,
      check_out_at: null,
      late_minutes: 22,
      early_leave_minutes: 0,
      occurred_at: todayIso,
      note: null,
      updated_at: `${todayIso}T09:22:00+03:00`,
    }),
    row({
      attendance_id: id('absent-1'),
      employee: { name: 'Bilal Chowdhury', employee_key: 'demo-bilal', position_title: 'Warehouse Operative', department: 'Warehouse' },
      exception_kind: 'absence',
      status: 'absent',
      attendance_date: todayIso,
      scheduled_start: `${todayIso}T08:00:00+03:00`,
      scheduled_end: `${todayIso}T16:00:00+03:00`,
      check_in_at: null,
      check_out_at: null,
      late_minutes: 0,
      early_leave_minutes: 0,
      occurred_at: todayIso,
      note: 'No-show — no punch recorded',
      updated_at: `${todayIso}T10:00:00+03:00`,
    }),
    row({
      attendance_id: id('miss-out-1'),
      employee: { name: 'Noura Hassan', employee_key: 'demo-noura', position_title: 'Sales Associate', department: 'Sales' },
      exception_kind: 'missing_check_out',
      status: 'incomplete',
      attendance_date: todayIso,
      scheduled_start: `${todayIso}T10:00:00+03:00`,
      scheduled_end: `${todayIso}T18:00:00+03:00`,
      check_in_at: `${todayIso}T09:58:00+03:00`,
      check_out_at: null,
      late_minutes: 0,
      early_leave_minutes: 0,
      occurred_at: todayIso,
      note: null,
      updated_at: `${todayIso}T18:30:00+03:00`,
    }),
  ]

  const unresolved: AttendanceException[] = [
    row({
      attendance_id: id('early-1'),
      employee: { name: 'Ahmed Darwish', employee_key: 'demo-ahmed', position_title: 'Customer Care', department: 'Support' },
      exception_kind: 'early_leave',
      status: 'completed',
      attendance_date: yesterday,
      scheduled_start: `${yesterday}T09:00:00+03:00`,
      scheduled_end: `${yesterday}T17:00:00+03:00`,
      check_in_at: `${yesterday}T08:55:00+03:00`,
      check_out_at: `${yesterday}T15:40:00+03:00`,
      late_minutes: 0,
      early_leave_minutes: 80,
      occurred_at: yesterday,
      note: 'Left early — family emergency noted by supervisor',
      updated_at: `${yesterday}T15:40:00+03:00`,
    }),
    row({
      attendance_id: id('miss-in-1'),
      employee: { name: 'Layla Farid', employee_key: 'demo-layla', position_title: 'Sales Associate', department: 'Sales' },
      exception_kind: 'missing_check_in',
      status: 'incomplete',
      attendance_date: threeAgo,
      scheduled_start: `${threeAgo}T09:00:00+03:00`,
      scheduled_end: `${threeAgo}T17:00:00+03:00`,
      check_in_at: null,
      check_out_at: `${threeAgo}T17:05:00+03:00`,
      late_minutes: 0,
      early_leave_minutes: 0,
      occurred_at: threeAgo,
      note: 'Checkout without check-in — schedule mismatch',
      updated_at: `${threeAgo}T17:05:00+03:00`,
    }),
    row({
      attendance_id: id('incomplete-1'),
      employee: { name: 'Omar Al-Sabah', employee_key: 'demo-omar', position_title: 'Shift Lead', department: 'Retail' },
      exception_kind: 'incomplete_session',
      status: 'pending',
      attendance_date: weekAgo,
      scheduled_start: `${weekAgo}T12:00:00+03:00`,
      scheduled_end: `${weekAgo}T20:00:00+03:00`,
      check_in_at: `${weekAgo}T12:10:00+03:00`,
      check_out_at: null,
      late_minutes: 0,
      early_leave_minutes: 0,
      occurred_at: weekAgo,
      note: 'Still open — awaiting HR correction',
      updated_at: `${weekAgo}T20:15:00+03:00`,
    }),
  ]

  return { source: ATTENDANCE_DEMO_SOURCE, today, unresolved }
}

function shiftDay(iso: string, delta: number): string {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + delta)
  return d.toISOString().slice(0, 10)
}

export function demoKindLabel(kind: AttendanceExceptionKind | null): string {
  return kind || 'incomplete_session'
}
