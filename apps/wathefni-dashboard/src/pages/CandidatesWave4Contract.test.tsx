import { describe, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'

import { CandidatesPage } from '@/pages/CandidatesPage'
import { EMPTY_CANDIDATE_FILTERS } from '@/lib/candidateFilterAuthority'
import type { CandidateFilters, DashboardAccess } from '@/types'

function renderCandidates(opts: {
  locale: 'en' | 'ar'
  filters?: CandidateFilters
  status?: string
  query?: string
  onFilters?: (next: CandidateFilters) => void
  access?: DashboardAccess
  importButton?: ReactNode
}) {
  let filters = opts.filters || {
    ...EMPTY_CANDIDATE_FILTERS,
    followUp: 'needed',
    overviewCohort: 'follow_up_needed',
    cohortKey: 'follow_up_needed',
    action: 'follow_up_failed_delivery',
    position: 'ACCOUNTING_EXCEL',
    assessmentStatus: 'completed',
  }
  const setFilters = vi.fn((updater: CandidateFilters | ((current: CandidateFilters) => CandidateFilters)) => {
    filters = typeof updater === 'function' ? updater(filters) : updater
    opts.onFilters?.(filters)
  })
  const view = render(
    <CandidatesPage
      access={opts.access}
      applications={[]}
      assessmentEnabled
      busy={false}
      filters={filters}
      importButton={opts.importButton}
      locale={opts.locale}
      onLocale={() => undefined}
      onSaveView={async () => undefined}
      onSelect={() => undefined}
      onSelectSavedView={() => undefined}
      positions={[{ position_code: 'ACCOUNTING_EXCEL', position_title: 'Accounting', application_count: 0, active_count: 0 }]}
      query={opts.query || ''}
      savedViews={[{ view_id: 'v1', name: 'Ready view', filters: { position: 'ACCOUNTING_EXCEL', status: 'new' } }]}
      setFilters={setFilters}
      setQuery={() => undefined}
      setStatus={() => undefined}
      status={opts.status || ''}
    />,
  )
  return { setFilters, rerender: view.rerender, getFilters: () => filters }
}

describe('CandidatesPage Wave 4 filter UX', () => {
  test('restricted viewers do not load or render candidate intake management', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderCandidates({
      locale: 'en',
      access: {
        token: 'viewer-token',
        companyCode: 'WATHEFNI',
        hrPhone: '',
      },
    })
    expect(screen.queryByTestId('held-intake-review')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  test('default bar keeps Search, Job, Stage, Filters (N) and follow-up chip', () => {
    renderCandidates({ locale: 'en' })
    const bar = screen.getByTestId('candidates-default-filter-bar')
    expect(within(bar).getByPlaceholderText('Search candidates')).toBeInTheDocument()
    expect(within(bar).getByDisplayValue('Accounting')).toBeInTheDocument()
    expect(within(bar).getByDisplayValue('All stages')).toBeInTheDocument()
    expect(within(bar).getByRole('button', { name: /Filters \(2\)/ })).toBeInTheDocument()
    expect(screen.getByTestId('candidate-filter-chip-followUp')).toHaveTextContent('Follow-up needed')
    expect(screen.getByTestId('candidates-clear-all-chips')).toBeInTheDocument()
  })

  test('opening and closing filters never loses applied state', () => {
    renderCandidates({ locale: 'en' })
    fireEvent.click(screen.getByTestId('candidates-open-filters'))
    expect(screen.getByTestId('candidates-filter-overlay')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Follow-up needed')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Completed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByTestId('candidates-filter-overlay')).not.toBeInTheDocument()
    expect(screen.getByTestId('candidate-filter-chip-followUp')).toBeInTheDocument()
    expect(screen.getByTestId('candidate-filter-chip-assessmentStatus')).toBeInTheDocument()
  })

  test('removing Follow-up needed chip clears cohort context', () => {
    let latest: CandidateFilters | null = null
    renderCandidates({
      locale: 'en',
      onFilters: (next) => {
        latest = next
      },
    })
    fireEvent.click(screen.getByTestId('candidate-filter-chip-followUp'))
    expect(latest).toMatchObject({
      followUp: '',
      overviewCohort: '',
      cohortKey: '',
      action: '',
      assessmentStatus: 'completed',
      position: 'ACCOUNTING_EXCEL',
    })
  })

  test('Clear all in drawer clears specialist filters and keeps job', () => {
    let latest: CandidateFilters | null = null
    renderCandidates({
      locale: 'en',
      onFilters: (next) => {
        latest = next
      },
    })
    fireEvent.click(screen.getByTestId('candidates-open-filters'))
    fireEvent.click(screen.getByTestId('candidates-clear-all-filters'))
    expect(latest).toMatchObject({
      followUp: '',
      assessmentStatus: '',
      overviewCohort: '',
      position: 'ACCOUNTING_EXCEL',
    })
  })

  test('EN/AR RTL and AR clear-all label', () => {
    const { rerender } = renderCandidates({ locale: 'en' })
    expect(screen.getByTestId('unified-candidates-page')).toHaveAttribute('dir', 'ltr')
    rerender(
      <CandidatesPage
        applications={[]}
        assessmentEnabled
        busy={false}
        filters={{
          ...EMPTY_CANDIDATE_FILTERS,
          followUp: 'needed',
          position: 'ACCOUNTING_EXCEL',
        }}
        locale="ar"
        onLocale={() => undefined}
        onSaveView={async () => undefined}
        onSelect={() => undefined}
        onSelectSavedView={() => undefined}
        positions={[{ position_code: 'ACCOUNTING_EXCEL', position_title: 'Accounting', application_count: 0, active_count: 0 }]}
        query=""
        savedViews={[]}
        setFilters={() => undefined}
        setQuery={() => undefined}
        setStatus={() => undefined}
        status=""
      />,
    )
    expect(screen.getByTestId('unified-candidates-page')).toHaveAttribute('dir', 'rtl')
    expect(screen.getByTestId('candidate-filter-chip-followUp')).toHaveTextContent('يحتاج متابعة')
    expect(screen.getByTestId('candidates-clear-all-chips')).toHaveTextContent('مسح الكل')
  })

  test('saved views panel still available with active filters', () => {
    renderCandidates({ locale: 'en' })
    fireEvent.click(screen.getByRole('button', { name: /Save this view|Saved views/i }))
    expect(screen.getByTestId('candidates-save-view-panel')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ready view' })).toBeInTheDocument()
  })

  test('Filters (N) count matches specialist chips', () => {
    renderCandidates({
      locale: 'en',
      filters: {
        ...EMPTY_CANDIDATE_FILTERS,
        followUp: 'needed',
        sourceChannel: 'email',
        interviewStatus: 'scheduled',
      },
    })
    expect(screen.getByRole('button', { name: 'Filters (3)' })).toBeInTheDocument()
    expect(screen.getByTestId('candidates-active-filter-chips').querySelectorAll('[data-testid^="candidate-filter-chip-"]')).toHaveLength(3)
  })
})
