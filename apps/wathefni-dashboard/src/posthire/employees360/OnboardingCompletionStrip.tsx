import { StatusPill } from '@/components/ui/page-chrome'
import type { OnboardingDetailResponse } from '@/types'

import { completionLabel, completionTone } from './onboardingCompletion'
import { nextActionOwnerLabel } from './onboardingDrawerGroups'

/**
 * Every HR surface renders this strip so the dashboard can never disagree with
 * the employee app about whether onboarding is complete.
 *
 * Top of the employee drawer: current state, progress, next action, owner.
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
  const owner = nextActionOwnerLabel(action?.owner, isAr)
  const satisfied = Number(completion?.satisfied_count || 0)
  const required = Number(completion?.required_total || 0)
  const waitingEmployee = Number(completion?.waiting_employee_count || 0)
  const waitingHr = Number(completion?.waiting_hr_count || 0)
  const blocked = Number(completion?.blocked_count || 0)
  return (
    <div
      className="space-y-2 rounded-[1.1rem] border border-line/55 bg-panel-muted/40 px-3.5 py-3"
      data-testid="onboarding-completion-strip"
      data-completion-state={state}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={completionTone(state)}>{label}</StatusPill>
        <span className="text-[13px] font-medium text-text">
          {satisfied}/{required} {isAr ? 'مكتمل' : 'done'}
        </span>
        {waitingHr ? (
          <span className="rounded-full bg-wf-accent-review-soft px-2 py-0.5 text-[11.5px] font-medium text-wf-accent-review-ink">
            {isAr ? `${waitingHr} على الموارد البشرية` : `${waitingHr} need HR`}
          </span>
        ) : null}
        {waitingEmployee ? (
          <span className="rounded-full border border-amber-200/80 bg-amber-50/80 px-2 py-0.5 text-[11.5px] font-medium text-amber-950">
            {isAr ? `${waitingEmployee} على الموظف` : `${waitingEmployee} on employee`}
          </span>
        ) : null}
        {blocked ? (
          <span className="text-[12px] text-wf-accent-active-ink">
            {isAr ? `${blocked} متوقف` : `${blocked} blocked`}
          </span>
        ) : null}
      </div>
      {message || owner ? (
        <div className="space-y-0.5">
          {message ? (
            <p className="text-[13.5px] font-medium leading-5 text-text" data-testid="onboarding-next-action">
              {isAr ? 'الإجراء التالي: ' : 'Next: '}
              {message}
            </p>
          ) : null}
          {owner ? (
            <p className="text-[12px] text-subtle/85" data-testid="onboarding-next-owner">
              {isAr ? 'المسؤول: ' : 'Owner: '}
              {owner}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
