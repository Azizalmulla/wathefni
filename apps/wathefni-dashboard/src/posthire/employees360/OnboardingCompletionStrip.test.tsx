import { describe, expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { OnboardingCompletionStrip } from './OnboardingCompletionStrip'
import { COMPLETION_LABELS, completionLabel, completionTone } from './onboardingCompletion'

const CANONICAL_STATES = [
  'not_started',
  'in_progress',
  'waiting_on_employee',
  'waiting_on_hr',
  'blocked',
  'completed',
  'reopened',
] as const

describe('onboarding completion strip', () => {
  test('covers exactly the canonical contract states', () => {
    expect(Object.keys(COMPLETION_LABELS).sort()).toEqual([...CANONICAL_STATES].sort())
  })

  test('every state is labelled in English and Arabic', () => {
    for (const state of CANONICAL_STATES) {
      expect(completionLabel(state, 'en')).toBeTruthy()
      expect(completionLabel(state, 'ar')).toBeTruthy()
    }
  })

  test('ownership is visually distinguishable', () => {
    expect(completionTone('completed')).toBe('success')
    expect(completionTone('waiting_on_hr')).toBe('review')
    expect(completionTone('waiting_on_employee')).toBe('warning')
    expect(completionTone('blocked')).toBe('danger')
    // waiting_on_employee and waiting_on_hr must not collapse to one tone.
    expect(completionTone('waiting_on_employee')).not.toBe(completionTone('waiting_on_hr'))
  })

  test('renders the canonical state, counts and next action', () => {
    const html = renderToStaticMarkup(
      <OnboardingCompletionStrip
        completion={{
          state: 'waiting_on_hr',
          required_total: 4,
          satisfied_count: 3,
          waiting_hr_count: 1,
          next_action: { owner: 'hr', message_en: 'HR needs to review what has been submitted.' },
        }}
      />,
    )
    expect(html).toContain('data-completion-state="waiting_on_hr"')
    expect(html).toContain('Waiting on HR')
    expect(html).toContain('3/4')
    expect(html).toContain('Next: ')
    expect(html).toContain('HR needs to review what has been submitted.')
    expect(html).toContain('Owner: ')
    expect(html).toContain('HR')
  })

  test('reopened is distinct from in_progress so history is not lost', () => {
    const html = renderToStaticMarkup(
      <OnboardingCompletionStrip completion={{ state: 'reopened', required_total: 5, satisfied_count: 4 }} />,
    )
    expect(html).toContain('Reopened')
    expect(html).not.toContain('In progress')
  })

  test('Arabic renders RTL and localized copy', () => {
    const html = renderToStaticMarkup(
      <OnboardingCompletionStrip
        completion={{ state: 'waiting_on_employee', waiting_employee_count: 2, next_action: { message_ar: 'أكمل البنود المتبقية.' } }}
        locale="ar"
      />,
    )
    expect(html).toContain('dir="rtl"')
    expect(html).toContain('بانتظار الموظف')
    expect(html).toContain('الإجراء التالي: ')
    expect(html).toContain('أكمل البنود المتبقية.')
  })

  test('a missing or unknown state renders nothing rather than a guess', () => {
    expect(renderToStaticMarkup(<OnboardingCompletionStrip completion={undefined} />)).toBe('')
    expect(renderToStaticMarkup(<OnboardingCompletionStrip completion={{ state: 'invented' }} />)).toBe('')
  })
})
