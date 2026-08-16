import { DashboardApiError } from '@/lib/api'

export type AccessIssue = {
  code: string
  title: string
  description: string
}

/** Calm copy shown when the saved session is no longer valid. */
export function sessionExpiredIssue(): AccessIssue {
  return {
    code: 'dashboard_auth_failed',
    title: 'Sign in to OctoHR',
    description: 'Your session expired. Please sign in again.',
  }
}

/** Map API auth/access failures to the sign-in screen. Returns null for ordinary errors. */
export function accessIssueFromError(error: unknown): AccessIssue | null {
  if (!(error instanceof DashboardApiError)) return null
  if (error.status === 401 || error.code === 'dashboard_auth_failed') {
    return sessionExpiredIssue()
  }
  if (error.code === 'dashboard_user_identity_required') {
    return {
      code: error.code,
      title: 'Sign in to OctoHR',
      description: 'Your session expired. Please sign in again.',
    }
  }
  if (error.code === 'dashboard_company_required') {
    return {
      code: error.code,
      title: 'Sign in to OctoHR',
      description: 'Your session expired. Please sign in again.',
    }
  }
  if (error.code === 'hr_user_not_allowed') {
    return {
      code: error.code,
      title: 'Access not allowed for this company',
      description: 'This HR phone is not registered for the selected company. Check the company code and HR phone, then sign in again.',
    }
  }
  if (error.code === 'permission_denied') {
    return {
      code: error.code,
      title: 'Your role cannot open this dashboard',
      description: 'Your HR role does not include pre-hiring access. Ask a company Owner or HR Manager to update your role.',
    }
  }
  if (error.code === 'account_inactive') {
    return {
      code: error.code,
      title: 'Your account is not active',
      description: 'Your account is not active. Ask a company Owner or HR Manager to restore access.',
    }
  }
  return null
}
