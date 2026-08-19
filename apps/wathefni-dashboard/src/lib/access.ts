import { DashboardApiError } from '@/lib/api'
import { authCopy, type AuthCopyKey } from '@/lib/authCopy'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

export type AccessIssue = {
  code: string
  title: string
  description: string
  copyKey?: AuthCopyKey
}

function localizedAuthIssue(
  code: string,
  locale: RecruitingLocale,
  copyKey: AuthCopyKey,
  titleKey: AuthCopyKey = 'authSignInTitle',
): AccessIssue {
  return {
    code,
    title: authCopy(locale, titleKey),
    description: authCopy(locale, copyKey),
    copyKey,
  }
}

/** Calm copy shown when the saved session is no longer valid. */
export function sessionExpiredIssue(locale: RecruitingLocale = 'en'): AccessIssue {
  return localizedAuthIssue('dashboard_auth_failed', locale, 'authSessionExpired')
}

export function accessIssueMessage(issue: AccessIssue, locale: RecruitingLocale): string {
  return issue.copyKey ? authCopy(locale, issue.copyKey) : issue.description
}

/** Map API auth/access failures to the sign-in screen. Returns null for ordinary errors. */
export function accessIssueFromError(error: unknown, locale: RecruitingLocale = 'en'): AccessIssue | null {
  if (!(error instanceof DashboardApiError)) return null
  if (error.status === 401 || error.code === 'dashboard_auth_failed') {
    return sessionExpiredIssue(locale)
  }
  if (error.code === 'dashboard_user_identity_required') {
    return localizedAuthIssue(error.code, locale, 'authSessionExpired')
  }
  if (error.code === 'dashboard_company_required') {
    return localizedAuthIssue(error.code, locale, 'authCompanyRequired')
  }
  if (error.code === 'hr_user_not_allowed') {
    return {
      code: error.code,
      title: locale === 'ar' ? authCopy(locale, 'authAccessNotAllowed') : 'Access not allowed for this company',
      description:
        locale === 'ar'
          ? authCopy(locale, 'authAccessNotAllowedBody')
          : 'This HR phone is not registered for the selected company. Check the company code and HR phone, then sign in again.',
      copyKey: 'authAccessNotAllowedBody',
    }
  }
  if (error.code === 'permission_denied') {
    return {
      code: error.code,
      title: locale === 'ar' ? authCopy(locale, 'authRoleCannotOpen') : 'Your role cannot open this dashboard',
      description:
        locale === 'ar'
          ? authCopy(locale, 'authRoleCannotOpenBody')
          : 'Your HR role does not include pre-hiring access. Ask a company Owner or HR Manager to update your role.',
      copyKey: 'authRoleCannotOpenBody',
    }
  }
  if (error.code === 'account_inactive') {
    return localizedAuthIssue(error.code, locale, 'authAccountInactiveBody', 'authAccountInactive')
  }
  return null
}
