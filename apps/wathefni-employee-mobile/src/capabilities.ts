import { ApiError } from '@/api/client'
import type { EmployeeFeatureKey, MeResponse } from '@/api/types'

export type AppAccessState =
  | 'active'
  | 'offline'
  | 'app_disabled'
  | 'company_disabled'
  | 'company_archived'
  | 'company_app_disabled'
  | 'employee_inactive'
  | 'session_expired'
  | 'unknown_error'

export function accessStateForError(error: unknown): AppAccessState {
  if (!(error instanceof ApiError)) return 'unknown_error'
  switch (error.code) {
    case 'network_error':
      return 'offline'
    case 'employee_app_disabled':
      return 'app_disabled'
    case 'company_disabled':
      return 'company_disabled'
    case 'company_archived':
      return 'company_archived'
    case 'employee_app_not_enabled_for_company':
      return 'company_app_disabled'
    case 'account_inactive':
      return 'employee_inactive'
    case 'app_auth_failed':
      return 'session_expired'
    default:
      return 'unknown_error'
  }
}

export function hasFeature(me: MeResponse | null, feature: EmployeeFeatureKey): boolean {
  return Boolean(me?.features?.[feature]?.enabled)
}

export function canUseFeatureAction(
  me: MeResponse | null,
  feature: EmployeeFeatureKey,
  action: string,
): boolean {
  const capability = me?.features?.[feature]
  return Boolean(capability?.enabled && capability.actions.includes(action))
}
