/**
 * Shared Wathefni workspace capability authority.
 *
 * Single client-side resolver for nav, Overview composition, tabs, and
 * deep-link allowlisting. Inputs: tenant effective modules + actor permissions
 * (+ optional provider flags). Mirrors backend workspace_capability.py.
 */

import type { DashboardUserAccess, Page } from '@/types'
import {
  anyPeopleModuleEnabled,
  isAlertsAndDeliveryRelevant,
  moduleEnabled,
  type ModuleWorkspaceCatalog,
} from '@/lib/moduleWorkspace'
import { hasDashboardPermission, hasJobsPermission } from '@/pages/shared/access'

export type SurfaceStatus =
  | 'available'
  | 'module_off'
  | 'permission_denied'
  | 'not_configured'
  | 'unsupported'

export type NavGroup = 'prehire' | 'posthire' | 'settings'

export type WorkspaceSurface = {
  id: string
  kind: 'nav' | 'overview' | 'tab' | 'settings' | 'assistant'
  page?: Page | string
  group?: NavGroup
  module?: string | null
  /** Alternate modules that also unlock this surface (legacy OR). */
  moduleAnyOf?: string[]
  permission?: string | null
  permissionAnyOf?: string[]
  jobsPermission?: string | null
  provider?: string | null
  label: string
}

export type ResolvedSurface = WorkspaceSurface & {
  status: SurfaceStatus
  offerable: boolean
}

export type OverviewLayoutMode = 'none' | 'one' | 'two' | 'three' | 'grid'

export type OverviewComposition = {
  layout: OverviewLayoutMode
  prioritySurfaces: string[]
  showWorkQueue: boolean
  showRolePriority: boolean
  showCalendar: boolean
  allClear: boolean
  headlineMode: 'hiring' | 'team' | 'mixed' | 'calm'
}

export type WorkspaceAuthority = {
  enabledModules: string[]
  permissions: string[]
  surfaces: Record<string, ResolvedSurface>
  navIds: string[]
  navGroups: Array<{ group: NavGroup; ids: string[] }>
  overview: OverviewComposition
  offerable: (surfaceId: string) => boolean
  pageAllowed: (page: string) => boolean
}

/** Canonical surface registry — nav + overview + representative tabs/settings. */
export const WORKSPACE_SURFACES: WorkspaceSurface[] = [
  // Pre-hire nav
  {
    id: 'nav.overview',
    kind: 'nav',
    page: 'overview',
    group: 'prehire',
    module: 'pre_hiring',
    permissionAnyOf: ['candidate.manage', 'jobs.create', 'report.export'],
    label: 'Overview',
  },
  {
    id: 'nav.ai',
    kind: 'nav',
    page: 'ai',
    group: 'prehire',
    moduleAnyOf: ['pre_hiring', 'leave', 'attendance', 'onboarding', 'shifts', 'payroll', 'compliance', 'analytics'],
    permissionAnyOf: ['candidate.manage', 'jobs.create', 'report.export', 'leave.read', 'attendance.read', 'onboarding.read', 'payroll.read'],
    label: 'Wathefni Assistant',
  },
  {
    id: 'nav.jobs',
    kind: 'nav',
    page: 'jobs',
    group: 'prehire',
    module: 'pre_hiring',
    jobsPermission: 'jobs.read',
    label: 'Jobs',
  },
  {
    id: 'nav.candidates',
    kind: 'nav',
    page: 'candidates',
    group: 'prehire',
    module: 'pre_hiring',
    permission: 'candidates.read',
    label: 'Candidates',
  },
  {
    id: 'nav.interviews',
    kind: 'nav',
    page: 'interviews',
    group: 'prehire',
    moduleAnyOf: ['interviews', 'video_interviews'],
    permission: 'prehire.read',
    label: 'Interviews',
  },
  {
    id: 'nav.calendar',
    kind: 'nav',
    page: 'calendar',
    group: 'prehire',
    module: 'calendar',
    permission: 'calendar.read',
    label: 'Calendar',
  },
  {
    id: 'nav.assessments',
    kind: 'nav',
    page: 'assessments',
    group: 'prehire',
    module: 'assessments',
    permission: 'assessment.manage',
    label: 'Assessments',
  },
  {
    id: 'nav.ranking',
    kind: 'nav',
    page: 'ranking',
    group: 'prehire',
    module: 'pre_hiring',
    permissionAnyOf: ['candidate.manage', 'jobs.create', 'report.export'],
    label: 'Ranking',
  },
  {
    id: 'nav.reports',
    kind: 'nav',
    page: 'reports',
    group: 'prehire',
    module: 'pre_hiring',
    permission: 'report.export',
    label: 'Reports',
  },
  // Post-hire nav
  {
    id: 'nav.employees',
    kind: 'nav',
    page: 'employees',
    group: 'posthire',
    permission: 'employees.read',
    label: 'Employees',
  },
  {
    id: 'nav.workforce',
    kind: 'nav',
    page: 'workforce',
    group: 'posthire',
    permission: 'employees.read',
    label: 'Workforce',
  },
  {
    id: 'nav.inbox',
    kind: 'nav',
    page: 'inbox',
    group: 'posthire',
    moduleAnyOf: [
      'analytics',
      'compliance',
      'onboarding',
      'attendance',
      'leave',
      'shifts',
      'payroll',
    ],
    permissionAnyOf: [
      'analytics.read',
      'compliance.read',
      'onboarding.read',
      'attendance.read',
      'leave.read',
      'shifts.read',
      'payroll.read',
      'employees.read',
    ],
    label: 'Action Inbox',
  },
  {
    id: 'nav.onboarding',
    kind: 'nav',
    page: 'onboarding',
    group: 'posthire',
    module: 'onboarding',
    permission: 'onboarding.read',
    label: 'Onboarding',
  },
  {
    id: 'nav.attendance',
    kind: 'nav',
    page: 'attendance',
    group: 'posthire',
    module: 'attendance',
    permission: 'attendance.read',
    label: 'Attendance',
  },
  {
    id: 'nav.leave',
    kind: 'nav',
    page: 'leave',
    group: 'posthire',
    module: 'leave',
    permission: 'leave.read',
    label: 'Leave',
  },
  {
    id: 'nav.shifts',
    kind: 'nav',
    page: 'shifts',
    group: 'posthire',
    module: 'shifts',
    permission: 'shifts.read',
    label: 'Shifts',
  },
  {
    id: 'nav.payroll',
    kind: 'nav',
    page: 'payroll',
    group: 'posthire',
    module: 'payroll',
    permission: 'payroll.read',
    label: 'Payroll',
  },
  {
    id: 'nav.analytics',
    kind: 'nav',
    page: 'analytics',
    group: 'posthire',
    module: 'analytics',
    permission: 'analytics.read',
    label: 'Analytics',
  },
  {
    id: 'nav.compliance',
    kind: 'nav',
    page: 'compliance',
    group: 'posthire',
    module: 'compliance',
    permission: 'compliance.read',
    label: 'Compliance',
  },
  // Workspace
  {
    id: 'nav.notifications',
    kind: 'nav',
    page: 'notifications',
    group: 'settings',
    label: 'Alerts & Delivery',
  },
  {
    id: 'nav.activity',
    kind: 'nav',
    page: 'activity',
    group: 'settings',
    permission: 'audit.read',
    label: 'Activity',
  },
  {
    id: 'nav.settings',
    kind: 'nav',
    page: 'settings',
    group: 'settings',
    permissionAnyOf: ['settings.manage', 'users.manage'],
    label: 'Settings',
  },
  // Overview priority surfaces
  {
    id: 'overview.action.review',
    kind: 'overview',
    module: 'pre_hiring',
    permission: 'candidates.read',
    label: 'Review candidates',
  },
  {
    id: 'overview.action.assessment',
    kind: 'overview',
    module: 'assessments',
    permission: 'assessment.manage',
    label: 'Assessments',
  },
  {
    id: 'overview.action.followup',
    kind: 'overview',
    module: 'pre_hiring',
    permission: 'candidates.read',
    label: 'Follow up',
  },
  {
    id: 'overview.work_queue',
    kind: 'overview',
    module: 'pre_hiring',
    permissionAnyOf: ['candidate.manage', 'jobs.create', 'report.export', 'candidates.read'],
    label: 'Work queue',
  },
  {
    id: 'overview.role_priority',
    kind: 'overview',
    module: 'pre_hiring',
    permissionAnyOf: ['candidate.manage', 'jobs.create', 'report.export'],
    label: 'Role priority',
  },
  {
    id: 'overview.calendar',
    kind: 'overview',
    module: 'calendar',
    permission: 'calendar.read',
    label: 'Calendar',
  },
  // Tabs
  {
    id: 'tab.interviews.video',
    kind: 'tab',
    module: 'video_interviews',
    permission: 'interview.manage',
    label: 'Video interviews',
  },
  {
    id: 'tab.assessments.setup',
    kind: 'tab',
    module: 'assessments',
    permission: 'assessment.manage',
    label: 'Assessment setup',
  },
  // Settings sections
  {
    id: 'settings.team',
    kind: 'settings',
    permission: 'users.manage',
    label: 'Team',
  },
  {
    id: 'settings.integrations',
    kind: 'settings',
    permission: 'settings.manage',
    label: 'Integrations',
  },
  {
    id: 'settings.platform',
    kind: 'settings',
    permission: 'settings.manage',
    label: 'Platform',
  },
]

function permOk(access: DashboardUserAccess | null | undefined, required: string | null | undefined): boolean {
  if (!required) return true
  return hasDashboardPermission(access, required)
}

function anyPermOk(access: DashboardUserAccess | null | undefined, required: string[] | undefined): boolean {
  if (!required || required.length === 0) return true
  return required.some((p) => hasDashboardPermission(access, p))
}

function moduleOk(
  enabledModules: string[] | null | undefined,
  surface: WorkspaceSurface,
  catalog?: ModuleWorkspaceCatalog[] | null,
): boolean {
  if (surface.id === 'nav.employees' || surface.id === 'nav.workforce') {
    return anyPeopleModuleEnabled(enabledModules, catalog)
  }
  if (surface.id === 'nav.notifications') {
    return isAlertsAndDeliveryRelevant(enabledModules, catalog)
  }
  if (surface.moduleAnyOf?.length) {
    return surface.moduleAnyOf.some((key) => moduleEnabled(enabledModules, key))
  }
  if (!surface.module) return true
  return moduleEnabled(enabledModules, surface.module)
}

export function resolveSurface(
  surface: WorkspaceSurface,
  enabledModules: string[] | null | undefined,
  access: DashboardUserAccess | null | undefined,
  catalog?: ModuleWorkspaceCatalog[] | null,
  providers?: Record<string, boolean> | null,
): ResolvedSurface {
  if (!moduleOk(enabledModules, surface, catalog)) {
    return { ...surface, status: 'module_off', offerable: false }
  }
  if (surface.jobsPermission && !hasJobsPermission(access, surface.jobsPermission as 'jobs.read')) {
    return { ...surface, status: 'permission_denied', offerable: false }
  }
  if (surface.permission && !permOk(access, surface.permission)) {
    return { ...surface, status: 'permission_denied', offerable: false }
  }
  if (surface.permissionAnyOf && !anyPermOk(access, surface.permissionAnyOf)) {
    return { ...surface, status: 'permission_denied', offerable: false }
  }
  if (surface.provider && providers && providers[surface.provider] === false) {
    return { ...surface, status: 'not_configured', offerable: false }
  }
  return { ...surface, status: 'available', offerable: true }
}

export function composeOverviewLayout(args: {
  surfaces: Record<string, ResolvedSurface>
  urgentCount: number
  hasRolePriority: boolean
}): OverviewComposition {
  const s = args.surfaces
  const priorityKeys = ['overview.action.review', 'overview.action.assessment', 'overview.action.followup'] as const
  const prioritySurfaces = priorityKeys.filter((id) => s[id]?.offerable)
  // Layout mode follows how many priority action cards are entitlement-eligible;
  // live counts further hide zero-work cards at render time.
  const n = prioritySurfaces.length
  let layout: OverviewLayoutMode = 'none'
  if (n === 1) layout = 'one'
  else if (n === 2) layout = 'two'
  else if (n === 3) layout = 'three'
  else if (n >= 4) layout = 'grid'

  const showWorkQueue = Boolean(s['overview.work_queue']?.offerable)
  const showRolePriority = Boolean(s['overview.role_priority']?.offerable)
  const showCalendar = Boolean(s['overview.calendar']?.offerable)
  const hasPrehire = Boolean(s['nav.overview']?.offerable)
  const hasPosthireNav = Object.values(s).some((row) => row.group === 'posthire' && row.offerable && row.kind === 'nav')
  let headlineMode: OverviewComposition['headlineMode'] = 'calm'
  if (hasPrehire && hasPosthireNav) headlineMode = 'mixed'
  else if (hasPrehire) headlineMode = 'hiring'
  else if (hasPosthireNav) headlineMode = 'team'
  const allClear = args.urgentCount <= 0

  return {
    layout,
    prioritySurfaces,
    showWorkQueue,
    showRolePriority,
    showCalendar,
    allClear,
    headlineMode,
  }
}

export function resolveWorkspaceAuthority(args: {
  enabledModules: string[] | null | undefined
  access: DashboardUserAccess | null | undefined
  catalog?: ModuleWorkspaceCatalog[] | null
  providers?: Record<string, boolean> | null
  urgentCount?: number
  hasRolePriority?: boolean
}): WorkspaceAuthority {
  const enabled = Array.isArray(args.enabledModules) ? args.enabledModules : []
  const permissions = Array.isArray(args.access?.permissions) ? args.access!.permissions.map(String) : []
  const surfaces: Record<string, ResolvedSurface> = {}
  for (const surface of WORKSPACE_SURFACES) {
    surfaces[surface.id] = resolveSurface(surface, enabled, args.access, args.catalog, args.providers)
  }

  // Employees: people modules unlock the directory for workspace admins
  // (settings/users manage) even when employees.read is omitted from a slim
  // owner fixture. Recruiters without employees.read stay gated out.
  if (surfaces['nav.employees'] && !surfaces['nav.employees'].offerable) {
    const peopleOn = anyPeopleModuleEnabled(enabled, args.catalog)
    const perms = new Set(permissions)
    const adminWorkspace =
      perms.has('employees.read') ||
      perms.has('settings.manage') ||
      perms.has('users.manage') ||
      perms.has('*:*') ||
      perms.size === 0
    if (peopleOn && adminWorkspace) {
      surfaces['nav.employees'] = { ...surfaces['nav.employees'], status: 'available', offerable: true }
    } else if (peopleOn) {
      surfaces['nav.employees'] = { ...surfaces['nav.employees'], status: 'permission_denied', offerable: false }
    }
  }

  // Assistant lives with post-hire when pre_hiring is off so the prehire group can hide.
  if (surfaces['nav.ai']?.offerable && !moduleEnabled(enabled, 'pre_hiring')) {
    surfaces['nav.ai'] = { ...surfaces['nav.ai'], group: 'posthire' }
  }

  const navIds = WORKSPACE_SURFACES.filter((s) => s.kind === 'nav' && surfaces[s.id]?.offerable).map((s) => s.page as string)
  // Rebuild nav ids from possibly reassigned groups
  const navIdsOrdered = (['prehire', 'posthire', 'settings'] as NavGroup[]).flatMap((group) =>
    Object.values(surfaces)
      .filter((s) => s.kind === 'nav' && s.group === group && s.offerable)
      .map((s) => String(s.page)),
  )
  const groupOrder: NavGroup[] = ['prehire', 'posthire', 'settings']
  const navGroups = groupOrder
    .map((group) => ({
      group,
      ids: Object.values(surfaces)
        .filter((s) => s.kind === 'nav' && s.group === group && s.offerable)
        .map((s) => String(s.page)),
    }))
    .filter((g) => g.ids.length > 0)

  const overview = composeOverviewLayout({
    surfaces,
    urgentCount: Number(args.urgentCount || 0),
    hasRolePriority: Boolean(args.hasRolePriority),
  })

  return {
    enabledModules: enabled,
    permissions,
    surfaces,
    navIds: navIdsOrdered.length ? navIdsOrdered : navIds,
    navGroups,
    overview,
    offerable: (id) => Boolean(surfaces[id]?.offerable),
    pageAllowed: (page) => (navIdsOrdered.length ? navIdsOrdered : navIds).includes(page),
  }
}

/** Adaptive CSS grid class for Overview priority action cards. */
export function overviewActionGridClass(layout: OverviewLayoutMode, visibleCardCount: number): string {
  const n = visibleCardCount
  if (n <= 0 || layout === 'none') return 'hidden'
  if (n === 1) return 'grid gap-3 grid-cols-1'
  if (n === 2) return 'grid gap-3 md:grid-cols-2'
  if (n === 3) return 'grid gap-3 md:grid-cols-3'
  return 'grid gap-3 sm:grid-cols-2 xl:grid-cols-4'
}

/** Filter tab list by offerable surface ids; collapse to content-only when one remains. */
export function filterTabsByAuthority<T extends { id: string }>(
  tabs: T[],
  authority: WorkspaceAuthority,
  tabSurfaceById: Record<string, string>,
): { tabs: T[]; hideTabBar: boolean } {
  const filtered = tabs.filter((tab) => {
    const surfaceId = tabSurfaceById[tab.id]
    if (!surfaceId) return true
    return authority.offerable(surfaceId)
  })
  return { tabs: filtered, hideTabBar: filtered.length <= 1 }
}

/** Matrix fixtures used by tests and the composition REPORT. */
export type CompositionMatrixRow = {
  id: string
  label: string
  modules: string[]
  role: 'owner' | 'recruiter'
  expectNavGroups: NavGroup[]
  expectNavIncludes: string[]
  expectNavExcludes: string[]
  expectOverviewLayout: OverviewLayoutMode
}

export const COMPOSITION_MATRIX: CompositionMatrixRow[] = [
  {
    id: 'one_module_prehire',
    label: 'One enabled module (pre_hiring)',
    modules: ['pre_hiring'],
    role: 'owner',
    expectNavGroups: ['prehire', 'settings'],
    expectNavIncludes: ['overview', 'jobs', 'candidates', 'ai'],
    expectNavExcludes: ['payroll', 'assessments', 'attendance', 'interviews'],
    expectOverviewLayout: 'two',
  },
  {
    id: 'two_modules',
    label: 'Two modules (pre_hiring + assessments)',
    modules: ['pre_hiring', 'assessments'],
    role: 'owner',
    expectNavGroups: ['prehire', 'settings'],
    expectNavIncludes: ['overview', 'assessments', 'jobs'],
    expectNavExcludes: ['payroll', 'leave', 'interviews'],
    expectOverviewLayout: 'three',
  },
  {
    id: 'three_four_modules',
    label: 'Three to four modules',
    modules: ['pre_hiring', 'assessments', 'interviews', 'calendar'],
    role: 'owner',
    expectNavGroups: ['prehire', 'settings'],
    expectNavIncludes: ['interviews', 'calendar', 'assessments'],
    expectNavExcludes: ['payroll'],
    expectOverviewLayout: 'three',
  },
  {
    id: 'full_prehiring',
    label: 'Full pre-hiring',
    modules: ['pre_hiring', 'assessments', 'interviews', 'video_interviews', 'calendar'],
    role: 'owner',
    expectNavGroups: ['prehire', 'settings'],
    expectNavIncludes: ['overview', 'ai', 'jobs', 'candidates', 'interviews', 'calendar', 'assessments', 'ranking', 'reports'],
    expectNavExcludes: ['payroll', 'onboarding'],
    expectOverviewLayout: 'three',
  },
  {
    id: 'posthire_only',
    label: 'Post-hire only',
    modules: ['onboarding', 'attendance', 'leave', 'payroll'],
    role: 'owner',
    expectNavGroups: ['posthire', 'settings'],
    expectNavIncludes: ['ai', 'onboarding', 'attendance', 'leave', 'payroll', 'employees'],
    expectNavExcludes: ['overview', 'jobs', 'candidates', 'assessments'],
    expectOverviewLayout: 'none',
  },
  {
    id: 'mixed',
    label: 'Mixed pre/post-hire',
    modules: ['pre_hiring', 'assessments', 'leave', 'attendance'],
    role: 'owner',
    expectNavGroups: ['prehire', 'posthire', 'settings'],
    expectNavIncludes: ['overview', 'assessments', 'leave', 'attendance'],
    expectNavExcludes: ['payroll', 'interviews'],
    expectOverviewLayout: 'three',
  },
  {
    id: 'restricted_recruiter',
    label: 'Restricted recruiter vs owner',
    modules: ['pre_hiring', 'assessments', 'interviews', 'leave', 'payroll'],
    role: 'recruiter',
    expectNavGroups: ['prehire', 'settings'],
    expectNavIncludes: ['jobs', 'candidates', 'interviews'],
    expectNavExcludes: ['overview', 'ai', 'ranking', 'reports', 'payroll', 'assessments'],
    expectOverviewLayout: 'two',
  },
]

export const ROLE_PERMISSIONS_FIXTURE: Record<'owner' | 'recruiter', string[]> = {
  owner: [
    'candidate.manage',
    'candidates.read',
    'jobs.create',
    'jobs.read',
    'jobs.edit',
    'jobs.publish',
    'jobs.close',
    'report.export',
    'prehire.read',
    'assessment.manage',
    'interview.manage',
    'calendar.read',
    'leave.read',
    'attendance.read',
    'onboarding.read',
    'payroll.read',
    'shifts.read',
    'compliance.read',
    'analytics.read',
    'employees.read',
    'settings.manage',
    'users.manage',
    'audit.read',
  ],
  recruiter: ['prehire.read', 'candidates.read', 'jobs.read', 'interview.manage'],
}

export function authorityForMatrixRow(row: CompositionMatrixRow, catalog?: ModuleWorkspaceCatalog[] | null): WorkspaceAuthority {
  const permissions = ROLE_PERMISSIONS_FIXTURE[row.role]
  return resolveWorkspaceAuthority({
    enabledModules: row.modules,
    access: { role: row.role, permissions },
    catalog,
    urgentCount: row.role === 'owner' ? 3 : 0,
    hasRolePriority: row.modules.includes('pre_hiring'),
  })
}
