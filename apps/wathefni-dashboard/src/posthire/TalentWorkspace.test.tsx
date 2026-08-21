import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { TalentWorkspace } from '@/posthire/TalentWorkspace'
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

describe('TalentWorkspace resource states', () => {
  test('workspace request failure renders error, not an empty Talent result', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed', message: 'boom' } }, 500)),
    )

    renderWithProviders(
      <TalentWorkspace
        access={access}
        permissions={['talent.manage', 'talent.review', 'talent.succession']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )

    const state = await screen.findByTestId('talent-workspace-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No Talent profiles yet/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('resource-state-empty')).not.toBeInTheDocument()
  })

  test('people tab request failure renders error, not a genuine empty list', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/talent/workspace')) {
        return jsonResponse({ ok: true, counts: { profiles: 1, open_reviews: 0 } })
      }
      if (path.includes('/talent/profiles')) {
        return jsonResponse({ detail: { error: 'upstream_failed' } }, 502)
      }
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <TalentWorkspace
        access={access}
        permissions={['talent.manage', 'talent.review', 'talent.succession']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )

    await screen.findByRole('tab', { name: 'People' })
    fireEvent.click(screen.getByRole('tab', { name: 'People' }))

    const state = await screen.findByTestId('talent-people-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No Talent profiles yet/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  test('successful empty people list is a true empty, not an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.includes('/talent/workspace')) {
          return jsonResponse({ ok: true, counts: { profiles: 0, open_reviews: 0 } })
        }
        if (path.includes('/talent/profiles')) {
          return jsonResponse({ profiles: [], total: 0 })
        }
        return jsonResponse({ ok: true })
      }),
    )

    renderWithProviders(
      <TalentWorkspace
        access={access}
        permissions={['talent.manage']}
        role="owner"
        onNotice={vi.fn()}
      />,
    )

    await screen.findByRole('tab', { name: 'People' })
    fireEvent.click(screen.getByRole('tab', { name: 'People' }))

    await waitFor(() => {
      expect(screen.getByTestId('talent-people-state')).toHaveTextContent(/No Talent profiles yet/i)
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
