import { describe, expect, test } from 'vitest'

import { resolvePrehireAuthority } from './prehireAuthority'

describe('resolvePrehireAuthority', () => {
  test('waits fail-closed until bootstrap settles', () => {
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: false,
        bootstrapError: false,
        bootstrapMissing: false,
        bootstrapEnabledModules: ['pre_hiring'],
      }),
    ).toEqual({ hasPrehire: false, fetchSummary: false, fetchPrehireCore: false })
  })

  test('bootstrap-dark does not invent pre_hiring before summary modules arrive', () => {
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: false,
        bootstrapMissing: true,
      }),
    ).toEqual({ hasPrehire: false, fetchSummary: true, fetchPrehireCore: false })
  })

  test('bootstrap-dark uses summary.enabled_modules only, never summary presence', () => {
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: false,
        bootstrapMissing: true,
        summaryEnabledModules: ['compliance'],
      }).hasPrehire,
    ).toBe(false)
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: false,
        bootstrapMissing: true,
        summaryEnabledModules: ['pre_hiring'],
      }),
    ).toEqual({ hasPrehire: true, fetchSummary: true, fetchPrehireCore: true })
  })

  test('canonical bootstrap modules win and fail closed when pre_hiring is absent', () => {
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: false,
        bootstrapMissing: false,
        bootstrapEnabledModules: ['attendance', 'leave'],
        summaryEnabledModules: ['pre_hiring'],
      }),
    ).toEqual({ hasPrehire: false, fetchSummary: false, fetchPrehireCore: false })
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: false,
        bootstrapMissing: false,
        bootstrapEnabledModules: ['pre_hiring'],
      }),
    ).toEqual({ hasPrehire: true, fetchSummary: true, fetchPrehireCore: true })
  })

  test('bootstrap errors fail closed', () => {
    expect(
      resolvePrehireAuthority({
        bootstrapSettled: true,
        bootstrapError: true,
        bootstrapMissing: false,
        bootstrapEnabledModules: ['pre_hiring'],
      }),
    ).toEqual({ hasPrehire: false, fetchSummary: false, fetchPrehireCore: false })
  })
})
