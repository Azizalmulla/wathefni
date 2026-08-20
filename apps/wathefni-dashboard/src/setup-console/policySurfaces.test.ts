import { describe, expect, test } from 'vitest'

import { isModuleDeployed, isModuleEntitled, isPolicySurfaceReady } from './policySurfaces'
import type { AvailableModule } from './types'

function module(partial: Partial<AvailableModule> & Pick<AvailableModule, 'key'>): AvailableModule {
  return {
    label: partial.key,
    suite: 'post_hire',
    configured: false,
    platform_available: true,
    effective: false,
    ...partial,
  }
}

describe('policy surface gating', () => {
  test('blocked performance is not a live Wave 4 card', () => {
    const performance = module({
      key: 'performance',
      configured: false,
      can_enable: false,
      effective_state: {
        effective_state: 'unavailable_deployment',
        deployment: { reason_code: 'pilot_allowlist', message_en: 'Blocked by a deployment allowlist or pilot gate.' },
      },
    })
    expect(isModuleEntitled(performance)).toBe(false)
    expect(isModuleDeployed(performance)).toBe(false)
    expect(isPolicySurfaceReady(performance)).toBe(false)
  })

  test('stored but allowlist-blocked is still not a live editor', () => {
    const performance = module({
      key: 'performance',
      configured: true,
      stored_enabled: true,
      usable: false,
      effective: false,
      effective_state: {
        effective_state: 'unavailable_deployment',
        stored_enabled: true,
        usable: false,
        deployment: { reason_code: 'pilot_allowlist' },
      },
    })
    expect(isModuleEntitled(performance)).toBe(true)
    expect(isPolicySurfaceReady(performance)).toBe(false)
  })

  test('entitled and usable performance can open Wave 4', () => {
    const performance = module({
      key: 'performance',
      configured: true,
      stored_enabled: true,
      usable: true,
      effective: true,
      effective_state: { effective_state: 'enabled_usable', usable: true, stored_enabled: true },
    })
    expect(isPolicySurfaceReady(performance)).toBe(true)
  })

  test('missing HTTP is not deployed', () => {
    const er = module({
      key: 'employee_relations',
      configured: true,
      stored_enabled: true,
      effective_state: {
        effective_state: 'unavailable_deployment',
        deployment: { reason_code: 'not_deployed' },
      },
    })
    expect(isModuleDeployed(er)).toBe(false)
    expect(isPolicySurfaceReady(er)).toBe(false)
  })
})
