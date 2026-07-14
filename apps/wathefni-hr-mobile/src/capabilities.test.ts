import { describe, expect, it } from 'vitest'

import { can, enabledWorkspaces, hasCapability } from './capabilities'
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
})
