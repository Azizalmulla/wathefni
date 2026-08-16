import type { BankDisplayValues } from '@/types'

/** Display order shared with the employee app so both surfaces read the same. */
export const BANK_FIELDS = ['iban', 'account_number', 'bank_name', 'account_holder', 'branch', 'swift'] as const

const FIELD_LABELS: Record<string, { en: string; ar: string }> = {
  iban: { en: 'IBAN', ar: 'الآيبان' },
  account_number: { en: 'Account number', ar: 'رقم الحساب' },
  bank_name: { en: 'Bank name', ar: 'اسم البنك' },
  account_holder: { en: 'Account holder', ar: 'صاحب الحساب' },
  branch: { en: 'Branch', ar: 'الفرع' },
  swift: { en: 'SWIFT / BIC', ar: 'سويفت' },
}

export const BANK_STATE_LABELS: Record<string, { en: string; ar: string }> = {
  none: { en: 'No submission', ar: 'لا يوجد طلب' },
  draft: { en: 'Employee draft', ar: 'مسودة الموظف' },
  pending_review: { en: 'Awaiting your review', ar: 'بانتظار مراجعتك' },
  approved: { en: 'Approved', ar: 'تمت الموافقة' },
  rejected: { en: 'Returned to employee', ar: 'أُعيد للموظف' },
  needs_correction: { en: 'Correction requested', ar: 'طُلب تصحيح' },
  withdrawn: { en: 'Withdrawn by employee', ar: 'سحبه الموظف' },
}

export function bankStateLabel(state: string, isAr: boolean): string {
  const entry = BANK_STATE_LABELS[state]
  if (!entry) return state.replace(/_/g, ' ')
  return isAr ? entry.ar : entry.en
}

export function bankStateTone(
  state: string,
): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  switch (state) {
    case 'approved':
      return 'success'
    case 'pending_review':
      return 'review'
    case 'rejected':
    case 'needs_correction':
      return 'danger'
    case 'draft':
    case 'withdrawn':
      return 'paused'
    default:
      return 'neutral'
  }
}

export function bankFieldLabel(field: string, isAr: boolean): string {
  const entry = FIELD_LABELS[field]
  if (entry) return isAr ? entry.ar : entry.en
  return field.replace(/_/g, ' ')
}

/** Only real values render; `_masked` / `_last4` are markers the backend adds. */
export function bankReadableFields(values: BankDisplayValues | undefined): Array<{ field: string; value: string }> {
  if (!values) return []
  return BANK_FIELDS.map((field) => ({ field, value: values[field] }))
    .filter((row) => row.value !== undefined && row.value !== null && row.value !== '')
    .map((row) => ({ field: row.field, value: String(row.value) }))
}
