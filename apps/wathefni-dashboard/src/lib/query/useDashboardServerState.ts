import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'

import type { ClassificationFiltersState } from '@/components/candidates/ClassificationFilters'
import { classificationFiltersToQuery } from '@/components/candidates/ClassificationFilters'
import { candidateListStageFilterStatuses } from '@/lib/candidatesListPresentation'
import {
  useAllPositionsQuery,
  useApplicationsInfiniteQuery,
  useAssessmentConfigQuery,
  useAssessmentQueueInfiniteQuery,
  useAssessmentsQuery,
  useBootstrapQuery,
  useCandidateFeaturesQuery,
  useClearQueriesOnTenantChange,
  useInterviewsQuery,
  useJobsQuery,
  useNotificationsQuery,
  useReportsQuery,
  useSummaryQuery,
} from '@/lib/query/hooks'
import { invalidate } from '@/lib/query/invalidation'
import { accessReady } from '@/lib/query/fetchers'
import {
  dashboardPerfMarkCachedPaint,
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
  dashboardPerfMarkOverviewInteractive,
  dashboardPerfMarkPageVisit,
} from '@/lib/perf/dashboardPerf'
import type {
  ApplicationSummary,
  DashboardAccess,
  DashboardBootstrapResponse,
  SummaryResponse,
} from '@/types'

export type CandidateFilterSnapshot = {
  position: string
  cvStatus: string
  assessmentStatus: string
  interviewStatus: string
  followUp: string
  reviewStatus: string
  overviewCohort: string
  activityFrom: string
  activityTo: string
  sort: string
  view: string
  sourceChannel: string
  recruiterOwner: string
  cvProcessingState: string
  receivedFrom: string
  receivedTo: string
  hasGroundedEmail: string
  hasGroundedPhone: string
  factCompleteness: string
  departmentIntakeTag: string
}

type Page =
  | 'overview'
  | 'ai'
  | 'jobs'
  | 'candidates'
  | 'interviews'
  | 'calendar'
  | 'assessments'
  | 'ranking'
  | 'notifications'
  | 'reports'
  | string

function assessmentModuleEnabled(
  moduleState: { enabled_modules?: string[] } | null | undefined,
  summary: SummaryResponse | null | undefined,
) {
  if (Array.isArray(moduleState?.enabled_modules)) return moduleState.enabled_modules.includes('assessments')
  if (typeof summary?.features?.assessments_enabled === 'boolean') return summary.features.assessments_enabled
  return false
}

/** Single TanStack Query authority for dashboard server reads (Wave 3 page-gated). */
export function useDashboardServerState(opts: {
  access: DashboardAccess
  blocked: boolean
  page: Page
  query: string
  status: string
  candidateFilters: CandidateFilterSnapshot
  classificationFilters: ClassificationFiltersState
  debouncedJobsQuery: string
  jobsStatusFilter: string
  jobsDepartmentFilter: string
  jobsLocationFilter: string
  jobsDeadlineFilter: string
  jobsRemainingOnly: boolean
  interviewTab: string
  interviewQuery: string
  interviewRole: string
  interviewDate: string
  interviewInterviewer: string
  interviewOffset: number
  assessmentOffset: number
  assessmentCohort: string
  assessmentTab: string
  recruitingLocale?: 'en' | 'ar'
}) {
  const {
    access,
    blocked,
    page,
    query,
    status,
    candidateFilters,
    classificationFilters,
    debouncedJobsQuery,
    jobsStatusFilter,
    jobsDepartmentFilter,
    jobsLocationFilter,
    jobsDeadlineFilter,
    jobsRemainingOnly,
    interviewTab,
    interviewQuery,
    interviewRole,
    interviewDate,
    interviewInterviewer,
    interviewOffset,
    assessmentOffset,
    assessmentCohort,
    assessmentTab,
    recruitingLocale = 'en',
  } = opts

  const client = useQueryClient()
  useClearQueriesOnTenantChange(access)

  const ready = accessReady(access) && !blocked

  const bootstrapQuery = useBootstrapQuery(access, ready)
  const bootstrapSettled = bootstrapQuery.isFetched || bootstrapQuery.isError
  const workspaceBootstrap = (bootstrapQuery.data ?? null) as DashboardBootstrapResponse | null
  const bootstrapMissing = bootstrapQuery.data === null && bootstrapQuery.isSuccess
  const hasPrehire =
    !bootstrapSettled
      ? true
      : bootstrapMissing
        ? true
        : Boolean(workspaceBootstrap?.enabled_modules?.includes('pre_hiring'))

  const coreEnabled = ready && bootstrapSettled && hasPrehire
  const alertsOnly =
    ready && bootstrapSettled && !hasPrehire && Boolean(workspaceBootstrap)

  const summaryQuery = useSummaryQuery(access, coreEnabled)
  // Alerts stay on personal scope. My/Company work-queue scope lives in OverviewPage
  // so toggling does not re-render the App shell.
  const notificationsQuery = useNotificationsQuery(
    access,
    'mine',
    coreEnabled || alertsOnly,
  )

  const overviewInteractive = Boolean(
    (coreEnabled && summaryQuery.data && notificationsQuery.data)
    || (alertsOnly && notificationsQuery.data),
  )

  useEffect(() => {
    if (overviewInteractive) dashboardPerfMarkOverviewInteractive({ page: 'overview' })
  }, [overviewInteractive])

  useEffect(() => {
    if (!page) return
    const root = qkRoot(access)
    let cached = false
    if (page === 'jobs') cached = client.getQueryCache().findAll({ queryKey: [...root, 'jobs'] }).some((q) => q.state.data)
    else if (page === 'candidates') cached = client.getQueryCache().findAll({ queryKey: [...root, 'applications'] }).some((q) => q.state.data)
    else if (page === 'interviews') cached = client.getQueryCache().findAll({ queryKey: [...root, 'interviews'] }).some((q) => q.state.data)
    else if (page === 'assessments') cached = client.getQueryCache().findAll({ queryKey: [...root, 'assessments'] }).some((q) => q.state.data)
    else if (page === 'reports') cached = Boolean(client.getQueryData(reportsKey(access)))
    else if (page === 'calendar') cached = client.getQueryCache().findAll({ queryKey: [...root, 'calendar'] }).some((q) => q.state.data)
    dashboardPerfMarkPageVisit(String(page), cached)
  }, [access, client, page])

  const moduleState = workspaceBootstrap || summaryQuery.data || null
  const prehireOn = (() => {
    if (!hasPrehire) return false
    const mods = (moduleState as { enabled_modules?: string[] } | null)?.enabled_modules
    if (mods) return mods.includes('pre_hiring')
    return Boolean(summaryQuery.data)
  })()

  const assessmentsOn = assessmentModuleEnabled(moduleState, summaryQuery.data)

  // Wave 3: assessment config only when Assessments is open (not Overview warm).
  const assessmentConfigQuery = useAssessmentConfigQuery(
    access,
    ready && prehireOn && assessmentsOn && page === 'assessments',
  )

  // Page-gated heavy lists — no Overview background warm.
  const appsEnabled = ready && prehireOn && page === 'candidates'
  const features = useCandidateFeaturesQuery(access, appsEnabled)
  const unifiedOn = Boolean(features.unified.data?.enabled_for_company)
  const classificationOn = Boolean(
    features.classification.data?.enabled_for_company && features.classification.data?.ui_enabled,
  )

  const applicationParams = useMemo(() => {
    const classificationQuery =
      unifiedOn && classificationOn ? classificationFiltersToQuery(classificationFilters) : {}
    // Stage toolbar values expand to display-bucket aliases (e.g. New → awaiting_cv + screening…).
    const stageStatuses = candidateListStageFilterStatuses(status)
    return {
      q: query,
      status: stageStatuses.length ? stageStatuses.join(',') : '',
      position: candidateFilters.position,
      cv_status: candidateFilters.cvStatus,
      assessment_status: candidateFilters.assessmentStatus,
      interview_status: candidateFilters.interviewStatus,
      follow_up: candidateFilters.followUp,
      review_status: candidateFilters.reviewStatus,
      overview_cohort: candidateFilters.overviewCohort,
      activity_from: candidateFilters.activityFrom,
      activity_to: candidateFilters.activityTo,
      sort: candidateFilters.sort,
      ...(unifiedOn
        ? {
            view: candidateFilters.view || 'all',
            source_channel: candidateFilters.sourceChannel,
            recruiter_owner: candidateFilters.recruiterOwner,
            cv_processing_state: candidateFilters.cvProcessingState,
            received_from: candidateFilters.receivedFrom,
            received_to: candidateFilters.receivedTo,
            has_grounded_email: candidateFilters.hasGroundedEmail,
            has_grounded_phone: candidateFilters.hasGroundedPhone,
            fact_completeness: candidateFilters.factCompleteness,
            department_intake_tag: candidateFilters.departmentIntakeTag,
            ...classificationQuery,
          }
        : {}),
    }
  }, [candidateFilters, classificationFilters, classificationOn, query, status, unifiedOn])

  const featuresReady =
    !appsEnabled
    || (features.unified.isFetched && features.classification.isFetched)

  const applicationsQuery = useApplicationsInfiniteQuery(
    access,
    applicationParams,
    appsEnabled && featuresReady,
  )

  const candidatesListPending =
    appsEnabled && (!featuresReady || (applicationsQuery.isPending && !applicationsQuery.data))

  useEffect(() => {
    if (!appsEnabled) return
    dashboardPerfMarkInteractionStart('candidates_list', { page: 'candidates' })
    if (applicationsQuery.applications.applications.length && applicationsQuery.isFetching) {
      dashboardPerfMarkCachedPaint('candidates_list', { fromCache: true })
    }
    if (applicationsQuery.isFetched && !applicationsQuery.isFetching) {
      dashboardPerfMarkNetworkComplete('candidates_list', {
        pages: applicationsQuery.data?.pages.length || 0,
        rows: applicationsQuery.applications.applications.length,
      })
    }
  }, [
    appsEnabled,
    applicationsQuery.applications.applications.length,
    applicationsQuery.data?.pages.length,
    applicationsQuery.isFetched,
    applicationsQuery.isFetching,
  ])

  const jobsEnabled = ready && prehireOn && page === 'jobs'
  const jobsQuery = useJobsQuery(
    access,
    {
      ...(debouncedJobsQuery ? { search: debouncedJobsQuery } : {}),
      ...(jobsStatusFilter ? { status: jobsStatusFilter } : {}),
      ...(jobsDepartmentFilter ? { department: jobsDepartmentFilter } : {}),
      ...(jobsLocationFilter ? { location: jobsLocationFilter } : {}),
      ...(jobsDeadlineFilter ? { deadline: jobsDeadlineFilter } : {}),
      ...(jobsRemainingOnly ? { has_remaining_vacancies: true } : {}),
    },
    jobsEnabled,
  )

  // Selector roster: only surfaces that need a full unfiltered job list.
  const selectorPages = page === 'candidates' || page === 'ranking' || page === 'assessments'
  const allPositionsQuery = useAllPositionsQuery(access, ready && prehireOn && selectorPages)

  // When Jobs page is open with no filters, reuse first jobs page as selector fallback
  // so we don't also hit positions-all unless another page needs it.
  const allPositions =
    allPositionsQuery.data?.positions
    || (page === 'jobs' && !debouncedJobsQuery && !jobsStatusFilter && !jobsDepartmentFilter && !jobsLocationFilter && !jobsDeadlineFilter && !jobsRemainingOnly
      ? jobsQuery.data?.positions || []
      : [])

  const interviewsEnabled = ready && prehireOn && page === 'interviews'
  const interviewsQuery = useInterviewsQuery(
    access,
    {
      status: interviewTab || 'upcoming',
      q: interviewQuery || undefined,
      role: interviewRole || undefined,
      date: interviewDate || undefined,
      interviewer: interviewInterviewer || undefined,
      offset: interviewOffset,
      limit: 25,
    },
    interviewsEnabled,
  )

  const assessmentsEnabled = ready && prehireOn && assessmentsOn && page === 'assessments'
  const assessmentAttemptFilter =
    assessmentTab === 'reports'
      ? { status: 'completed' as const }
      : assessmentTab === 'needs_review'
        ? { needs_review: true as const }
        : {}
  const assessmentsQuery = useAssessmentsQuery(access, assessmentOffset, assessmentsEnabled, assessmentAttemptFilter)
  const assessmentQueueQuery = useAssessmentQueueInfiniteQuery(
    access,
    assessmentCohort,
    assessmentsEnabled && Boolean(assessmentCohort),
  )

  const reportsQuery = useReportsQuery(access, ready && prehireOn && page === 'reports', recruitingLocale)

  return {
    client,
    workspaceBootstrap: bootstrapMissing ? null : workspaceBootstrap,
    bootstrapLoading: ready && !bootstrapSettled,
    bootstrapSettled,
    bootstrapQuery,
    summary: summaryQuery.data ?? null,
    summaryQuery,
    notifications: notificationsQuery.data ?? null,
    notificationsQuery,
    assessmentConfig: assessmentConfigQuery.data ?? null,
    applications: applicationsQuery.applications,
    applicationsQuery,
    candidatesListPending,
    candidatesRefreshing: applicationsQuery.isFetching && Boolean(applicationsQuery.data),
    candidatesHasMore: Boolean(applicationsQuery.hasNextPage),
    candidatesFetchingMore: applicationsQuery.isFetchingNextPage,
    loadMoreCandidates: () => applicationsQuery.fetchNextPage(),
    featuresReady,
    unifiedCandidatesEnabled: unifiedOn,
    classificationUiEnabled: classificationOn,
    classificationDimensions: features.taxonomy.data?.dimensions || [],
    savedViews: features.views.data?.views || [],
    jobsData: jobsQuery.data ?? null,
    jobsQuery,
    jobsLoading: jobsQuery.isPending && !jobsQuery.data,
    jobsRefreshing: jobsQuery.isFetching && Boolean(jobsQuery.data),
    allPositions,
    interviews: interviewsQuery.data ?? null,
    interviewsQuery,
    interviewsLoading: interviewsQuery.isPending && !interviewsQuery.data,
    interviewsError: interviewsQuery.isError && !interviewsQuery.data,
    interviewsRefreshing: interviewsQuery.isFetching && Boolean(interviewsQuery.data),
    assessments: assessmentsQuery.data ?? null,
    assessmentsQuery,
    assessmentsRefreshing: assessmentsQuery.isFetching && Boolean(assessmentsQuery.data),
    assessmentQueueApps: assessmentQueueQuery.applications,
    assessmentQueueTotal: assessmentQueueQuery.total,
    assessmentQueueQuery,
    assessmentQueueHasMore: Boolean(assessmentQueueQuery.hasNextPage),
    assessmentQueueFetchingMore: assessmentQueueQuery.isFetchingNextPage,
    loadMoreAssessmentQueue: () => assessmentQueueQuery.fetchNextPage(),
    reports: reportsQuery.data ?? null,
    reportsQuery,
    reportsRefreshing: reportsQuery.isFetching && Boolean(reportsQuery.data),
    reportsError: reportsQuery.isError && !reportsQuery.data,
    overviewInteractive,
    prehireEnabled: prehireOn,
    coreEnabled,
    hasPrehire,
    invalidate,
    refreshOverviewCore: () => invalidate.overviewCore(client, access),
    refreshApplications: () => invalidate.applications(client, access),
    refreshJobs: () => invalidate.jobs(client, access),
    refreshInterviews: () => invalidate.interviews(client, access),
    refreshAssessments: () => invalidate.assessments(client, access),
    refreshReports: () => invalidate.reports(client, access),
    refreshAfterCandidate: (appKey?: string) => invalidate.afterCandidateAction(client, access, appKey),
    refreshAfterInterview: (appKey?: string) => invalidate.afterInterviewAction(client, access, appKey),
    refreshAfterJob: () => invalidate.afterJobAction(client, access),
    refreshAllTenant: () => invalidate.allTenant(client, access),
  }
}

function qkRoot(access: DashboardAccess) {
  const company = String(access.companyCode || '').trim().toUpperCase() || 'UNKNOWN'
  const actor = String(access.email || access.hrPhone || access.token.slice(0, 12) || 'anon').trim().toLowerCase()
  return ['wathefni', company, actor] as const
}

function reportsKey(access: DashboardAccess) {
  return [...qkRoot(access), 'reports'] as const
}

export type DashboardServerState = ReturnType<typeof useDashboardServerState>

export function syncSelectedApplication(
  selected: ApplicationSummary | null,
  applications: ApplicationSummary[] | undefined,
): ApplicationSummary | null {
  if (!selected) return null
  return applications?.find((item) => item.app_key === selected.app_key) || selected
}
