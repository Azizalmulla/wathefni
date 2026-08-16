import { describe, expect, test } from 'vitest'

import { DEFAULT_CLASSIFICATION_FILTERS } from '@/components/candidates/ClassificationFilters'
import { EMPTY_CANDIDATE_FILTERS } from '@/lib/candidateFilterAuthority'
import {
  buildCandidateFilterChips,
  classificationActiveCount,
} from '@/lib/candidateFilterChips'

describe('candidateFilterChips', () => {
  test('Follow-up needed chip stays visible when active', () => {
    const chips = buildCandidateFilterChips({
      locale: 'en',
      filters: {
        ...EMPTY_CANDIDATE_FILTERS,
        followUp: 'needed',
        overviewCohort: 'follow_up_needed',
        cohortKey: 'follow_up_needed',
      },
    })
    expect(chips.some((chip) => chip.id === 'followUp' && chip.label === 'Follow-up needed')).toBe(true)
  })

  test('AR labels for follow-up chip', () => {
    const chips = buildCandidateFilterChips({
      locale: 'ar',
      filters: { ...EMPTY_CANDIDATE_FILTERS, followUp: 'needed' },
    })
    expect(chips[0]?.label).toBe('يحتاج متابعة')
  })

  test('counts specialist filters independently of search/job/stage', () => {
    const chips = buildCandidateFilterChips({
      locale: 'en',
      filters: {
        ...EMPTY_CANDIDATE_FILTERS,
        position: 'ACCOUNTING_EXCEL',
        assessmentStatus: 'completed',
        sourceChannel: 'email',
        sort: 'last_activity',
      },
    })
    expect(chips.map((c) => c.id).sort()).toEqual(['assessmentStatus', 'sort', 'sourceChannel'].sort())
  })

  test('classification chip reflects active classification count', () => {
    const classificationFilters = {
      ...DEFAULT_CLASSIFICATION_FILTERS,
      dimensionNodes: { career_area: ['node-1', 'node-2'] },
      includeMediumAi: true,
    }
    expect(classificationActiveCount(classificationFilters)).toBe(3)
    const chips = buildCandidateFilterChips({
      locale: 'en',
      filters: EMPTY_CANDIDATE_FILTERS,
      classificationEnabled: true,
      classificationFilters,
    })
    expect(chips.some((chip) => chip.id === 'classification' && chip.label.includes('3'))).toBe(true)
  })
})
