import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ShiftsWorkspace } from '@/posthire/ShiftsWorkspace'
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

afterEach(() => {
  vi.unstubAllGlobals()
})

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
})

describe('Shifts org-unit filter resource states', () => {
  test('org-unit request failure renders error, not an empty org catalog', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.includes('/employee-org/units')) {
          return jsonResponse({ detail: { error: 'upstream_failed' } }, 500)
        }
        if (path.includes('/dashboard/posthire/shifts')) {
          return jsonResponse({
            company_code: 'WATHEFNI',
            shifts: [],
            swaps: [],
            availability: [],
            reconciliation_flags: [],
            terminal_reminders: [],
          })
        }
        return jsonResponse({ ok: true })
      }),
    )

    renderWithProviders(
      <ShiftsWorkspace
        access={access}
        permissions={['shifts.manage']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )

    const state = await screen.findByTestId('shifts-org-units-filter-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'All branches' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'All teams' })).not.toBeInTheDocument()
  })

  test('successful empty org-unit catalog is a true empty filter, not an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.includes('/employee-org/units')) {
          return jsonResponse({ units: [] })
        }
        if (path.includes('/dashboard/posthire/shifts')) {
          return jsonResponse({
            company_code: 'WATHEFNI',
            shifts: [],
            swaps: [],
            availability: [],
            reconciliation_flags: [],
            terminal_reminders: [],
          })
        }
        return jsonResponse({ ok: true })
      }),
    )

    renderWithProviders(
      <ShiftsWorkspace
        access={access}
        permissions={['shifts.manage']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )

    expect(await screen.findByRole('option', { name: 'All teams' })).toBeInTheDocument()
    expect(screen.queryByTestId('shifts-org-units-filter-state')).not.toBeInTheDocument()
    expect(screen.queryByText(/not an empty result/i)).not.toBeInTheDocument()
  })
})
