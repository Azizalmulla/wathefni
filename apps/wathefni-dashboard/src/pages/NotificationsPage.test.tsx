import { screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { NotificationsPage } from '@/pages/NotificationsPage'
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
  window.history.replaceState({}, '', '/')
  vi.unstubAllGlobals()
})

describe('NotificationsPage resource states', () => {
  test('HR task request failure renders error, not an all-clear empty state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)),
    )

    renderWithProviders(
      <NotificationsPage
        access={access}
        permissions={['users.manage']}
        actionItems={[]}
        notifications={[]}
        onNavigate={vi.fn()}
        posthireEnabled
      />,
    )

    const state = await screen.findByTestId('alerts-delivery-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/All clear/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/No delivery issues need attention right now/i)).not.toBeInTheDocument()
  })

  test('successful empty delivery queue is a true empty, not an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ tasks: [], messages: [], total: 0, open_count: 0 })),
    )

    renderWithProviders(
      <NotificationsPage
        access={access}
        permissions={['users.manage']}
        actionItems={[]}
        notifications={[]}
        onNavigate={vi.fn()}
        posthireEnabled
      />,
    )

    expect(await screen.findByText(/All clear — no delivery issues in this view/i)).toBeInTheDocument()
    expect(screen.queryByTestId('alerts-delivery-state')).not.toBeInTheDocument()
    expect(screen.queryByText(/not an empty result/i)).not.toBeInTheDocument()
  })
})
