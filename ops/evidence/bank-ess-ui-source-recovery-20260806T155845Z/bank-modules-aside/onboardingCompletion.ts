import type { OnboardingCompletionState } from '@/types'

/**
 * The canonical onboarding completion vocabulary. These are the only states the
 * contract emits, so no surface may invent, merge or re-derive one; the state
 * and counts come straight from onboarding_completion_contract.
 */
export const COMPLETION_LABELS: Record<string, { en: string; ar: string }> = {
  not_started: { en: 'Not started', ar: 'لم يبدأ' },
  in_progress: { en: 'In progress', ar: 'قيد التقدم' },
  waiting_on_employee: { en: 'Waiting on employee', ar: 'بانتظار الموظف' },
  waiting_on_hr: { en: 'Waiting on HR', ar: 'بانتظار الموارد البشرية' },
  blocked: { en: 'Blocked', ar: 'متوقف' },
  completed: { en: 'Complete', ar: 'مكتمل' },
  reopened: { en: 'Reopened', ar: 'أُعيد فتحه' },
}

export function completionTone(
  state: string,
): 'neutral' | 'success' | 'warning' | 'danger' | 'review' | 'paused' {
  switch (state) {
    case 'completed':
      return 'success'
    case 'blocked':
      return 'danger'
    case 'waiting_on_hr':
      return 'review'
    case 'waiting_on_employee':
    case 'reopened':
      return 'warning'
    case 'not_started':
      return 'paused'
    default:
      return 'neutral'
  }
}

/** Returns null for an unknown state so callers render nothing, never a guess. */
export function completionLabel(state: OnboardingCompletionState, locale: 'en' | 'ar'): string | null {
  const entry = COMPLETION_LABELS[String(state)]
  if (!entry) return null
  return locale === 'ar' ? entry.ar : entry.en
}
