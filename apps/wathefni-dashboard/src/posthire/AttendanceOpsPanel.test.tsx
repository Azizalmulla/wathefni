import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { AttendanceOpsPanel } from '@/posthire/AttendanceOpsPanel'
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

describe('AttendanceOpsPanel resource states', () => {
  test('exceptions request failure renders error, not an empty queue', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)),
    )

    renderWithProviders(
      <AttendanceOpsPanel access={access} canManage onNotice={vi.fn()} />,
    )

    const state = await screen.findByTestId('attendance-ops-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No open exceptions/i)).not.toBeInTheDocument()
  })

  test('successful empty queue is a true empty, not an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ exceptions: [], cases: [], disputes: [] })),
    )

    renderWithProviders(
      <AttendanceOpsPanel access={access} canManage onNotice={vi.fn()} />,
    )

    await waitFor(() => {
      expect(screen.getByText(/No open exceptions/i)).toBeInTheDocument()
    })
    expect(screen.queryByTestId('attendance-ops-state')).not.toBeInTheDocument()
    expect(screen.queryByText(/not an empty result/i)).not.toBeInTheDocument()
  })
})
