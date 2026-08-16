import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { HeldIntakeReviewCard } from '@/components/candidates/HeldIntakeReviewCard'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess, ImportIntakeResponse, PositionSummary } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

const positions: PositionSummary[] = [
  { position_code: 'ENG', position_title: 'Engineer', status: 'open' } as PositionSummary,
  { position_code: 'OPS', position_title: 'Operations', status: 'open' } as PositionSummary,
]

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const twoUnclear: ImportIntakeResponse = {
  company_code: 'WATHEFNI',
  total: 2,
  auto_admit_explicit_imports: false,
  auto_admitted_total: 0,
  groups: [
    {
      key: 'unclear',
      kind: 'unclear',
      role_code: null,
      role_title: null,
      confidence: 'none',
      count: 2,
      app_keys: ['app-1', 'app-2'],
      items: [
        { app_key: 'app-1', candidate_name: 'Sara Held', status: 'needs_role', original_filename: 'sara.pdf' },
        { app_key: 'app-2', candidate_name: 'Omar Held', status: 'needs_role', original_filename: 'omar.pdf' },
      ],
    },
  ],
}

describe('HeldIntakeReviewCard', () => {
  test('source stays product language and uses explicit selection only', () => {
    const src = readFileSync(resolve(__dirname, './HeldIntakeReviewCard.tsx'), 'utf8')
    expect(src).toContain('Held CVs waiting for a job')
    expect(src).toContain('Assign job')
    expect(src).toContain('Assign and admit')
    expect(src).toContain('data-held-assign-scope="explicit"')
    expect(src).toContain('held-bulk-toolbar')
    expect(src).toContain('all selected candidates will receive the same job')
    expect(src).not.toMatch(/picked\.length \? picked : group\.app_keys/)
    expect(src).not.toMatch(/selectedCount \|\| group\.count/)
    expect(src).not.toMatch(/IntakeOperations|getIntakeOperations|ProcessingAttention/)
  })

  test('default action is per-candidate Assign job; bulk toolbar hidden until selection', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/dashboard/prehire/import/intake')) return jsonResponse(twoUnclear)
        return jsonResponse({})
      }),
    )

    renderWithProviders(
      <HeldIntakeReviewCard
        access={access}
        applications={[]}
        locale="en"
        onChanged={vi.fn()}
        positions={positions}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('held-intake-review')).toBeInTheDocument()
    })
    expect(screen.getByText('Sara Held')).toBeInTheDocument()
    expect(screen.getByText('Omar Held')).toBeInTheDocument()
    expect(screen.getByTestId('held-assign-job-app-1')).toBeInTheDocument()
    expect(screen.getByTestId('held-assign-job-app-2')).toBeInTheDocument()
    expect(screen.queryByTestId('held-bulk-toolbar')).not.toBeInTheDocument()
    expect(screen.queryByText('Assign & admit')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('held-assign-job-app-1'))
    expect(screen.getByTestId('held-row-assign-app-1')).toBeInTheDocument()
    const rowAdmit = screen.getByTestId('held-row-assign-admit-app-1')
    expect(rowAdmit).toBeDisabled()
    // Other candidate must not share this selector.
    expect(screen.queryByTestId('held-row-assign-app-2')).not.toBeInTheDocument()
  })

  test('bulk toolbar appears only after checkboxes; confirm disabled until job chosen', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/dashboard/prehire/import/intake')) return jsonResponse(twoUnclear)
      if (url.includes('/dashboard/prehire/import/items/bulk') && init?.method === 'POST') {
        return jsonResponse({ ok: true, promoted: 1, skipped: 0 })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <HeldIntakeReviewCard
        access={access}
        applications={[]}
        locale="en"
        onChanged={vi.fn()}
        positions={positions}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('held-select-app-1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('held-select-app-1'))
    await waitFor(() => expect(screen.getByTestId('held-bulk-toolbar')).toBeInTheDocument())
    expect(screen.getByTestId('held-bulk-copy')).toHaveTextContent(
      '1 selected — all selected candidates will receive the same job.',
    )
    const bulkAdmit = screen.getByTestId('held-bulk-assign-admit')
    expect(bulkAdmit).toBeDisabled()
    expect(bulkAdmit).toHaveTextContent('Assign and admit 1')

    fireEvent.click(screen.getByTestId('held-select-app-2'))
    await waitFor(() =>
      expect(screen.getByTestId('held-bulk-copy')).toHaveTextContent(
        '2 selected — all selected candidates will receive the same job.',
      ),
    )
    expect(screen.getByTestId('held-bulk-assign-admit')).toHaveTextContent('Assign and admit 2')
  })

  test('per-candidate assign posts only that app_key — never the sibling row', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/dashboard/prehire/import/intake')) return jsonResponse(twoUnclear)
      if (url.includes('/dashboard/prehire/import/items/bulk') && init?.method === 'POST') {
        return jsonResponse({ ok: true, promoted: 1, skipped: 0 })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <HeldIntakeReviewCard
        access={access}
        applications={[]}
        locale="en"
        onChanged={vi.fn()}
        positions={positions}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('held-assign-job-app-1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('held-assign-job-app-1'))
    fireEvent.change(screen.getByTestId('held-row-job-select-app-1'), { target: { value: 'ENG' } })
    expect(screen.getByTestId('held-row-assign-admit-app-1')).not.toBeDisabled()
    expect(screen.queryByTestId('held-bulk-toolbar')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('held-row-assign-admit-app-1'))
    await waitFor(() => expect(screen.getByText('Assign and admit 1?')).toBeInTheDocument())
    expect(screen.getByText(/This candidate will be assigned to “Engineer” then admitted/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Admit' }))

    await waitFor(() => {
      const bulkCalls = fetchMock.mock.calls.filter(
        ([input, init]) => String(input).includes('/import/items/bulk') && init?.method === 'POST',
      )
      expect(bulkCalls.length).toBe(1)
      const body = JSON.parse(String(bulkCalls[0][1]?.body || '{}'))
      expect(body).toEqual({
        action: 'assign',
        app_keys: ['app-1'],
        position_code: 'ENG',
        position_title: 'Engineer',
      })
      expect(body.app_keys).not.toContain('app-2')
    })
  })

  test('bulk assign posts only checked keys and requires a job', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/dashboard/prehire/import/intake')) return jsonResponse(twoUnclear)
      if (url.includes('/dashboard/prehire/import/items/bulk') && init?.method === 'POST') {
        return jsonResponse({ ok: true, promoted: 2, skipped: 0 })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(
      <HeldIntakeReviewCard
        access={access}
        applications={[]}
        locale="en"
        onChanged={vi.fn()}
        positions={positions}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('held-select-app-1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('held-select-app-1'))
    fireEvent.click(screen.getByTestId('held-select-app-2'))
    await waitFor(() => expect(screen.getByTestId('held-bulk-assign-admit')).toBeDisabled())

    fireEvent.change(screen.getByTestId('held-bulk-job-select'), { target: { value: 'OPS' } })
    expect(screen.getByTestId('held-bulk-assign-admit')).not.toBeDisabled()
    fireEvent.click(screen.getByTestId('held-bulk-assign-admit'))
    await waitFor(() => expect(screen.getByText('Assign and admit 2?')).toBeInTheDocument())
    expect(
      screen.getByText(/2 selected candidates will all receive the same job “Operations” then be admitted/),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Admit' }))

    await waitFor(() => {
      const bulkCalls = fetchMock.mock.calls.filter(
        ([input, init]) => String(input).includes('/import/items/bulk') && init?.method === 'POST',
      )
      expect(bulkCalls.length).toBe(1)
      const body = JSON.parse(String(bulkCalls[0][1]?.body || '{}'))
      expect(body.action).toBe('assign')
      expect(body.app_keys).toEqual(['app-1', 'app-2'])
      expect(body.position_code).toBe('OPS')
    })
  })

  test('AR render uses RTL and Arabic title with per-row Assign job', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/dashboard/prehire/import/intake')) {
          return jsonResponse({
            company_code: 'WATHEFNI',
            total: 1,
            auto_admit_explicit_imports: false,
            auto_admitted_total: 0,
            groups: [
              {
                key: 'suggested:ENG',
                kind: 'suggested',
                role_code: 'ENG',
                role_title: 'Engineer',
                confidence: 'medium',
                count: 1,
                app_keys: ['app-2'],
                items: [{ app_key: 'app-2', candidate_name: 'علي', status: 'needs_role' }],
              },
            ],
          })
        }
        return jsonResponse({})
      }),
    )

    const { container } = renderWithProviders(
      <HeldIntakeReviewCard
        access={access}
        applications={[]}
        locale="ar"
        onChanged={vi.fn()}
        positions={positions}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('سير معلّقة بانتظار وظيفة')).toBeInTheDocument()
    })
    expect(container.querySelector('[dir="rtl"]')).toBeTruthy()
    expect(screen.getByTestId('held-assign-job-app-2')).toBeInTheDocument()
    expect(screen.getByText('تعيين وظيفة')).toBeInTheDocument()
    expect(screen.getByTestId('held-suggestion-app-2')).toHaveTextContent('اقتراح: Engineer')
    // Bulk admit for suggested group is available only after selection.
    expect(screen.queryByTestId('held-bulk-toolbar')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('held-select-app-2'))
    await waitFor(() => expect(screen.getByTestId('held-bulk-admit')).toBeInTheDocument())
  })
})
