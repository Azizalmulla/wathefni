import { fireEvent, within } from '@testing-library/react'
import { screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { jobCapacityDisplay, JobsPage } from '@/pages/JobsPage'
import { renderWithProviders } from '@/test/render'
import type { PositionSummary, PositionsResponse } from '@/types'

function job(partial: Partial<PositionSummary> & Pick<PositionSummary, 'position_code'>): PositionSummary {
  return {
    position_code: partial.position_code,
    title: partial.title || partial.position_code,
    title_en: partial.title_en || partial.title || partial.position_code,
    title_ar: partial.title_ar,
    status: partial.status || 'open',
    department: partial.department,
    location: partial.location,
    application_count: partial.application_count ?? 0,
    active_count: partial.active_count ?? partial.application_count ?? 0,
    vacancies: partial.vacancies,
    remaining_vacancies: partial.remaining_vacancies,
    recruiter_name: partial.recruiter_name,
    recruiter_user_id: partial.recruiter_user_id,
    application_deadline: partial.application_deadline,
    apply_code: partial.apply_code,
  } as PositionSummary
}

function jobsPayload(positions: PositionSummary[], total = positions.length): PositionsResponse {
  return {
    company_code: 'WATHEFNI',
    positions,
    total_count: total,
    summary: {
      open_positions: positions.filter((p) => p.status === 'open').length,
      draft_positions: 0,
      paused_positions: 0,
      closed_positions: 0,
      total_applications: positions.reduce((n, p) => n + Number(p.application_count || 0), 0),
    },
  } as PositionsResponse
}

const baseProps = {
  canCreateJobs: true,
  deadlineFilter: '',
  departmentFilter: '',
  loadingMore: false,
  locationFilter: '',
  onAssistantCreate: vi.fn(),
  onCreate: vi.fn(),
  onDeadlineFilterChange: vi.fn(),
  onDepartmentFilterChange: vi.fn(),
  onLoadMore: vi.fn(),
  onLocaleChange: vi.fn(),
  onLocationFilterChange: vi.fn(),
  onQueryChange: vi.fn(),
  onRemainingOnlyChange: vi.fn(),
  onSelect: vi.fn(),
  onStatusFilterChange: vi.fn(),
  onViewCandidates: vi.fn(),
  query: '',
  remainingOnly: false,
  statusFilter: '',
}

describe('jobCapacityDisplay', () => {
  test('priority: vacancies, then overdue, then short deadline, else dash', () => {
    expect(
      jobCapacityDisplay(job({ position_code: 'A', vacancies: 2, remaining_vacancies: 1, application_deadline: '2020-01-01' }), 'en').text,
    ).toBe('1 remaining of 2')

    const overdue = jobCapacityDisplay(
      job({ position_code: 'B', application_deadline: '2020-01-01T00:00:00Z' }),
      'en',
    )
    expect(overdue.overdue).toBe(true)
    expect(overdue.text).toBe('Deadline overdue')

    const future = jobCapacityDisplay(
      job({ position_code: 'C', application_deadline: '2099-08-12T00:00:00Z' }),
      'en',
    )
    expect(future.overdue).toBe(false)
    expect(future.text).not.toBe('—')
    expect(future.text).not.toContain('remaining')

    expect(jobCapacityDisplay(job({ position_code: 'D' }), 'en').text).toBe('—')
  })
})

describe('JobsPage minimal desktop table', () => {
  test('desktop table has exactly the approved columns', () => {
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([
          job({
            position_code: 'ACC',
            title: 'Accounting Excel',
            department: 'Finance',
            location: 'Kuwait',
            application_count: 3,
            vacancies: 2,
            remaining_vacancies: 1,
            recruiter_name: 'Aziz',
          }),
        ])}
        locale="en"
      />,
    )

    const table = screen.getByTestId('jobs-desktop-table')
    const headers = within(table).getAllByRole('columnheader').map((el) => el.textContent?.trim())
    expect(headers).toEqual(['Job', 'Status', 'Applications', 'Capacity', 'Owner', 'Open'])
    expect(within(table).queryByText('APPLY code')).not.toBeInTheDocument()
    expect(within(table).queryByText('Age')).not.toBeInTheDocument()
    expect(screen.queryByText('Export')).not.toBeInTheDocument()
    expect(within(table).queryByRole('button', { name: 'Manage' })).not.toBeInTheDocument()
    expect(within(table).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  test('desktop row click opens Manage; applicants link stops propagation', () => {
    const onSelect = vi.fn()
    const onViewCandidates = vi.fn()
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([job({ position_code: 'ACC', title: 'Accounting Excel', application_count: 3 })])}
        locale="en"
        onSelect={onSelect}
        onViewCandidates={onViewCandidates}
      />,
    )

    const table = screen.getByTestId('jobs-desktop-table')
    fireEvent.click(within(table).getByRole('button', { name: 'Manage Accounting Excel' }))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ position_code: 'ACC' }))
    expect(onViewCandidates).not.toHaveBeenCalled()

    onSelect.mockClear()
    fireEvent.click(within(table).getByRole('button', { name: 'View candidates for Accounting Excel' }))
    expect(onViewCandidates).toHaveBeenCalledWith(expect.objectContaining({ position_code: 'ACC' }))
    expect(onSelect).not.toHaveBeenCalled()
  })

  test('keyboard accessibility: Enter and Space open Manage on desktop row', () => {
    const onSelect = vi.fn()
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([job({ position_code: 'SALES', title: 'Sales Lead', application_count: 0 })])}
        locale="en"
        onSelect={onSelect}
      />,
    )
    const row = within(screen.getByTestId('jobs-desktop-table')).getByRole('button', { name: 'Manage Sales Lead' })
    expect(row).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(row, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledTimes(1)
    onSelect.mockClear()
    fireEvent.keyDown(row, { key: ' ' })
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  test('status badge is not an interactive control', () => {
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([job({ position_code: 'ACC', title: 'Accounting', application_count: 1, status: 'open' })])}
        locale="en"
      />,
    )
    const table = screen.getByTestId('jobs-desktop-table')
    const statusCell = within(table).getByTestId('jobs-status-cell')
    expect(statusCell.textContent).toContain('Open')
    expect(statusCell.querySelector('button')).toBeNull()
  })

  test('desktop header and rows share the same grid template', () => {
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([job({ position_code: 'ACC', title: 'Accounting', application_count: 1 })])}
        locale="en"
      />,
    )
    const table = screen.getByTestId('jobs-desktop-table')
    const header = table.firstElementChild as HTMLElement
    const row = within(table).getByRole('button', { name: 'Manage Accounting' })
    expect(header.className).toContain('grid-cols-[minmax(260px,2.2fr)_120px_130px_180px_160px_32px]')
    expect(row.className).toContain('grid-cols-[minmax(260px,2.2fr)_120px_130px_180px_160px_32px]')
    expect(within(table).getAllByRole('columnheader')[0].className).toContain('tracking-[0.08em]')
  })

  test('mobile list remains present alongside desktop table', () => {
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([job({ position_code: 'ACC', title: 'Accounting', application_count: 2 })])}
        locale="en"
      />,
    )
    expect(screen.getByTestId('jobs-mobile-list')).toBeInTheDocument()
    expect(screen.getByTestId('jobs-desktop-table')).toBeInTheDocument()
  })

  test('loading, empty, filtered-empty states', () => {
    const { rerender } = renderWithProviders(
      <JobsPage {...baseProps} jobsData={null} loading locale="en" />,
    )
    expect(screen.getByLabelText('Loading…')).toBeInTheDocument()

    rerender(<JobsPage {...baseProps} jobsData={jobsPayload([])} locale="en" />)
    expect(screen.getByText('No job openings yet. Create a job to save a draft or publish.')).toBeInTheDocument()

    rerender(
      <JobsPage {...baseProps} jobsData={jobsPayload([])} locale="en" statusFilter="open" />,
    )
    expect(screen.getByText('No openings match these filters.')).toBeInTheDocument()
  })

  test('API failure shows error, not a fake empty jobs list', () => {
    renderWithProviders(
      <JobsPage {...baseProps} jobsData={null} listError locale="en" />,
    )
    expect(screen.getByTestId('jobs-list-error')).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No job openings yet/i)).not.toBeInTheDocument()
  })

  test('Arabic RTL desktop headers and capacity', () => {
    renderWithProviders(
      <JobsPage
        {...baseProps}
        jobsData={jobsPayload([
          job({
            position_code: 'ACC',
            title_ar: 'محاسبة',
            title: 'Accounting',
            application_count: 2,
            vacancies: 2,
            remaining_vacancies: 1,
          }),
        ])}
        locale="ar"
      />,
    )
    expect(screen.getByTestId('jobs-page')).toHaveAttribute('dir', 'rtl')
    const table = screen.getByTestId('jobs-desktop-table')
    expect(within(table).getByRole('columnheader', { name: 'الوظيفة' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'الحالة' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'الطلبات' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'السعة' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'المسؤول' })).toBeInTheDocument()
    expect(within(table).getByText('1 متبقي من 2')).toBeInTheDocument()
  })

  test('create permission disabled title', () => {
    renderWithProviders(
      <JobsPage {...baseProps} canCreateJobs={false} jobsData={jobsPayload([])} locale="en" />,
    )
    expect(screen.getByRole('button', { name: 'Create job' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Create job' })).toHaveAttribute(
      'title',
      'Creating job openings is disabled for your role',
    )
  })
})
