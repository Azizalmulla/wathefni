import { describe, expect, test } from 'vitest'

import {
  applyCandidateFilterUpdate,
  candidateFiltersFromSavedViewBlob,
  clearCandidateAdvancedFilters,
  clearFollowUpNeededContext,
  EMPTY_CANDIDATE_FILTERS,
} from './candidateFilterAuthority'
import {
  buildDashboardSearchParams,
  candidateFiltersFromNav,
  clearFollowUpNeededFromNavFilters,
  navFiltersFromCandidateState,
  readDashboardNavState,
} from './dashboardNavigation'

describe('candidateFilterAuthority', () => {
  test('clearing Follow-up needed drops follow_up + overview_cohort + cohort_key + action', () => {
    const current = {
      ...EMPTY_CANDIDATE_FILTERS,
      followUp: 'needed',
      overviewCohort: 'follow_up_needed',
      cohortKey: 'follow_up_needed',
      action: 'follow_up_failed_delivery',
      position: 'ACCOUNTING_EXCEL',
    }
    const cleared = applyCandidateFilterUpdate(current, 'followUp', '')
    expect(cleared.followUp).toBe('')
    expect(cleared.overviewCohort).toBe('')
    expect(cleared.cohortKey).toBe('')
    expect(cleared.action).toBe('')
    expect(cleared.position).toBe('ACCOUNTING_EXCEL')
  })

  test('clearing one filter does not remove unrelated filters', () => {
    const current = {
      ...EMPTY_CANDIDATE_FILTERS,
      position: 'ACCOUNTING_EXCEL',
      assessmentStatus: 'completed',
      interviewStatus: 'scheduled',
      sourceChannel: 'email',
      sort: 'last_activity',
    }
    const next = applyCandidateFilterUpdate(current, 'assessmentStatus', '')
    expect(next.assessmentStatus).toBe('')
    expect(next.position).toBe('ACCOUNTING_EXCEL')
    expect(next.interviewStatus).toBe('scheduled')
    expect(next.sourceChannel).toBe('email')
    expect(next.sort).toBe('last_activity')
  })

  test('changing a non-context filter clears overview cohort context only', () => {
    const current = {
      ...EMPTY_CANDIDATE_FILTERS,
      followUp: 'needed',
      overviewCohort: 'follow_up_needed',
      cohortKey: 'follow_up_needed',
      action: 'follow_up_failed_delivery',
    }
    const next = applyCandidateFilterUpdate(current, 'position', 'X')
    expect(next.followUp).toBe('needed')
    expect(next.overviewCohort).toBe('')
    expect(next.cohortKey).toBe('')
    expect(next.action).toBe('')
    expect(next.position).toBe('X')
  })

  test('clear advanced filters clears follow-up context and preserves position/view', () => {
    const current = {
      ...EMPTY_CANDIDATE_FILTERS,
      position: 'ACCOUNTING_EXCEL',
      view: 'talent_pool' as const,
      followUp: 'needed',
      overviewCohort: 'follow_up_needed',
      cohortKey: 'follow_up_needed',
      action: 'follow_up_failed_delivery',
      cvStatus: 'with_cv',
    }
    const cleared = clearCandidateAdvancedFilters(current)
    expect(cleared.position).toBe('ACCOUNTING_EXCEL')
    expect(cleared.view).toBe('talent_pool')
    expect(cleared.followUp).toBe('')
    expect(cleared.overviewCohort).toBe('')
    expect(cleared.cohortKey).toBe('')
    expect(cleared.action).toBe('')
    expect(cleared.cvStatus).toBe('')
  })

  test('saved view select replaces leftover follow-up instead of merging', () => {
    const prior = {
      ...EMPTY_CANDIDATE_FILTERS,
      followUp: 'needed',
      overviewCohort: 'follow_up_needed',
      cohortKey: 'follow_up_needed',
      action: 'follow_up_failed_delivery',
      position: 'OLD',
    }
    void prior
    const restored = candidateFiltersFromSavedViewBlob({
      query: 'sara',
      status: 'new',
      position: 'ACCOUNTING_EXCEL',
      view: 'talent_pool',
      sort: 'newest',
    })
    expect(restored.query).toBe('sara')
    expect(restored.status).toBe('new')
    expect(restored.filters.position).toBe('ACCOUNTING_EXCEL')
    expect(restored.filters.view).toBe('talent_pool')
    expect(restored.filters.followUp).toBe('')
    expect(restored.filters.overviewCohort).toBe('')
    expect(restored.filters.cohortKey).toBe('')
    expect(restored.filters.action).toBe('')
  })

  test('clearFollowUpNeededContext is idempotent on already-clear state', () => {
    expect(clearFollowUpNeededContext(EMPTY_CANDIDATE_FILTERS)).toEqual(EMPTY_CANDIDATE_FILTERS)
  })
})

describe('Candidates URL contract (Wave 3)', () => {
  test('round-trips meaningful flat filters through URL', () => {
    const written = buildDashboardSearchParams({
      page: 'candidates',
      candidate: null,
      filters: navFiltersFromCandidateState({
        q: 'sara',
        status: 'new',
        filters: {
          position: 'ACCOUNTING_EXCEL',
          followUp: 'needed',
          view: 'talent_pool',
          cvStatus: 'with_cv',
          sourceChannel: 'email',
          recruiterOwner: 'unassigned',
          cvProcessingState: 'ready',
          receivedFrom: '2026-07-01',
          receivedTo: '2026-07-31',
          assessmentStatus: 'completed',
          interviewStatus: 'scheduled',
          sort: 'last_activity',
        },
        overviewCohort: 'follow_up_needed',
        cohortKey: 'follow_up_needed',
        action: 'follow_up_failed_delivery',
      }),
    })
    expect(written.get('page')).toBe('candidates')
    expect(written.get('q')).toBe('sara')
    expect(written.get('status')).toBe('new')
    expect(written.get('view')).toBe('talent_pool')
    expect(written.get('position')).toBe('ACCOUNTING_EXCEL')
    expect(written.get('follow_up')).toBe('needed')
    expect(written.get('cv_status')).toBe('with_cv')
    expect(written.get('source_channel')).toBe('email')
    expect(written.get('recruiter_owner')).toBe('unassigned')
    expect(written.get('cv_processing_state')).toBe('ready')
    expect(written.get('received_from')).toBe('2026-07-01')
    expect(written.get('received_to')).toBe('2026-07-31')
    expect(written.get('assessment_status')).toBe('completed')
    expect(written.get('interview_status')).toBe('scheduled')
    expect(written.get('sort')).toBe('last_activity')
    expect(written.get('overview_cohort')).toBe('follow_up_needed')
    expect(written.get('cohort_key')).toBe('follow_up_needed')
    expect(written.get('action')).toBe('follow_up_failed_delivery')

    const nav = readDashboardNavState(`?${written.toString()}`)
    const mapped = candidateFiltersFromNav(nav.filters)
    expect(mapped.q).toBe('sara')
    expect(mapped.status).toBe('new')
    expect(mapped.view).toBe('talent_pool')
    expect(mapped.position).toBe('ACCOUNTING_EXCEL')
    expect(mapped.followUp).toBe('needed')
    expect(mapped.cvStatus).toBe('with_cv')
    expect(mapped.sourceChannel).toBe('email')
    expect(nav.filters.overview_cohort).toBe('follow_up_needed')
    expect(nav.filters.cohort_key).toBe('follow_up_needed')
    expect(nav.filters.action).toBe('follow_up_failed_delivery')
  })

  test('omits default view=all and sort=newest from shared URLs', () => {
    const params = buildDashboardSearchParams({
      page: 'candidates',
      candidate: null,
      filters: navFiltersFromCandidateState({
        filters: { sort: 'newest', view: 'all', position: 'X' },
      }),
    })
    expect(params.get('view')).toBeNull()
    expect(params.get('sort')).toBeNull()
    expect(params.get('position')).toBe('X')
  })

  test('clearing follow-up from nav filters preserves unrelated URL filters', () => {
    const before = navFiltersFromCandidateState({
      q: 'sara',
      status: 'new',
      filters: {
        position: 'ACCOUNTING_EXCEL',
        followUp: 'needed',
        assessmentStatus: 'completed',
        view: 'talent_pool',
      },
      overviewCohort: 'follow_up_needed',
      cohortKey: 'follow_up_needed',
      action: 'follow_up_failed_delivery',
    })
    const after = clearFollowUpNeededFromNavFilters(before)
    expect(after.follow_up).toBeUndefined()
    expect(after.overview_cohort).toBeUndefined()
    expect(after.cohort_key).toBeUndefined()
    expect(after.action).toBeUndefined()
    expect(after.q).toBe('sara')
    expect(after.status).toBe('new')
    expect(after.position).toBe('ACCOUNTING_EXCEL')
    expect(after.assessment_status).toBe('completed')
    expect(after.view).toBe('talent_pool')
  })

  test('candidates stage status is not promoted from interview_status', () => {
    const nav = readDashboardNavState(
      '?page=candidates&overview_cohort=interview_scheduling_debt&interview_status=none&cohort_key=interview_scheduling_debt',
    )
    expect(nav.filters.interview_status).toBe('none')
    expect(nav.filters.status).toBeUndefined()
  })

  test('shared follow-up URL reproduces the same durable keys after reload parse', () => {
    const shared =
      '?page=candidates&follow_up=needed&overview_cohort=follow_up_needed&cohort_key=follow_up_needed&position=ACCOUNTING_EXCEL'
    const first = readDashboardNavState(shared)
    const params = buildDashboardSearchParams({
      page: 'candidates',
      candidate: null,
      filters: {
        ...navFiltersFromCandidateState({
          filters: {
            followUp: first.filters.follow_up,
            position: first.filters.position,
          },
          overviewCohort: first.filters.overview_cohort,
          cohortKey: first.filters.cohort_key,
        }),
      },
    })
    const second = readDashboardNavState(`?${params.toString()}`)
    expect(second.filters.follow_up).toBe('needed')
    expect(second.filters.overview_cohort).toBe('follow_up_needed')
    expect(second.filters.cohort_key).toBe('follow_up_needed')
    expect(second.filters.position).toBe('ACCOUNTING_EXCEL')
  })
})
