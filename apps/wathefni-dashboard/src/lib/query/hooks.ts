import { useInfiniteQuery, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useEffect, useMemo, useRef } from 'react'

import type { DashboardAccess } from '@/types'
import { qk, stableFiltersKey } from '@/lib/query/keys'
import { FRESHNESS_MS, useVisibilityRefetchInterval } from '@/lib/query/freshness'
import {
  accessReady,
  APPLICATIONS_PAGE_SIZE,
  ASSESSMENT_QUEUE_PAGE_SIZE,
  fetchAllPositions,
  fetchApplicationsPage,
  fetchAssessmentConfig,
  fetchAssessmentQueuePage,
  fetchAssessmentReport,
  fetchAssessments,
  fetchBootstrap,
  fetchCalendarEvent,
  fetchCalendarEventSync,
  fetchCalendarEvents,
  fetchCalendarOverview,
  fetchCalendarReschedule,
  fetchCalendarSyncConnections,
  fetchCalendarTeamScopes,
  fetchCandidatePersonProfile,
  fetchClassificationFeature,
  fetchClassificationTaxonomy,
  fetchInterviews,
  fetchJobs,
  fetchNotifications,
  fetchReports,
  fetchSavedViews,
  fetchSummary,
  fetchUnifiedCandidatesFeature,
  fetchWorkQueue,
  fetchActionInbox,
  fetchIntelligenceOverview,
  type ApplicationsQueryParams,
} from '@/lib/query/fetchers'
import { dashboardPerfCountRequest } from '@/lib/perf/dashboardPerf'

export function useAccessReady(access: DashboardAccess) {
  return accessReady(access)
}

/** Drop cached tenant data when company changes (cross-tenant safety). */
export function useClearQueriesOnTenantChange(access: DashboardAccess) {
  const client = useQueryClient()
  const company = String(access.companyCode || '').trim().toUpperCase()
  const prevCompany = useRef<string | null>(null)
  useEffect(() => {
    if (prevCompany.current && prevCompany.current !== company) {
      client.clear()
    }
    prevCompany.current = company
  }, [client, company])
}

export function useSummaryQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.summary(access),
    queryFn: ({ signal }) => fetchSummary(access, signal),
    enabled: enabled && accessReady(access),
  })
}

export function useBootstrapQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.bootstrap(access),
    queryFn: ({ signal }) => fetchBootstrap(access, signal),
    enabled: enabled && accessReady(access),
    staleTime: 60_000,
  })
}

export function useWorkQueueQuery(access: DashboardAccess, scope: 'mine' | 'company' | 'attention', enabled = true) {
  // Opt out of client-default keepPreviousData: scope is part of the key.
  // Keeping the prior scope's rows makes My Work / Company Attention briefly wrong; opposite scope is prefetched instead.
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.workQueue, enabled)
  return useQuery({
    queryKey: qk.workQueue(access, scope),
    queryFn: ({ signal }) => fetchWorkQueue(access, scope, signal),
    enabled: enabled && accessReady(access),
    placeholderData: undefined,
    refetchInterval,
  })
}

export function useActionInboxQuery(access: DashboardAccess, enabled = true) {
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.actionInbox, enabled)
  return useQuery({
    queryKey: qk.actionInbox(access),
    queryFn: ({ signal }) => fetchActionInbox(access, signal),
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useIntelligenceOverviewQuery(access: DashboardAccess, lang: string, enabled = true) {
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.intelligenceOverview, enabled)
  return useQuery({
    queryKey: qk.intelligenceOverview(access, lang),
    queryFn: ({ signal }) => fetchIntelligenceOverview(access, lang, signal),
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useNotificationsQuery(access: DashboardAccess, scope: 'mine' | 'company', enabled = true) {
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.notifications, enabled)
  return useQuery({
    queryKey: qk.notifications(access, scope),
    queryFn: ({ signal }) => fetchNotifications(access, scope, signal),
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useReportsQuery(access: DashboardAccess, enabled = true, locale: string = 'en') {
  return useQuery({
    queryKey: qk.reports(access, locale),
    queryFn: ({ signal }) => fetchReports(access, signal, locale),
    enabled: enabled && accessReady(access),
  })
}

export function useAssessmentConfigQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.assessmentConfig(access),
    queryFn: ({ signal }) => fetchAssessmentConfig(access, signal),
    enabled: enabled && accessReady(access),
  })
}

export function useApplicationsInfiniteQuery(
  access: DashboardAccess,
  params: ApplicationsQueryParams,
  enabled = true,
) {
  const { limit: _limit, offset: _offset, ...filterParams } = params || {}
  const filtersKey = stableFiltersKey(filterParams)
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.applications, enabled)
  const query = useInfiniteQuery({
    queryKey: qk.applications(access, filtersKey),
    queryFn: async ({ pageParam, signal }) => {
      dashboardPerfCountRequest('applications')
      return fetchApplicationsPage(
        access,
        { ...filterParams, limit: APPLICATIONS_PAGE_SIZE, offset: pageParam },
        signal,
      )
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, page) => n + (page.applications?.length || 0), 0)
      const total = Number(lastPage.total || 0)
      if (!lastPage.applications?.length) return undefined
      if (loaded >= total) return undefined
      return loaded
    },
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })

  const applications = useMemo(() => {
    const rows = query.data?.pages.flatMap((page) => page.applications || []) || []
    const last = query.data?.pages[query.data.pages.length - 1]
    const total = Number(last?.total ?? rows.length)
    return {
      company_code: last?.company_code || access.companyCode,
      applications: rows,
      total,
      limit: APPLICATIONS_PAGE_SIZE,
      offset: 0,
    }
  }, [access.companyCode, query.data])

  return { ...query, applications }
}

/** @deprecated Prefer useApplicationsInfiniteQuery (Wave 3). */
export function useApplicationsQuery(
  access: DashboardAccess,
  params: ApplicationsQueryParams,
  enabled = true,
) {
  return useApplicationsInfiniteQuery(access, params, enabled)
}

export function useJobsQuery(
  access: DashboardAccess,
  opts: {
    search?: string
    status?: string
    department?: string
    location?: string
    deadline?: string
    has_remaining_vacancies?: boolean
  },
  enabled = true,
) {
  const filtersKey = stableFiltersKey(opts)
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.jobs, enabled)
  return useQuery({
    queryKey: qk.jobs(access, filtersKey),
    queryFn: ({ signal }) => {
      dashboardPerfCountRequest('jobs')
      return fetchJobs(access, opts, signal)
    },
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useAllPositionsQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.allPositions(access),
    queryFn: ({ signal }) => {
      dashboardPerfCountRequest('positions-all')
      return fetchAllPositions(access, signal)
    },
    enabled: enabled && accessReady(access),
    staleTime: 60_000,
  })
}

export function useInterviewsQuery(
  access: DashboardAccess,
  params: {
    status?: string
    q?: string
    role?: string
    date?: string
    interviewer?: string
    offset?: number
    limit?: number
  },
  enabled = true,
) {
  const filtersKey = stableFiltersKey(params)
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.interviews, enabled)
  return useQuery({
    queryKey: qk.interviews(access, filtersKey),
    queryFn: ({ signal }) => {
      dashboardPerfCountRequest('interviews')
      return fetchInterviews(access, params, signal)
    },
    enabled: enabled && accessReady(access),
    // Keep prior tab rows painted while filters refetch — avoids blanking the table
    // and slamming the detail drawer. Settled data still replaces badges/rows.
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useAssessmentsQuery(
  access: DashboardAccess,
  offset: number,
  enabled = true,
  filter: { status?: string; needs_review?: boolean } = {},
) {
  const filterKey = filter.needs_review
    ? 'needs_review'
    : filter.status
      ? `status:${filter.status}`
      : 'all'
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.assessments, enabled)
  return useQuery({
    queryKey: qk.assessments(access, offset, filterKey),
    queryFn: ({ signal }) => {
      dashboardPerfCountRequest('assessments')
      return fetchAssessments(
        access,
        {
          limit: 50,
          offset,
          status: filter.status,
          needs_review: filter.needs_review,
        },
        signal,
      )
    },
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useAssessmentQueueInfiniteQuery(access: DashboardAccess, cohort: string, enabled = true) {
  const query = useInfiniteQuery({
    queryKey: qk.assessmentQueue(access, cohort),
    queryFn: async ({ pageParam, signal }) => {
      dashboardPerfCountRequest('assessment-queue')
      return fetchAssessmentQueuePage(access, cohort, pageParam, signal)
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, page) => n + (page.applications?.length || 0), 0)
      if (!lastPage.applications?.length) return undefined
      if (loaded >= Number(lastPage.total || 0)) return undefined
      return loaded
    },
    enabled: enabled && accessReady(access) && Boolean(cohort),
    placeholderData: keepPreviousData,
  })

  const flat = useMemo(() => {
    const applications = query.data?.pages.flatMap((page) => page.applications || []) || []
    const total = Number(query.data?.pages[query.data.pages.length - 1]?.total ?? applications.length)
    return { applications, total, pageSize: ASSESSMENT_QUEUE_PAGE_SIZE }
  }, [query.data])

  return { ...query, ...flat }
}

/** @deprecated Prefer useAssessmentQueueInfiniteQuery (Wave 3). */
export function useAssessmentQueueQuery(access: DashboardAccess, cohort: string, enabled = true) {
  return useAssessmentQueueInfiniteQuery(access, cohort, enabled)
}

export function useAssessmentReportQuery(access: DashboardAccess, attemptId: string, enabled = true) {
  return useQuery({
    queryKey: qk.assessmentReport(access, attemptId),
    queryFn: ({ signal }) => fetchAssessmentReport(access, attemptId, signal),
    enabled: enabled && accessReady(access) && Boolean(attemptId),
  })
}

export function useCandidateProfileQuery(access: DashboardAccess, appKey: string, enabled = true) {
  return useQuery({
    queryKey: qk.candidateProfile(access, appKey),
    queryFn: ({ signal }) => fetchCandidatePersonProfile(access, appKey, signal),
    enabled: enabled && accessReady(access) && Boolean(appKey),
  })
}

export function useCalendarOverviewQuery(
  access: DashboardAccess,
  scope: 'mine' | 'company',
  enabled = true,
) {
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.calendarOverview, enabled)
  return useQuery({
    queryKey: qk.calendarOverview(access, scope),
    queryFn: ({ signal }) => fetchCalendarOverview(access, scope, signal),
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useCalendarEventsQuery(
  access: DashboardAccess,
  params: {
    start: string
    end: string
    scope: string
    orgScopeId?: string
    typeFilter?: string
    statusFilter?: string
    mineOnly?: boolean
  },
  enabled = true,
) {
  const refetchInterval = useVisibilityRefetchInterval(FRESHNESS_MS.calendarEvents, enabled)
  return useQuery({
    queryKey: qk.calendarEvents(access, params),
    queryFn: ({ signal }) =>
      fetchCalendarEvents(
        access,
        {
          start: params.start,
          end: params.end,
          scope: params.scope,
          org_scope_id: params.orgScopeId,
          event_type: params.typeFilter,
          status: params.statusFilter,
          mine_only: params.mineOnly,
        },
        signal,
      ),
    enabled: enabled && accessReady(access),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useCalendarTeamScopesQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.calendarTeamScopes(access),
    queryFn: ({ signal }) => fetchCalendarTeamScopes(access, signal),
    enabled: enabled && accessReady(access),
    staleTime: 60_000,
  })
}

export function useCalendarEventQuery(access: DashboardAccess, eventId: string, enabled = true) {
  return useQuery({
    queryKey: qk.calendarEvent(access, eventId),
    queryFn: ({ signal }) => fetchCalendarEvent(access, eventId, signal),
    enabled: enabled && accessReady(access) && Boolean(eventId),
    // Detail drawer mounts on selectedId — never soft-keep a prior event's payload.
    placeholderData: undefined,
  })
}

export function useCalendarEventSyncQuery(access: DashboardAccess, eventId: string, enabled = true) {
  return useQuery({
    queryKey: qk.calendarEventSync(access, eventId),
    queryFn: ({ signal }) => fetchCalendarEventSync(access, eventId, signal),
    enabled: enabled && accessReady(access) && Boolean(eventId),
    placeholderData: undefined,
  })
}

export function useCalendarRescheduleQuery(access: DashboardAccess, eventId: string, enabled = true) {
  return useQuery({
    queryKey: qk.calendarReschedule(access, eventId),
    queryFn: ({ signal }) => fetchCalendarReschedule(access, eventId, signal),
    enabled: enabled && accessReady(access) && Boolean(eventId),
    placeholderData: undefined,
  })
}

export function useCalendarSyncConnectionsQuery(access: DashboardAccess, enabled = true) {
  return useQuery({
    queryKey: qk.calendarSyncConnections(access),
    queryFn: ({ signal }) => fetchCalendarSyncConnections(access, signal),
    enabled: enabled && accessReady(access),
  })
}

export function useCandidateFeaturesQuery(access: DashboardAccess, enabled = true) {
  const unified = useQuery({
    queryKey: qk.candidateFeature(access),
    queryFn: () => fetchUnifiedCandidatesFeature(access),
    enabled: enabled && accessReady(access),
    staleTime: 60_000,
  })
  const classification = useQuery({
    queryKey: qk.classificationFeature(access),
    queryFn: () => fetchClassificationFeature(access),
    enabled: enabled && accessReady(access),
    staleTime: 60_000,
  })
  const taxonomy = useQuery({
    queryKey: qk.classificationTaxonomy(access),
    queryFn: () => fetchClassificationTaxonomy(access),
    enabled: enabled && accessReady(access) && Boolean(classification.data?.enabled_for_company && classification.data?.ui_enabled),
    staleTime: 60_000,
  })
  const views = useQuery({
    queryKey: qk.savedViews(access),
    queryFn: () => fetchSavedViews(access),
    enabled: enabled && accessReady(access) && Boolean(unified.data?.enabled_for_company),
    staleTime: 60_000,
  })
  return { unified, classification, taxonomy, views }
}

export function usePrefetchOppositeWorkScope(access: DashboardAccess, scope: 'mine' | 'company' | 'attention', enabled: boolean) {
  const client = useQueryClient()
  useEffect(() => {
    if (!enabled || !accessReady(access)) return
    const other = scope === 'mine' ? 'attention' : 'mine'
    const notifyScope = other === 'attention' ? 'company' : 'mine'
    const handle = window.setTimeout(() => {
      void client.prefetchQuery({
        queryKey: qk.workQueue(access, other),
        queryFn: ({ signal }) => fetchWorkQueue(access, other, signal),
      })
      void client.prefetchQuery({
        queryKey: qk.notifications(access, notifyScope),
        queryFn: ({ signal }) => fetchNotifications(access, notifyScope, signal),
      })
    }, 120)
    return () => window.clearTimeout(handle)
  }, [access, client, enabled, scope])
}
