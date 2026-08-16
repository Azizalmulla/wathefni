import { describe, expect, test } from 'vitest'

import {
  isRankable,
  rankingAssessmentEvidenceEnabled,
  rankingCopy,
  rankingEligibilityLabel,
  rankingExcludedCount,
  topNRankable,
} from '@/lib/rankingQueueContract'

describe('rankingQueueContract (client)', () => {
  test('not_applicable is rankable but not hard-eligible', () => {
    expect(isRankable({ eligibility_bucket: 'not_applicable', required_evidence_complete: true })).toBe(true)
    expect(isRankable({ eligibility_bucket: 'eligible', required_evidence_complete: true })).toBe(true)
    expect(isRankable({ eligibility_bucket: 'requirement_not_met', required_evidence_complete: true })).toBe(false)
  })

  test('top_n never fills with unrankable', () => {
    const items = [
      { eligibility_bucket: 'requirement_not_met', required_evidence_complete: true, app_key: 'bad' },
      { eligibility_bucket: 'eligible', required_evidence_complete: true, app_key: 'good' },
      { eligibility_bucket: 'insufficient_information', required_evidence_complete: false, app_key: 'bad2' },
    ]
    expect(topNRankable(items, 10).map((i) => i.app_key)).toEqual(['good'])
  })

  test('plain-language labels and excluded count', () => {
    expect(rankingCopy('en', 'in_review_order')).toBe('In review order')
    expect(rankingCopy('en', 'job_matches')).toBe('Job matches')
    expect(rankingCopy('en', 'meets_all_requirements')).toBe('Meets all requirements')
    expect(rankingEligibilityLabel('en', 'not_applicable')).toBe('Hard requirements do not apply')
    expect(rankingExcludedCount({ matching_count: 2, rankable_count: 0 })).toBe(2)
    expect(rankingAssessmentEvidenceEnabled({ sources: { assessment: 'unused' } })).toBe(false)
    expect(rankingAssessmentEvidenceEnabled({ sources: { assessment: 'optional' } })).toBe(true)
  })
})
