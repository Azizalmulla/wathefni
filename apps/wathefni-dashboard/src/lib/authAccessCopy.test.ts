import { describe, expect, test } from 'vitest'

import { accessIssueFromError, accessIssueMessage, sessionExpiredIssue } from './access'
import { authCopy, isDefaultAuthPrompt } from './authCopy'
import { DashboardApiError } from './api'

describe('auth copy', () => {
  test('keeps Latin OctoHR in Arabic and never uses Wathefni branding', () => {
    expect(authCopy('ar', 'authSignInTitle')).toContain('OctoHR')
    expect(authCopy('en', 'authSignInTitle')).toContain('OctoHR')
    expect(authCopy('ar', 'authBrandBlurb')).not.toMatch(/Wathefni|واثقني/)
    expect(authCopy('en', 'authBrandBlurb')).not.toMatch(/Wathefni|واثقني/)
    expect(authCopy('ar', 'authSignIn')).toBe('تسجيل الدخول')
  })

  test('default sign-in and invite prompts are recognized in both locales', () => {
    expect(isDefaultAuthPrompt(authCopy('en', 'authSignInDescription'))).toBe(true)
    expect(isDefaultAuthPrompt(authCopy('ar', 'authInviteDescription'))).toBe(true)
    expect(isDefaultAuthPrompt(authCopy('en', 'authSessionExpired'))).toBe(false)
  })
})

describe('access issues', () => {
  test('session expired copy is bilingual via the canonical locale', () => {
    const en = sessionExpiredIssue('en')
    const ar = sessionExpiredIssue('ar')
    expect(en.description).toMatch(/session expired/i)
    expect(ar.description).toBe(authCopy('ar', 'authSessionExpired'))
    expect(accessIssueMessage(en, 'ar')).toBe(authCopy('ar', 'authSessionExpired'))
  })

  test('401 maps to session expired for the requested locale', () => {
    const error = new DashboardApiError(401, { error: 'dashboard_auth_failed' }, 'Unauthorized')
    const issue = accessIssueFromError(error, 'ar')
    expect(issue?.copyKey).toBe('authSessionExpired')
    expect(issue?.description).toBe(authCopy('ar', 'authSessionExpired'))
  })

  test('omitted locale keeps English descriptions for signed-in consumers', () => {
    const error = new DashboardApiError(403, { error: 'permission_denied' }, 'Forbidden')
    const issue = accessIssueFromError(error)
    expect(issue?.description).toBe(
      'Your HR role does not include pre-hiring access. Ask a company Owner or HR Manager to update your role.',
    )
    expect(accessIssueMessage(issue!, 'ar')).toBe(authCopy('ar', 'authRoleCannotOpenBody'))
  })
})
