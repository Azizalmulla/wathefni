import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { PeoplePicker } from '@/components/PeoplePicker'
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

describe('PeoplePicker resource states', () => {
  test('directory request failure is not shown as no eligible people', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: { error: 'upstream_failed' } }, 500)),
    )

    renderWithProviders(
      <PeoplePicker access={access} purpose="directory" value="" onChange={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Unassigned/i }))
    expect(await screen.findByTestId('people-picker-error')).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No eligible people/i)).not.toBeInTheDocument()
  })

  test('successful empty search remains a true empty result', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ people: [] })))

    renderWithProviders(
      <PeoplePicker access={access} purpose="directory" value="" onChange={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Unassigned/i }))
    await waitFor(() => {
      expect(screen.getByText(/No eligible people/i)).toBeInTheDocument()
    })
    expect(screen.queryByTestId('people-picker-error')).not.toBeInTheDocument()
  })
})
