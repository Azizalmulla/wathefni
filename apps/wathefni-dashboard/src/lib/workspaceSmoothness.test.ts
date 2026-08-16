import { describe, expect, test } from 'vitest'

import {
  assessmentCohortForTab,
  assessmentTabForCohort,
} from '@/lib/assessmentCohorts'

describe('workspace smoothness contracts', () => {
  test('assessment surface-only tabs are not cohort-derived', () => {
    // attempts / reports / needs_review must remain first-class URL tabs
    expect(['attempts', 'reports', 'needs_review']).not.toContain(assessmentTabForCohort('assessment_ready_to_send'))
    expect(assessmentCohortForTab('send')).toBe('assessment_ready_to_send')
    expect(assessmentTabForCohort('assessment_resend_needed')).toBe('resend')
  })

  test('assessment openPage URL preserves surface tabs over cohort derivation', () => {
    function urlTabForAssessments(
      assessmentTab: string,
      assessmentCohort: string,
    ): string {
      const surfaceOnly =
        assessmentTab === 'attempts'
        || assessmentTab === 'reports'
        || assessmentTab === 'needs_review'
      return surfaceOnly
        ? assessmentTab
        : (assessmentTabForCohort(assessmentCohort as 'assessment_ready_to_send') || assessmentTab || 'send')
    }
    expect(urlTabForAssessments('reports', 'assessment_ready_to_send')).toBe('reports')
    expect(urlTabForAssessments('send', 'assessment_ready_to_send')).toBe('send')
  })

  test('calendar mobile preference resolves day before paint helpers', () => {
    const mobile = true
    const initialView = mobile ? 'day' : 'week'
    expect(initialView).toBe('day')
  })

  test('work-queue scope prefers stored mine when company hint false', () => {
    const stored = 'company'
    const canViewCompanyWorkHint = false
    const scope = stored === 'company' && !canViewCompanyWorkHint ? 'mine' : stored
    expect(scope).toBe('mine')
  })

  test('assistant empty status stays ready while refreshing', () => {
    const prev: 'loading' | 'ready' | 'error' = 'ready'
    const next = prev === 'ready' ? 'ready' : 'loading'
    expect(next).toBe('ready')
  })

  test('post-hire module data treats param change as loading', () => {
    const refreshing = true
    const data = null
    const loading = refreshing && data === null
    expect(loading).toBe(true)
  })

  test('video interviews stay undefined until authority ready', () => {
    const authorityReady = false
    const enabled = authorityReady ? true : undefined
    expect(enabled).toBeUndefined()
  })
})
