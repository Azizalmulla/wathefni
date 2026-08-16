import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'
import {
  ACTION_LABELS,
  CANONICAL_APPLICATION_STAGES,
  COMMUNICATION_LABELS,
  COMMUNICATION_STATES,
  STAGE_LABELS,
  canonicalStage,
  facetStatusLabel,
} from './recruitingLifecycle'

describe('canonical recruiting lifecycle labels', () => {
  test('web exposes only the eight canonical stages', () => {
    expect(CANONICAL_APPLICATION_STAGES).toEqual([
      'awaiting_cv',
      'cv_processing',
      'ready_for_review',
      'shortlisted',
      'interview',
      'hired',
      'rejected',
      'withdrawn',
    ])
  })

  test('English and Arabic stage labels are present for every canonical stage', () => {
    for (const stage of CANONICAL_APPLICATION_STAGES) {
      expect(STAGE_LABELS.en[stage]).toBeTruthy()
      expect(STAGE_LABELS.ar[stage]).toBeTruthy()
    }
  })

  test('communication states and labels are complete', () => {
    expect(COMMUNICATION_STATES.length).toBeGreaterThan(0)
    for (const state of COMMUNICATION_STATES) {
      expect(COMMUNICATION_LABELS.en[state]).toBeTruthy()
      expect(COMMUNICATION_LABELS.ar[state]).toBeTruthy()
    }
  })

  test('interview and facet statuses have explicit bilingual labels', () => {
    expect(facetStatusLabel('scheduled', 'en')).toBe('Scheduled')
    expect(facetStatusLabel('scheduled', 'ar')).toBe('مجدولة')
    expect(facetStatusLabel('not_confirmed', 'en')).toBe('Not confirmed')
    expect(facetStatusLabel('not_confirmed', 'ar')).toBe('لم يتم التأكيد')
  })

  test('legacy statuses are read aliases, never new UI stages', () => {
    expect(canonicalStage('screening_complete')).toBe('ready_for_review')
    expect(canonicalStage('offer_sent')).toBe('shortlisted')
    expect(STAGE_LABELS.en).not.toHaveProperty('offer_sent')
  })

  test('consequential action labels exist in English and Arabic', () => {
    for (const action of ['shortlist', 'reject', 'schedule_interview', 'hire']) {
      expect(ACTION_LABELS.en[action]).toBeTruthy()
      expect(ACTION_LABELS.ar[action]).toBeTruthy()
    }
  })

  test('HR mobile lifecycle module stays in lockstep with web stage contract', () => {
    const mobileSource = readFileSync(
      resolve(__dirname, '../../../wathefni-hr-mobile/src/features/recruiting/lifecycle.ts'),
      'utf8',
    )
    for (const stage of CANONICAL_APPLICATION_STAGES) {
      expect(mobileSource).toContain(`'${stage}'`)
    }
    expect(mobileSource).toContain("scheduled: ['Scheduled', 'مجدولة']")
  })

  test('web action visibility comes from backend allowed_actions', () => {
    const appSource = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    const interviewsSource = readFileSync(resolve(__dirname, '../pages/InterviewsPage.tsx'), 'utf8')
    expect(appSource).toContain("const allowedActions = new Set(candidate.allowed_actions || [])")
    expect(interviewsSource).toContain("const allowedActions = new Set(interview.allowed_actions || [])")
  })

  test('shortlist, reject and hire keep explicit confirmation', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toContain("'Shortlist this candidate?'")
    expect(source).toContain("'Reject this candidate?'")
    expect(source).toContain("'Hire this candidate?'")
    expect(source).toContain("'إضافة المرشح للقائمة المختصرة؟'")
    expect(source).toContain("'رفض هذا المرشح؟'")
    expect(source).toContain("'توظيف هذا المرشح؟'")
    expect(source).toContain('askDashboardAssistant')
  })
})
