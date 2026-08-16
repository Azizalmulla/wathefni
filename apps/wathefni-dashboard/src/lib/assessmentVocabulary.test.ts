import { describe, expect, test } from 'vitest'

import {
  assessmentActionLabel,
  assessmentCohortChipLabel,
  assessmentCopy,
  assessmentStatusLabel,
} from '@/lib/assessmentVocabulary'

describe('assessmentVocabulary', () => {
  test('canonical EN labels match locked vocabulary', () => {
    expect(assessmentCopy('en', 'ready_to_send')).toBe('Ready to send')
    expect(assessmentCopy('en', 'sent_pending')).toBe('Sent pending')
    expect(assessmentCopy('en', 'in_progress')).toBe('In progress')
    expect(assessmentCopy('en', 'resend_needed')).toBe('Resend needed')
    expect(assessmentCopy('en', 'delivery_failed')).toBe('Delivery failed')
    expect(assessmentCopy('en', 'completed')).toBe('Completed')
    expect(assessmentCopy('en', 'needs_review')).toBe('Needs review')
    expect(assessmentCopy('en', 'expired')).toBe('Expired')
    expect(assessmentCopy('en', 'cancelled')).toBe('Cancelled')
  })

  test('Arabic labels are present and enums are not leaked', () => {
    expect(assessmentStatusLabel('ar', 'cancelled')).toBe('ملغى')
    expect(assessmentStatusLabel('en', 'cancelled')).toBe('Cancelled')
    expect(assessmentActionLabel('en', 'send_assessment')).toBe('Send assessment')
    expect(assessmentActionLabel('ar', 'resend_assessment')).toBe('إعادة إرسال التقييم')
    expect(assessmentActionLabel('en', 'wait_for_candidate')).not.toContain('_')
  })

  test('cohort chips use shared vocabulary', () => {
    expect(assessmentCohortChipLabel('en', 'assessment_ready_to_send')).toBe('Ready to send')
    expect(assessmentCohortChipLabel('en', 'assessment_sent_pending')).toBe('Sent pending')
    expect(assessmentCohortChipLabel('en', 'assessment_resend_needed')).toBe('Resend needed')
    expect(assessmentCohortChipLabel('en', 'assessment_expired')).toBe('Resend needed')
  })
})
