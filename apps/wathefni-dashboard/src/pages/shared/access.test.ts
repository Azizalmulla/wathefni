import { describe, expect, test } from 'vitest'

import { hasActorPermission, hasDashboardPermission, hasJobsPermission } from './access'
import type { DashboardUserAccess } from '@/types'

function access(permissions: string[]): DashboardUserAccess {
  return { role: 'hr_admin', permissions }
}

describe('dashboard permission checks', () => {
  test('missing access and empty grants fail closed', () => {
    expect(hasDashboardPermission(null, 'jobs.create')).toBe(false)
    expect(hasDashboardPermission(access([]), 'jobs.create')).toBe(false)
    expect(hasJobsPermission(null, 'jobs.create')).toBe(false)
    expect(hasJobsPermission(access([]), 'jobs.read')).toBe(false)
    expect(hasActorPermission([], 'employees.read')).toBe(false)
  })

  test('exact jobs.* grants are sufficient', () => {
    const jobs = access(['jobs.read', 'jobs.create', 'jobs.edit', 'jobs.publish', 'jobs.close'])
    expect(hasJobsPermission(jobs, 'jobs.read')).toBe(true)
    expect(hasJobsPermission(jobs, 'jobs.create')).toBe(true)
    expect(hasJobsPermission(jobs, 'jobs.close')).toBe(true)
  })

  test('frontend does not expand Jobs access from settings.manage or prehire.read', () => {
    expect(hasJobsPermission(access(['settings.manage']), 'jobs.create')).toBe(false)
    expect(hasJobsPermission(access(['settings.manage']), 'jobs.edit')).toBe(false)
    expect(hasJobsPermission(access(['settings.manage']), 'jobs.publish')).toBe(false)
    expect(hasJobsPermission(access(['settings.manage']), 'jobs.close')).toBe(false)
    expect(hasJobsPermission(access(['settings.manage']), 'jobs.read')).toBe(false)
    expect(hasJobsPermission(access(['prehire.read']), 'jobs.read')).toBe(false)
    expect(hasJobsPermission(access(['prehire.read']), 'jobs.create')).toBe(false)
  })

  test('wildcard *:* matches any requested permission', () => {
    expect(hasDashboardPermission(access(['*:*']), 'jobs.create')).toBe(true)
    expect(hasDashboardPermission(access(['*:*']), 'employees.read')).toBe(true)
    expect(hasJobsPermission(access(['*:*']), 'jobs.close')).toBe(true)
    expect(hasActorPermission(['*:*'], 'talent.manage')).toBe(true)
  })

  test('unrelated permissions do not expand Jobs access', () => {
    expect(hasJobsPermission(access(['users.manage', 'candidates.read']), 'jobs.create')).toBe(false)
    expect(hasJobsPermission(access(['users.manage']), 'jobs.read')).toBe(false)
  })
})
