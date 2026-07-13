import { ApiError } from '@/api/client'

type Translate = (key: string) => string

export function approvedErrorMessage(error: unknown, t: Translate): string {
  if (!(error instanceof ApiError)) return t('error.generic')
  switch (error.code) {
    case 'network_error':
      return t('access.offline.message')
    case 'employee_app_disabled':
      return t('access.app_disabled.message')
    case 'company_disabled':
      return t('access.company_disabled.message')
    case 'company_archived':
      return t('access.company_archived.message')
    case 'employee_app_not_enabled_for_company':
      return t('access.company_app_disabled.message')
    case 'account_inactive':
      return t('access.employee_inactive.message')
    case 'app_auth_failed':
      return t('access.session_expired.message')
    case 'app_activation_failed':
      return t('auth.invalidCode')
    case 'too_many_attempts':
      return t('auth.tooManyAttempts')
    case 'already_activated':
      return t('auth.alreadyActivated')
    case 'employee_feature_disabled':
      return t('feature.unavailable.message')
    case 'leave_type_not_available':
      return t('leave.typeUnavailable')
    default:
      return t('error.generic')
  }
}
