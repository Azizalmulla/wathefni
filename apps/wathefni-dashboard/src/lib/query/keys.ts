import type { DashboardAccess } from '@/types'

/** Tenant-safe root. Every dashboard query key must start with this. */
export function tenantRoot(access: DashboardAccess) {
  const company = String(access.companyCode || '').trim().toUpperCase() || 'UNKNOWN'
  // Actor segment prevents cross-user cache bleed within the same company SPA session.
  const actor = String(access.email || access.hrPhone || access.token.slice(0, 12) || 'anon').trim().toLowerCase()
  return ['wathefni', company, actor] as const
}

export const qk = {
  root: (access: DashboardAccess) => tenantRoot(access),

  bootstrap: (access: DashboardAccess) => [...tenantRoot(access), 'bootstrap'] as const,
  summary: (access: DashboardAccess) => [...tenantRoot(access), 'summary'] as const,
  assessmentConfig: (access: DashboardAccess) => [...tenantRoot(access), 'assessment-config'] as const,

  workQueue: (access: DashboardAccess, scope: 'mine' | 'company' | 'attention') =>
    [...tenantRoot(access), 'workspace-work', scope === 'company' ? 'attention' : scope] as const,
  notifications: (access: DashboardAccess, scope: 'mine' | 'company') =>
    [...tenantRoot(access), 'notifications', scope] as const,

  reports: (access: DashboardAccess, locale = 'en') => [...tenantRoot(access), 'reports', locale] as const,

  applications: (access: DashboardAccess, filtersKey: string) =>
    [...tenantRoot(access), 'applications', 'infinite', filtersKey] as const,
  candidateProfile: (access: DashboardAccess, appKey: string) =>
    [...tenantRoot(access), 'candidate-profile', appKey] as const,
  candidateFeature: (access: DashboardAccess) => [...tenantRoot(access), 'candidates-feature'] as const,
  classificationFeature: (access: DashboardAccess) => [...tenantRoot(access), 'classification-feature'] as const,
  classificationTaxonomy: (access: DashboardAccess) => [...tenantRoot(access), 'classification-taxonomy'] as const,
  savedViews: (access: DashboardAccess) => [...tenantRoot(access), 'candidate-saved-views'] as const,

  jobs: (access: DashboardAccess, filtersKey: string) => [...tenantRoot(access), 'jobs', filtersKey] as const,
  allPositions: (access: DashboardAccess) => [...tenantRoot(access), 'positions-all'] as const,

  interviews: (access: DashboardAccess, filtersKey: string) =>
    [...tenantRoot(access), 'interviews', filtersKey] as const,

  assessments: (access: DashboardAccess, offset: number, filterKey = 'all') =>
    [...tenantRoot(access), 'assessments', filterKey, offset] as const,
  assessmentQueue: (access: DashboardAccess, cohort: string) =>
    [...tenantRoot(access), 'assessment-queue', 'infinite', cohort] as const,
  assessmentReport: (access: DashboardAccess, attemptId: string) =>
    [...tenantRoot(access), 'assessment-report', attemptId] as const,

  calendarOverview: (access: DashboardAccess, scope: 'mine' | 'company') =>
    [...tenantRoot(access), 'calendar', 'overview', scope] as const,
  calendarEvents: (
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
  ) => [...tenantRoot(access), 'calendar', 'events', params] as const,
  calendarTeamScopes: (access: DashboardAccess) => [...tenantRoot(access), 'calendar', 'team-scopes'] as const,
  calendarEvent: (access: DashboardAccess, eventId: string) =>
    [...tenantRoot(access), 'calendar', 'event', eventId] as const,
  calendarEventSync: (access: DashboardAccess, eventId: string) =>
    [...tenantRoot(access), 'calendar', 'event-sync', eventId] as const,
  calendarReschedule: (access: DashboardAccess, eventId: string) =>
    [...tenantRoot(access), 'calendar', 'reschedule', eventId] as const,
  calendarSyncConnections: (access: DashboardAccess) =>
    [...tenantRoot(access), 'calendar', 'sync-connections'] as const,

  actionInbox: (access: DashboardAccess) => [...tenantRoot(access), 'action-inbox'] as const,
  intelligenceOverview: (access: DashboardAccess, lang: string) =>
    [...tenantRoot(access), 'intelligence-overview', lang] as const,

  employeeBankReview: (access: DashboardAccess, employeeKey: string, locale: string) =>
    [...tenantRoot(access), 'employee-bank-review', employeeKey, locale] as const,
}

export function stableFiltersKey(value: unknown): string {
  try {
    return JSON.stringify(value ?? null)
  } catch {
    return String(value)
  }
}
