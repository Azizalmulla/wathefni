import { describe, expect, test } from 'vitest'

import {
  buildDashboardSearchParams,
  candidateFiltersFromNav,
  destinationToNavState,
  navFiltersFromCandidateState,
  readDashboardNavState,
} from './dashboardNavigation'

describe('dashboardNavigation', () => {
  test('reads durable candidate cohort filters from URL', () => {
    const nav = readDashboardNavState(
      '?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&sort=newest',
    )
    expect(nav.page).toBe('candidates')
    expect(nav.filters.follow_up).toBe('needed')
    expect(nav.filters.overview_cohort).toBe('follow_up_needed')
    expect(candidateFiltersFromNav(nav.filters).followUp).toBe('needed')
  })

  test('writes candidate filters into search params', () => {
    const params = buildDashboardSearchParams({
      page: 'candidates',
      candidate: null,
      filters: navFiltersFromCandidateState({
        filters: { followUp: 'needed', sort: 'newest' },
        overviewCohort: 'follow_up_needed',
        cohortKey: 'follow_up_needed',
      }),
    })
    expect(params.get('page')).toBe('candidates')
    expect(params.get('follow_up')).toBe('needed')
    expect(params.get('overview_cohort')).toBe('follow_up_needed')
    expect(params.get('cohort_key')).toBe('follow_up_needed')
  })

  test('writes and restores stage + view for Candidates', () => {
    const params = buildDashboardSearchParams({
      page: 'candidates',
      candidate: null,
      filters: navFiltersFromCandidateState({
        status: 'new',
        filters: { view: 'talent_pool', position: 'X' },
      }),
    })
    expect(params.get('status')).toBe('new')
    expect(params.get('view')).toBe('talent_pool')
    const nav = readDashboardNavState(`?${params.toString()}`)
    expect(nav.filters.status).toBe('new')
    expect(candidateFiltersFromNav(nav.filters).view).toBe('talent_pool')
  })

  test('maps interview scheduling debt to candidates cohort', () => {
    const nav = destinationToNavState({
      page: 'interviews',
      filters: { status: 'needs_scheduling' },
      cohort_key: 'interview_scheduling_debt',
    })
    expect(nav.page).toBe('candidates')
    expect(nav.filters.overview_cohort).toBe('interview_scheduling_debt')
    expect(nav.filters.interview_status).toBe('none')
  })

  test('maps role destination with position and cohort', () => {
    const nav = destinationToNavState({
      page: 'candidates',
      filters: { position: 'ACCOUNTING_EXCEL', overview_cohort: 'role_active' },
      cohort_key: 'role_active:ACCOUNTING_EXCEL',
    })
    expect(nav.page).toBe('candidates')
    expect(nav.filters.position).toBe('ACCOUNTING_EXCEL')
    expect(nav.filters.cohort_key).toBe('role_active:ACCOUNTING_EXCEL')
  })

  test('person destination keeps candidate app_key', () => {
    const nav = destinationToNavState({
      page: 'candidates',
      filters: {
        follow_up: 'needed',
        q: '96597485758-WATHEFNI-ACCOUNTING_EXCEL',
        action: 'follow_up_failed_delivery',
      },
      cohort_key: 'follow_up_needed',
    })
    expect(nav.candidate).toBe('96597485758-WATHEFNI-ACCOUNTING_EXCEL')
  })

  test('overview scroll is restored from URL', () => {
    const nav = readDashboardNavState('?page=overview&overview_scroll=420')
    expect(nav.page).toBe('overview')
    expect(nav.overviewScrollY).toBe(420)
  })

  test('maps assessment resend cohort to Assessments action surface', () => {
    const nav = destinationToNavState({
      page: 'assessments',
      filters: {
        assessment_cohort: 'assessment_resend_needed',
        overview_cohort: 'assessment_resend_needed',
      },
      cohort_key: 'assessment_resend_needed',
    })
    expect(nav.page).toBe('assessments')
    expect(nav.filters.tab).toBe('resend')
    expect(nav.filters.assessment_cohort).toBe('assessment_resend_needed')
    const params = buildDashboardSearchParams(nav)
    expect(params.get('page')).toBe('assessments')
    expect(params.get('assessment_cohort')).toBe('assessment_resend_needed')
    expect(params.get('tab')).toBe('resend')
  })

  test('maps delivery failed and in-progress assessment cohorts', () => {
    const failed = destinationToNavState({
      page: 'assessments',
      filters: { assessment_cohort: 'assessment_delivery_failed' },
      cohort_key: 'assessment_delivery_failed',
    })
    expect(failed.filters.tab).toBe('delivery_failed')
    const progress = destinationToNavState({
      page: 'assessments',
      filters: { overview_cohort: 'assessment_in_progress' },
      cohort_key: 'assessment_in_progress',
    })
    expect(progress.filters.tab).toBe('in_progress')
    expect(progress.filters.assessment_cohort).toBe('assessment_in_progress')
  })

  test('legacy migration-sync deep link opens Employees Migration Sync', () => {
    const nav = readDashboardNavState('?page=migration-sync')
    expect(nav.page).toBe('employees')
    expect(nav.filters.view).toBe('migration')
    const params = buildDashboardSearchParams({
      page: 'employees',
      candidate: null,
      filters: { view: 'migration' },
    })
    expect(params.get('page')).toBe('employees')
    expect(params.get('view')).toBe('migration')
  })
})
