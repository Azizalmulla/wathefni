import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { CandidateClassificationSection } from '@/components/candidates/CandidateClassificationSection'
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

describe('CandidateClassificationSection resource states', () => {
  test('classification request failure renders error, not an unclassified empty section', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.includes('/taxonomy')) return jsonResponse({ dimensions: [] })
        return jsonResponse({ detail: { error: 'upstream_failed' } }, 500)
      }),
    )

    renderWithProviders(
      <CandidateClassificationSection access={access} appKey="app-1" enabled />,
    )

    const state = await screen.findByTestId('candidate-classification-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/None confirmed yet/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/No active AI suggestions/i)).not.toBeInTheDocument()
  })

  test('taxonomy request failure does not look like there are no nodes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.includes('/taxonomy')) return jsonResponse({ detail: { error: 'upstream_failed' } }, 500)
        return jsonResponse({
          classification: {
            status: 'unclassified',
            confirmed: [],
            ai_suggested: [],
          },
        })
      }),
    )

    renderWithProviders(
      <CandidateClassificationSection access={access} appKey="app-1" enabled />,
    )

    const state = await screen.findByTestId('candidate-classification-taxonomy-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/Add taxonomy node/i)).not.toBeInTheDocument()
  })
})
