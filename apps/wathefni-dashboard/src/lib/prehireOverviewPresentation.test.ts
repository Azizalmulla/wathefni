import { describe, expect, test } from 'vitest'

import {
  dedupeWorkQueueItems,
  roleBottleneckLabel,
  workQueueDisplayTotal,
  workQueueItemKey,
} from './prehireOverviewPresentation'
import type { PositionSummary, PrehireWorkQueueItem } from '@/types'

function item(partial: Partial<PrehireWorkQueueItem> & Pick<PrehireWorkQueueItem, 'action_type' | 'reason'>): PrehireWorkQueueItem {
  return {
    priority: 50,
    ...partial,
  }
}

describe('dedupeWorkQueueItems', () => {
  test('same application + same action collapses to one row (keeps higher priority)', () => {
    const items = [
      item({
        action_type: 'follow_up_failed_delivery',
        app_key: 'APP-1',
        candidate_name: 'Hamad',
        reason: 'a',
        priority: 80,
      }),
      item({
        action_type: 'follow_up_failed_delivery',
        app_key: 'APP-1',
        candidate_name: 'Hamad Almulla',
        reason: 'b',
        priority: 99,
      }),
    ]
    const out = dedupeWorkQueueItems(items)
    expect(out).toHaveLength(1)
    expect(out[0].priority).toBe(99)
    expect(workQueueItemKey(out[0])).toBe('follow_up_failed_delivery:APP-1')
  })

  test('same candidate across separate applications is preserved', () => {
    const items = [
      item({
        action_type: 'follow_up_failed_delivery',
        app_key: 'APP-A',
        candidate_name: 'Hamad Almulla',
        reason: 'a',
        priority: 90,
      }),
      item({
        action_type: 'follow_up_failed_delivery',
        app_key: 'APP-B',
        candidate_name: 'Hamad Almulla',
        reason: 'a',
        priority: 88,
      }),
    ]
    const out = dedupeWorkQueueItems(items)
    expect(out).toHaveLength(2)
    expect(out.map((row) => row.app_key).sort()).toEqual(['APP-A', 'APP-B'])
  })

  test('same candidate + different action types are preserved', () => {
    const items = [
      item({
        action_type: 'follow_up_failed_delivery',
        app_key: 'APP-1',
        candidate_name: 'Aziz',
        reason: 'follow',
        priority: 99,
      }),
      item({
        action_type: 'ready_for_review',
        app_key: 'APP-1',
        candidate_name: 'Aziz',
        reason: 'ready',
        priority: 80,
      }),
      item({
        action_type: 'send_pending_assessments',
        app_key: 'APP-1',
        candidate_name: 'Aziz',
        reason: 'assessment',
        priority: 70,
      }),
    ]
    expect(dedupeWorkQueueItems(items)).toHaveLength(3)
  })

  test('display total subtracts collapsed page duplicates without inventing work', () => {
    expect(workQueueDisplayTotal(12, 5, 3)).toBe(10)
    expect(workQueueDisplayTotal(12, 5, 5)).toBe(12)
    expect(workQueueDisplayTotal(0, 0, 0)).toBe(0)
  })
})

describe('roleBottleneckLabel Arabic', () => {
  test('returns natural Arabic body copy for shortlisted roles', () => {
    const job = {
      position_code: 'HR',
      position_title: 'HR',
      application_count: 2,
      active_count: 2,
      stage_counts: [{ status: 'shortlisted', count: 2 }],
    } as PositionSummary
    expect(roleBottleneckLabel(job, 'ar', true)).toBe('خطّط لمقابلات أو تقييمات لـ 2 مرشحين في القائمة المختصرة.')
    expect(roleBottleneckLabel(job, 'en', true)).toContain('Plan interviews or assessments')
  })
})
