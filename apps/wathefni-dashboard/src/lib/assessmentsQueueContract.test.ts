import { describe, expect, test } from 'vitest'

import { applicationCountOnly, cohortCountsFromPayload } from './assessmentsQueueContract'

describe('assessmentsQueueContract', () => {
  test('applicationCountOnly ignores people/display and never invents attempt fallbacks', () => {
    expect(
      applicationCountOnly({
        application_count: 2,
        people_count: 9,
        display_count: 9,
        people: 9,
      }),
    ).toBe(2)
    expect(applicationCountOnly({ applications: 3, people_count: 1 })).toBe(3)
    expect(applicationCountOnly({ people_count: 5, display_count: 5 })).toBe(0)
    expect(applicationCountOnly(null)).toBe(0)
  })

  test('cohortCountsFromPayload reads nested cohorts map', () => {
    const counts = cohortCountsFromPayload({
      cohorts: {
        assessment_resend_needed: { application_count: 2 },
        assessment_in_progress: { application_count: 0, people_count: 4 },
      },
    })
    expect(applicationCountOnly(counts.assessment_resend_needed)).toBe(2)
    expect(applicationCountOnly(counts.assessment_in_progress)).toBe(0)
    expect(cohortCountsFromPayload(null)).toEqual({})
  })
})
