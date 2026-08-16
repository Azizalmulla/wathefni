import { describe, expect, test } from 'vitest'

import {
  dedupeWorkQueueItems,
  formatOverviewPeopleMetric,
  formatWorkQueueShownTotal,
  roleDisplayCount,
  workQueueDisplayTotal,
  workQueueItemKey,
} from './prehireOverviewPresentation'
import type { PrehireRolePriority, PrehireWorkQueueItem } from '@/types'

function item(partial: Partial<PrehireWorkQueueItem> & Pick<PrehireWorkQueueItem, 'action_type' | 'reason'>): PrehireWorkQueueItem {
  return {
    priority: 50,
    ...partial,
  }
}

describe('dedupeWorkQueueItems person-first', () => {
  test('same person_key collapses to one row', () => {
    const items = [
      item({
        action_type: 'follow_up_failed_delivery',
        person_key: 'phone:96597485758',
        app_key: 'APP-1',
        candidate_name: 'Hamad',
        reason: 'a',
        priority: 80,
      }),
      item({
        action_type: 'ready_for_review',
        person_key: 'phone:96597485758',
        app_key: 'APP-2',
        candidate_name: 'Hamad Almulla',
        reason: 'b',
        priority: 99,
      }),
    ]
    const out = dedupeWorkQueueItems(items)
    expect(out).toHaveLength(1)
    expect(out[0].priority).toBe(99)
    expect(workQueueItemKey(out[0])).toBe('person:phone:96597485758')
  })

  test('backend total is trusted without FE business math', () => {
    expect(workQueueDisplayTotal(2, 14, 2)).toBe(2)
  })
})

describe('roleDisplayCount', () => {
  test('never sums overlapping signals', () => {
    const role: PrehireRolePriority = {
      position_code: 'ACCOUNTING_EXCEL',
      position_title: 'Accounting Excel',
      people_count: 1,
      application_count: 1,
      display_count: 1,
      follow_up_count: 1,
      ready_count: 1,
      assessment_pending_count: 1,
      priority: 99,
      reason: 'signals separate',
    }
    expect(roleDisplayCount(role)).toBe(1)
  })
})

describe('Wave 2 people vs applications wording', () => {
  test('surfaces applications only when they differ from people', () => {
    const same = formatOverviewPeopleMetric('en', 2, 2)
    expect(same.primary).toBe(2)
    expect(same.unitLabel).toBe('people')
    expect(same.applicationsHint).toBeNull()

    const different = formatOverviewPeopleMetric('en', 2, 4)
    expect(different.primary).toBe(2)
    expect(different.unitLabel).toBe('people')
    expect(different.applicationsHint).toBe('4 applications')

    const mine = formatOverviewPeopleMetric('en', 1, null)
    expect(mine.primary).toBe(1)
    expect(mine.unitLabel).toBe('person')
    expect(mine.applicationsHint).toBeNull()
  })

  test('work queue footer labels people explicitly', () => {
    expect(formatWorkQueueShownTotal('en', 5, 12)).toBe('5 shown · 12 people')
    expect(formatWorkQueueShownTotal('ar', 5, 12)).toContain('5')
    expect(formatWorkQueueShownTotal('ar', 5, 12)).toContain('12')
  })
})
