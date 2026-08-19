import { describe, expect, test } from 'vitest'

import {
  assessmentCohortForTab,
  assessmentQueueActionLabel,
  assessmentTabForCohort,
  normalizeAssessmentCohortKey,
  queuePrimaryAction,
} from './assessmentCohorts'

describe('assessmentCohorts', () => {
  test('normalizes aliases and tabs', () => {
    expect(normalizeAssessmentCohortKey('expired')).toBe('assessment_expired')
    expect(normalizeAssessmentCohortKey('resend')).toBe('assessment_resend_needed')
    expect(assessmentTabForCohort('assessment_resend_needed')).toBe('resend')
    expect(assessmentCohortForTab('delivery_failed')).toBe('assessment_delivery_failed')
  })

  test('queue copy never says Send pending for resend', () => {
    const copy = assessmentQueueActionLabel('assessment_resend_needed')
    expect(copy.title.toLowerCase()).toContain('resend')
    expect(copy.title.toLowerCase()).not.toContain('send pending')
    expect(copy.button).toBe('Resend assessment')
  })

  test('primary action prefers backend allowed actions and fails closed without them', () => {
    expect(queuePrimaryAction('assessment_ready_to_send', ['send_assessment'])).toBe('send')
    expect(queuePrimaryAction('assessment_delivery_failed', ['resend_assessment'])).toBe('resend')
    expect(queuePrimaryAction('assessment_in_progress', ['view_assessment'])).toBe('view')
    expect(queuePrimaryAction('assessment_ready_to_send', [])).toBe('view')
    expect(queuePrimaryAction('assessment_ready_to_send')).toBe('view')
    expect(queuePrimaryAction('assessment_resend_needed', ['view_assessment'])).toBe('view')
  })
})
