import { describe, expect, test } from 'vitest'

import {
  CANONICAL_POSTHIRE_MODULES,
  CANONICAL_POSTHIRE_PEOPLE_MODULES,
  anyPeopleModuleEnabled,
  anyPosthireModuleEnabled,
  isAlertsAndDeliveryRelevant,
  isHrNavExcludedModule,
  isPostHireNavPage,
  navShapeForModules,
  peopleModuleKeys,
  postHireModuleKeys,
} from './moduleWorkspace'
import type { ModuleWorkspaceCatalog } from './moduleWorkspace'

const catalog: ModuleWorkspaceCatalog[] = [
  { key: 'pre_hiring', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'assessments', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'video_interviews', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'onboarding', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'compliance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'attendance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'shifts', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'leave', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'payroll', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'analytics', suite: 'post_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'employee_app', suite: 'post_hire', people_surface: false, effective: false, configured: true, platform_available: false },
]

const navItems = [
  { id: 'overview', module: 'pre_hiring', group: 'prehire' },
  { id: 'assessments', module: 'assessments', group: 'prehire' },
  { id: 'notifications', group: 'settings' },
  { id: 'employees', group: 'posthire' },
  { id: 'attendance', module: 'attendance', group: 'posthire' },
  { id: 'analytics', module: 'analytics', group: 'posthire' },
  { id: 'activity', group: 'settings' },
  { id: 'settings', group: 'settings' },
]

describe('moduleWorkspace', () => {
  test('canonical fallbacks match module_catalog post-hire sets', () => {
    expect([...CANONICAL_POSTHIRE_MODULES].sort()).toEqual(
      ['analytics', 'attendance', 'benefits', 'comp_planning', 'compliance', 'employee_relations', 'engagement', 'learning', 'leave', 'onboarding', 'payroll', 'performance', 'shifts', 'talent', 'workforce_planning'].sort(),
    )
    expect([...CANONICAL_POSTHIRE_PEOPLE_MODULES].sort()).toEqual(
      ['attendance', 'compliance', 'learning', 'leave', 'onboarding', 'payroll', 'performance', 'shifts', 'talent'].sort(),
    )
    expect(CANONICAL_POSTHIRE_MODULES).not.toContain('employee_app')
    expect(isHrNavExcludedModule('employee_app')).toBe(true)
  })

  test('derives post-hire and people keys from catalog and excludes employee_app', () => {
    expect(postHireModuleKeys(catalog)).toEqual([
      'onboarding',
      'compliance',
      'attendance',
      'shifts',
      'leave',
      'payroll',
      'analytics',
    ])
    expect(peopleModuleKeys(catalog)).toEqual([
      'onboarding',
      'compliance',
      'attendance',
      'shifts',
      'leave',
      'payroll',
    ])
    expect(postHireModuleKeys(catalog)).not.toContain('employee_app')
  })

  test('pre-hire-only shape hides post-hire and keeps Alerts & Delivery', () => {
    const shape = navShapeForModules(['pre_hiring', 'assessments', 'employee_app'], navItems, catalog)
    expect(shape.prehireVisible).toBe(true)
    expect(shape.posthireVisible).toBe(false)
    expect(shape.alertsAndDeliveryVisible).toBe(true)
    expect(shape.employeeAppInNav).toBe(false)
    expect(shape.visibleIds).toEqual(expect.arrayContaining(['overview', 'assessments', 'notifications', 'settings']))
    expect(shape.visibleIds).not.toContain('attendance')
    expect(shape.visibleIds).not.toContain('employees')
  })

  test('post-hire-only shape hides pre-hire and keeps Alerts & Delivery', () => {
    const shape = navShapeForModules(['attendance', 'leave', 'payroll'], navItems, catalog)
    expect(shape.prehireVisible).toBe(false)
    expect(shape.posthireVisible).toBe(true)
    expect(shape.alertsAndDeliveryVisible).toBe(true)
    expect(shape.employeeAppInNav).toBe(false)
    expect(shape.visibleIds).toEqual(expect.arrayContaining(['employees', 'attendance', 'notifications', 'settings']))
    expect(shape.visibleIds).not.toContain('overview')
  })

  test('mixed tenant shows both suites and Alerts & Delivery', () => {
    const shape = navShapeForModules(['pre_hiring', 'attendance', 'analytics'], navItems, catalog, { auditRead: true })
    expect(shape.prehireVisible).toBe(true)
    expect(shape.posthireVisible).toBe(true)
    expect(shape.alertsAndDeliveryVisible).toBe(true)
    expect(shape.visibleIds).toEqual(
      expect.arrayContaining(['overview', 'employees', 'attendance', 'analytics', 'notifications', 'activity', 'settings']),
    )
  })

  test('Alerts & Delivery is irrelevant when no suite modules are enabled', () => {
    expect(isAlertsAndDeliveryRelevant([], catalog)).toBe(false)
    expect(isAlertsAndDeliveryRelevant(['employee_app'], catalog)).toBe(false)
    expect(anyPosthireModuleEnabled(['employee_app'], catalog)).toBe(false)
    expect(anyPeopleModuleEnabled(['analytics'], catalog)).toBe(false)
  })

  test('isPostHireNavPage recognizes people and module pages', () => {
    expect(isPostHireNavPage('employees')).toBe(true)
    expect(isPostHireNavPage('workforce')).toBe(true)
    expect(isPostHireNavPage('compliance')).toBe(true)
    expect(isPostHireNavPage('notifications')).toBe(false)
    expect(isPostHireNavPage('overview')).toBe(false)
  })
})
