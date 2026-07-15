import { describe, expect, it } from 'vitest'

import {
  can,
  destinationAvailable,
  enabledWorkspaces,
  hasCapability,
  routeAvailable,
  workspaceRoutes,
} from './capabilities'
import { meFixture } from './preview/fixtures'

describe('capability-driven navigation', () => {
  it('never infers workspaces from role names', () => {
    const me = meFixture('hr-only')
    me.principal.role = 'owner'
    expect(enabledWorkspaces(me)).toEqual(['hr'])
  })

  it('shows only backend-enabled recruiting workspace', () => {
    expect(enabledWorkspaces(meFixture('recruiter-only'))).toEqual(['recruiting'])
    expect(enabledWorkspaces(meFixture('multi-workspace'))).toEqual(['hr', 'recruiting'])
  })

  it('keeps employee search grant-only', () => {
    const me = meFixture('hr-only')
    expect(hasCapability(me, 'hr', 'employee_search')).toBe(false)
    expect(can(me, 'hr', 'employee_search', 'read')).toBe(false)
  })

  it('requires the exact action returned by the backend', () => {
    const me = meFixture('multi-workspace')
    expect(can(me, 'recruiting', 'candidate_hire', 'hire')).toBe(true)
    expect(can(me, 'recruiting', 'candidate_hire', 'reject')).toBe(false)
  })

  it('builds workspace navigation only from capability grants', () => {
    const recruiter = meFixture('recruiter-only')
    recruiter.principal.role = 'hr_manager'
    expect(workspaceRoutes(recruiter).map((route) => route.key)).toEqual(['candidates', 'interviews'])
    expect(routeAvailable(recruiter, 'attendance')).toBe(false)
  })

  it('hides routes immediately when a feature is disabled', () => {
    const me = meFixture('multi-workspace')
    me.workspaces.hr.features.attendance_exceptions.enabled = false
    expect(routeAvailable(me, 'attendance')).toBe(false)
  })

  it('does not open a priority destination outside current capabilities', () => {
    expect(destinationAvailable(meFixture('recruiter-only'), '/attendance')).toBe(false)
    expect(destinationAvailable(meFixture('hr-only'), '/candidates/c-1')).toBe(false)
    expect(destinationAvailable(meFixture('multi-workspace'), '/candidates/c-1')).toBe(true)
    expect(destinationAvailable(meFixture('multi-workspace'), '/unknown-admin')).toBe(false)
  })
})
