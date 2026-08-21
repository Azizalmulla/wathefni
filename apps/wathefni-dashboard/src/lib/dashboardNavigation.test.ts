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

  test('writes and restores enterprise workspace tabs', () => {
    const params = buildDashboardSearchParams({
      page: 'talent',
      candidate: null,
      filters: { tab: 'people' },
    })
    expect(params.get('page')).toBe('talent')
    expect(params.get('tab')).toBe('people')
    const nav = readDashboardNavState(`?${params.toString()}`)
    expect(nav.page).toBe('talent')
    expect(nav.filters.tab).toBe('people')
  })

  test('writes and restores Settings sections', () => {
    const params = buildDashboardSearchParams({
      page: 'settings',
      candidate: null,
      filters: { tab: 'team' },
    })
    expect(params.get('page')).toBe('settings')
    expect(params.get('tab')).toBe('team')
    const nav = readDashboardNavState(`?${params.toString()}`)
    expect(nav.filters.tab).toBe('team')
  })

  test('writes and restores Leave view', () => {
    const params = buildDashboardSearchParams({
      page: 'leave',
      candidate: null,
      filters: { view: 'history' },
    })
    expect(params.get('page')).toBe('leave')
    expect(params.get('view')).toBe('history')
    const nav = readDashboardNavState(`?${params.toString()}`)
    expect(nav.filters.view).toBe('history')
  })

  test('writes Leave history status, Attendance dates, and Payroll tabs', () => {
    const leave = buildDashboardSearchParams({
      page: 'leave',
      candidate: null,
      filters: { view: 'history', status: 'approved' },
    })
    expect(leave.get('view')).toBe('history')
    expect(leave.get('status')).toBe('approved')
    expect(readDashboardNavState(`?${leave.toString()}`).filters.status).toBe('approved')

    const attendance = buildDashboardSearchParams({
      page: 'attendance',
      candidate: null,
      filters: { date: '2026-08-01', date_end: '2026-08-07' },
    })
    expect(attendance.get('date')).toBe('2026-08-01')
    expect(attendance.get('date_end')).toBe('2026-08-07')
    const attendanceNav = readDashboardNavState(`?${attendance.toString()}`)
    expect(attendanceNav.filters.date).toBe('2026-08-01')
    expect(attendanceNav.filters.date_end).toBe('2026-08-07')

    const payroll = buildDashboardSearchParams({
      page: 'payroll',
      candidate: null,
      filters: { tab: 'records', view: 'close' },
    })
    expect(payroll.get('tab')).toBe('records')
    expect(payroll.get('view')).toBe('close')
    const payrollNav = readDashboardNavState(`?${payroll.toString()}`)
    expect(payrollNav.filters.tab).toBe('records')
    expect(payrollNav.filters.view).toBe('close')
  })

  test('writes People spine URL chrome (employee, directory filters, workforce alias)', () => {
    const employees = buildDashboardSearchParams({
      page: 'employees',
      candidate: null,
      filters: {
        q: 'aziz',
        status: 'left',
        department: 'Finance',
        onboarding: 'open',
        employee: 'WATHEFNI-AZIZ',
        view: 'migration',
      },
    })
    expect(employees.get('q')).toBe('aziz')
    expect(employees.get('status')).toBe('left')
    expect(employees.get('department')).toBe('Finance')
    expect(employees.get('onboarding')).toBe('open')
    expect(employees.get('employee')).toBe('WATHEFNI-AZIZ')
    expect(employees.get('view')).toBe('migration')
    const employeesNav = readDashboardNavState(`?${employees.toString()}`)
    expect(employeesNav.filters.employee).toBe('WATHEFNI-AZIZ')
    expect(employeesNav.filters.department).toBe('Finance')

    const activeDefault = buildDashboardSearchParams({
      page: 'employees',
      candidate: null,
      filters: { status: 'active' },
    })
    expect(activeDefault.get('status')).toBeNull()

    const onboarding = buildDashboardSearchParams({
      page: 'onboarding',
      candidate: null,
      filters: { tab: 'in_progress', employee: 'WATHEFNI-AZIZ', q: 'aziz' },
    })
    expect(onboarding.get('tab')).toBe('in_progress')
    expect(onboarding.get('employee')).toBe('WATHEFNI-AZIZ')
    expect(onboarding.get('q')).toBe('aziz')

    const workforceAlias = readDashboardNavState('?page=workforce&workforce=lifecycle')
    expect(workforceAlias.filters.tab).toBe('lifecycle')
  })

  test('enterprise flagship details write q without recruiting chrome', () => {
    const intelligence = buildDashboardSearchParams({
      page: 'analytics',
      candidate: null,
      filters: { q: 'workforce.headcount' },
    })
    expect(intelligence.get('page')).toBe('analytics')
    expect(intelligence.get('q')).toBe('workforce.headcount')

    const er = buildDashboardSearchParams({
      page: 'employee-relations',
      candidate: null,
      filters: { tab: 'detail', q: 'CASE-1' },
    })
    expect(er.get('tab')).toBe('detail')
    expect(er.get('q')).toBe('CASE-1')
  })
})
