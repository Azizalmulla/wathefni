import { screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { AssessmentsPage } from '@/pages/AssessmentsPage'
import { RankingPage } from '@/pages/RankingPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { renderWithProviders } from '@/test/render'
import type { DashboardAccess } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

describe('HR Web list failure states', () => {
  test('ranking request failure renders error, not an empty ranked list', () => {
    renderWithProviders(
      <RankingPage
        busy={false}
        locale="en"
        onSelect={vi.fn()}
        positions={[{ position_code: 'OPS', position_title: 'Ops', application_count: 0, active_count: 0 }]}
        rankPosition="OPS"
        ranking={null}
        rankingError
        runRanking={vi.fn()}
        setRankPosition={vi.fn()}
      />,
    )
    const state = screen.getByTestId('ranking-list-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No ranked candidates in the current result/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('ranking-previous')).not.toBeInTheDocument()
  })

  test('ranking refresh failure keeps previous cards only as non-authoritative previous results', () => {
    renderWithProviders(
      <RankingPage
        busy={false}
        locale="en"
        onSelect={vi.fn()}
        positions={[{ position_code: 'OPS', position_title: 'Ops', application_count: 0, active_count: 0 }]}
        rankPosition="OPS"
        ranking={{
          company_code: 'WATHEFNI',
          total_matching: 1,
          candidates: [{ app_key: 'app-1', phone: '96500000000', name: 'Prior Candidate' }],
        }}
        rankingError
        runRanking={vi.fn()}
        setRankPosition={vi.fn()}
      />,
    )
    const state = screen.getByTestId('ranking-list-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/previous, not a new ranking/i)
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.getByTestId('ranking-previous')).toBeInTheDocument()
    expect(screen.getByText('Prior Candidate')).toBeInTheDocument()
    expect(screen.queryByText(/In review order/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/No ranked candidates in the current result/i)).not.toBeInTheDocument()
  })

  test('assessment queue failure renders error, not an empty send queue', () => {
    renderWithProviders(
      <AssessmentsPage
        access={access}
        applications={[]}
        assessmentTab="send"
        locale="en"
        cohortKey="assessment_ready_to_send"
        canManageAssessments
        enabled
        config={null}
        attempts={[]}
        busy={false}
        limit={25}
        offset={0}
        total={0}
        onSelectCohort={vi.fn()}
        onSelectTab={vi.fn()}
        onOpenCandidate={vi.fn()}
        onOpenFollowUpCandidates={vi.fn()}
        onCancelAttempt={vi.fn()}
        onResendAttempt={vi.fn()}
        onReviewAttempt={vi.fn()}
        onRecalculateNorms={vi.fn()}
        onRefresh={vi.fn()}
        onSendAssessment={vi.fn()}
        onResendAssessment={vi.fn()}
        onSetOffset={vi.fn()}
        queueError
      />,
    )
    const state = screen.getByTestId('assessments-queue-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
    expect(screen.queryByText(/No candidates are ready for a first assessment send/i)).not.toBeInTheDocument()
  })

  test('reports request failure renders error, not an empty reports page', () => {
    renderWithProviders(
      <ReportsPage
        assessmentEnabled
        canExportReports
        locale="en"
        onExportAssessments={vi.fn()}
        onExportCandidates={vi.fn()}
        onExportFollowUps={vi.fn()}
        onExportDeliveryHistory={vi.fn()}
        onExportInterviews={vi.fn()}
        onExportRoles={vi.fn()}
        reports={null}
        reportsError
      />,
    )
    const state = screen.getByTestId('reports-page-state')
    expect(state).toHaveAttribute('role', 'alert')
    expect(state).toHaveTextContent(/not an empty result/i)
  })
})
