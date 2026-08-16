import { describe, expect, test, beforeEach } from 'vitest'

import {
  dashboardPerfCountRequest,
  dashboardPerfMarkCachedPaint,
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkOverviewInteractive,
  dashboardPerfMarkPageVisit,
  dashboardPerfReset,
  dashboardPerfSnapshot,
} from './dashboardPerf'

describe('dashboardPerf', () => {
  beforeEach(() => {
    dashboardPerfReset()
  })

  test('tracks interaction → cached paint without PII fields', () => {
    dashboardPerfMarkInteractionStart('candidates_scope', { page: 'candidates' })
    dashboardPerfMarkCachedPaint('candidates_scope', { fromCache: true })
    const snap = dashboardPerfSnapshot()
    expect(snap.events.some((e) => e.kind === 'interaction_start')).toBe(true)
    expect(snap.events.some((e) => e.kind === 'cached_paint' && e.durMs != null)).toBe(true)
    const blob = JSON.stringify(snap)
    expect(blob).not.toMatch(/@|Bearer |app_key|phone=|\+965/i)
  })

  test('counts requests and marks overview interactive once', () => {
    dashboardPerfCountRequest('summary')
    dashboardPerfCountRequest('work-queue')
    dashboardPerfMarkOverviewInteractive()
    dashboardPerfMarkOverviewInteractive()
    const snap = dashboardPerfSnapshot()
    expect(snap.requestCount).toBe(2)
    expect(snap.events.filter((e) => e.kind === 'overview_interactive')).toHaveLength(1)
  })

  test('distinguishes page first load vs cached return', () => {
    dashboardPerfMarkPageVisit('jobs', false)
    dashboardPerfMarkPageVisit('jobs', true)
    const kinds = dashboardPerfSnapshot().events.map((e) => e.kind)
    expect(kinds).toContain('page_first_load')
    expect(kinds).toContain('page_cached_return')
  })
})
