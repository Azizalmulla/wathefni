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

export function filterHrNavModuleKey(moduleKey: string | null | undefined): string | null {
  if (!moduleKey || isHrNavExcludedModule(moduleKey)) return null
  return moduleKey
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
    if (item.id === 'employees') return anyPeopleModuleEnabled(enabledModules, catalog)
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
