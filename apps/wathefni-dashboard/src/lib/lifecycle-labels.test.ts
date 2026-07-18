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
import {
  canonicalStages as mobileCanonicalStages,
  communicationLabels as mobileCommunicationLabels,
  communicationStates as mobileCommunicationStates,
  facetStatusLabel as mobileFacetStatusLabel,
  stageLabels as mobileStageLabels,
} from '../../../wathefni-hr-mobile/src/features/recruiting/lifecycle'

describe('canonical recruiting lifecycle labels', () => {
  test('web and HR mobile expose only the eight canonical stages', () => {
    expect(CANONICAL_APPLICATION_STAGES).toEqual(mobileCanonicalStages)
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

  test('English and Arabic stage labels match on web and HR mobile', () => {
    expect(STAGE_LABELS).toEqual(mobileStageLabels)
  })

  test('communication states and labels match on both clients', () => {
    expect(COMMUNICATION_STATES).toEqual(mobileCommunicationStates)
    expect(COMMUNICATION_LABELS).toEqual(mobileCommunicationLabels)
  })

  test('interview and facet statuses have explicit bilingual labels', () => {
    expect(facetStatusLabel('scheduled', 'en')).toBe('Scheduled')
    expect(facetStatusLabel('scheduled', 'ar')).toBe('مجدولة')
    expect(facetStatusLabel('not_confirmed', 'en')).toBe('Not confirmed')
    expect(facetStatusLabel('not_confirmed', 'ar')).toBe('لم يتم التأكيد')
    expect(mobileFacetStatusLabel('scheduled', 'ar')).toBe(facetStatusLabel('scheduled', 'ar'))
    expect(mobileFacetStatusLabel('notes_pending', 'en')).toBe(facetStatusLabel('notes_pending', 'en'))
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

  test('web action visibility comes from backend allowed_actions', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toContain("const allowedActions = new Set(candidate.allowed_actions || [])")
    expect(source).toContain("const allowedActions = new Set(interview.allowed_actions || [])")
  })

  test('shortlist, reject and hire keep explicit confirmation', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toContain("title: 'Shortlist this candidate?'")
    expect(source).toContain("title: 'Reject this candidate?'")
    expect(source).toContain("title: 'Hire this candidate?'")
    expect(source).toContain('askDashboardAssistant')
  })
})
