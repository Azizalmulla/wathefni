/**
 * OctoHR HR Web Surface Registry — Phase 1 census source of truth.
 *
 * Every authenticated HR Web destination must appear here (or in
 * HR_WEB_SURFACE_EXCLUSIONS with a documented reason). Coverage contracts
 * fail CI when a new Page / ?page= / workspace tab / Setup opsHref is added
 * without a registry row.
 *
 * This file is inventory + coverage, not a second capability authority.
 * Module entitlements and permissions still resolve through
 * `workspaceCapability.ts` → backend `workspace_capability.py`.
 */

import { POSTHIRE_NAV_PAGES } from '@/lib/moduleWorkspace'
import { WORKSPACE_SURFACES } from '@/lib/workspaceCapability'
import type { Page } from '@/types'

export type SurfaceKind =
  | 'page'
  | 'tab'
  | 'subtab'
  | 'detail'
  | 'drawer'
  | 'modal'
  | 'settings'
  | 'overview'
  | 'legacy'
  | 'setup'
  | 'notification'
  | 'auth'

export type UrlStateKind = 'page' | 'query' | 'hash' | 'local' | 'alias'

export type I18nStatus = 'en_ar' | 'partial' | 'en_only' | 'unknown'
export type RtlStatus = 'supported' | 'partial' | 'unknown'
export type ResponsiveStatus = 'shell' | 'partial' | 'unknown'

export type MigrationStatus =
  | 'canonical'
  | 'preserve'
  | 'consolidate'
  | 'orphan_sidebar'
  | 'broken_deeplink'
  | 'legacy_alias'
  | 'local_only_tab'
  | 'enterprise'
  | 'excluded'

export type HrWebSurface = {
  surface_id: string
  kind: SurfaceKind
  /** Deep link or route pattern. Local-only tabs still record the parent page URL. */
  route: string
  parent: string | null
  page: Page | string | null
  module: string | null
  permission: string | null
  permission_any_of?: string[]
  component: string
  api_authority: string
  i18n: I18nStatus
  rtl: RtlStatus
  responsive: ResponsiveStatus
  loading: boolean
  error: boolean
  empty: boolean
  url_state: UrlStateKind
  in_sidebar: boolean
  in_page_union: boolean
  in_capability: boolean
  migration_status: MigrationStatus
  notes?: string
}

export type HrWebExclusion = {
  id: string
  reason: string
  pattern: string
}

type PageDef = {
  page: Page
  module: string | null
  permission: string | null
  permission_any_of?: string[]
  component: string
  api_authority: string
  in_sidebar: boolean
  in_capability: boolean
  migration_status: MigrationStatus
  notes?: string
  i18n?: I18nStatus
}

const PAGE_DEFS: PageDef[] = [
  {
    page: 'overview',
    module: null,
    permission: null,
    permission_any_of: ['candidate.manage', 'jobs.create', 'report.export', 'leave.read', 'attendance.read', 'analytics.read', 'calendar.read'],
    component: 'OverviewPage',
    api_authority: 'composed: work-queue + action-inbox + intelligence/overview + calendar',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Module-composed company home. Recruiting bands hide when pre_hiring is off. Soft-keep on every band.',
  },
  {
    page: 'ai',
    module: 'pre_hiring',
    permission: null,
    permission_any_of: ['candidate.manage', 'jobs.create', 'report.export', 'leave.read', 'attendance.read'],
    component: 'AdminAIPage',
    api_authority: '/dashboard/assistant (chat) — never a second evaluator',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Chat consumer of canonical domain APIs — never a second evaluator or ranking path.',
  },
  {
    page: 'jobs',
    module: 'pre_hiring',
    permission: 'jobs.read',
    component: 'JobsPage + JobWorkspace',
    api_authority: '/dashboard/prehire/positions',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Openings inventory with status tiles. Search and status are URL-backed. Distinct from job architecture.',
  },
  {
    page: 'requisitions',
    module: 'requisitions',
    permission: 'requisitions.read',
    component: 'RequisitionsWorkspace',
    api_authority: '/dashboard/prehire/requisitions',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Headcount approval before jobs publish. Queue tab and selected requisition are URL-backed. SoD stays backend.',
  },
  {
    page: 'candidates',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'CandidatesPage + CandidateProfilePage',
    api_authority: '/dashboard/prehire/applications',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Saved views stay (all / with a job / no job / hired / archived / restricted). Distinct from talent_pool vs Talent Intelligence.',
  },
  {
    page: 'interviews',
    module: 'interviews',
    permission: 'prehire.read',
    component: 'InterviewsPage',
    api_authority: '/dashboard/prehire/interviews',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Also unlocked by video_interviews via moduleAnyOf. URL-backed tabs and interview states stay backend.',
  },
  {
    page: 'calendar',
    module: 'calendar',
    permission: 'calendar.read',
    component: 'CalendarShell',
    api_authority: '/dashboard/prehire/calendar',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Spatial board kept. Day/week/month and anchor date are URL-backed. Scope remains a local preference.',
  },
  {
    page: 'assessments',
    module: 'assessments',
    permission: 'assessment.manage',
    component: 'AssessmentsPage',
    api_authority: '/dashboard/prehire/assessments',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Assessment authority stays backend. Cached report paint preserved.',
  },
  {
    page: 'ranking',
    module: 'pre_hiring',
    permission: null,
    permission_any_of: ['candidate.manage', 'jobs.create', 'report.export'],
    component: 'RankingPage',
    api_authority: '/dashboard/prehire/ranking',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Evidence-based and explainable. Frontend displays backend ranking — it does not invent scores.',
  },
  {
    page: 'notifications',
    module: null,
    permission: null,
    permission_any_of: ['notifications.manage', 'settings.manage'],
    component: 'NotificationsPage',
    api_authority: '/dashboard/prehire/notifications',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 8 workspace. Alerts & Delivery. Visible when pre_hiring or any post-hire module is on. Filter (`?tab=`) is URL-backed. Delivery/channel authority stays backend-canonical.',
  },
  {
    page: 'reports',
    module: 'pre_hiring',
    permission: 'report.export',
    component: 'ReportsPage',
    api_authority: '/dashboard/prehire/reports',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 7 recruiting. Leadership snapshot and exports. Counts come from the reports API — the UI does not recompute funnel math.',
  },
  {
    page: 'employees',
    module: null,
    permission: 'employees.read',
    component: 'EmployeesPage (PostHire)',
    api_authority: '/dashboard/posthire/employees',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'People spine — Phase 5 UX migrated. Offerable when any people_surface module is on. Directory filters (`q`, `status`, `department`, `onboarding`) and `employee` 360 deep-link are URL-backed. `view=migration` is Migration Sync.',
  },
  {
    page: 'workforce',
    module: null,
    permission: 'employees.read',
    component: 'WorkforcePage',
    api_authority: '/dashboard/posthire/employees (org)',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'People spine — Phase 5 UX migrated. Structure is first paint; Advanced queues stay behind the toggle. `?tab=` (legacy `?workforce=` alias) is URL-backed.',
  },
  {
    page: 'inbox',
    module: null,
    permission: null,
    permission_any_of: ['analytics.read', 'compliance.read', 'employees.read'],
    component: 'ActionInboxPage',
    api_authority: '/dashboard/posthire/action-inbox',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Fail-closed on bootstrap action_inbox.offerable. Phase 5 UX migrated. Presentation filters are URL-backed (`?tab=`). Board title uses published `summary.total` when filter is All; does not invent a second approvals model.',
  },
  {
    page: 'preboarding',
    module: 'preboarding',
    permission: 'preboarding.read',
    component: 'PreboardingWorkspace',
    api_authority: '/dashboard/posthire/preboarding',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'People spine — Phase 5 UX migrated. Frozen preboarding authority unchanged. Status filter is URL-backed (`?tab=`); selected joiner uses `?employee=`.',
  },
  {
    page: 'onboarding',
    module: 'onboarding',
    permission: 'onboarding.read',
    component: 'OnboardingPage',
    api_authority: '/dashboard/posthire/onboarding',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'People spine — Phase 5 UX migrated. Queue-first. Filter is URL-backed (`?tab=`); checklist focus uses `?employee=`. Search uses `?q=`.',
  },
  {
    page: 'probation',
    module: 'probation',
    permission: 'probation.read',
    component: 'ProbationWorkspace',
    api_authority: '/dashboard/posthire/probation',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'People spine — Phase 5 UX migrated. Frozen probation authority unchanged. Status filter is URL-backed (`?tab=`); selected case uses `?employee=`.',
  },
  {
    page: 'attendance',
    module: 'attendance',
    permission: 'attendance.read',
    component: 'AttendancePage',
    api_authority: '/dashboard/posthire/attendance',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 4 UX migrated. Board range is URL-backed (`?date=` / `?date_end=`). Capture ops tabs stay local behind Operations.',
  },
  {
    page: 'leave',
    module: 'leave',
    permission: 'leave.read',
    component: 'LeavePage / LeaveWorkspace',
    api_authority: '/dashboard/posthire/leave',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 4 UX migrated. Active/history via `?view=`; history status via `?status=`. No frontend leave formulas.',
  },
  {
    page: 'performance',
    module: 'performance',
    permission: 'performance.read',
    component: 'PerformanceWorkspace',
    api_authority: '/dashboard/posthire/performance',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Flagship goals/reviews/calibration/development chrome. Backend remains progress, rollup, rating, and allowed_actions authority. No Talent vocabulary.',
  },
  {
    page: 'talent',
    module: 'talent',
    permission: 'talent.read',
    component: 'TalentWorkspace',
    api_authority: '/dashboard/posthire/talent',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Flagship profiles, succession, mobility, and derived 9-box visualization. No master talent score. Distinct from Performance and recruiting talent_pool.',
  },
  {
    page: 'learning',
    module: 'learning',
    permission: 'learning.read',
    component: 'LearningWorkspace',
    api_authority: '/dashboard/posthire/learning',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Catalog, assignments, sessions, certifications stay backend-authored. Learning completion does not close development plans.',
  },
  {
    page: 'benefits',
    module: 'benefits',
    permission: 'benefits.read',
    component: 'BenefitsWorkspace',
    api_authority: '/dashboard/posthire/benefits',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Plans, eligibility, enrollment, coverage, and contributions. Not claims and not payroll deductions.',
  },
  {
    page: 'employee-relations',
    module: 'employee_relations',
    permission: 'er.read',
    component: 'EmployeeRelationsWorkspace',
    api_authority: '/dashboard/posthire/employee-relations',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Case detail via `?tab=detail&q={case_id}`. Investigation/decision stay allowed_actions.',
  },
  {
    page: 'engagement',
    module: 'engagement',
    permission: null,
    permission_any_of: ['engagement.read', 'engagement.manager'],
    component: 'EngagementWorkspace',
    api_authority: '/dashboard/posthire/engagement',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Campaign results via `?tab=results&q={campaign_id}`. Suppression stays backend.',
  },
  {
    page: 'compensation-planning',
    module: 'comp_planning',
    permission: null,
    permission_any_of: ['comp_planning.read', 'comp_planning.manager'],
    component: 'CompensationPlanningWorkspace',
    api_authority: '/dashboard/posthire/comp-planning',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Worksheet via `?tab=worksheet&q={cycle_id}`. Amounts stay backend money authority.',
  },
  {
    page: 'workforce-planning',
    module: 'workforce_planning',
    permission: null,
    permission_any_of: ['workforce_planning.read', 'workforce_planning.manager'],
    component: 'WorkforcePlanningWorkspace',
    api_authority: '/dashboard/posthire/workforce-planning',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Demand, cost, scenarios, and execution remain backend-planned.',
  },
  {
    page: 'job-architecture',
    module: null,
    permission: 'job_architecture.read',
    component: 'JobArchitectureWorkspace',
    api_authority: '/dashboard/posthire/job-architecture',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. No dedicated module SKU; permission-gated. Catalog, grades, paths, mappings stay backend-authored. Not recruiting job descriptions.',
  },
  {
    page: 'shifts',
    module: 'shifts',
    permission: 'shifts.read',
    component: 'ShiftsPage / ShiftsWorkspace',
    api_authority: '/dashboard/posthire/shifts',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 4 UX migrated. Schedule / Requests / Planning via `?tab=`. Board range stays committed soft-keep.',
  },
  {
    page: 'payroll',
    module: 'payroll',
    permission: 'payroll.read',
    component: 'PayrollPage',
    api_authority: '/dashboard/posthire/payroll',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 4 UX migrated. Run / Hours / Records via `?tab=`; records panels via `?view=`. Backend remains money authority. Do not optimistic-mutate payroll.',
  },
  {
    page: 'analytics',
    module: 'analytics',
    permission: 'analytics.read',
    component: 'IntelligenceWorkspace (fallback AnalyticsPage)',
    api_authority: '/dashboard/intelligence + /dashboard/posthire/analytics',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 6 UX migrated. Governed KPI evaluate/trend/segment/drill remain backend. Freshness, suppression, and drill authority are not recomputed in the UI. Metric detail via `?q={semantic_key}`.',
  },
  {
    page: 'compliance',
    module: 'compliance',
    permission: 'compliance.read',
    component: 'CompliancePage',
    api_authority: '/dashboard/posthire/compliance',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
  },
  {
    page: 'activity',
    module: null,
    permission: 'audit.read',
    component: 'Activity (App.tsx)',
    api_authority: '/dashboard/audit',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 8 workspace. Immutable backend audit via /dashboard/audit. Search, date range, and result (`q`, `date`, `date_end`, `status`) are URL-backed. The UI displays backend events — it does not reinterpret them.',
  },
  {
    page: 'settings',
    module: null,
    permission: null,
    permission_any_of: ['settings.manage', 'users.manage'],
    component: 'SettingsPage',
    api_authority: '/dashboard/settings + /dashboard/users',
    in_sidebar: true,
    in_capability: true,
    migration_status: 'canonical',
    notes: 'Phase 8 workspace. Configuration-oriented Settings. Sections stay URL-backed via ?tab=. Advanced remains admin recovery/diagnostics — not merged into Integrations. Business configuration semantics unchanged.',
  },
]

function pageSurface(def: PageDef): HrWebSurface {
  return {
    surface_id: `page.${def.page}`,
    kind: 'page',
    route: `/dashboard?page=${def.page}`,
    parent: null,
    page: def.page,
    module: def.module,
    permission: def.permission,
    permission_any_of: def.permission_any_of,
    component: def.component,
    api_authority: def.api_authority,
    i18n: def.i18n || 'en_ar',
    rtl: 'supported',
    responsive: 'shell',
    loading: true,
    error: true,
    empty: true,
    url_state: 'page',
    in_sidebar: def.in_sidebar,
    in_page_union: true,
    in_capability: def.in_capability,
    migration_status: def.in_sidebar ? def.migration_status : 'broken_deeplink',
    notes: def.notes,
  }
}

function nested(args: {
  id: string
  kind: SurfaceKind
  parent: string
  page: string
  route: string
  module: string | null
  permission: string | null
  component: string
  api_authority: string
  url_state: UrlStateKind
  migration_status: MigrationStatus
  notes?: string
  loading?: boolean
  error?: boolean
  empty?: boolean
}): HrWebSurface {
  return {
    surface_id: args.id,
    kind: args.kind,
    route: args.route,
    parent: args.parent,
    page: args.page as Page,
    module: args.module,
    permission: args.permission,
    component: args.component,
    api_authority: args.api_authority,
    i18n: 'en_ar',
    rtl: 'supported',
    responsive: args.kind === 'drawer' || args.kind === 'modal' ? 'partial' : 'shell',
    loading: args.loading ?? true,
    error: args.error ?? true,
    empty: args.empty ?? true,
    url_state: args.url_state,
    in_sidebar: false,
    in_page_union: false,
    in_capability: false,
    migration_status: args.migration_status,
    notes: args.notes,
  }
}

const CANDIDATE_VIEWS = ['all', 'active', 'talent_pool', 'hired', 'archived', 'restricted'] as const
const INTERVIEW_TABS = ['upcoming', 'needs_feedback', 'video_interviews', 'completed', 'all', 'no_show', 'cancelled'] as const
const ASSESSMENT_TABS = [
  'send',
  'resend',
  'delivery_failed',
  'in_progress',
  'sent_pending',
  'completed',
  'attempts',
  'reports',
  'needs_review',
] as const
const SETTINGS_SECTIONS = ['account', 'team', 'company', 'communications', 'integrations', 'advanced'] as const
const WORKSPACE_TABS: Record<string, string[]> = {
  performance: ['overview', 'goals', 'reviews', 'calibration', 'development'],
  talent: ['overview', 'people', 'reviews', 'succession', 'mobility', 'ninebox', 'models', 'rolefit', 'map'],
  learning: ['overview', 'catalog', 'assignments', 'sessions', 'certifications', 'requests', 'history'],
  benefits: ['overview', 'plans', 'enrollment', 'coverage', 'contributions', 'history'],
  'employee-relations': ['overview', 'cases', 'detail', 'my-work', 'history'],
  engagement: ['overview', 'surveys', 'results', 'actions', 'history'],
  'compensation-planning': ['overview', 'worksheet', 'calibration', 'approvals', 'finalized', 'history'],
  'workforce-planning': ['overview', 'plan', 'scenarios', 'demand', 'cost', 'approvals', 'execution', 'history'],
  'job-architecture': ['overview', 'catalog', 'grades', 'paths', 'mappings'],
  shifts: ['schedule', 'requests', 'planning'],
  payroll: ['run', 'hours', 'records'],
  workforce: ['organization', 'lifecycle', 'remediation', 'migration', 'requests'],
  onboarding: ['needs_attention', 'in_progress', 'not_started', 'completed', 'all'],
  preboarding: ['all', 'blocked', 'ready', 'in_progress', 'not_started'],
  probation: ['attention', 'active', 'under_review', 'confirmed', 'extended', 'failed'],
  inbox: ['needs_action', 'due_soon', 'blocked', 'all'],
  requisitions: ['attention', 'draft', 'pending_approval', 'approved', 'open', 'filled'],
  calendar: ['day', 'week', 'month'],
  notifications: ['needs_follow_up', 'failed', 'retrying', 'resolved', 'all'],
}

const NESTED: HrWebSurface[] = [
  nested({
    id: 'legacy.migration-sync',
    kind: 'legacy',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=migration-sync',
    module: null,
    permission: 'employees.read',
    component: 'readDashboardNavState alias',
    api_authority: '/dashboard/posthire/employees (migration view)',
    url_state: 'alias',
    migration_status: 'legacy_alias',
    notes: 'Rewritten to ?page=employees&view=migration. Keep alias forever.',
  }),
  nested({
    id: 'detail.employees.profile',
    kind: 'detail',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees&employee={employee_key}',
    module: null,
    permission: 'employees.read',
    component: 'EmployeeProfile (360)',
    api_authority: '/dashboard/posthire/employees/{employee_key}',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'Canonical employee record. Phase 5: identity header, jump nav, module sections remain backend-published. Mutations stay on owning modules.',
  }),
  nested({
    id: 'drawer.analytics.metric',
    kind: 'drawer',
    parent: 'page.analytics',
    page: 'analytics',
    route: '/dashboard?page=analytics&q={semantic_key}',
    module: 'analytics',
    permission: 'analytics.read',
    component: 'IntelligenceDetailDrawer',
    api_authority: '/dashboard/intelligence evaluate + trend + drill',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'Phase 6. Metric detail is URL-backed. Evaluate/trend/segment/drill stay governed backend. Suppression and freshness are displayed, not recomputed.',
  }),
  nested({
    id: 'page.employees.view.migration',
    kind: 'tab',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees&view=migration',
    module: null,
    permission: 'employees.read',
    component: 'EmployeesPage Migration & Sync',
    api_authority: '/dashboard/posthire/employees/migration',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'detail.candidates.profile',
    kind: 'detail',
    parent: 'page.candidates',
    page: 'candidates',
    route: '/dashboard?page=candidates&candidate={app_key}',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'CandidateProfilePage',
    api_authority: '/dashboard/prehire/applications/{app_key}',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'detail.jobs.workspace',
    kind: 'detail',
    parent: 'page.jobs',
    page: 'jobs',
    route: '/dashboard?page=jobs (selected position)',
    module: 'pre_hiring',
    permission: 'jobs.read',
    component: 'JobWorkspace',
    api_authority: '/dashboard/prehire/positions/{code}',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'Selected job is not a first-class URL key.',
  }),
  nested({
    id: 'drawer.interviews.detail',
    kind: 'drawer',
    parent: 'page.interviews',
    page: 'interviews',
    route: '/dashboard?page=interviews',
    module: 'interviews',
    permission: 'prehire.read',
    component: 'InterviewDetailDrawer',
    api_authority: '/dashboard/prehire/interviews/{id}',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'drawer.calendar.event',
    kind: 'drawer',
    parent: 'page.calendar',
    page: 'calendar',
    route: '/dashboard?page=calendar',
    module: 'calendar',
    permission: 'calendar.read',
    component: 'CalendarShell event drawer',
    api_authority: '/dashboard/prehire/calendar/events/{id}',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'drawer.onboarding.detail',
    kind: 'drawer',
    parent: 'page.onboarding',
    page: 'onboarding',
    route: '/dashboard?page=onboarding',
    module: 'onboarding',
    permission: 'onboarding.read',
    component: 'OnboardingDetailDrawer',
    api_authority: '/dashboard/posthire/onboarding/{id}',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.employees.approver-pick',
    kind: 'modal',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees',
    module: null,
    permission: 'employees.manage',
    component: 'ApproverPickModal',
    api_authority: 'POST /dashboard/posthire/employees (approver assignment)',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.leave.file',
    kind: 'modal',
    parent: 'page.leave',
    page: 'leave',
    route: '/dashboard?page=leave',
    module: 'leave',
    permission: 'leave.manage',
    component: 'FileLeaveModal',
    api_authority: 'POST /dashboard/posthire/leave',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'drawer.leave.detail',
    kind: 'drawer',
    parent: 'page.leave',
    page: 'leave',
    route: '/dashboard?page=leave',
    module: 'leave',
    permission: 'leave.read',
    component: 'LeaveDetailDrawer',
    api_authority: '/dashboard/posthire/leave/{id}',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.interviews.action',
    kind: 'modal',
    parent: 'page.interviews',
    page: 'interviews',
    route: '/dashboard?page=interviews',
    module: 'interviews',
    permission: 'interview.manage',
    component: 'InterviewActionDialog',
    api_authority: '/dashboard/prehire/interviews (mutate)',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.employees.add',
    kind: 'modal',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees',
    module: null,
    permission: 'employees.manage',
    component: 'AddEmployeeModal',
    api_authority: 'POST /dashboard/posthire/employees',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.employees.edit',
    kind: 'modal',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees',
    module: null,
    permission: 'employees.manage',
    component: 'EditEmployeeModal',
    api_authority: 'PATCH /dashboard/posthire/employees/{id}',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.employees.import',
    kind: 'modal',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees&view=migration',
    module: null,
    permission: 'employees.manage',
    component: 'ImportEmployeesModal',
    api_authority: 'POST /dashboard/posthire/employees/import',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.employees.activation',
    kind: 'modal',
    parent: 'page.employees',
    page: 'employees',
    route: '/dashboard?page=employees',
    module: null,
    permission: 'employees.manage',
    component: 'ActivationHandoffModal',
    api_authority: 'activation handoff payload (no client-side truth)',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.candidates.add-to-job',
    kind: 'modal',
    parent: 'page.candidates',
    page: 'candidates',
    route: '/dashboard?page=candidates',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'AddToJobDialog',
    api_authority: 'POST /dashboard/prehire/applications (job assign)',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.shared.confirm',
    kind: 'modal',
    parent: null,
    page: null,
    route: '(overlay)',
    module: null,
    permission: null,
    component: 'ConfirmDialog (shared) + PostHire local ConfirmDialog',
    api_authority: 'mutation endpoints of caller',
    url_state: 'local',
    migration_status: 'consolidate',
    notes: 'PostHire.tsx ships a second ConfirmDialog. Keep one shared overlay.',
  }),
  nested({
    id: 'modal.payroll.export-detail',
    kind: 'modal',
    parent: 'page.payroll',
    page: 'payroll',
    route: '/dashboard?page=payroll',
    module: 'payroll',
    permission: 'payroll.read',
    component: 'PayrollExportDetailModal',
    api_authority: '/dashboard/posthire/payroll/exports/{id}',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'modal.attendance.import',
    kind: 'modal',
    parent: 'page.attendance',
    page: 'attendance',
    route: '/dashboard?page=attendance',
    module: 'attendance',
    permission: 'attendance.manage',
    component: 'AttendanceImportDialog',
    api_authority: 'POST /dashboard/posthire/attendance/import',
    url_state: 'local',
    migration_status: 'preserve',
  }),
  nested({
    id: 'tab.attendance.capture',
    kind: 'subtab',
    parent: 'page.attendance',
    page: 'attendance',
    route: '/dashboard?page=attendance',
    module: 'attendance',
    permission: 'attendance.read',
    component: 'AttendanceCaptureOps',
    api_authority: '/dashboard/posthire/attendance/capture',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'connectors | mapping | missing | conflicts — local tab state behind collapsed Operations. Not URL-backed on purpose.',
  }),
  nested({
    id: 'tab.leave.active',
    kind: 'tab',
    parent: 'page.leave',
    page: 'leave',
    route: '/dashboard?page=leave&view=active',
    module: 'leave',
    permission: 'leave.read',
    component: 'LeaveWorkspace',
    api_authority: '/dashboard/posthire/leave?view=active',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'Active/history via `?view=`. Refresh/back restore the same queue.',
  }),
  nested({
    id: 'tab.leave.history',
    kind: 'tab',
    parent: 'page.leave',
    page: 'leave',
    route: '/dashboard?page=leave&view=history',
    module: 'leave',
    permission: 'leave.read',
    component: 'LeaveWorkspace',
    api_authority: '/dashboard/posthire/leave?view=history',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'History status filter is URL-backed via ?status=.',
  }),
  nested({
    id: 'tab.payroll.records.payslips',
    kind: 'subtab',
    parent: 'tab.payroll.records',
    page: 'payroll',
    route: '/dashboard?page=payroll&tab=records&view=payslips',
    module: 'payroll',
    permission: 'payroll.read',
    component: 'PayslipWorkspace',
    api_authority: '/dashboard/posthire/payroll/payslips',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'tab.payroll.records.close',
    kind: 'subtab',
    parent: 'tab.payroll.records',
    page: 'payroll',
    route: '/dashboard?page=payroll&tab=records&view=close',
    module: 'payroll',
    permission: 'payroll.read',
    component: 'CloseExportWorkspace',
    api_authority: '/dashboard/posthire/payroll/close-export',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'tab.payroll.records.statutory',
    kind: 'subtab',
    parent: 'tab.payroll.records',
    page: 'payroll',
    route: '/dashboard?page=payroll&tab=records&view=statutory',
    module: 'payroll',
    permission: 'payroll.read',
    component: 'StatutoryWorksheetWorkspace',
    api_authority: '/dashboard/posthire/payroll/statutory',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'tab.interviews.video',
    kind: 'tab',
    parent: 'page.interviews',
    page: 'interviews',
    route: '/dashboard?page=interviews&tab=video_interviews',
    module: 'video_interviews',
    permission: 'interview.manage',
    component: 'InterviewsPage',
    api_authority: '/dashboard/prehire/interviews (video)',
    url_state: 'query',
    migration_status: 'canonical',
    notes: 'Also registered as workspaceCapability tab.interviews.video.',
  }),
  nested({
    id: 'overview.action.review',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=candidates&review_status=ready',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'OverviewPage priority card',
    api_authority: 'prehire_overview.ready_for_review',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'overview.action.assessment',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=assessments',
    module: 'assessments',
    permission: 'assessment.manage',
    component: 'OverviewPage priority card',
    api_authority: 'prehire_overview.assessment_pending',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'overview.action.followup',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=candidates&follow_up=needed',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'OverviewPage priority card',
    api_authority: 'prehire_overview.follow_up_needed',
    url_state: 'query',
    migration_status: 'canonical',
  }),
  nested({
    id: 'overview.work_queue',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=overview',
    module: 'pre_hiring',
    permission: 'candidates.read',
    component: 'OverviewPage work queue',
    api_authority: '/dashboard/prehire/overview/work-queue',
    url_state: 'page',
    migration_status: 'canonical',
  }),
  nested({
    id: 'overview.approvals',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=inbox',
    module: null,
    permission: null,
    component: 'OverviewPage approvals peek',
    api_authority: '/dashboard/posthire/action-inbox',
    url_state: 'page',
    migration_status: 'canonical',
    notes: 'Fail-closed on bootstrap action_inbox.offerable. Peek only — no client ranking.',
  }),
  nested({
    id: 'overview.signals',
    kind: 'overview',
    parent: 'page.overview',
    page: 'overview',
    route: '/dashboard?page=analytics',
    module: 'analytics',
    permission: 'analytics.read',
    component: 'OverviewPage workforce signals',
    api_authority: '/dashboard/posthire/intelligence/overview',
    url_state: 'page',
    migration_status: 'canonical',
    notes: 'C1 evaluations as published. Stale/suppressed/insufficient are not labelled current.',
  }),
  nested({
    id: 'setup.console.modules',
    kind: 'setup',
    parent: null,
    page: null,
    route: '/setup-console?view=modules',
    module: null,
    permission: 'settings.manage',
    component: 'SetupConsoleApp',
    api_authority: '/dashboard/setup (canonical config, not ops truth)',
    url_state: 'query',
    migration_status: 'preserve',
    notes: 'Adjacent MPA. Listed because Settings and ownership cards deep-link here.',
  }),
  nested({
    id: 'setup.console.policies',
    kind: 'setup',
    parent: 'setup.console.modules',
    page: null,
    route: '/setup-console?view=policies',
    module: null,
    permission: 'settings.manage',
    component: 'SetupConsoleApp',
    api_authority: '/dashboard/setup',
    url_state: 'query',
    migration_status: 'preserve',
  }),
  nested({
    id: 'setup.console.classic',
    kind: 'setup',
    parent: 'setup.console.modules',
    page: null,
    route: '/setup-console?view=classic',
    module: null,
    permission: 'settings.manage',
    component: 'SetupConsoleApp',
    api_authority: '/dashboard/setup',
    url_state: 'hash',
    migration_status: 'preserve',
  }),
  nested({
    id: 'auth.sign-in',
    kind: 'auth',
    parent: null,
    page: null,
    route: '/dashboard (unauthenticated)',
    module: null,
    permission: null,
    component: 'AccessVerificationPage',
    api_authority: '/dashboard/auth',
    url_state: 'page',
    migration_status: 'excluded',
    notes: 'Pre-auth. Tracked so census does not treat it as a missing page.',
    loading: true,
    error: true,
    empty: false,
  }),
  nested({
    id: 'auth.invite',
    kind: 'auth',
    parent: null,
    page: null,
    route: '/dashboard?invite={token}',
    module: null,
    permission: null,
    component: 'Invite acceptance (App.tsx)',
    api_authority: '/dashboard/invite',
    url_state: 'query',
    migration_status: 'excluded',
    notes: 'Pre-auth invite acceptance.',
    loading: true,
    error: true,
    empty: false,
  }),
]

for (const view of CANDIDATE_VIEWS) {
  NESTED.push(
    nested({
      id: `tab.candidates.view.${view}`,
      kind: 'tab',
      parent: 'page.candidates',
      page: 'candidates',
      route: `/dashboard?page=candidates&view=${view}`,
      module: 'pre_hiring',
      permission: 'candidates.read',
      component: 'CandidatesPage',
      api_authority: '/dashboard/prehire/applications',
      url_state: 'query',
      migration_status: 'canonical',
    }),
  )
}

for (const tab of INTERVIEW_TABS) {
  if (tab === 'video_interviews') continue
  NESTED.push(
    nested({
      id: `tab.interviews.${tab}`,
      kind: 'tab',
      parent: 'page.interviews',
      page: 'interviews',
      route: `/dashboard?page=interviews&tab=${tab}`,
      module: 'interviews',
      permission: 'prehire.read',
      component: 'InterviewsPage',
      api_authority: '/dashboard/prehire/interviews',
      url_state: 'query',
      migration_status: 'canonical',
    }),
  )
}

for (const tab of ASSESSMENT_TABS) {
  NESTED.push(
    nested({
      id: `tab.assessments.${tab}`,
      kind: 'tab',
      parent: 'page.assessments',
      page: 'assessments',
      route: `/dashboard?page=assessments&tab=${tab}`,
      module: 'assessments',
      permission: 'assessment.manage',
      component: 'AssessmentsPage',
      api_authority: '/dashboard/prehire/assessments',
      url_state: 'query',
      migration_status: 'canonical',
    }),
  )
}

for (const section of SETTINGS_SECTIONS) {
  NESTED.push(
    nested({
      id: `settings.${section}`,
      kind: 'settings',
      parent: 'page.settings',
      page: 'settings',
      route: `/dashboard?page=settings&tab=${section}`,
      module: null,
      permission: section === 'account' ? null : 'users.manage',
      component: 'SettingsPage',
      api_authority: '/dashboard/settings',
      url_state: 'query',
      migration_status: section === 'advanced' ? 'consolidate' : 'canonical',
      notes:
        section === 'advanced'
          ? 'Phase 8. Capability registry still names this settings.platform. SettingsPage id is advanced. Admin-only recovery/diagnostics — not merged into Integrations. URL-backed via ?tab=.'
          : 'Phase 8. Settings section is URL-backed via ?tab=. Unauthorized sections still fall back in-page. Configuration semantics unchanged.',
    }),
  )
}

for (const [page, tabs] of Object.entries(WORKSPACE_TABS)) {
  const parent = PAGE_DEFS.find((row) => row.page === page)
  for (const tab of tabs) {
    NESTED.push(
      nested({
        id: `tab.${page}.${tab}`,
        kind: tab === 'detail' ? 'detail' : 'tab',
        parent: `page.${page}`,
        page,
        route: `/dashboard?page=${page}&tab=${tab}`,
        module: parent?.module || null,
        permission: parent?.permission || null,
        component: parent?.component || `${page} workspace`,
        api_authority: parent?.api_authority || '/dashboard/posthire',
        url_state: 'query',
        migration_status:
          page === 'shifts' ||
          page === 'payroll' ||
          page === 'workforce' ||
          page === 'onboarding' ||
          page === 'preboarding' ||
          page === 'probation' ||
          page === 'inbox' ||
          page === 'performance' ||
          page === 'talent' ||
          page === 'learning' ||
          page === 'benefits' ||
          page === 'employee-relations' ||
          page === 'engagement' ||
          page === 'compensation-planning' ||
          page === 'workforce-planning' ||
          page === 'job-architecture' ||
          page === 'requisitions' ||
          page === 'calendar' ||
          page === 'notifications' ||
          page === 'settings'
            ? 'canonical'
            : 'enterprise',
        notes:
          page === 'shifts' || page === 'payroll'
            ? 'Phase 4 operational core. Workspace tab is URL-backed via ?tab=. Refresh/back/forward restore the same chrome.'
            : page === 'workforce' ||
                page === 'onboarding' ||
                page === 'preboarding' ||
                page === 'probation' ||
                page === 'inbox'
              ? 'Phase 5 People spine. Workspace tab is URL-backed via ?tab=. Refresh/back/forward restore the same chrome.'
              : page === 'performance' ||
                  page === 'talent' ||
                  page === 'learning' ||
                  page === 'benefits' ||
                  page === 'employee-relations' ||
                  page === 'engagement' ||
                  page === 'compensation-planning' ||
                  page === 'workforce-planning' ||
                  page === 'job-architecture'
                ? 'Phase 6 enterprise flagship. Workspace tab is URL-backed via ?tab=. Refresh/back/forward restore the same chrome.'
                : page === 'requisitions' || page === 'calendar'
                  ? 'Phase 7 recruiting. Workspace tab is URL-backed via ?tab=. Refresh/back/forward restore the same chrome.'
                : page === 'notifications'
                  ? 'Phase 8 workspace. Delivery issue filter is URL-backed via ?tab=. Refresh/back/forward restore the same chrome. Channel/delivery authority stays backend-canonical.'
                : page === 'settings'
                  ? 'Phase 8 workspace. Settings section is URL-backed via ?tab=. Configuration semantics unchanged.'
                : 'Workspace tab is URL-backed via ?tab=. Refresh/back/forward restore the same chrome.',
      }),
    )
  }
}

export const HR_WEB_SURFACE_REGISTRY: HrWebSurface[] = [...PAGE_DEFS.map(pageSurface), ...NESTED]

export const HR_WEB_SURFACE_EXCLUSIONS: HrWebExclusion[] = [
  {
    id: 'employee_app',
    reason: 'Employee-surface entitlement. Must never appear in HR nav (moduleWorkspace.HR_NAV_EXCLUDED_MODULES).',
    pattern: 'employee_app',
  },
  {
    id: 'futureModuleItems',
    reason: 'Empty future-tools list in App.tsx. Not a live destination.',
    pattern: 'futureModuleItems',
  },
  {
    id: 'setup-console.html',
    reason: 'Vite MPA entry rewritten to /setup-console. Covered by setup.* registry rows.',
    pattern: '/setup-console.html',
  },
]

/** Empty after Phase 2 lockstep: catalog + resolveWorkspaceAuthority cover every capability nav page. */
export const HR_WEB_SIDEBAR_COVERAGE_GAPS: Page[] = []

export const HR_WEB_PAGE_IDS: Page[] = PAGE_DEFS.map((row) => row.page)

export function registryById(): Record<string, HrWebSurface> {
  return Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
}

export function registryPageIds(): string[] {
  return HR_WEB_SURFACE_REGISTRY.filter((row) => row.kind === 'page').map((row) => String(row.page))
}

export function capabilityNavPages(): string[] {
  return WORKSPACE_SURFACES.filter((row) => row.kind === 'nav' && row.page).map((row) => String(row.page))
}

export function posthireSwitchPages(): readonly string[] {
  return POSTHIRE_NAV_PAGES
}

export const HR_WEB_CENSUS_META = {
  phase: '1',
  kind: 'surface-census-interaction-audit',
  as_of: '2026-08-21',
  source_of_truth: 'apps/wathefni-dashboard/src/lib/hrWebSurfaceRegistry.ts',
  capability_authority: 'apps/wathefni-dashboard/src/lib/workspaceCapability.ts',
  backend_authority: 'wathefni-orchestrator workspace_capability / module_catalog',
} as const
