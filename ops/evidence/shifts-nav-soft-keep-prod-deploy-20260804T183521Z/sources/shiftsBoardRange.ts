/**
 * Shifts board range transition helpers.
 * Soft-keep prior board until the latest matching request commits atomically.
 * Never apply a slower older response over a newer selection.
 */

import type { PosthireShiftsResponse } from '@/types'

export type ShiftsViewMode = 'day' | 'week'

export type ShiftsBoardCommit = {
  week: number
  view: ShiftsViewMode
  /** ISO date (yyyy-mm-dd) of the navigation anchor used to paint day headers. */
  anchorIso: string
  filtersKey: string
  data: PosthireShiftsResponse
}

export function shiftsFiltersKey(filters: Record<string, string>): string {
  return [
    filters.employee || '',
    filters.branch_key || '',
    filters.site_key || '',
    filters.team_key || '',
    filters.role || '',
  ].join('|')
}

/** Week payload cache key — day view paints from the containing week. */
export function shiftsWeekCacheKey(week: number, filtersKey: string): string {
  return `w:${week}|${filtersKey}`
}

export function isoDateLocal(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * Commit only the newest in-flight request for the currently selected target.
 * Returns null when the response is stale (outranked by a newer navigation).
 */
export function commitIfLatest(args: {
  requestId: number
  latestRequestId: number
  targetWeek: number
  targetView: ShiftsViewMode
  targetAnchorIso: string
  targetFiltersKey: string
  requestedWeek: number
  requestedFiltersKey: string
  data: PosthireShiftsResponse
}): ShiftsBoardCommit | null {
  if (args.requestId !== args.latestRequestId) return null
  if (args.requestedWeek !== args.targetWeek) return null
  if (args.requestedFiltersKey !== args.targetFiltersKey) return null
  return {
    week: args.targetWeek,
    view: args.targetView,
    anchorIso: args.targetAnchorIso,
    filtersKey: args.targetFiltersKey,
    data: args.data,
  }
}

export function adjacentWeeks(week: number, radius = 1): number[] {
  const out: number[] = []
  for (let delta = -radius; delta <= radius; delta += 1) {
    if (delta === 0) continue
    const next = week + delta
    if (next < -26 || next > 26) continue
    out.push(next)
  }
  return out
}

export function filterShiftsForDay(data: PosthireShiftsResponse, dayIso: string): PosthireShiftsResponse {
  const shifts = (data.shifts || []).filter((row) => String(row.shift_date || '').slice(0, 10) === dayIso)
  return { ...data, shifts, view: 'day', start_date: dayIso, end_date: dayIso }
}
