import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { OverviewCalendarPanel } from '@/components/OverviewCalendarPanel'
import { renderWithProviders } from '@/test/render'

const access = { companyCode: 'WATHEFNI', hrPhone: '96555511122', token: 'tok' }

function overviewPayload(scopeNote = 'mine') {
  return {
    today: '2026-07-28',
    month: { year: 2026, month: 7, busy_days: ['2026-07-28', '2026-07-30'] },
    upcoming: [
      {
        event_id: 'evt-1',
        title: '1:1 with recruiter',
        start_at: '2026-07-28T10:00:00+03:00',
        end_at: '2026-07-28T10:30:00+03:00',
        scope_note: scopeNote,
      },
    ],
  }
}

describe('OverviewCalendarPanel', () => {
  test('is a personal My calendar widget with no My/Company toggle', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      expect(path).toContain('/dashboard/calendar/overview')
      expect(path).toContain('scope=mine')
      expect(path).not.toContain('scope=company')
      return new Response(JSON.stringify(overviewPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const onOpenCalendar = vi.fn()
    renderWithProviders(
      <OverviewCalendarPanel
        access={access}
        locale="en"
        calendarEnabled
        onOpenCalendar={onOpenCalendar}
        onAddEvent={onOpenCalendar}
      />,
    )

    expect(await screen.findByRole('heading', { name: 'My calendar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View full calendar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'My' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Company' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Team' })).not.toBeInTheDocument()

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    const paths = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(paths.every((p) => p.includes('scope=mine'))).toBe(true)
    expect(paths.some((p) => p.includes('scope=company'))).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'View full calendar' }))
    expect(onOpenCalendar).toHaveBeenCalledTimes(1)
  })

  test('renders Arabic personal heading and keeps full-calendar CTA', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify(overviewPayload()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    renderWithProviders(
      <OverviewCalendarPanel
        access={access}
        locale="ar"
        calendarEnabled
        onOpenCalendar={() => undefined}
      />,
    )

    expect(await screen.findByRole('heading', { name: 'تقويمي' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'عرض التقويم الكامل' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'خاصتي' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'الشركة' })).not.toBeInTheDocument()
  })

  test('does not prefetch company-scope overview', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(overviewPayload()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <OverviewCalendarPanel access={access} calendarEnabled onOpenCalendar={() => undefined} />,
    )

    await screen.findByRole('heading', { name: 'My calendar' })
    await new Promise((r) => window.setTimeout(r, 500))
    const paths = fetchMock.mock.calls.map((c) => String((c as unknown[])[0] ?? ''))
    expect(paths.some((p) => p.includes('scope=company'))).toBe(false)
    expect(paths.filter((p) => p.includes('/dashboard/calendar/overview')).length).toBe(1)
  })
})
