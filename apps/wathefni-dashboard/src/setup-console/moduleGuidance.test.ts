import { describe, expect, test } from 'vitest'

import {
  applyBundleModules,
  deriveAppSurfaces,
  expandHardDependencies,
  removeModuleWithDependents,
  softRecommendations,
} from './moduleGuidance'
import type { AvailableModule, ModuleBundle } from './types'

const catalog: AvailableModule[] = [
  {
    key: 'pre_hiring',
    label: 'Pre-Hiring',
    suite: 'pre_hire',
    configured: false,
    platform_available: true,
    effective: false,
  },
  {
    key: 'assessments',
    label: 'Assessments',
    suite: 'pre_hire',
    configured: false,
    platform_available: true,
    effective: false,
    depends_on: ['pre_hiring'],
    recommended_with: ['video_interviews'],
    recommendation_copy: 'Requires Pre-Hiring.',
  },
  {
    key: 'video_interviews',
    label: 'Video Interviews',
    suite: 'pre_hire',
    configured: false,
    platform_available: true,
    effective: false,
    depends_on: ['pre_hiring'],
  },
  {
    key: 'attendance',
    label: 'Attendance',
    suite: 'post_hire',
    configured: false,
    platform_available: true,
    effective: false,
    recommended_with: ['shifts'],
    recommendation_copy: 'Recommend Shifts for scheduled work.',
    app_surface_key: 'attendance',
    app_surface_label: 'Attendance status',
  },
  {
    key: 'shifts',
    label: 'Shifts',
    suite: 'post_hire',
    configured: false,
    platform_available: true,
    effective: false,
    app_surface_key: 'shifts',
    app_surface_label: 'Today and upcoming shifts',
  },
  {
    key: 'leave',
    label: 'Leave',
    suite: 'post_hire',
    configured: false,
    platform_available: true,
    effective: false,
    app_surface_key: 'leave',
    app_surface_label: 'Leave requests and status',
  },
  {
    key: 'payroll',
    label: 'Payroll',
    suite: 'post_hire',
    configured: false,
    platform_available: true,
    effective: false,
    recommended_with: ['attendance', 'leave'],
    recommendation_copy: 'Recommend Attendance and Leave. HR-dashboard-first for V1.',
  },
  {
    key: 'employee_app',
    label: 'Employee App',
    suite: 'post_hire',
    configured: false,
    platform_available: false,
    effective: false,
    app_surface_key: 'inbox',
    app_surface_label: 'In-app inbox and push',
  },
]

describe('moduleGuidance', () => {
  test('auto-includes hard dependencies with clear notices', () => {
    const result = expandHardDependencies(['assessments'], catalog)
    expect(result.selected).toEqual(['assessments', 'pre_hiring'])
    expect(result.notices[0]).toMatch(/Assessments requires Pre-Hiring, so Pre-Hiring was included/)
  })

  test('soft recommendations never force selection', () => {
    const recs = softRecommendations(['payroll'], catalog)
    expect(recs.map((item) => item.key).sort()).toEqual(['attendance', 'leave'])
    expect(expandHardDependencies(['payroll'], catalog).selected).toEqual(['payroll'])
  })

  test('bundle apply unions modules and expands hard deps', () => {
    const bundle: ModuleBundle = {
      id: 'hiring_assessment_suite',
      label: 'Hiring Assessment Suite',
      description: 'Full candidate evaluation',
      modules: ['assessments', 'video_interviews'],
    }
    const result = applyBundleModules([], catalog, bundle)
    expect(result.selected).toEqual(['assessments', 'pre_hiring', 'video_interviews'])
  })

  test('operator can remove a recommended module after a bundle apply', () => {
    const bundle: ModuleBundle = {
      id: 'workforce_operations',
      label: 'Workforce Operations',
      description: 'Suggested package',
      modules: ['shifts', 'attendance', 'leave', 'payroll'],
    }
    const applied = applyBundleModules([], catalog, bundle)
    expect(applied.selected).toEqual(['attendance', 'leave', 'payroll', 'shifts'])
    const removed = removeModuleWithDependents(applied.selected, catalog, 'shifts')
    expect(removed.selected).toEqual(['attendance', 'leave', 'payroll'])
  })

  test('app surface preview derives from selected modules only when employee_app is on', () => {
    expect(deriveAppSurfaces(['attendance', 'leave'], catalog)).toEqual([])
    const surfaces = deriveAppSurfaces(['employee_app', 'attendance', 'payroll'], catalog)
    expect(surfaces.map((surface) => surface.surface_key).sort()).toEqual(['attendance', 'inbox'])
  })
})
