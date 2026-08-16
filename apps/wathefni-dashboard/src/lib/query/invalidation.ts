import type { QueryClient } from '@tanstack/react-query'

import type { DashboardAccess } from '@/types'
import { qk, tenantRoot } from '@/lib/query/keys'

/** Narrow invalidation helpers — prefer these over dashboard-wide fan-out. */
export const invalidate = {
  allTenant(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: tenantRoot(access) })
  },

  overviewCore(client: QueryClient, access: DashboardAccess) {
    return Promise.all([
      client.invalidateQueries({ queryKey: qk.summary(access) }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'work-queue'] }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'notifications'] }),
    ])
  },

  workQueues(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: [...tenantRoot(access), 'work-queue'] })
  },

  applications(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: [...tenantRoot(access), 'applications'] })
  },

  candidateProfile(client: QueryClient, access: DashboardAccess, appKey?: string) {
    if (appKey) return client.invalidateQueries({ queryKey: qk.candidateProfile(access, appKey) })
    return client.invalidateQueries({ queryKey: [...tenantRoot(access), 'candidate-profile'] })
  },

  jobs(client: QueryClient, access: DashboardAccess) {
    return Promise.all([
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'jobs'] }),
      client.invalidateQueries({ queryKey: qk.allPositions(access) }),
    ])
  },

  interviews(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: [...tenantRoot(access), 'interviews'] })
  },

  assessments(client: QueryClient, access: DashboardAccess) {
    return Promise.all([
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'assessments'] }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'assessment-queue'] }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'assessment-report'] }),
    ])
  },

  reports(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: [...qk.root(access), 'reports'] })
  },

  calendarAll(client: QueryClient, access: DashboardAccess) {
    return client.invalidateQueries({ queryKey: [...tenantRoot(access), 'calendar'] })
  },

  calendarEvent(client: QueryClient, access: DashboardAccess, eventId: string) {
    return Promise.all([
      client.invalidateQueries({ queryKey: qk.calendarEvent(access, eventId) }),
      client.invalidateQueries({ queryKey: qk.calendarEventSync(access, eventId) }),
      client.invalidateQueries({ queryKey: qk.calendarReschedule(access, eventId) }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'calendar', 'events'] }),
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'calendar', 'overview'] }),
    ])
  },

  /** Candidate pipeline action: lists + queues + summary counts + optional profile. */
  afterCandidateAction(client: QueryClient, access: DashboardAccess, appKey?: string) {
    return Promise.all([
      invalidate.overviewCore(client, access),
      invalidate.applications(client, access),
      invalidate.assessments(client, access),
      invalidate.interviews(client, access),
      appKey ? invalidate.candidateProfile(client, access, appKey) : Promise.resolve(),
    ])
  },

  /** Interview mutation: interviews + candidate lists + calendar + overview counts. */
  afterInterviewAction(client: QueryClient, access: DashboardAccess, appKey?: string) {
    return Promise.all([
      // Active refetch so tab badges (status/feedback/video counts) refresh immediately.
      client.invalidateQueries({ queryKey: [...tenantRoot(access), 'interviews'], refetchType: 'active' }),
      invalidate.applications(client, access),
      invalidate.calendarAll(client, access),
      invalidate.overviewCore(client, access),
      appKey ? invalidate.candidateProfile(client, access, appKey) : Promise.resolve(),
    ])
  },

  /** Post-hire source changed a date that may be projected on Calendar. */
  afterPostHireProjectionTouch(client: QueryClient, access: DashboardAccess) {
    return invalidate.calendarAll(client, access)
  },

  /** Job mutation: jobs + selector roster only. */
  afterJobAction(client: QueryClient, access: DashboardAccess) {
    return invalidate.jobs(client, access)
  },
}
