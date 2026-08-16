import { fireEvent, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  calendarEventDensity,
  CalendarShell,
  layoutTimedCalendarEvents,
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

describe('CalendarShell sync authority + polish', () => {
  test('classifies duration density and cascade overlaps instead of narrow lanes', () => {
    const events = [
      {
        event_id: 'short',
        start_at: '2026-07-31T09:00:00+03:00',
        end_at: '2026-07-31T09:30:00+03:00',
      },
      {
        event_id: 'medium',
        start_at: '2026-07-31T10:00:00+03:00',
        end_at: '2026-07-31T11:30:00+03:00',
      },
      {
        event_id: 'long',
        start_at: '2026-07-31T10:30:00+03:00',
        end_at: '2026-07-31T13:30:00+03:00',
      },
    ]

    expect(calendarEventDensity(events[0])).toBe('short')
    expect(calendarEventDensity(events[1])).toBe('medium')
    expect(calendarEventDensity(events[2])).toBe('long')

    const layout = layoutTimedCalendarEvents(events)
    expect(layout.find((item) => item.event.event_id === 'short')).toMatchObject({
      placement: 'solo',
      laneCount: 1,
      hidden: false,
    })
    expect(layout.find((item) => item.event.event_id === 'medium')).toMatchObject({
      placement: 'cascade',
      cascadeIndex: 0,
      hidden: false,
    })
    expect(layout.find((item) => item.event.event_id === 'long')).toMatchObject({
      placement: 'cascade',
      cascadeIndex: 1,
      hidden: false,
    })
    expect(events[2].start_at).toBe('2026-07-31T10:30:00+03:00')
    expect(events[2].end_at).toBe('2026-07-31T13:30:00+03:00')
  })

  test('overflows dense cascades with +N instead of sub-min-width columns', () => {
    const base = '2026-08-03T07:00:00+03:00'
    const events = Array.from({ length: 5 }, (_, index) => ({
      event_id: `dense-${index}`,
      start_at: base,
      end_at: '2026-08-03T08:00:00+03:00',
      title: `Event ${index}`,
      event_type: 'meeting',
    }))
    const layout = layoutTimedCalendarEvents(events)
    expect(layout.filter((item) => !item.hidden)).toHaveLength(3)
    expect(layout.filter((item) => item.hidden)).toHaveLength(2)
    const topVisible = layout.find((item) => item.overflowCount > 0)
    expect(topVisible?.overflowCount).toBe(2)
    expect(topVisible?.overflowEvents.map((e) => e.event_id)).toEqual(['dense-3', 'dense-4'])
    expect(layout.every((item) => item.placement === 'cascade')).toBe(true)
  })

  test('renders progressive timed cards, participant context, and Teams Join while card opens details', async () => {
    const today = new Date()
    const at = (hour: number, minute = 0) => {
      const value = new Date(today)
      value.setHours(hour, minute, 0, 0)
      return value.toISOString()
    }
    const events = [
      {
        event_id: 'short-card',
        title: 'Candidate check-in',
        event_type: 'meeting',
        status: 'confirmed',
        start_at: at(8),
        end_at: at(8, 30),
        timezone: 'Asia/Kuwait',
        detail_level: 'full',
        attendees: [],
        guests: [],
      },
      {
        event_id: 'medium-card',
        title: 'Hiring review',
        event_type: 'deadline',
        status: 'tentative',
        start_at: at(9),
        end_at: at(10, 30),
        timezone: 'Asia/Kuwait',
        detail_level: 'full',
        attendees: [],
        guests: [],
      },
      {
        event_id: 'teams-card',
        title: 'Interview · Sara · Product Designer',
        event_type: 'interview',
        status: 'confirmed',
        start_at: at(11),
        end_at: at(14),
        timezone: 'Asia/Kuwait',
        detail_level: 'full',
        meeting_url: 'https://teams.microsoft.com/l/meetup-join/example',
        metadata: { candidate_name: 'Sara', job_title: 'Product Designer' },
        attendees: [{ user_id: 'owner-1' }, { user_id: 'recruiter-2' }],
        guests: [{ display_name: 'Sara' }],
      },
    ]
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events/teams-card')) {
        return jsonResponse({ ok: true, event: events[2] })
      }
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({ ok: true, events, team: { show_team_switch: false, scopes: [] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, has_team_scope: false, scopes: [] })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)

    renderWithProviders(<CalendarShell access={access} canManage canCompany locale="en" />)

    const short = await screen.findByTestId('calendar-timed-event-short-card')
    const medium = screen.getByTestId('calendar-timed-event-medium-card')
    const teams = screen.getByTestId('calendar-timed-event-teams-card')
    expect(short).toHaveAttribute('data-density', 'short')
    expect(medium).toHaveAttribute('data-density', 'medium')
    expect(teams).toHaveAttribute('data-density', 'long')
    expect(teams).toHaveTextContent('Sara · Product Designer')
    expect(teams).toHaveTextContent('Teams')
    expect(screen.getByLabelText('3 participants')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    expect(open).toHaveBeenCalledWith(
      'https://teams.microsoft.com/l/meetup-join/example',
      '_blank',
      'noopener,noreferrer',
    )

    fireEvent.click(teams)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/dashboard/calendar/events/teams-card'))).toBe(true)
    })
  })

  test('source removes External sync console and keeps quiet Synced/Not synced only', () => {
    const src = readFileSync(resolve(__dirname, 'CalendarShell.tsx'), 'utf8')
    expect(src).not.toContain('External sync')
    expect(src).not.toContain('مزامنة خارجية')
    expect(src).not.toContain('Platform integrations')
    expect(src).not.toContain('Ensure legacy operator')
    expect(src).not.toContain('Open external')
    expect(src).not.toContain('retryCalendarEventSync')
    expect(src).toMatch(/Synced|تمت المزامنة/)
    expect(src).toMatch(/Not synced|غير متزامن/)
    expect(src).toContain('eventTypeLabel')
    expect(src).toContain("effectiveScope !== 'mine'")
  })

  test('owner/hr calendar UI has no External sync control', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync') && !path.includes('/reschedule')) {
        return jsonResponse({ ok: true, events: [], team: { show_team_switch: true, scopes: [] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: true, scopes: [], primary_org_scope_id: null })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany canOverride locale="en" />,
    )

    expect(await screen.findByTestId('calendar-board')).toBeInTheDocument()
    expect(document.querySelector('[data-calendar-wave1c]')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /External sync/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Platform integrations/i)).not.toBeInTheDocument()
  })

  test('hides Mine only while in My scope and shows labeled type filters', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({ ok: true, events: [], team: { show_team_switch: true, scopes: [{ org_scope_id: 's1', label: 'Team A' }] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({
          ok: true,
          show_team_switch: true,
          scopes: [{ org_scope_id: 's1', label: 'Team A' }],
          primary_org_scope_id: 's1',
        })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany locale="en" />,
    )

    await screen.findByTestId('calendar-board')
    const mineOnly = screen.getByText('Mine only').closest('label')
    expect(mineOnly).toHaveClass('invisible')
    expect(mineOnly).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByRole('option', { name: 'Meeting' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Confirmed' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Company$/i }))
    await waitFor(() => {
      expect(screen.getByText('Mine only')).toBeInTheDocument()
    })
  })

  test('scope labels are unambiguous and switch changes events query scope', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({
          ok: true,
          events: [],
          team: { show_team_switch: true, has_team_scope: true, scopes: [{ org_scope_id: 's1', label: 'Team A' }] },
        })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({
          ok: true,
          show_team_switch: true,
          has_team_scope: true,
          scopes: [{ org_scope_id: 's1', label: 'Team A' }],
          primary_org_scope_id: 's1',
        })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany locale="en" />,
    )

    expect(await screen.findByRole('button', { name: 'Mine' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Team' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Company' })).toBeInTheDocument()
    expect(screen.getByTitle('Events you own, organize, or attend')).toBeInTheDocument()
    expect(screen.getByTitle('Events shared with your hiring team scope')).toBeInTheDocument()
    expect(screen.getByTitle('Company-wide events you are allowed to see')).toBeInTheDocument()

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('scope=mine'))).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('scope=team'))).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Company' }))
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('scope=company'))).toBe(true)
    })
  })

  test('hides Team without org scopes and Company without permission', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({
          ok: true,
          events: [],
          team: { show_team_switch: false, has_team_scope: false, scopes: [], no_team_guidance: true },
        })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({
          ok: true,
          show_team_switch: false,
          has_team_scope: false,
          has_company_oversight: true,
          no_team_guidance: true,
          scopes: [],
          primary_org_scope_id: null,
        })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = renderWithProviders(
      <CalendarShell access={access} canManage canCompany={false} locale="en" />,
    )

    await screen.findByRole('button', { name: 'Mine' })
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Team' })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Company' })).not.toBeInTheDocument()

    rerender(<CalendarShell access={access} canManage canCompany locale="en" />)
    expect(await screen.findByRole('button', { name: 'Company' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Team' })).not.toBeInTheDocument()
  })

  test('Arabic type and status filter labels are localized', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({ ok: true, events: [], team: { show_team_switch: false, scopes: [] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany locale="ar" />,
    )

    await screen.findByTestId('calendar-board')
    expect(screen.getByRole('option', { name: 'اجتماع' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'مؤكد' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'meeting' })).not.toBeInTheDocument()
  })

  test('event drawer shows quiet Synced without provider evidence', async () => {
    const at = (hour: number, minute = 0) => {
      const value = new Date()
      value.setHours(hour, minute, 0, 0)
      return value.toISOString()
    }
    const event = {
      event_id: 'evt-1',
      title: 'Standup',
      event_type: 'meeting',
      status: 'confirmed',
      start_at: at(10),
      end_at: at(10, 30),
      timezone: 'Asia/Kuwait',
      detail_level: 'full',
      attendees: [],
      guests: [],
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events/evt-1/sync')) {
        return jsonResponse({ ok: true, event_id: 'evt-1', detail: 'status', customer_status: 'synced', bindings: [] })
      }
      if (path.includes('/dashboard/calendar/events/evt-1/reschedule')) {
        return jsonResponse({ ok: true, requests: [] })
      }
      if (path.includes('/dashboard/calendar/events/evt-1')) {
        return jsonResponse({ ok: true, event })
      }
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({ ok: true, events: [event], team: { show_team_switch: false, scopes: [] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany locale="en" />,
    )

    fireEvent.click(await screen.findByText('Meeting · Standup'))
    expect(await screen.findByText('Synced')).toBeInTheDocument()
    expect(screen.queryByText(/google_workspace|microsoft_365|Open external|Retry/i)).not.toBeInTheDocument()
    expect(screen.getAllByText('Meeting').length).toBeGreaterThan(0)
  })

  test('event drawer shows quiet Not synced without provider evidence', async () => {
    const at = (hour: number, minute = 0) => {
      const value = new Date()
      value.setHours(hour, minute, 0, 0)
      return value.toISOString()
    }
    const event = {
      event_id: 'evt-2',
      title: 'Planning',
      event_type: 'meeting',
      status: 'confirmed',
      start_at: at(11),
      end_at: at(11, 30),
      timezone: 'Asia/Kuwait',
      detail_level: 'full',
      attendees: [],
      guests: [],
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/dashboard/calendar/events/evt-2/sync')) {
        return jsonResponse({
          ok: true,
          event_id: 'evt-2',
          detail: 'status',
          customer_status: 'unavailable',
          bindings: [],
        })
      }
      if (path.includes('/dashboard/calendar/events/evt-2/reschedule')) {
        return jsonResponse({ ok: true, requests: [] })
      }
      if (path.includes('/dashboard/calendar/events/evt-2')) {
        return jsonResponse({ ok: true, event })
      }
      if (path.includes('/dashboard/calendar/events') && !path.includes('/sync')) {
        return jsonResponse({ ok: true, events: [event], team: { show_team_switch: false, scopes: [] } })
      }
      if (path.includes('/dashboard/calendar/team-scopes')) {
        return jsonResponse({ ok: true, show_team_switch: false, scopes: [] })
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <CalendarShell access={access} canManage canCompany locale="en" />,
    )

    fireEvent.click(await screen.findByText('Meeting · Planning'))
    expect(await screen.findByText('Not synced')).toBeInTheDocument()
    expect(screen.queryByText(/google_workspace|microsoft_365|last_error|Open external|Retry/i)).not.toBeInTheDocument()
  })
})
