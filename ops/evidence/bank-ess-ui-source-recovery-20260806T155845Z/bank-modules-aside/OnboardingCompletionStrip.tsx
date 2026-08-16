import { StatusPill } from '@/components/ui/page-chrome'
import type { OnboardingDetailResponse } from '@/types'

import { completionLabel, completionTone } from './onboardingCompletion'

/**
 * Every HR surface renders this strip so the dashboard can never disagree with
 * the employee app about whether onboarding is complete.
 */
export function OnboardingCompletionStrip({
  completion,
  locale = 'en',
}: {
  completion: OnboardingDetailResponse['completion']
  locale?: 'en' | 'ar'
}) {
  const isAr = locale === 'ar'
  const state = String(completion?.state || '')
  // An unknown or missing state renders nothing rather than a guessed status.
  const label = completionLabel(state, locale)
  if (!label) return null
  const action = completion?.next_action
  const message = (isAr ? action?.message_ar : action?.message_en) || action?.message || ''
  const waitingEmployee = Number(completion?.waiting_employee_count || 0)
  const waitingHr = Number(completion?.waiting_hr_count || 0)
  const blocked = Number(completion?.blocked_count || 0)
  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-[1rem] border border-line/55 bg-panel-muted/40 px-3 py-2"
      data-testid="onboarding-completion-strip"
      data-completion-state={state}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      <StatusPill tone={completionTone(state)}>{label}</StatusPill>
      <span className="text-[12.5px] text-subtle/90">
        {completion?.satisfied_count ?? 0}/{completion?.required_total ?? 0}{' '}
        {isAr ? 'بند مطلوب مكتمل' : 'required items done'}
      </span>
      {waitingEmployee ? (
        <span className="text-[12px] text-subtle/80">
          {isAr ? `${waitingEmployee} على الموظف` : `${waitingEmployee} on employee`}
        </span>
      ) : null}
      {waitingHr ? (
        <span className="text-[12px] text-subtle/80">
          {isAr ? `${waitingHr} على الموارد البشرية` : `${waitingHr} on HR`}
        </span>
      ) : null}
      {blocked ? (
        <span className="text-[12px] text-wf-accent-active-ink">
          {isAr ? `${blocked} متوقف` : `${blocked} blocked`}
        </span>
      ) : null}
      {message ? <span className="basis-full text-[12.5px] leading-5 text-subtle/90">{message}</span> : null}
    </div>
  )
}
