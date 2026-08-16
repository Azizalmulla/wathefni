import {
  getApplications,
  getAssessmentConfig,
  getAssessmentReportPayload,
  getAssessments,
  getCalendarEvent,
  getCalendarEventSync,
  getCalendarEvents,
  getCalendarOverview,
  getCalendarRescheduleRequests,
  getCalendarSyncConnections,
  getCalendarTeamScopes,
  getCandidatePersonProfile,
  getCandidateSavedViews,
  getDashboardBootstrap,
  getInterviews,
  getNotifications,
  getPrehirePositions,
  getPrehireReports,
  getPrehireWorkQueue,
  getSummary,
  getTalentPoolClassificationFeature,
  getTalentPoolClassificationTaxonomy,
  getUnifiedCandidatesFeature,
  type CalendarEvent,
} from '@/lib/api'
import type {
  ApplicationSummary,
  ApplicationsResponse,
  DashboardAccess,
} from '@/types'
import { DashboardApiError } from '@/lib/api'

export function accessReady(access: DashboardAccess) {
  return Boolean(access.token?.trim() && access.companyCode?.trim())
}

export async function fetchSummary(access: DashboardAccess, signal?: AbortSignal) {
  return getSummary(access, { signal })
}

export async function fetchBootstrap(access: DashboardAccess, _signal?: AbortSignal) {
  try {
    return await getDashboardBootstrap(access)
  } catch (error) {
    if (error instanceof DashboardApiError && error.status === 404) return null
    throw error
  }
}

export async function fetchWorkQueue(
  access: DashboardAccess,
  scope: 'mine' | 'company',
  signal?: AbortSignal,
) {
  return getPrehireWorkQueue(access, { limit: 10, scope }, { signal })
}

export async function fetchNotifications(
  access: DashboardAccess,
  scope: 'mine' | 'company',
  signal?: AbortSignal,
) {
  return getNotifications(access, { limit: 25, scope }, { signal })
}

export async function fetchReports(
  access: DashboardAccess,
  signal?: AbortSignal,
  locale: string = 'en',
) {
  return getPrehireReports(access, { signal, locale })
}

export async function fetchAssessmentConfig(access: DashboardAccess, _signal?: AbortSignal) {
  return getAssessmentConfig(access)
}

export type ApplicationsQueryParams = Parameters<typeof getApplications>[1]

/** Wave 3: one server page only — never crawl up to 1000 for the first screen. */
export const APPLICATIONS_PAGE_SIZE = 100
export const ASSESSMENT_QUEUE_PAGE_SIZE = 50

export async function fetchApplicationsPage(
  access: DashboardAccess,
  params: ApplicationsQueryParams,
  signal?: AbortSignal,
): Promise<ApplicationsResponse> {
  const limit = Number(params?.limit || APPLICATIONS_PAGE_SIZE)
  const offset = Number(params?.offset || 0)
  return getApplications(access, { ...params, limit, offset }, { signal })
}

/** @deprecated Wave 3 — use fetchApplicationsPage / infinite query. Kept for emergency rollback only. */
export async function fetchApplicationsAggregated(
  access: DashboardAccess,
  params: ApplicationsQueryParams,
  signal?: AbortSignal,
): Promise<ApplicationsResponse> {
  return fetchApplicationsPage(access, { ...params, limit: APPLICATIONS_PAGE_SIZE, offset: 0 }, signal)
}

export async function fetchJobs(
  access: DashboardAccess,
  opts: Parameters<typeof getPrehirePositions>[1],
  signal?: AbortSignal,
) {
  return getPrehirePositions(access, { limit: 100, ...opts }, { signal })
}

export async function fetchAllPositions(access: DashboardAccess, signal?: AbortSignal) {
  return getPrehirePositions(access, { limit: 200 }, { signal })
}

export async function fetchInterviews(
  access: DashboardAccess,
  params: Parameters<typeof getInterviews>[1],
  signal?: AbortSignal,
) {
  return getInterviews(access, params, { signal })
}

export async function fetchAssessments(
  access: DashboardAccess,
  params: { limit?: number; offset?: number; status?: string; needs_review?: boolean },
  signal?: AbortSignal,
) {
  return getAssessments(access, params, { signal })
}

export async function fetchAssessmentQueuePage(
  access: DashboardAccess,
  cohort: string,
  offset = 0,
  signal?: AbortSignal,
): Promise<{ applications: ApplicationSummary[]; total: number; offset: number; limit: number }> {
  const limit = ASSESSMENT_QUEUE_PAGE_SIZE
  const batch = await getApplications(
    access,
    {
      overview_cohort: cohort,
      assessment_cohort: cohort,
      limit,
      offset,
      sort: 'newest',
    },
    { signal },
  )
  return {
    applications: batch.applications || [],
    total: Number(batch.total || 0),
    offset,
    limit,
  }
}

/** @deprecated Wave 3 — use fetchAssessmentQueuePage / infinite query. */
export async function fetchAssessmentQueue(
  access: DashboardAccess,
  cohort: string,
  signal?: AbortSignal,
): Promise<{ applications: ApplicationSummary[]; total: number }> {
  return fetchAssessmentQueuePage(access, cohort, 0, signal)
}

export async function fetchAssessmentReport(access: DashboardAccess, attemptId: string, signal?: AbortSignal) {
  return getAssessmentReportPayload(access, attemptId, { signal })
}

export async function fetchCandidatePersonProfile(access: DashboardAccess, appKey: string, signal?: AbortSignal) {
  return getCandidatePersonProfile(access, appKey, { signal })
}

export async function fetchCalendarOverview(
  access: DashboardAccess,
  scope: 'mine' | 'company',
  signal?: AbortSignal,
) {
  return getCalendarOverview(access, scope, { signal })
}

export async function fetchCalendarEvents(
  access: DashboardAccess,
  params: {
    start: string
    end: string
    scope?: string
    org_scope_id?: string
    event_type?: string
    status?: string
    mine_only?: boolean
  },
  signal?: AbortSignal,
) {
  return getCalendarEvents(access, params as any, { signal })
}

export async function fetchCalendarTeamScopes(access: DashboardAccess, signal?: AbortSignal) {
  return getCalendarTeamScopes(access, { signal })
}

export async function fetchCalendarEvent(access: DashboardAccess, eventId: string, signal?: AbortSignal) {
  return getCalendarEvent(access, eventId, { signal })
}

export async function fetchCalendarEventSync(access: DashboardAccess, eventId: string, signal?: AbortSignal) {
  return getCalendarEventSync(access, eventId, { signal })
}

export async function fetchCalendarReschedule(access: DashboardAccess, eventId: string, signal?: AbortSignal) {
  return getCalendarRescheduleRequests(access, { event_id: eventId, status: 'pending' }, { signal })
}

export async function fetchCalendarSyncConnections(access: DashboardAccess, _signal?: AbortSignal) {
  return getCalendarSyncConnections(access)
}

export async function fetchUnifiedCandidatesFeature(access: DashboardAccess) {
  return getUnifiedCandidatesFeature(access)
}

export async function fetchClassificationFeature(access: DashboardAccess) {
  return getTalentPoolClassificationFeature(access)
}

export async function fetchClassificationTaxonomy(access: DashboardAccess) {
  return getTalentPoolClassificationTaxonomy(access)
}

export async function fetchSavedViews(access: DashboardAccess) {
  return getCandidateSavedViews(access)
}

export type { CalendarEvent }
