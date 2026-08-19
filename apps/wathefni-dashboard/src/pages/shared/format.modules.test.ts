import { describe, expect, test } from 'vitest'

import { assessmentModuleEnabled } from '@/pages/shared/format'
import type { SummaryResponse } from '@/types'

function summaryWithAssessmentsFlag(enabled: boolean): SummaryResponse {
  return { features: { assessments_enabled: enabled } } as SummaryResponse
}

describe('assessmentModuleEnabled', () => {
  test('uses enabled_modules and fails closed when the list is missing', () => {
    expect(assessmentModuleEnabled({ enabled_modules: ['pre_hiring', 'assessments'] })).toBe(true)
    expect(assessmentModuleEnabled({ enabled_modules: ['pre_hiring'] })).toBe(false)
    expect(assessmentModuleEnabled(null, summaryWithAssessmentsFlag(true))).toBe(true)
    expect(assessmentModuleEnabled(null, summaryWithAssessmentsFlag(false))).toBe(false)
    expect(assessmentModuleEnabled(null, null)).toBe(false)
    expect(assessmentModuleEnabled({})).toBe(false)
  })

  test('enabled_modules wins over a stale assessments_enabled feature flag', () => {
    expect(assessmentModuleEnabled({ enabled_modules: ['pre_hiring'] }, summaryWithAssessmentsFlag(true))).toBe(false)
  })
})
