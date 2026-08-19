import { describe, expect, test } from 'vitest'

import { customerVisibleBatteryName, customerVisibleBrandCopy } from './publicBrand'

describe('customer-visible OctoHR brand copy', () => {
  test('rewrites legacy product names in prose and Arabic', () => {
    expect(customerVisibleBrandCopy('Send through Wathefni')).toBe('Send through OctoHR')
    expect(customerVisibleBrandCopy('Forward CVs to Wathefni.')).toBe('Forward CVs to OctoHR.')
    expect(customerVisibleBrandCopy('حوّل السير إلى وظفني.')).toBe('حوّل السير إلى OctoHR.')
    expect(customerVisibleBrandCopy('مساعد واثقني')).toBe('مساعد OctoHR')
    expect(customerVisibleBatteryName('Wathefni Ability Assessment')).toBe('OctoHR Ability Assessment')
  })

  test('keeps operational hosts, sender ids, and tenant codes', () => {
    expect(customerVisibleBrandCopy('acme@inbound.wathefni.ai')).toBe('acme@inbound.wathefni.ai')
    expect(customerVisibleBrandCopy('hr@wathefni.ai')).toBe('hr@wathefni.ai')
    expect(customerVisibleBrandCopy('wathefni')).toBe('OctoHR')
    expect(customerVisibleBrandCopy('WATHEFNI')).toBe('WATHEFNI')
    expect(customerVisibleBrandCopy('allow_wathefni_emergency_fallback')).toBe('allow_wathefni_emergency_fallback')
    expect(customerVisibleBrandCopy('wathefni_ability_v1')).toBe('wathefni_ability_v1')
  })
})
