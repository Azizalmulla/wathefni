import { describe, expect, test } from 'vitest'

import {
  actionInboxHasEntitledSource,
  resolveFocusedPosthireLanding,
  scopeDeliveryNotificationRows,
} from './moduleWorkspace'
import { resolveWorkspaceAuthority } from './workspaceCapability'
import type { ModuleWorkspaceCatalog } from './moduleWorkspace'

const catalog: ModuleWorkspaceCatalog[] = [
  { key: 'pre_hiring', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'onboarding', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'compliance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'attendance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'leave', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'shifts', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'payroll', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'analytics', suite: 'post_hire', people_surface: false, effective: true, configured: true, platform_available: true },
]

const ownerPerms = [
  'prehire.read',
  'employees.read',
  'leave.read',
  'attendance.read',
  'shifts.read',
  'payroll.read',
  'onboarding.read',
  'compliance.read',
  'analytics.read',
  'settings.manage',
  'users.manage',
  'candidate.manage',
  'jobs.create',
  'report.export',
]

function pagesFor(modules: string[], inboxOfferable = true) {
  const authority = resolveWorkspaceAuthority({
    enabledModules: modules,
    access: { role: 'owner', permissions: ownerPerms },
    catalog,
    actionInboxOfferable: inboxOfferable,
  })
  return authority.navIds
}

function land(modules: string[], inboxOfferable = true) {
  const available = pagesFor(modules, inboxOfferable)
  return resolveFocusedPosthireLanding({
    enabledModules: modules,
    availablePageIds: available,
    prehireEnabled: modules.includes('pre_hiring'),
    overviewAvailable: available.includes('overview'),
    actionInboxOfferable: inboxOfferable && available.includes('inbox'),
    permissions: ownerPerms,
    catalog,
  })
}

describe('module-aware shell wave0 focused landing', () => {
  test('Leave only → leave', () => {
    expect(land(['leave'])).toBe('leave')
    expect(pagesFor(['leave'])).toContain('employees')
    expect(pagesFor(['leave'])).not.toContain('overview')
  })

  test('Shifts only → shifts', () => {
    expect(land(['shifts'])).toBe('shifts')
  })

  test('Attendance only → attendance', () => {
    expect(land(['attendance'])).toBe('attendance')
  })

  test('Payroll only → payroll', () => {
    expect(land(['payroll'])).toBe('payroll')
  })

  test('Onboarding + Compliance → inbox when offerable', () => {
    expect(land(['onboarding', 'compliance'], true)).toBe('inbox')
    expect(land(['onboarding', 'compliance'], false)).toBe('onboarding')
  })

  test('Shifts + Attendance + Leave → inbox when offerable else leave priority', () => {
    expect(land(['shifts', 'attendance', 'leave'], true)).toBe('inbox')
    expect(land(['shifts', 'attendance', 'leave'], false)).toBe('leave')
  })

  test('Leave + Attendance + Shifts + Payroll → inbox when offerable', () => {
    expect(land(['leave', 'attendance', 'shifts', 'payroll'], true)).toBe('inbox')
  })

  test('full suite → overview', () => {
    expect(
      land(
        [
          'pre_hiring',
          'assessments',
          'leave',
          'attendance',
          'shifts',
          'payroll',
          'onboarding',
          'compliance',
          'analytics',
        ],
        true,
      ),
    ).toBe('overview')
  })

  test('entitled inbox source requires people or analytics/compliance', () => {
    expect(
      actionInboxHasEntitledSource({
        enabledModules: ['leave'],
        permissions: ownerPerms,
        catalog,
      }),
    ).toBe(true)
    expect(
      actionInboxHasEntitledSource({
        enabledModules: ['analytics'],
        permissions: ['analytics.read'],
        catalog,
      }),
    ).toBe(true)
    expect(
      actionInboxHasEntitledSource({
        enabledModules: [],
        permissions: ownerPerms,
        catalog,
      }),
    ).toBe(false)
    expect(
      actionInboxHasEntitledSource({
        enabledModules: ['leave'],
        permissions: [],
        catalog,
      }),
    ).toBe(false)
    expect(
      actionInboxHasEntitledSource({
        enabledModules: ['leave'],
        permissions: ['settings.manage', 'users.manage'],
        catalog,
      }),
    ).toBe(false)
    expect(
      actionInboxHasEntitledSource({
        enabledModules: ['leave'],
        permissions: ['*:*'],
        catalog,
      }),
    ).toBe(true)
  })

  test('alerts delivery keeps post-hire rows when pre_hiring off', () => {
    const rows = [
      { delivery_id: '1', last_error: 'onboarding reminder failed', status: 'failed' },
      { delivery_id: '2', last_error: 'assessment delivery failed', candidate_name: 'Ada', status: 'failed' },
      { delivery_id: '3', last_error: 'smtp timeout', status: 'failed' },
    ]
    const scoped = scopeDeliveryNotificationRows(rows, ['leave', 'attendance'])
    expect(scoped.map((r) => r.delivery_id)).toEqual(['1', '3'])
  })
})
