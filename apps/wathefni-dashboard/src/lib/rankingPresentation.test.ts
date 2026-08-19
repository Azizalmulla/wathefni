import { describe, expect, test } from 'vitest'

import { rankingComponentRows, rankingDecisionFor } from './rankingPresentation'
import type { RankingCandidate } from '@/types'

describe('ranking component contract', () => {
  test('prefers server max and label when ranking_decision carries component_score_meta', () => {
    const rows = rankingComponentRows(
      {
        component_scores: { skills_alignment: 18, experience_alignment: 10 },
        component_score_meta: {
          skills_alignment: { value: 18, max: 30, weight: 30, label: 'Skills match' },
          experience_alignment: { value: 10, max: 25, weight: 25, label: 'Relevant experience' },
        },
      },
      'en',
    )
    expect(rows.map((row) => ({ key: row.key, max: row.max }))).toEqual([
      { key: 'skills_alignment', max: 30 },
      { key: 'experience_alignment', max: 25 },
    ])
  })

  test('falls back to local maxima when the backend has not emitted component meta', () => {
    const rows = rankingComponentRows({ component_scores: { skills_alignment: 12 } }, 'en')
    expect(rows).toEqual([
      expect.objectContaining({ key: 'skills_alignment', value: 12, max: 30, group: 'cv' }),
    ])
  })

  test('copies presentation.score.components onto the client ranking_decision', () => {
    const candidate = {
      name: 'Ada',
      presentation: {
        score: {
          show_numeric: true,
          value: 70,
          components: {
            skills_alignment: { value: 21, max: 30, weight: 30, label: 'Skills match' },
          },
        },
      },
      component_scores: { skills_alignment: 21 },
    } as RankingCandidate
    const decision = rankingDecisionFor(candidate)
    expect(decision.component_score_meta?.skills_alignment?.max).toBe(30)
    expect(rankingComponentRows(decision, 'en')[0]?.max).toBe(30)
  })
})
