import { describe, expect, test } from 'vitest'

import { accessIssueFromError, accessIssueMessage, isSessionAuthFailure, sessionExpiredIssue } from './access'
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

  test('resource-level permission_denied does not become a global auth wall', () => {
    const error = new DashboardApiError(403, { error: 'permission_denied' }, 'Forbidden')
    expect(isSessionAuthFailure(error)).toBe(false)
    expect(accessIssueFromError(error)).toBeNull()
    expect(accessIssueFromError(error, 'ar')).toBeNull()
  })

  test('module and action forbids stay in-page', () => {
    expect(accessIssueFromError(new DashboardApiError(403, { error: 'module_disabled' }, 'Off'))).toBeNull()
    expect(accessIssueFromError(new DashboardApiError(403, { error: 'action_forbidden' }, 'No'))).toBeNull()
  })

  test('401 and identity failures remain session-ending', () => {
    expect(isSessionAuthFailure(new DashboardApiError(401, { error: 'dashboard_auth_failed' }, 'Unauthorized'))).toBe(true)
    expect(isSessionAuthFailure(new DashboardApiError(403, { error: 'hr_user_not_allowed' }, 'No'))).toBe(true)
    expect(isSessionAuthFailure(new DashboardApiError(403, { error: 'account_inactive' }, 'No'))).toBe(true)
    expect(isSessionAuthFailure(new DashboardApiError(400, { error: 'dashboard_company_required' }, 'No'))).toBe(true)
  })
})
