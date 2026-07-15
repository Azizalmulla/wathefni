import { describe, expect, it } from 'vitest'

import { previewOperators, previewScenarios, previewUrl, previewViews } from './inventory'

describe('HR-3 preview inventory', () => {
  it('covers every primary screen family', () => {
    expect(previewViews).toEqual(
      expect.arrayContaining([
        'sign-in',
        'home',
        'tasks',
        'onboarding',
        'documents',
        'attendance',
        'shifts',
        'shift-swap',
        'employees',
        'employee-profile',
        'delivery-alerts',
        'candidates',
        'candidate',
        'interviews',
        'interview',
        'settings',
        'leave',
      ]),
    )
  })

  it('retains the operator and explicit state matrix', () => {
    expect(previewOperators).toHaveLength(4)
    expect(previewScenarios).toEqual(
      expect.arrayContaining(['offline', 'permission', 'company-archived', 'session-expired']),
    )
  })

  it('uses view= and clean controls=0 links', () => {
    const url = previewUrl(
      'http://127.0.0.1:4177/design-preview',
      'employees',
      'ar',
      'restricted-manager',
      'ready',
    )
    expect(url).toContain('view=employees')
    expect(url).toContain('controls=0')
    expect(url).not.toContain('screen=')
  })
})
