/**
 * HR dashboard workspace helpers derived from the canonical module catalog.
 *
 * Source of truth: wathefni-orchestrator/module_catalog.py
 * employee_app is an employee-surface entitlement and must never appear in HR nav.
 */

import type { DashboardModuleDefinition } from '@/types'

/** Fallback when /dashboard/bootstrap is dark (WATHEFNI_WORKSPACE_BOOT off). */
export const CANONICAL_POSTHIRE_MODULES = [
  'onboarding',
  'compliance',
  'attendance',
  'shifts',
  'leave',
  'payroll',
  'analytics',
] as const

export const CANONICAL_POSTHIRE_PEOPLE_MODULES = [
  'onboarding',
  'compliance',
  'attendance',
  'shifts',
  'leave',
  'payroll',
] as const

/** Post-Hire sidebar pages (includes Employees people surface). */
export const POSTHIRE_NAV_PAGES = [
  'employees',
  'workforce',
  'inbox',
  'onboarding',
  'attendance',
  'leave',
  'shifts',
  'payroll',
  'analytics',
  'compliance',
] as const

export type PostHireNavPage = (typeof POSTHIRE_NAV_PAGES)[number]

export const HR_NAV_EXCLUDED_MODULES = ['employee_app'] as const

export type ModuleWorkspaceCatalog = Pick<
  DashboardModuleDefinition,
  'key' | 'suite' | 'people_surface' | 'effective' | 'configured' | 'platform_available'
>

export function isHrNavExcludedModule(moduleKey: string | null | undefined): boolean {
  return HR_NAV_EXCLUDED_MODULES.includes(moduleKey as (typeof HR_NAV_EXCLUDED_MODULES)[number])
}

export function postHireModuleKeys(catalog?: ModuleWorkspaceCatalog[] | null): string[] {
  if (catalog && catalog.length > 0) {
    return catalog
      .filter((module) => module.suite === 'post_hire' && !isHrNavExcludedModule(module.key))
      .map((module) => module.key)
  }
  return [...CANONICAL_POSTHIRE_MODULES]
}

export function peopleModuleKeys(catalog?: ModuleWorkspaceCatalog[] | null): string[] {
  if (catalog && catalog.length > 0) {
    return catalog
      .filter((module) => module.people_surface && !isHrNavExcludedModule(module.key))
      .map((module) => module.key)
  }
  return [...CANONICAL_POSTHIRE_PEOPLE_MODULES]
}

export function enabledModuleSet(enabledModules: string[] | null | undefined): Set<string> {
  return new Set(Array.isArray(enabledModules) ? enabledModules : [])
}

export function moduleEnabled(enabledModules: string[] | null | undefined, moduleKey: string): boolean {
  return enabledModuleSet(enabledModules).has(moduleKey)
}

export function anyPosthireModuleEnabled(
  enabledModules: string[] | null | undefined,
  catalog?: ModuleWorkspaceCatalog[] | null,
): boolean {
  const enabled = enabledModuleSet(enabledModules)
  if (enabled.size === 0) return false
  return postHireModuleKeys(catalog).some((key) => enabled.has(key))
}

export function anyPeopleModuleEnabled(
  enabledModules: string[] | null | undefined,
  catalog?: ModuleWorkspaceCatalog[] | null,
): boolean {
  const enabled = enabledModuleSet(enabledModules)
  if (enabled.size === 0) return false
  return peopleModuleKeys(catalog).some((key) => enabled.has(key))
}

/** Alerts & Delivery is a shared Workspace surface (page id remains `notifications`). */
export function isAlertsAndDeliveryRelevant(
  enabledModules: string[] | null | undefined,
  catalog?: ModuleWorkspaceCatalog[] | null,
): boolean {
  return moduleEnabled(enabledModules, 'pre_hiring') || anyPosthireModuleEnabled(enabledModules, catalog)
}

export function isPostHireNavPage(page: string): page is PostHireNavPage {
  return (POSTHIRE_NAV_PAGES as readonly string[]).includes(page)
}

/**
 * Post-hire operational modules that can be a focused default landing.
 * Employees / Workforce / Inbox are spine or composition surfaces — not SKUs.
 */
export const POSTHIRE_OPERATIONAL_LANDING_PRIORITY = [
  'leave',
  'attendance',
  'shifts',
  'payroll',
  'onboarding',
  'compliance',
  'analytics',
] as const

export type PostHireOperationalLandingPage = (typeof POSTHIRE_OPERATIONAL_LANDING_PRIORITY)[number]

export const PEOPLE_SURFACE_MODULE_KEYS = [
  'onboarding',
  'compliance',
  'attendance',
  'shifts',
  'leave',
  'payroll',
] as const

/** True when Action Inbox has at least one entitled compose source for this tenant/actor. */
export function actionInboxHasEntitledSource(args: {
  enabledModules: string[] | null | undefined
  permissions?: string[] | null
  catalog?: ModuleWorkspaceCatalog[] | null
}): boolean {
  const enabled = enabledModuleSet(args.enabledModules)
  const perms = new Set((args.permissions || []).map(String))
  const permOk = (p: string) => perms.has(p) || perms.has('*:*') || perms.size === 0
  if (enabled.has('analytics') && permOk('analytics.read')) return true
  if (enabled.has('compliance') && permOk('compliance.read')) return true
  if (anyPeopleModuleEnabled(args.enabledModules, args.catalog)) {
    if (permOk('employees.read') || permOk('settings.manage') || permOk('users.manage')) return true
  }
  return false
}

/**
 * Focused Workforce Experience landing (Module-Aware Shell Wave 0).
 * - Pre-Hiring Overview when pre_hiring + overview available
 * - One operational module → that module
 * - Several → Action Inbox when offerable and entitled source exists; else priority primary
 * - Employees stays visible but is not the default when an ops module exists
 */
export function resolveFocusedPosthireLanding(args: {
  enabledModules: string[] | null | undefined
  availablePageIds: string[]
  prehireEnabled: boolean
  overviewAvailable: boolean
  actionInboxOfferable: boolean
  permissions?: string[] | null
  catalog?: ModuleWorkspaceCatalog[] | null
}): string {
  const available = new Set(args.availablePageIds)
  if (args.prehireEnabled && args.overviewAvailable && available.has('overview')) {
    return 'overview'
  }

  const enabled = enabledModuleSet(args.enabledModules)
  const operational = POSTHIRE_OPERATIONAL_LANDING_PRIORITY.filter(
    (page) => enabled.has(page) && available.has(page),
  )

  if (operational.length === 1) {
    return operational[0]
  }

  if (operational.length >= 2) {
    if (
      args.actionInboxOfferable &&
      available.has('inbox') &&
      actionInboxHasEntitledSource({
        enabledModules: args.enabledModules,
        permissions: args.permissions,
        catalog: args.catalog,
      })
    ) {
      return 'inbox'
    }
    return operational[0]
  }

  if (available.has('employees')) return 'employees'
  if (available.has('inbox') && args.actionInboxOfferable) return 'inbox'
  return args.availablePageIds[0] || 'settings'
}

export function filterHrNavModuleKey(moduleKey: string | null | undefined): string | null {
  if (!moduleKey || isHrNavExcludedModule(moduleKey)) return null
  return moduleKey
}

/** Scope Alerts delivery issue rows by enabled modules (Shell Wave 0). */
export function scopeDeliveryNotificationRows<T extends Record<string, unknown>>(
  rows: T[],
  enabledModules?: string[] | null,
): T[] {
  if (!enabledModules?.length) return rows
  if (enabledModules.includes('pre_hiring')) return rows
  const posthireOn = enabledModules.some((key) =>
    ['onboarding', 'compliance', 'attendance', 'leave', 'shifts', 'payroll', 'analytics'].includes(key),
  )
  if (!posthireOn) return []
  return rows.filter((item) => {
    const blob = [
      item.last_error,
      item.dashboard_status,
      item.status,
      item.app_key,
      item.position_title,
      item.candidate_name,
    ]
      .map((value) => String(value || '').toLowerCase())
      .join(' ')
    if (
      blob.includes('assessment') ||
      blob.includes('interview') ||
      blob.includes('screening') ||
      blob.includes('video_interview')
    ) {
      return false
    }
    if (
      blob.includes('onboarding') ||
      blob.includes('compliance') ||
      blob.includes('employee') ||
      blob.includes('leave') ||
      blob.includes('shift') ||
      blob.includes('attendance') ||
      blob.includes('payroll')
    ) {
      return true
    }
    if (item.candidate_name || item.app_key || item.position_code) return false
    return true
  })
}

export type NavShapeProof = {
  prehireVisible: boolean
  posthireVisible: boolean
  alertsAndDeliveryVisible: boolean
  employeeAppInNav: boolean
  visibleIds: string[]
}

export function navShapeForModules(
  enabledModules: string[],
  navItems: Array<{ id: string; module?: string; group: string }>,
  catalog?: ModuleWorkspaceCatalog[] | null,
  options: { auditRead?: boolean } = {},
): NavShapeProof {
  const visible = navItems.filter((item) => {
    if (item.id === 'employees' || item.id === 'workforce') return anyPeopleModuleEnabled(enabledModules, catalog)
    if (item.id === 'notifications') return isAlertsAndDeliveryRelevant(enabledModules, catalog)
    if (item.id === 'activity') return options.auditRead === true
    if (item.id === 'settings') return true
    const moduleKey = filterHrNavModuleKey(item.module)
    if (!moduleKey) return !item.module
    return moduleEnabled(enabledModules, moduleKey)
  })
  const visibleIds = visible.map((item) => item.id)
  return {
    prehireVisible: visible.some((item) => item.group === 'prehire'),
    posthireVisible: visible.some((item) => item.group === 'posthire'),
    alertsAndDeliveryVisible: visibleIds.includes('notifications'),
    employeeAppInNav: visibleIds.includes('employee_app') || visible.some((item) => item.module === 'employee_app'),
    visibleIds,
  }
}
