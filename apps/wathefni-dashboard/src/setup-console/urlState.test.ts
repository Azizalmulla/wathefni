import { describe, expect, test } from 'vitest'

import { readCompanyParam, setupConsoleHref, viewFromLocation } from './urlState'

describe('setup console URL state', () => {
  test('reads company from the query string', () => {
    expect(readCompanyParam('?company=wathefni')).toBe('WATHEFNI')
    expect(readCompanyParam('?view=classic')).toBe('')
  })

  test('defaults to Modules & Access, not Launch Readiness', () => {
    expect(viewFromLocation('', '')).toBe('modules')
    expect(viewFromLocation('?company=WATHEFNI', '')).toBe('modules')
  })

  test('classic deep links still open classic setup except modules and policies', () => {
    expect(viewFromLocation('', '#classic-profile')).toBe('classic')
    expect(viewFromLocation('', '#classic-modules')).toBe('modules')
    expect(viewFromLocation('', '#classic-wave4-performance')).toBe('policies')
    expect(viewFromLocation('?view=policies', '')).toBe('policies')
    expect(viewFromLocation('?view=control', '')).toBe('control')
  })

  test('canonical href keeps company sticky', () => {
    expect(setupConsoleHref({ company: 'wathefni' })).toBe('/setup-console?company=WATHEFNI')
    expect(setupConsoleHref({ company: 'WATHEFNI', view: 'launch' })).toBe(
      '/setup-console?company=WATHEFNI&view=launch',
    )
  })
})
