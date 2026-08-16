/**
 * Setup Console Phase 5 — Employee App composition contract.
 *
 * Single client-side derivation from `/app/me` features (Setup Console entitlements).
 * Do not invent a parallel feature registry from company_modules names.
 */
import type { EmployeeFeatureKey, MeResponse } from '@/api/types'
import { canUseFeatureAction, hasFeature } from '@/capabilities'

/** Platform shell — always available when the employee is signed in. */
export const CORE_SURFACES = ['home', 'inbox', 'profile', 'settings'] as const

/** Entitlement-controlled module surfaces (purchased / enabled company modules). */
export const MODULE_SURFACES = [
  'onboarding',
  'documents',
  'attendance',
  'shifts',
  'leave',
  'payslips',
  'bank',
  'performance',
  'talent',
  'learning',
  'benefits',
  'engagement',
] as const

export type ModuleSurface = (typeof MODULE_SURFACES)[number]

/**
 * Home destinations. `schedule` is the single surface over the Shifts and Attendance
 * authorities: the employee has one workday, so exposing two backend modules as two
 * destinations exposed our boundaries rather than their day.
 */
export type HomeModuleTile =
  | 'schedule'
  | 'leave'
  | 'documents'
  | 'payslips'
  | 'performance'
  | 'talent'
  | 'learning'
  | 'benefits'
  | 'engagement'

export type HomeDestination = {
  id: HomeModuleTile
  /** Canonical registry route; Home never assembles a path of its own. */
  href: string
}

export type HomePrimaryAction = {
  id: 'leave_request'
  href: string
}

/**
 * Module surfaces that own a bottom tab when entitled.
 *
 * Home does not re-advertise these: a module reachable in one tap from every
 * screen does not also need a card on Home. Documents is deliberately absent —
 * it has no tab, so Home is its only launcher.
 */
export const TABBED_MODULE_SURFACES = ['schedule', 'leave', 'payslips'] as const

export type EmployeeAppComposition = {
  /** Core shell flags (inbox is platform, not a purchased module). */
  core: {
    home: true
    inbox: true
    profile: true
    settings: true
  }
  modules: Record<ModuleSurface, boolean>
  /**
   * Schedule presents whichever of Shifts / Attendance is entitled. It is a combined
   * read of existing authority, never a new one, so it appears when either is on.
   */
  schedule: {
    available: boolean
    shifts: boolean
    attendance: boolean
  }
  /** Every entitled module surface, in canonical order. Excludes Inbox. */
  homeTiles: HomeModuleTile[]
  /** Wide layout when 0–1 entitlement tiles (intentional sparse Home). */
  wideHomeTiles: boolean
  /**
   * What Home actually offers as a destination: the entitled modules that have no
   * bottom tab. Schedule, Leave and Payslips are permanently one tap away, so
   * repeating them on Home was three routes to the same place.
   */
  homeDestinations: HomeDestination[]
  /**
   * Primary action shown beside the destinations. Requesting leave is a different
   * job from browsing leave, so it survives the Leave tab; a plain "open Leave"
   * shortcut would not.
   */
  homePrimaryAction: HomePrimaryAction | null
  /** Show temporary onboarding journey chrome (attention / incomplete checklist). */
  showOnboardingJourney: boolean
  /** Demote onboarding after completion — no empty permanent module. */
  onboardingDemoted: boolean
  /**
   * Preboarding / probation are journeys, not Home tiles. Reachable from Home
   * journey cards, Profile, and push — never from MODULE_SURFACES destinations.
   */
  showPreboardingJourney: boolean
  showProbationJourney: boolean
  /**
   * Bottom tab visibility. Inbox is deliberately not a tab: it is a platform
   * surface an employee visits when something arrives, not a place they work, so
   * it lives behind the unread bell in the Home header and keeps a tab slot for a
   * module they use. Optional tabs disappear entirely when unentitled rather than
   * leaving a dead slot.
   */
  tabs: {
    home: true
    schedule: boolean
    leave: boolean
    payslips: boolean
    profile: true
  }
  /** Inbox entry point. Reachable from Home, push and deep links — never a tab. */
  inboxEntry: {
    surface: 'home_header'
    href: string
  }
  /** No separate employee Compliance tab — Documents owns compliance. */
  separateComplianceTab: false
}

export type OnboardingJourneyState = {
  featureEnabled: boolean
  requiredPending: number
  pendingCount: number
  requiredTotal: number
}

const TILE_ROUTES: Record<HomeModuleTile, string> = {
  schedule: '/(tabs)/schedule',
  leave: '/(tabs)/leave',
  documents: '/documents',
  payslips: '/payslips',
  performance: '/performance',
  talent: '/talent',
  learning: '/learning',
  benefits: '/benefits',
  engagement: '/engagement',
}

export function compositionFromMe(
  me: MeResponse | null,
  onboarding?: OnboardingJourneyState | null,
): EmployeeAppComposition {
  const modules = {
    onboarding: hasFeature(me, 'onboarding'),
    documents: hasFeature(me, 'documents'),
    attendance: hasFeature(me, 'attendance'),
    shifts: hasFeature(me, 'shifts'),
    leave: hasFeature(me, 'leave'),
    payslips: hasFeature(me, 'payslips'),
    bank: hasFeature(me, 'bank'),
    performance: hasFeature(me, 'performance'),
    talent: hasFeature(me, 'talent'),
    learning: hasFeature(me, 'learning'),
    benefits: hasFeature(me, 'benefits'),
    engagement: hasFeature(me, 'engagement'),
  } satisfies Record<ModuleSurface, boolean>

  const schedule = {
    available: modules.shifts || modules.attendance,
    shifts: modules.shifts,
    attendance: modules.attendance,
  }

  const homeTiles: HomeModuleTile[] = []
  if (schedule.available) homeTiles.push('schedule')
  if (modules.leave) homeTiles.push('leave')
  if (modules.documents) homeTiles.push('documents')
  if (modules.payslips) homeTiles.push('payslips')
  if (modules.performance) homeTiles.push('performance')
  if (modules.talent) homeTiles.push('talent')
  if (modules.learning) homeTiles.push('learning')
  if (modules.benefits) homeTiles.push('benefits')
  if (modules.engagement) homeTiles.push('engagement')

  const requiredPending = onboarding?.requiredPending ?? 0
  const pendingCount = onboarding?.pendingCount ?? 0
  const featureOn = Boolean(onboarding?.featureEnabled ?? modules.onboarding)
  const incomplete = featureOn && (requiredPending > 0 || pendingCount > 0)
  const completed =
    featureOn &&
    !incomplete &&
    (onboarding?.requiredTotal ?? 0) > 0 &&
    requiredPending === 0 &&
    pendingCount === 0

  const tabbed = new Set<HomeModuleTile>(TABBED_MODULE_SURFACES)

  return {
    core: { home: true, inbox: true, profile: true, settings: true },
    modules,
    schedule,
    homeTiles,
    wideHomeTiles: homeTiles.length <= 1,
    homeDestinations: homeTiles
      .filter((id) => !tabbed.has(id))
      .map((id) => ({ id, href: TILE_ROUTES[id] })),
    homePrimaryAction: canUseFeatureAction(me, 'leave', 'request')
      ? { id: 'leave_request', href: '/leave/request' }
      : null,
    showOnboardingJourney: incomplete,
    onboardingDemoted: completed || !featureOn,
    showPreboardingJourney: hasFeature(me, 'preboarding'),
    showProbationJourney: hasFeature(me, 'probation'),
    tabs: {
      home: true,
      schedule: schedule.available,
      leave: modules.leave,
      payslips: modules.payslips,
      profile: true,
    },
    inboxEntry: { surface: 'home_header', href: INBOX_ROUTE },
    separateComplianceTab: false,
  }
}

/**
 * Explicit route registry. Every navigable in-app destination is listed once with the
 * entitlement that owns it and the query parameters it accepts. Nothing outside this
 * table is navigable: substring guessing let an unknown or hostile path through as long
 * as it happened to contain a known word, and it silently accepted parameters no screen
 * reads. `core` = always allowed once signed in.
 */
export const HOME_ROUTE = '/(tabs)' as const

/**
 * Inbox is a pushed screen rather than a tab, so its canonical path leaves the
 * tab group. The old `/(tabs)/notifications` path stays an alias below: push
 * payloads and notifications already in flight still carry it.
 */
export const INBOX_ROUTE = '/notifications' as const

type RouteSpec = {
  /**
   * Owning entitlement. A tuple means the destination combines existing authorities and
   * opens when *any* of them is entitled (Schedule over Shifts / Attendance); it never
   * grants access to an authority the employee does not have.
   */
  feature: EmployeeFeatureKey | 'core' | readonly EmployeeFeatureKey[]
  /** Query parameters this route reads. Any other parameter makes the link invalid. */
  params?: readonly string[]
}

export const APP_ROUTES = {
  '/(tabs)': { feature: 'core' },
  '/(tabs)/index': { feature: 'core' },
  '/notifications': { feature: 'core' },
  '/(tabs)/profile': { feature: 'core' },
  '/settings': { feature: 'core' },
  '/privacy-support': { feature: 'core' },
  '/change-pin': { feature: 'core' },
  '/(tabs)/schedule': { feature: ['shifts', 'attendance'] },
  '/schedule/history': { feature: 'attendance' },
  '/(tabs)/leave': { feature: 'leave' },
  '/leave/request': { feature: 'leave' },
  '/leave/history': { feature: 'leave' },
  '/documents': { feature: 'documents' },
  '/onboarding': { feature: 'onboarding' },
  '/preboarding': { feature: 'preboarding' },
  '/probation': { feature: 'probation' },
  '/performance': { feature: 'performance' },
  '/performance/goals': { feature: 'performance' },
  '/performance/reviews': { feature: 'performance' },
  '/performance/check-ins': { feature: 'performance' },
  '/performance/development': { feature: 'performance' },
  '/talent': { feature: 'talent' },
  '/talent/profile': { feature: 'talent' },
  '/learning': { feature: 'learning' },
  '/learning/catalog': { feature: 'learning' },
  '/learning/certificates': { feature: 'learning' },
  '/learning/session': { feature: 'learning', params: ['session_id'] },
  '/benefits': { feature: 'benefits' },
  '/benefits/plan': { feature: 'benefits', params: ['plan_id'] },
  '/benefits/history': { feature: 'benefits' },
  '/engagement': { feature: 'engagement' },
  '/engagement/survey': { feature: 'engagement', params: ['campaign_id'] },
  '/payslips': { feature: 'payslips', params: ['payslip_id'] },
  '/bank': { feature: 'bank' },
} as const satisfies Record<string, RouteSpec>

export type AppRoute = keyof typeof APP_ROUTES

/**
 * Server/notification aliases for canonical routes. Kept explicit, never inferred.
 * `/shifts` and `/attendance` are the pre-Schedule paths that shift reminders and older
 * notifications still carry, so both land on the combined surface. `/(tabs)/notifications`
 * is the pre-bell Inbox path and is kept for the same reason.
 */
const ROUTE_ALIASES: Record<string, AppRoute> = {
  '/': '/(tabs)',
  '/home': '/(tabs)',
  '/inbox': '/notifications',
  '/(tabs)/notifications': '/notifications',
  '/profile': '/(tabs)/profile',
  '/schedule': '/(tabs)/schedule',
  '/shifts': '/(tabs)/schedule',
  '/(tabs)/shifts': '/(tabs)/schedule',
  '/attendance': '/(tabs)/schedule',
  '/attendance/history': '/schedule/history',
  '/leave': '/(tabs)/leave',
}

export type ResolvedRoute = {
  route: AppRoute
  params: Record<string, string>
  /** Canonical href to hand to the router, with validated params re-encoded. */
  href: string
}

const PARAM_VALUE = /^[A-Za-z0-9_.:-]{1,128}$/

/**
 * Resolve a candidate path against the registry. Returns null for anything absolute,
 * unknown, or carrying a parameter the destination does not read — the caller then
 * falls back to Home instead of pushing a route that would dead-end.
 */
export function resolveRoute(path: string): ResolvedRoute | null {
  const raw = String(path || '').trim()
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return null
  // Reject anything that is not a plain in-app path.
  if (/[\s<>"'\\]/.test(raw) || raw.includes('://') || raw.includes('..')) return null
  const [rawPath, rawQuery = ''] = raw.split('?')
  if (rawQuery.includes('?') || rawQuery.includes('#') || rawPath.includes('#')) return null
  const trimmed = rawPath.length > 1 && rawPath.endsWith('/') ? rawPath.slice(0, -1) : rawPath
  const route = (trimmed in APP_ROUTES ? (trimmed as AppRoute) : ROUTE_ALIASES[trimmed]) ?? null
  if (!route) return null
  const spec: RouteSpec = APP_ROUTES[route]
  const allowed = new Set<string>(spec.params ?? [])
  const params: Record<string, string> = {}
  for (const pair of rawQuery.split('&')) {
    if (!pair) continue
    const eq = pair.indexOf('=')
    const name = eq === -1 ? pair : pair.slice(0, eq)
    const value = eq === -1 ? '' : decodeURIComponent(pair.slice(eq + 1))
    if (!allowed.has(name)) return null
    if (!PARAM_VALUE.test(value)) return null
    params[name] = value
  }
  const query = Object.entries(params)
    .map(([name, value]) => `${name}=${encodeURIComponent(value)}`)
    .join('&')
  return { route, params, href: query ? `${route}?${query}` : route }
}

function routeAllowed(me: MeResponse | null, route: AppRoute): boolean {
  const { feature } = APP_ROUTES[route] as RouteSpec
  if (feature === 'core') return true
  if (typeof feature === 'string') return hasFeature(me, feature)
  return feature.some((key) => hasFeature(me, key))
}

/**
 * Feature key owning a deep-link path. `core` = always allowed when signed in; a tuple
 * means the destination combines authorities and any one of them admits it.
 */
export function featureKeyForPath(
  path: string,
): EmployeeFeatureKey | 'core' | readonly EmployeeFeatureKey[] | null {
  const resolved = resolveRoute(path)
  return resolved ? (APP_ROUTES[resolved.route] as RouteSpec).feature : null
}

export function canOpenPath(me: MeResponse | null, path: string): boolean {
  const resolved = resolveRoute(path)
  return resolved ? routeAllowed(me, resolved.route) : false
}

/**
 * Resolve a link for navigation: canonical href when the route exists and the employee
 * is entitled, otherwise null so the caller can fall back to Home calmly.
 */
export function openableHref(me: MeResponse | null, path: string): string | null {
  const resolved = resolveRoute(path)
  if (!resolved) return null
  return routeAllowed(me, resolved.route) ? resolved.href : null
}

/** Task kinds emitted by the server `/app/home` projection. */
export const HOME_TASK_KINDS = [
  'onboarding_documents',
  'document_renewal',
  'leave_pending',
  'payslip_released',
] as const

export type HomeTaskKind = (typeof HOME_TASK_KINDS)[number]

/**
 * Optional per-task detail. Today only `document_renewal` carries it: the
 * documents module's own row for the most urgent renewal, passed through by the
 * Home projection. Every field is the owning module's value — nothing here is
 * derived, and a task without detail is normal, not degraded.
 */
export type ServerHomeTaskDetail = {
  document_type?: string | null
  label?: string | null
  expiry_date?: string | null
  review_status?: string | null
}

export type ServerHomeTask = {
  kind?: string
  module?: string
  count?: number
  severity?: string
  detail?: ServerHomeTaskDetail | null
}

export type HomeTask = {
  id: string
  kind: HomeTaskKind
  href: AppRoute
  count: number
  severity: 'action_required' | 'informational'
  detail: ServerHomeTaskDetail | null
}

const TASK_ROUTES: Record<HomeTaskKind, AppRoute> = {
  onboarding_documents: '/onboarding',
  document_renewal: '/documents',
  leave_pending: '/(tabs)/leave',
  payslip_released: '/payslips',
}

/**
 * Present the server's task projection. The owning modules decide that a task exists;
 * the client only maps it to its own route and drops tasks it cannot open (entitlement
 * removed between the projection and the tap).
 */
export function homeTasksFromServer(
  me: MeResponse | null,
  tasks: ServerHomeTask[] | null | undefined,
): HomeTask[] {
  const out: HomeTask[] = []
  for (const task of tasks ?? []) {
    const kind = String(task?.kind || '') as HomeTaskKind
    if (!HOME_TASK_KINDS.includes(kind)) continue
    const href = TASK_ROUTES[kind]
    if (!canOpenPath(me, href)) continue
    out.push({
      id: kind,
      kind,
      href,
      count: Number(task?.count ?? 0),
      severity: task?.severity === 'informational' ? 'informational' : 'action_required',
      detail: normalizeTaskDetail(task?.detail),
    })
  }
  return out
}

/**
 * Keep only string fields the server actually sent. A detail object that
 * survives with every field empty is dropped, so the caller's "is there detail?"
 * check cannot be satisfied by an empty shell.
 */
function normalizeTaskDetail(detail: ServerHomeTaskDetail | null | undefined): ServerHomeTaskDetail | null {
  if (!detail || typeof detail !== 'object') return null
  const out: ServerHomeTaskDetail = {}
  for (const key of ['document_type', 'label', 'expiry_date', 'review_status'] as const) {
    const value = String(detail[key] ?? '').trim()
    if (value) out[key] = value
  }
  return Object.keys(out).length ? out : null
}
