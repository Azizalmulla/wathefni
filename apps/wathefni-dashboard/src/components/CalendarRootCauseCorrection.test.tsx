import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  CALENDAR_MIN_EVENT_HEIGHT_PX,
  CalendarShell,
  layoutTimedCalendarEvents,
  splitCalendarDayEvents,
  timedEventGeometry,
} from '@/components/CalendarShell'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

function eventForToday() {
  const start = new Date()
  start.setHours(9, 0, 0, 0)
  const end = new Date(start)
  end.setMinutes(45)
  return {
    event_id: 'calprev-video-lina',
    title: 'Video interview · Lina',
    event_type: 'other',
    status: 'confirmed',
    start_at: start.toISOString(),
    end_at: end.toISOString(),
    timezone: 'Asia/Kuwait',
    all_day: false,
    detail_level: 'full',
    preview_only: true,
    attendees: [],
    guests: [],
  }
}

describe('Calendar root-cause correction', () => {
  test('source gates selected derivation and portals detail drawer', () => {
    const src = readFileSync(resolve(__dirname, 'CalendarShell.tsx'), 'utf8')
    const hooks = readFileSync(resolve(__dirname, '../lib/query/hooks.ts'), 'utf8')
    expect(src).toContain('createPortal')
    expect(src).toContain('selectedId && selected && !composerOpen')
    expect(src).toContain('!selectedId')
    expect(src).toContain('removeQueries')
    expect(src).toContain('data-calendar-all-day-row')
    expect(src).toContain('data-calendar-overlap-menu')
    expect(src).toContain('multilineTitle')
    expect(src).toContain('CALENDAR_MIN_EVENT_HEIGHT_PX')
    expect(src).not.toContain('whitespace-nowrap')
    expect(hooks).toMatch(/useCalendarEventQuery[\s\S]*?placeholderData:\s*undefined/)
  })

  test('splits all-day from timed and clamps out-of-range geometry', () => {
    const { allDay, timed } = splitCalendarDayEvents([
      { event_id: 'a', all_day: true, start_at: '2026-08-05T00:00:00+03:00', end_at: '2026-08-06T00:00:00+03:00' },
      { event_id: 't', all_day: false, start_at: '2026-08-05T09:00:00+03:00', end_at: '2026-08-05T09:30:00+03:00' },
    ] as any)
    expect(allDay.map((e) => e.event_id)).toEqual(['a'])
    expect(timed.map((e) => e.event_id)).toEqual(['t'])

    const early = timedEventGeometry({
      event_id: 'early',
      start_at: '2026-08-05T05:00:00+03:00',
      end_at: '2026-08-05T06:00:00+03:00',
    } as any)
    expect(early.completelyOutside).toBe(true)
    expect(early.clippedStart).toBe(true)
    expect(early.height).toBeGreaterThanOrEqual(CALENDAR_MIN_EVENT_HEIGHT_PX)

    const late = timedEventGeometry({
      event_id: 'late',
      start_at: '2026-08-05T22:00:00+03:00',
      end_at: '2026-08-05T23:00:00+03:00',
    } as any)
    expect(late.completelyOutside).toBe(true)
    expect(late.clippedEnd).toBe(true)

    const short = timedEventGeometry({
      event_id: 'short',
      start_at: '2026-08-05T09:00:00+03:00',
      end_at: '2026-08-05T09:20:00+03:00',
    } as any)
    expect(short.height).toBeGreaterThanOrEqual(CALENDAR_MIN_EVENT_HEIGHT_PX)
  })

  test('overlap overflow exposes events via +N list instead of silent drop', () => {
    const events = Array.from({ length: 5 }, (_, index) => ({
      event_id: `dense-${index}`,
      start_at: '2026-08-03T07:00:00+03:00',
      end_at: '2026-08-03T08:00:00+03:00',
      title: `Event ${index}`,
      event_type: 'meeting',
    }))
    const layout = layoutTimedCalendarEvents(events)
    const visible = layout.filter((item) => !item.hidden)
    const hidden = layout.filter((item) => item.hidden)
    expect(visible).toHaveLength(3)
    expect(hidden).toHaveLength(2)
    const anchor = visible.find((item) => item.overflowCount > 0)
    expect(anchor?.overflowEvents.map((e) => e.event_id)).toEqual(['dense-3', 'dense-4'])
  })

  test('drawer unmounts fully after X close (no keepPreviousData reuse)', async () => {
    const previewEvent = eventForToday()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes(previewEvent.event_id)) {
        return jsonResponse({
          ok: true,
          events: [previewEvent],
          populated_preview: { enabled: true, injected: 1 },
          team: { show_team_switch: false, scopes: [] },
        })
      }
      if (path.includes(`/dashboard/calendar/events/${previewEvent.event_id}`)) {
        return jsonResponse({ ok: true, event: previewEvent })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      if (path.includes('/sync')) return jsonResponse({ ok: true, customer_status: 'unavailable' })
      if (path.includes('/reschedule')) return jsonResponse({ ok: true, requests: [] })
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)

    fireEvent.click(await screen.findByRole('button', { name: 'Day' }))
    const card = await screen.findByText('Video interview · Lina')
    fireEvent.click(card.closest('[data-calendar-event]') || card)

    const drawer = await waitFor(() => {
      const node = document.querySelector('[data-calendar-detail-drawer]')
      expect(node).toBeTruthy()
      return node as HTMLElement
    })
    expect(drawer.querySelector('[data-calendar-detail-close]')).toBeTruthy()

    fireEvent.click(drawer.querySelector('[data-calendar-detail-close]') as HTMLElement)
    await waitFor(() => {
      expect(document.querySelector('[data-calendar-detail-drawer]')).toBeNull()
    })

    // Re-open then Escape
    fireEvent.click(screen.getByText('Video interview · Lina').closest('[data-calendar-event]') as HTMLElement)
    await waitFor(() => expect(document.querySelector('[data-calendar-detail-drawer]')).toBeTruthy())
    fireEvent.keyDown(window, { key: 'Escape', bubbles: true })
    await waitFor(() => {
      expect(document.querySelector('[data-calendar-detail-drawer]')).toBeNull()
    })
  })

  test('switching view clears drawer selection', async () => {
    const previewEvent = eventForToday()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes(previewEvent.event_id)) {
        return jsonResponse({
          ok: true,
          events: [previewEvent],
          team: { show_team_switch: false, scopes: [] },
        })
      }
      if (path.includes(`/dashboard/calendar/events/${previewEvent.event_id}`)) {
        return jsonResponse({ ok: true, event: previewEvent })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      if (path.includes('/sync')) return jsonResponse({ ok: true })
      if (path.includes('/reschedule')) return jsonResponse({ ok: true, requests: [] })
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Day' }))
    fireEvent.click((await screen.findByText('Video interview · Lina')).closest('[data-calendar-event]') as HTMLElement)
    await waitFor(() => expect(document.querySelector('[data-calendar-detail-drawer]')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Week' }))
    await waitFor(() => {
      expect(document.querySelector('[data-calendar-detail-drawer]')).toBeNull()
    })
  })

  test('keeps the last complete board painted while a new view is fetching', async () => {
    const previewEvent = eventForToday()
    let listCalls = 0
    let resolveDay: (() => void) | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes(previewEvent.event_id)) {
        listCalls += 1
        if (listCalls === 1) {
          return jsonResponse({ ok: true, events: [previewEvent], team: { show_team_switch: false, scopes: [] } })
        }
        return new Promise<Response>((resolve) => {
          resolveDay = () => resolve(jsonResponse({ ok: true, events: [previewEvent], team: { show_team_switch: false, scopes: [] } }))
        })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)
    const board = await screen.findByTestId('calendar-board')
    await waitFor(() => expect(board.getAttribute('data-calendar-painted-view')).toBe('week'))

    fireEvent.click(screen.getByRole('button', { name: 'Day' }))
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2))
    expect(board.getAttribute('data-calendar-painted-view')).toBe('week')
    expect(board.querySelector('[data-rendering-updating-rail]')).toBeTruthy()

    await act(async () => resolveDay?.())
    await waitFor(() => expect(board.getAttribute('data-calendar-painted-view')).toBe('day'))
  })

  test('keeps the last complete board painted while Mine→Company is fetching', async () => {
    const mineEvent = {
      ...eventForToday(),
      event_id: 'calprev-mine-only',
      title: 'Mine only meeting',
    }
    const companyEvent = {
      ...eventForToday(),
      event_id: 'calprev-company-only',
      title: 'Company town hall',
    }
    let resolveCompany: (() => void) | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes('calprev-')) {
        if (path.includes('scope=company')) {
          return new Promise<Response>((resolve) => {
            resolveCompany = () =>
              resolve(jsonResponse({ ok: true, events: [companyEvent], team: { show_team_switch: false, scopes: [] } }))
          })
        }
        return jsonResponse({ ok: true, events: [mineEvent], team: { show_team_switch: false, scopes: [] } })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)
    const board = await screen.findByTestId('calendar-board')
    expect(await screen.findByText(/Mine only meeting/)).toBeTruthy()

    fireEvent.click(screen.getByTestId('calendar-scope-company'))
    await waitFor(() => expect(board.getAttribute('data-calendar-board-pending')).toBe('true'))
    expect(screen.getByText(/Mine only meeting/)).toBeTruthy()
    expect(screen.queryByText(/Company town hall/)).toBeNull()
    expect(board.querySelector('[data-rendering-updating-rail]')).toBeTruthy()

    await act(async () => resolveCompany?.())
    await waitFor(() => expect(screen.getByText(/Company town hall/)).toBeTruthy())
    expect(board.getAttribute('data-calendar-board-pending')).toBeNull()
    expect(screen.queryByText(/Mine only meeting/)).toBeNull()
  })

  test('keeps the last complete board painted while a type filter is fetching', async () => {
    const allEvent = {
      ...eventForToday(),
      event_id: 'calprev-all-types',
      title: 'Open filter meeting',
      event_type: 'meeting',
    }
    const interviewEvent = {
      ...eventForToday(),
      event_id: 'calprev-interview-only',
      title: 'Filtered interview',
      event_type: 'interview',
    }
    let resolveFilter: (() => void) | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes('calprev-')) {
        if (path.includes('event_type=interview')) {
          return new Promise<Response>((resolve) => {
            resolveFilter = () =>
              resolve(jsonResponse({ ok: true, events: [interviewEvent], team: { show_team_switch: false, scopes: [] } }))
          })
        }
        return jsonResponse({ ok: true, events: [allEvent], team: { show_team_switch: false, scopes: [] } })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)
    const board = await screen.findByTestId('calendar-board')
    expect(await screen.findByText(/Open filter meeting/)).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'interview' } })
    await waitFor(() => expect(board.getAttribute('data-calendar-board-pending')).toBe('true'))
    expect(screen.getByText(/Open filter meeting/)).toBeTruthy()
    expect(screen.queryByText(/Filtered interview/)).toBeNull()

    await act(async () => resolveFilter?.())
    await waitFor(() => expect(screen.getByText(/Filtered interview/)).toBeTruthy())
    expect(board.getAttribute('data-calendar-board-pending')).toBeNull()
    expect(screen.queryByText(/Open filter meeting/)).toBeNull()
  })
})
