import { describe, expect, test } from 'vitest'

import { canManageAlertsAndDelivery } from './alertsDeliveryAccess'

describe('canManageAlertsAndDelivery', () => {
  test('owner-style users.manage is enough', () => {
    expect(canManageAlertsAndDelivery(['users.manage'])).toBe(true)
  })

  test('module operators with *.manage can open the page', () => {
    expect(canManageAlertsAndDelivery(['leave.manage'])).toBe(true)
    expect(canManageAlertsAndDelivery(['onboarding.read'])).toBe(false)
  })

  test('recruiter-style permissions fail closed', () => {
    expect(canManageAlertsAndDelivery(['prehire.read', 'candidates.read', 'jobs.read', 'interview.manage'])).toBe(false)
    expect(canManageAlertsAndDelivery([])).toBe(false)
    expect(canManageAlertsAndDelivery(undefined)).toBe(false)
  })
})
