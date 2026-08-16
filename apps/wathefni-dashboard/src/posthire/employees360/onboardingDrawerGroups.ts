import type { OnboardingItem } from '@/types'

/**
 * HR-facing ownership buckets for the onboarding drawer.
 * Keys match the lifecycle projection groups; labels are operator-facing.
 */
export const HR_OWNERSHIP_GROUP_ORDER = [
  'being_reviewed',
  'your_actions',
  'handled_by_others',
  'completed',
] as const

export type HrOwnershipGroup = (typeof HR_OWNERSHIP_GROUP_ORDER)[number]

export const HR_OWNERSHIP_GROUP_LABELS: Record<HrOwnershipGroup, { en: string; ar: string }> = {
  being_reviewed: { en: 'Needs HR action', ar: 'يحتاج إجراء الموارد البشرية' },
  your_actions: { en: 'Waiting on employee', ar: 'بانتظار الموظف' },
  handled_by_others: { en: 'Waiting on payroll/other', ar: 'بانتظار الرواتب/أخرى' },
  completed: { en: 'Completed', ar: 'مكتمل' },
}

const CLOSED = new Set([
  'received',
  'complete',
  'completed',
  'verified',
  'accepted',
  'waived',
  'cancelled_onboarding',
  'abandoned_employment_ended',
  'retired_legacy',
])

export function isOnboardingItemClosed(item: OnboardingItem): boolean {
  return CLOSED.has(String(item.status || '').toLowerCase())
}

export function hrOwnershipGroupForItem(item: OnboardingItem): HrOwnershipGroup {
  const raw = String(item.group || '').toLowerCase()
  if (raw === 'being_reviewed' || raw === 'your_actions' || raw === 'handled_by_others' || raw === 'completed') {
    return raw
  }
  if (isOnboardingItemClosed(item)) return 'completed'
  const party = String(item.owner_group || item.owner || item.waiting_on || '').toLowerCase()
  const status = String(item.status || '').toLowerCase()
  if (status === 'submitted' || status === 'processing' || status === 'pending_hr_review' || status === 'received') {
    return 'being_reviewed'
  }
  if (party === 'employee' || party === 'your_actions') return 'your_actions'
  if (party === 'payroll' || party === 'compliance' || party === 'it' || party === 'system') {
    return 'handled_by_others'
  }
  // Default open HR-owned work to Needs HR.
  return 'being_reviewed'
}

/**
 * Plain-language status for one checklist item. Raw contract statuses like
 * `replacement_required` or `draft_parts` are machine vocabulary; HR reads what
 * the state means for the employee instead. Unknown statuses return null so the
 * caller renders nothing rather than a title-cased database value.
 */
const ITEM_STATUS_LABELS: Record<string, { en: string; ar: string; tone: OnboardingItemTone }> = {
  pending: { en: 'Not started', ar: 'لم يبدأ', tone: 'muted' },
  in_progress: { en: 'In progress', ar: 'قيد التقدم', tone: 'warning' },
  submitted: { en: 'Submitted', ar: 'مُرسَل', tone: 'warning' },
  received: { en: 'Submitted', ar: 'مُرسَل', tone: 'warning' },
  processing: { en: 'With HR to review', ar: 'قيد مراجعة الموارد البشرية', tone: 'warning' },
  pending_hr_review: { en: 'With HR to review', ar: 'قيد مراجعة الموارد البشرية', tone: 'warning' },
  draft_parts: { en: 'Upload incomplete', ar: 'التحميل غير مكتمل', tone: 'warning' },
  replacement_required: { en: 'Correction requested', ar: 'مطلوب تصحيح', tone: 'danger' },
  rejected: { en: 'Sent back', ar: 'أُعيد للتصحيح', tone: 'danger' },
  blocked: { en: 'Blocked', ar: 'متوقف', tone: 'danger' },
  accepted: { en: 'Done', ar: 'مكتمل', tone: 'success' },
  complete: { en: 'Done', ar: 'مكتمل', tone: 'success' },
  completed: { en: 'Done', ar: 'مكتمل', tone: 'success' },
  verified: { en: 'Done', ar: 'مكتمل', tone: 'success' },
  waived: { en: 'Waived', ar: 'مُستثنى', tone: 'success' },
  cancelled_onboarding: { en: 'Not required', ar: 'غير مطلوب', tone: 'muted' },
  abandoned_employment_ended: { en: 'Not required', ar: 'غير مطلوب', tone: 'muted' },
  retired_legacy: { en: 'Not required', ar: 'غير مطلوب', tone: 'muted' },
}

export type OnboardingItemTone = 'muted' | 'warning' | 'danger' | 'success'

export function onboardingItemStatusLabel(
  status: string | null | undefined,
  isAr: boolean,
): { label: string; tone: OnboardingItemTone } | null {
  const entry = ITEM_STATUS_LABELS[String(status || '').trim().toLowerCase()]
  if (!entry) return null
  return { label: isAr ? entry.ar : entry.en, tone: entry.tone }
}

export function ownerLabel(item: OnboardingItem, isAr: boolean): string {
  const party = String(
    (item as OnboardingItem & { waiting_on?: string | null; responsible_party?: string | null }).waiting_on ||
      (item as OnboardingItem & { responsible_party?: string | null }).responsible_party ||
      item.owner_group ||
      item.owner ||
      '',
  ).toLowerCase()
  const map: Record<string, { en: string; ar: string }> = {
    employee: { en: 'Employee', ar: 'الموظف' },
    hr: { en: 'HR', ar: 'الموارد البشرية' },
    payroll: { en: 'Payroll', ar: 'الرواتب' },
    compliance: { en: 'Compliance', ar: 'الامتثال' },
    it: { en: 'IT', ar: 'تقنية المعلومات' },
    system: { en: 'System', ar: 'النظام' },
    none: { en: '—', ar: '—' },
  }
  const entry = map[party]
  if (!entry) return isAr ? '—' : '—'
  return isAr ? entry.ar : entry.en
}

export function nextActionOwnerLabel(owner: string | null | undefined, isAr: boolean): string {
  const key = String(owner || '').toLowerCase()
  if (!key) return ''
  return ownerLabel({ owner: key } as OnboardingItem, isAr)
}
