export type CandidateNavFilterState = {
  position?: string
  followUp?: string
  reviewStatus?: string
  assessmentStatus?: string
  interviewStatus?: string
  sort?: string
  view?: string
  cvStatus?: string
  sourceChannel?: string
  recruiterOwner?: string
  cvProcessingState?: string
  receivedFrom?: string
  receivedTo?: string
  activityFrom?: string
  activityTo?: string
  hasGroundedEmail?: string
  hasGroundedPhone?: string
  factCompleteness?: string
  departmentIntakeTag?: string
}

export type DashboardNavFilters = {
  q?: string
  status?: string
  view?: string
  follow_up?: string
  review_status?: string
  assessment_status?: string
  assessment_cohort?: string
  interview_status?: string
  position?: string
  position_code?: string
  sort?: string
  overview_cohort?: string
  tab?: string
  role?: string
  date?: string
  date_end?: string
  interviewer?: string
  action?: string
  cohort_key?: string
  department?: string
  onboarding?: string
  employee?: string
  cv_status?: string
  source_channel?: string
  recruiter_owner?: string
  cv_processing_state?: string
  received_from?: string
  received_to?: string
  activity_from?: string
  activity_to?: string
  has_grounded_email?: string
  has_grounded_phone?: string
  fact_completeness?: string
  department_intake_tag?: string
}

export type DashboardNavState = {
  page: string
  candidate?: string | null
  filters: DashboardNavFilters
  overviewScrollY?: number
}

/** Durable Candidates URL keys — every meaningful flat filter that affects list results or deep-link context. */
export const CANDIDATE_FILTER_KEYS = [
  'q',
  'status',
  'view',
  'follow_up',
  'review_status',
  'assessment_status',
  'assessment_cohort',
  'interview_status',
  'position',
  'sort',
  'overview_cohort',
  'action',
  'cohort_key',
  'cv_status',
  'source_channel',
  'recruiter_owner',
  'cv_processing_state',
  'received_from',
  'received_to',
  'activity_from',
  'activity_to',
  'has_grounded_email',
  'has_grounded_phone',
  'fact_completeness',
  'department_intake_tag',
] as const

const INTERVIEW_FILTER_KEYS = ['status', 'tab', 'role', 'date', 'interviewer', 'cohort_key', 'overview_cohort', 'q'] as const
const RANKING_FILTER_KEYS = ['position_code', 'cohort_key'] as const
const ASSESSMENT_FILTER_KEYS = ['assessment_cohort', 'overview_cohort', 'cohort_key', 'tab', 'action', 'q'] as const
const PEOPLE_FILTER_KEYS = ['q', 'status', 'view', 'tab', 'department', 'onboarding', 'employee'] as const

export function readDashboardNavState(search = typeof window !== 'undefined' ? window.location.search : ''): DashboardNavState {
  const params = new URLSearchParams(search)
  let page = String(params.get('page') || 'overview').trim() || 'overview'
  const candidate = String(params.get('candidate') || '').trim() || null
  const filters: DashboardNavFilters = {}
  for (const key of [...CANDIDATE_FILTER_KEYS, ...INTERVIEW_FILTER_KEYS, ...RANKING_FILTER_KEYS, ...ASSESSMENT_FILTER_KEYS, ...PEOPLE_FILTER_KEYS, 'date_end'] as const) {
    const value = String(params.get(key) || '').trim()
    if (value) filters[key as keyof DashboardNavFilters] = value
  }
  if (!filters.assessment_cohort && filters.overview_cohort?.startsWith('assessment_')) {
    filters.assessment_cohort = filters.overview_cohort
  }
  // Interview tab aliases — never promote into Candidates stage `status`.
  if (page === 'interviews') {
    if (!filters.status && filters.interview_status) filters.status = filters.interview_status
    if (!filters.tab && filters.status) filters.tab = filters.status
  }
  if (!filters.position && filters.position_code) filters.position = filters.position_code
  // Legacy Setup→Ops alias. There is no `migration-sync` page — open Employees Migration Sync.
  if (page === 'workforce' && !filters.tab) {
    const workforceTab = String(params.get('workforce') || '').trim()
    if (workforceTab) filters.tab = workforceTab
  }
  if (page === 'migration-sync') {
    page = 'employees'
    if (!filters.view) filters.view = 'migration'
  }
  const overviewScrollYRaw = params.get('overview_scroll')
  const overviewScrollY = overviewScrollYRaw != null && overviewScrollYRaw !== '' ? Number(overviewScrollYRaw) : undefined
  return {
    page,
    candidate,
    filters,
    overviewScrollY: Number.isFinite(overviewScrollY) ? overviewScrollY : undefined,
  }
}

export function buildDashboardSearchParams(
  state: DashboardNavState,
  currentSearch = typeof window !== 'undefined' ? window.location.search : '',
): URLSearchParams {
  const params = new URLSearchParams(currentSearch)
  for (const key of [
    'page',
    'candidate',
    'overview_scroll',
    'date_end',
    'employee',
    'department',
    'onboarding',
    'workforce',
    ...CANDIDATE_FILTER_KEYS,
    ...INTERVIEW_FILTER_KEYS,
    ...RANKING_FILTER_KEYS,
    ...ASSESSMENT_FILTER_KEYS,
  ]) {
    params.delete(key)
  }
  params.set('page', state.page)
  if (state.candidate) params.set('candidate', state.candidate)
  const filters = state.filters || {}
  if (state.page === 'candidates') {
    for (const key of CANDIDATE_FILTER_KEYS) {
      const value = String(filters[key as keyof DashboardNavFilters] || '').trim()
      if (value) params.set(key, value)
    }
  } else if (state.page === 'interviews') {
    for (const key of INTERVIEW_FILTER_KEYS) {
      const value = String(filters[key as keyof DashboardNavFilters] || '').trim()
      if (value) params.set(key, value)
    }
  } else if (state.page === 'ranking') {
    for (const key of RANKING_FILTER_KEYS) {
      const value = String(filters[key as keyof DashboardNavFilters] || '').trim()
      if (value) params.set(key, value)
    }
  } else if (state.page === 'assessments') {
    for (const key of ASSESSMENT_FILTER_KEYS) {
      const value = String(filters[key as keyof DashboardNavFilters] || '').trim()
      if (value) params.set(key, value)
    }
  } else if (state.page === 'employees') {
    const view = String(filters.view || '').trim()
    const q = String(filters.q || '').trim()
    const status = String(filters.status || '').trim()
    const department = String(filters.department || '').trim()
    const onboarding = String(filters.onboarding || '').trim()
    const employee = String(filters.employee || '').trim()
    if (view) params.set('view', view)
    if (q) params.set('q', q)
    if (status && status !== 'active') params.set('status', status)
    if (department) params.set('department', department)
    if (onboarding && onboarding !== 'any') params.set('onboarding', onboarding)
    if (employee) params.set('employee', employee)
  } else if (state.page === 'onboarding' || state.page === 'preboarding' || state.page === 'probation') {
    const q = String(filters.q || '').trim()
    const employee = String(filters.employee || '').trim()
    if (q) params.set('q', q)
    if (employee) params.set('employee', employee)
  } else if (state.page === 'leave' || state.page === 'payroll') {
    const view = String(filters.view || '').trim()
    if (view) params.set('view', view)
    if (state.page === 'leave') {
      const status = String(filters.status || '').trim()
      if (status) params.set('status', status)
    }
  } else if (state.page === 'jobs' || state.page === 'requisitions') {
    const status = String(filters.status || '').trim()
    const q = String(filters.q || '').trim()
    const tab = String(filters.tab || '').trim()
    if (status) params.set('status', status)
    if (q) params.set('q', q)
    if (state.page === 'requisitions' && tab) params.set('tab', tab)
  } else if (state.page === 'attendance' || state.page === 'calendar') {
    const date = String(filters.date || '').trim()
    const dateEnd = String(filters.date_end || '').trim()
    if (date) params.set('date', date)
    if (dateEnd) params.set('date_end', dateEnd)
  } else if (state.page === 'activity') {
    const q = String(filters.q || '').trim()
    const date = String(filters.date || '').trim()
    const dateEnd = String(filters.date_end || '').trim()
    const status = String(filters.status || '').trim()
    if (q) params.set('q', q)
    if (date) params.set('date', date)
    if (dateEnd) params.set('date_end', dateEnd)
    if (status && status !== 'all') params.set('status', status)
  } else if (
    state.page === 'analytics' ||
    state.page === 'employee-relations' ||
    state.page === 'engagement' ||
    state.page === 'compensation-planning'
  ) {
    const q = String(filters.q || '').trim()
    if (q) params.set('q', q)
  } else if (state.page === 'overview' && typeof state.overviewScrollY === 'number' && state.overviewScrollY > 0) {
    params.set('overview_scroll', String(Math.round(state.overviewScrollY)))
  }
  if (!['candidates', 'interviews', 'assessments'].includes(state.page)) {
    const tab = String(filters.tab || '').trim()
    if (tab) params.set('tab', tab)
  }
  return params
}

export function writeDashboardNavUrl(state: DashboardNavState, mode: 'push' | 'replace' = 'replace') {
  const params = buildDashboardSearchParams(state)
  const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
  const historyState = {
    page: state.page,
    candidate: state.candidate || null,
    filters: state.filters || {},
    overviewScrollY: state.overviewScrollY || 0,
  }
  if (mode === 'push') window.history.pushState(historyState, '', next)
  else window.history.replaceState(historyState, '', next)
}

export function candidateFiltersFromNav(filters: DashboardNavFilters): CandidateNavFilterState & { q?: string; status?: string } {
  return {
    q: filters.q || '',
    status: filters.status || '',
    position: filters.position || filters.position_code || '',
    followUp: filters.follow_up || '',
    reviewStatus: filters.review_status || '',
    assessmentStatus: filters.assessment_status || '',
    interviewStatus: filters.interview_status || '',
    sort: filters.sort || 'newest',
    view: filters.view || 'all',
    cvStatus: filters.cv_status || '',
    sourceChannel: filters.source_channel || '',
    recruiterOwner: filters.recruiter_owner || '',
    cvProcessingState: filters.cv_processing_state || '',
    receivedFrom: filters.received_from || '',
    receivedTo: filters.received_to || '',
    activityFrom: filters.activity_from || '',
    activityTo: filters.activity_to || '',
    hasGroundedEmail: filters.has_grounded_email || '',
    hasGroundedPhone: filters.has_grounded_phone || '',
    factCompleteness: filters.fact_completeness || '',
    departmentIntakeTag: filters.department_intake_tag || '',
  }
}

export function navFiltersFromCandidateState(input: {
  q?: string
  status?: string
  filters: CandidateNavFilterState
  overviewCohort?: string
  assessmentCohort?: string
  action?: string
  cohortKey?: string
}): DashboardNavFilters {
  const out: DashboardNavFilters = {}
  if (input.q) out.q = input.q
  if (input.status) out.status = input.status
  if (input.filters.position) out.position = input.filters.position
  if (input.filters.followUp) out.follow_up = input.filters.followUp
  if (input.filters.reviewStatus) out.review_status = input.filters.reviewStatus
  if (input.filters.assessmentStatus) out.assessment_status = input.filters.assessmentStatus
  if (input.filters.interviewStatus) out.interview_status = input.filters.interviewStatus
  if (input.filters.sort && input.filters.sort !== 'newest') out.sort = input.filters.sort
  if (input.filters.view && input.filters.view !== 'all') out.view = input.filters.view
  if (input.filters.cvStatus) out.cv_status = input.filters.cvStatus
  if (input.filters.sourceChannel) out.source_channel = input.filters.sourceChannel
  if (input.filters.recruiterOwner) out.recruiter_owner = input.filters.recruiterOwner
  if (input.filters.cvProcessingState) out.cv_processing_state = input.filters.cvProcessingState
  if (input.filters.receivedFrom) out.received_from = input.filters.receivedFrom
  if (input.filters.receivedTo) out.received_to = input.filters.receivedTo
  if (input.filters.activityFrom) out.activity_from = input.filters.activityFrom
  if (input.filters.activityTo) out.activity_to = input.filters.activityTo
  if (input.filters.hasGroundedEmail) out.has_grounded_email = input.filters.hasGroundedEmail
  if (input.filters.hasGroundedPhone) out.has_grounded_phone = input.filters.hasGroundedPhone
  if (input.filters.factCompleteness) out.fact_completeness = input.filters.factCompleteness
  if (input.filters.departmentIntakeTag) out.department_intake_tag = input.filters.departmentIntakeTag
  if (input.overviewCohort) out.overview_cohort = input.overviewCohort
  if (input.assessmentCohort) out.assessment_cohort = input.assessmentCohort
  if (input.action) out.action = input.action
  if (input.cohortKey) out.cohort_key = input.cohortKey
  return out
}

/** Remove Follow-up needed URL keys without touching unrelated filters. */
export function clearFollowUpNeededFromNavFilters(filters: DashboardNavFilters): DashboardNavFilters {
  const next = { ...filters }
  delete next.follow_up
  delete next.overview_cohort
  delete next.cohort_key
  delete next.action
  return next
}

export function destinationToNavState(
  destination: {
    page?: string
    filters?: Record<string, string>
    cohort_key?: string
  } | null | undefined,
  fallbackPage = 'overview',
): DashboardNavState {
  const page = String(destination?.page || fallbackPage)
  const raw = { ...(destination?.filters || {}) }
  const filters: DashboardNavFilters = { ...raw }
  if (destination?.cohort_key) filters.cohort_key = destination.cohort_key
  if (raw.position_code && !raw.position) filters.position = raw.position_code
  if (raw.overview_cohort) filters.overview_cohort = raw.overview_cohort
  let candidate: string | null = null
  if (page === 'candidates' && raw.q && String(raw.q).includes('-')) {
    candidate = String(raw.q)
  }
  if (page === 'interviews') {
    if (raw.status) {
      filters.status = raw.status
      filters.tab = raw.status
    }
    // Exact interview-debt cohort lives on Candidates via overview_cohort.
    if (raw.status === 'needs_scheduling' || filters.overview_cohort === 'interview_scheduling_debt') {
      return {
        page: 'candidates',
        candidate: null,
        filters: {
          overview_cohort: 'interview_scheduling_debt',
          cohort_key: filters.cohort_key || 'interview_scheduling_debt',
          interview_status: 'none',
        },
      }
    }
  }
  if (page === 'assessments') {
    const cohort = filters.assessment_cohort || filters.overview_cohort || filters.cohort_key || ''
    if (cohort) {
      filters.assessment_cohort = cohort
      filters.overview_cohort = cohort
      filters.cohort_key = cohort
    }
    if (!filters.tab && cohort) {
      if (cohort.includes('resend') || cohort.includes('expired')) filters.tab = 'resend'
      else if (cohort.includes('delivery_failed')) filters.tab = 'delivery_failed'
      else if (cohort.includes('in_progress')) filters.tab = 'in_progress'
      else if (cohort.includes('ready_to_send')) filters.tab = 'send'
      else if (cohort.includes('sent_pending')) filters.tab = 'sent_pending'
      else if (cohort.includes('completed')) filters.tab = 'completed'
      else filters.tab = 'send'
    }
  }
  return { page, candidate, filters }
}
