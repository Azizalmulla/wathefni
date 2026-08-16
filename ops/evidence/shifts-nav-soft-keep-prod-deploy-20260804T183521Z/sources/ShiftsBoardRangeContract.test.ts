import { describe, expect, it } from 'vitest'

import {
  adjacentWeeks,
  commitIfLatest,
  filterShiftsForDay,
  shiftsFiltersKey,
  shiftsWeekCacheKey,
} from './shiftsBoardRange'
import type { PosthireShiftsResponse } from '@/types'

function payload(shifts: Array<{ shift_id: string; shift_date: string }>): PosthireShiftsResponse {
  return {
    company_code: 'WATHEFNI',
    shifts: shifts.map((row) => ({ ...row, status: 'scheduled' })),
    swaps: [],
  }
}

describe('Shifts board range soft-keep / request race', () => {
  it('commits only the latest matching request', () => {
    const data = payload([{ shift_id: 'a', shift_date: '2026-08-16' }])
    const ok = commitIfLatest({
      requestId: 3,
      latestRequestId: 3,
      targetWeek: 2,
      targetView: 'week',
      targetAnchorIso: '2026-08-16',
      targetFiltersKey: '||||',
      requestedWeek: 2,
      requestedFiltersKey: '||||',
      data,
    })
    expect(ok?.week).toBe(2)
    expect(ok?.data.shifts).toHaveLength(1)

    const stale = commitIfLatest({
      requestId: 2,
      latestRequestId: 3,
      targetWeek: 2,
      targetView: 'week',
      targetAnchorIso: '2026-08-16',
      targetFiltersKey: '||||',
      requestedWeek: 1,
      requestedFiltersKey: '||||',
      data,
    })
    expect(stale).toBeNull()
  })

  it('rejects responses that no longer match the selected week/filters', () => {
    const data = payload([{ shift_id: 'a', shift_date: '2026-08-16' }])
    expect(
      commitIfLatest({
        requestId: 5,
        latestRequestId: 5,
        targetWeek: 3,
        targetView: 'week',
        targetAnchorIso: '2026-08-23',
        targetFiltersKey: '||||',
        requestedWeek: 2,
        requestedFiltersKey: '||||',
        data,
      }),
    ).toBeNull()

    expect(
      commitIfLatest({
        requestId: 5,
        latestRequestId: 5,
        targetWeek: 2,
        targetView: 'week',
        targetAnchorIso: '2026-08-16',
        targetFiltersKey: 'ali||||',
        requestedWeek: 2,
        requestedFiltersKey: '||||',
        data,
      }),
    ).toBeNull()
  })

  it('filters day view from the cached week payload without dropping other days from cache', () => {
    const week = payload([
      { shift_id: 'a', shift_date: '2026-08-17' },
      { shift_id: 'b', shift_date: '2026-08-18' },
      { shift_id: 'c', shift_date: '2026-08-18' },
    ])
    const day = filterShiftsForDay(week, '2026-08-18')
    expect(day.shifts.map((s) => s.shift_id)).toEqual(['b', 'c'])
    expect(week.shifts).toHaveLength(3)
  })

  it('builds stable cache keys and adjacent week targets', () => {
    expect(shiftsFiltersKey({ employee: 'A', branch_key: '', site_key: '', team_key: '', role: '' })).toBe('A||||')
    expect(shiftsWeekCacheKey(2, 'A||||')).toBe('w:2|A||||')
    expect(adjacentWeeks(0)).toEqual([-1, 1])
    expect(adjacentWeeks(26)).toEqual([25])
  })
})
