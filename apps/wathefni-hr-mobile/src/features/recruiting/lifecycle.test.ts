import { describe, expect, it } from 'vitest'

import {
  canonicalStage,
  canonicalStages,
  communicationState,
  communicationStates,
  facetStatusLabel,
  lifecycleActionLabel,
  lifecycleStageLabel,
} from './lifecycle'

describe('canonical recruiting lifecycle presentation', () => {
  it('keeps application stage separate from interview and communication facets', () => {
    expect(canonicalStages).toEqual([
      'awaiting_cv',
      'cv_processing',
      'ready_for_review',
      'shortlisted',
      'interview',
      'hired',
      'rejected',
      'withdrawn',
    ])
    expect(canonicalStages).not.toContain('scheduled' as never)
    expect(canonicalStages).not.toContain('sent' as never)
  })

  it('maps legacy read aliases without creating new stages', () => {
    expect(canonicalStage('screening_complete')).toBe('ready_for_review')
    expect(canonicalStage('offer_sent')).toBe('shortlisted')
    expect(lifecycleStageLabel('ready_for_review', 'ar')).toBe('جاهز للمراجعة')
  })

  it('uses the four canonical communication states', () => {
    expect(communicationStates).toEqual(['pending', 'sent', 'failed', 'intentionally_skipped'])
    expect(communicationState('queued')).toBe('pending')
    expect(communicationState('delivered')).toBe('sent')
    expect(communicationState('suppressed')).toBe('intentionally_skipped')
  })

  it('localizes interview facets and consequential actions', () => {
    expect(facetStatusLabel('scheduled', 'ar')).toBe('مجدولة')
    expect(facetStatusLabel('not_confirmed', 'ar')).toBe('لم يتم التأكيد')
    expect(lifecycleActionLabel('shortlist', 'ar')).toBe('إضافة للقائمة المختصرة')
    expect(lifecycleActionLabel('hire', 'en')).toBe('Hire')
  })
})
