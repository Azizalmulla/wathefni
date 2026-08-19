/** Attendance shared status / eligibility helpers (customer-facing). */

export type AttendanceLocale = 'en' | 'ar'

export type AttendanceLifeState =
  | 'captured'
  | 'incomplete'
  | 'needs_review'
  | 'approved'
  | 'disputed'
  | 'locked'
  | 'absent'
  | 'on_leave'

const ATTENDANCE_LIFE_STATES: readonly AttendanceLifeState[] = [
  'captured',
  'incomplete',
  'needs_review',
  'approved',
  'disputed',
  'locked',
  'absent',
  'on_leave',
]

function asLifeState(value: unknown): AttendanceLifeState | null {
  const key = String(value || '').trim().toLowerCase()
  return (ATTENDANCE_LIFE_STATES as readonly string[]).includes(key) ? (key as AttendanceLifeState) : null
}

export function attendanceLifeState(row: {
  status?: string | null
  late_minutes?: number | null
  early_leave_minutes?: number | null
  exception_state?: string | null
  approval_status?: string | null
  payroll_eligible?: boolean | null
  payroll_locked?: boolean | null
  life_state?: string | null
  metadata?: Record<string, unknown> | null
}): AttendanceLifeState {
  const meta = row.metadata || {}
  const provided = asLifeState(row.life_state ?? meta.life_state)
  if (provided) return provided
  const exception = String(row.exception_state || meta.exception_state || 'none')
  const approval = String(row.approval_status || meta.approval_status || '').toLowerCase()
  const status = String(row.status || '').toLowerCase()
  const locked = Boolean(row.payroll_locked || meta.payroll_locked)
  if (locked) return 'locked'
  if (approval === 'disputed' || status === 'disputed') return 'disputed'
  if (approval === 'approved') return 'approved'
  if (status === 'approved_leave') return 'on_leave'
  if (status === 'absent') return 'absent'
  if (exception && exception !== 'none') return 'incomplete'
  if (approval === 'rejected' || Number(row.late_minutes || 0) > 0 || Number(row.early_leave_minutes || meta.early_leave_minutes || 0) > 0) {
    return 'needs_review'
  }
  if (['incomplete', 'void'].includes(status)) return 'incomplete'
  return 'captured'
}

export function lifeStateLabel(state: AttendanceLifeState, locale: AttendanceLocale): string {
  const map: Record<AttendanceLifeState, { en: string; ar: string }> = {
    captured: { en: 'Captured', ar: 'مسجّل' },
    incomplete: { en: 'Incomplete', ar: 'غير مكتمل' },
    needs_review: { en: 'Needs review', ar: 'يحتاج مراجعة' },
    approved: { en: 'Approved', ar: 'معتمد' },
    disputed: { en: 'Disputed', ar: 'متنازع عليه' },
    locked: { en: 'Payroll locked', ar: 'مقفل للرواتب' },
    absent: { en: 'Absent', ar: 'غياب' },
    on_leave: { en: 'On leave', ar: 'إجازة' },
  }
  return map[state][locale]
}

export function lifeStateTone(
  state: AttendanceLifeState,
): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  if (state === 'approved' || state === 'captured') return 'success'
  if (state === 'needs_review' || state === 'incomplete') return 'review'
  if (state === 'disputed' || state === 'absent') return 'danger'
  if (state === 'locked') return 'warning'
  if (state === 'on_leave') return 'paused'
  return 'info'
}

export function payrollExclusionReason(
  row: {
    status?: string | null
    exception_state?: string | null
    approval_status?: string | null
    payroll_eligible?: boolean | null
    payroll_locked?: boolean | null
    payroll_exclusion_reason?: string | null
    payroll_exclusion_reason_en?: string | null
    payroll_exclusion_reason_ar?: string | null
    metadata?: Record<string, unknown> | null
  },
  locale: AttendanceLocale,
): string | null {
  const meta = row.metadata || {}
  const localized =
    locale === 'ar'
      ? String(row.payroll_exclusion_reason_ar || meta.payroll_exclusion_reason_ar || '').trim()
      : String(row.payroll_exclusion_reason_en || meta.payroll_exclusion_reason_en || '').trim()
  if (localized) return localized
  const provided = String(row.payroll_exclusion_reason || meta.payroll_exclusion_reason || '').trim()
  if (provided) return provided
  const eligible = row.payroll_eligible ?? meta.payroll_eligible
  const locked = Boolean(row.payroll_locked || meta.payroll_locked)
  const exception = String(row.exception_state || meta.exception_state || 'none')
  const approval = String(row.approval_status || meta.approval_status || '').toLowerCase()
  const status = String(row.status || '').toLowerCase()

  if (locked) {
    return locale === 'ar'
      ? 'الفترة مقفلة في كشف الرواتب — لا يمكن تعديل الحضور.'
      : 'This period is locked in Payroll — attendance cannot be changed.'
  }
  if (eligible === true && approval === 'approved') return null
  if (approval === 'disputed') {
    return locale === 'ar'
      ? 'مستبعد من الرواتب لأن السجل متنازع عليه حتى يتم الحل.'
      : 'Excluded from Payroll because this day is disputed until resolved.'
  }
  if (exception && exception !== 'none') {
    const kind =
      locale === 'ar'
        ? {
            missing_check_in: 'دخول ناقص',
            missing_check_out: 'خروج ناقص',
            ambiguous_punches: 'بصمات غامضة',
            incomplete_session: 'جلسة غير مكتملة',
          }[exception] || exception
        : exception.replace(/_/g, ' ')
    return locale === 'ar'
      ? `مستبعد من الرواتب: ${kind}. أكمل التصحيح ثم اعتمد اليوم.`
      : `Excluded from Payroll: ${kind}. Complete the correction, then approve the day.`
  }
  if (status === 'incomplete' || status === 'absent') {
    return locale === 'ar'
      ? 'مستبعد من الرواتب حتى يُراجع ويُعتمد السجل.'
      : 'Excluded from Payroll until the record is reviewed and approved.'
  }
  if (approval !== 'approved') {
    return locale === 'ar'
      ? 'مستبعد من الرواتب حتى يتم اعتماد الحضور.'
      : 'Excluded from Payroll until attendance is approved.'
  }
  if (eligible === false) {
    return locale === 'ar' ? 'مستبعد من الرواتب لهذا اليوم.' : 'Excluded from Payroll for this day.'
  }
  return null
}

export function exceptionKindLabel(kind: string, locale: AttendanceLocale): string {
  const map: Record<string, { en: string; ar: string }> = {
    missing_check_in: { en: 'Missing check-in', ar: 'دخول ناقص' },
    missing_check_out: { en: 'Missing check-out', ar: 'خروج ناقص' },
    ambiguous_punches: { en: 'Ambiguous punches', ar: 'بصمات غامضة' },
    incomplete_session: { en: 'Incomplete session', ar: 'جلسة غير مكتملة' },
    absence: { en: 'Absence', ar: 'غياب' },
    lateness: { en: 'Lateness', ar: 'تأخير' },
    early_leave: { en: 'Early leave', ar: 'انصراف مبكر' },
    connector_issue: { en: 'Connector issue', ar: 'مشكلة موصل' },
  }
  return map[kind]?.[locale] || kind.replace(/_/g, ' ')
}

export function caseStatusLabel(status: string, locale: AttendanceLocale): string {
  const map: Record<string, { en: string; ar: string }> = {
    requested: { en: 'Requested', ar: 'مطلوب' },
    under_review: { en: 'Under review', ar: 'قيد المراجعة' },
    approved: { en: 'Approved — ready to apply', ar: 'معتمد — جاهز للتطبيق' },
    rejected: { en: 'Rejected', ar: 'مرفوض' },
    pending_dual_approval: { en: 'Awaiting second approval', ar: 'بانتظار موافقة ثانية' },
    applied: { en: 'Applied', ar: 'مُطبَّق' },
    disputed: { en: 'Disputed', ar: 'متنازع عليه' },
    reopened: { en: 'Reopened', ar: 'أُعيد فتحه' },
  }
  return map[status]?.[locale] || status.replace(/_/g, ' ')
}

export function formatMinutes(mins: number | null | undefined, locale: AttendanceLocale): string {
  const n = Number(mins || 0)
  if (!n) return locale === 'ar' ? '—' : '—'
  if (n < 60) return locale === 'ar' ? `${n} د` : `${n}m`
  const h = Math.floor(n / 60)
  const m = n % 60
  return locale === 'ar' ? `${h} س ${m} د` : `${h}h ${m}m`
}
