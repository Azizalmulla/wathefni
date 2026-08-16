import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '..')
const calendarSrc = readFileSync(resolve(root, 'components/CalendarShell.tsx'), 'utf8')
const hooksSrc = readFileSync(resolve(root, 'lib/query/hooks.ts'), 'utf8')
const freshnessSrc = readFileSync(resolve(root, 'lib/query/freshness.ts'), 'utf8')
const softPollSrc = readFileSync(resolve(root, 'lib/query/useVisibilitySoftPoll.ts'), 'utf8')
const postHireSrc = readFileSync(resolve(root, 'posthire/PostHire.tsx'), 'utf8')
const alertsSrc = readFileSync(resolve(root, 'pages/NotificationsPage.tsx'), 'utf8')

describe('Calendar Wave 1b UX Closure + freshness contract', () => {
  it('preserves selected event snapshot and scroll across navigation', () => {
    expect(calendarSrc).toContain('selectedSnapshot')
    expect(calendarSrc).toContain('captureScroll')
    expect(calendarSrc).toContain('pendingScrollRestoreRef')
    expect(calendarSrc).toContain('boardScrollRef')
    expect(calendarSrc).toContain('changeView')
    expect(calendarSrc).toContain('data-calendar-board')
  })

  it('uses shared Wathefni tokens for category surfaces (no legacy hex fills)', () => {
    expect(calendarSrc).toContain('bg-wf-accent-follow-soft')
    expect(calendarSrc).toContain('bg-wf-accent-review-soft')
    expect(calendarSrc).toContain('bg-wf-frame')
    expect(calendarSrc).not.toMatch(/bg-\[#b9cde8\]/)
    expect(calendarSrc).not.toMatch(/bg-\[#f3d85f\]/)
    expect(calendarSrc).not.toMatch(/bg-\[#e9e4d9\]/)
  })

  it('keeps category labels separate from status in the drawer', () => {
    expect(calendarSrc).toContain('data-calendar-category')
    expect(calendarSrc).toContain('data-calendar-status')
    expect(calendarSrc).toContain("'Personal time'")
    expect(calendarSrc).toContain('وقت شخصي')
  })

  it('retains adjacent prefetch and interview ownership gates', () => {
    expect(calendarSrc).toContain('adjacent-range prefetch')
    expect(calendarSrc).toContain('interview_managed')
    expect(calendarSrc).toContain('Managed through Interviews')
  })

  it('adds visibility-paused refetch intervals on operational TanStack queues', () => {
    expect(freshnessSrc).toContain('useVisibilityRefetchInterval')
    expect(freshnessSrc).toContain('workQueue: 60_000')
    expect(hooksSrc).toMatch(/useWorkQueueQuery[\s\S]*refetchInterval/)
    expect(hooksSrc).toMatch(/useCalendarEventsQuery[\s\S]*refetchInterval/)
    expect(hooksSrc).toMatch(/useApplicationsInfiniteQuery[\s\S]*refetchInterval/)
    expect(hooksSrc).toMatch(/useInterviewsQuery[\s\S]*refetchInterval/)
    expect(softPollSrc).toContain('inFlight.current')
    expect(postHireSrc).toContain('useVisibilitySoftPoll(reload, FRESHNESS_MS.actionInbox')
    expect(alertsSrc).toContain('useVisibilitySoftPoll(reload, FRESHNESS_MS.notifications')
  })
})
