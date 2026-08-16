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
  pending_hr: { en: 'Awaiting HR review', ar: 'بانتظار مراجعة الموارد البشرية' },
  pending_review: { en: 'Awaiting HR review', ar: 'بانتظار مراجعة الموارد البشرية' },
  pending_payroll: { en: 'HR verified · awaiting payroll', ar: 'موثقة · بانتظار الرواتب' },
  approved: { en: 'Payroll approved · not yet effective', ar: 'وافقت الرواتب · ليست سارية بعد' },
  applied: { en: 'Payroll-effective', ar: 'ساري للرواتب' },
  rejected: { en: 'Returned to employee', ar: 'أُعيد للموظف' },
  needs_correction: { en: 'Correction requested', ar: 'طُلب تصحيح' },
  withdrawn: { en: 'Withdrawn by employee', ar: 'سحبه الموظف' },
}

export function bankStateLabel(state: string, isAr: boolean): string {
  const entry = BANK_STATE_LABELS[state]
  if (!entry) return state.replace(/_/g, ' ')
  return isAr ? entry.ar : entry.en
}

const WORKFLOW_STAGE_LABELS: Record<string, { en: string; ar: string }> = {
  pending_hr: { en: 'Awaiting HR approval', ar: 'بانتظار موافقة الموارد البشرية' },
  pending_payroll: { en: 'Pending payroll approval', ar: 'بانتظار موافقة الرواتب' },
  approved: { en: 'Ready to apply', ar: 'جاهز للتطبيق' },
  applied: { en: 'Payroll-effective', ar: 'ساري للرواتب' },
  rejected: { en: 'Returned to employee', ar: 'أُعيد للموظف' },
  needs_information: { en: 'Correction requested', ar: 'طُلب تصحيح' },
}

/** Exact authority stage for HR; never collapse HR and payroll approval. */
export function bankWorkflowStageLabel(
  workflowState: string | null | undefined,
  submissionState: string,
  isAr: boolean,
): string {
  const entry = WORKFLOW_STAGE_LABELS[String(workflowState || '').toLowerCase()]
  if (entry) return isAr ? entry.ar : entry.en
  return bankStateLabel(submissionState, isAr)
}

export function bankStateTone(
  state: string,
): 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'review' | 'paused' {
  switch (state) {
    case 'applied':
      return 'success'
    case 'approved':
    case 'pending_payroll':
      return 'warning'
    case 'pending_hr':
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
