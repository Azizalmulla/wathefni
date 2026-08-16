import { describe, expect, test, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { CandidatesPage } from '@/pages/CandidatesPage'
import { EMPTY_CANDIDATE_FILTERS } from '@/lib/candidateFilterAuthority'
import type { CandidateFilters } from '@/types'

function renderCandidates(opts: {
  locale: 'en' | 'ar'
  filters?: CandidateFilters
  onFilters?: (next: CandidateFilters) => void
}) {
  const filters = opts.filters || {
    ...EMPTY_CANDIDATE_FILTERS,
    followUp: 'needed',
    overviewCohort: 'follow_up_needed',
    cohortKey: 'follow_up_needed',
    action: 'follow_up_failed_delivery',
    position: 'ACCOUNTING_EXCEL',
  }
  const setFilters = vi.fn((updater: CandidateFilters | ((current: CandidateFilters) => CandidateFilters)) => {
    const next = typeof updater === 'function' ? updater(filters) : updater
    opts.onFilters?.(next)
  })
  render(
    <CandidatesPage
      applications={[]}
      assessmentEnabled
      busy={false}
      filters={filters}
      locale={opts.locale}
      onLocale={() => undefined}
      onSaveView={async () => undefined}
      onSelect={() => undefined}
      onSelectSavedView={() => undefined}
      positions={[{ position_code: 'ACCOUNTING_EXCEL', position_title: 'Accounting', application_count: 0, active_count: 0 }]}
      query=""
      savedViews={[]}
      setFilters={setFilters}
      setQuery={() => undefined}
      setStatus={() => undefined}
      status=""
    />,
  )
  return { setFilters }
}

describe('CandidatesPage Wave 3 filter authority', () => {
  test('EN page keeps rtl/ltr contract and Follow-up clear drops context', () => {
    let latest: CandidateFilters | null = null
    renderCandidates({
      locale: 'en',
      onFilters: (next) => {
        latest = next
      },
    })
    const root = screen.getByTestId('unified-candidates-page')
    expect(root).toHaveAttribute('dir', 'ltr')
    fireEvent.click(screen.getByRole('button', { name: /Filters/i }))
    const followUp = screen.getByDisplayValue('Follow-up needed')
    fireEvent.change(followUp, { target: { value: '' } })
    expect(latest).toMatchObject({
      followUp: '',
      overviewCohort: '',
      cohortKey: '',
      action: '',
      position: 'ACCOUNTING_EXCEL',
    })
  })

  test('AR page uses rtl and Clear all drops follow-up context', () => {
    let latest: CandidateFilters | null = null
    renderCandidates({
      locale: 'ar',
      onFilters: (next) => {
        latest = next
      },
    })
    expect(screen.getByTestId('unified-candidates-page')).toHaveAttribute('dir', 'rtl')
    fireEvent.click(screen.getByRole('button', { name: /مرشحات/ }))
    fireEvent.click(screen.getByTestId('candidates-clear-all-filters'))
    expect(latest).toMatchObject({
      followUp: '',
      overviewCohort: '',
      cohortKey: '',
      action: '',
      position: 'ACCOUNTING_EXCEL',
    })
  })
})
