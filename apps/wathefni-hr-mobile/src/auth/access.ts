import { ApiError } from '@/api/client'

export type OperatorAccessState =
  | 'active'
  | 'session_expired'
  | 'session_revoked'
  | 'operator_disabled'
  | 'company_disabled'
  | 'company_archived'
  | 'rate_limited'
  | 'permission_revoked'
  | 'scope_denied'
  | 'unknown_error'

const codeMap: Record<string, OperatorAccessState> = {
  session_expired: 'session_expired',
  session_revoked: 'session_revoked',
  operator_disabled: 'operator_disabled',
  company_disabled: 'company_disabled',
  company_archived: 'company_archived',
  rate_limited: 'rate_limited',
  action_forbidden: 'permission_revoked',
  feature_disabled: 'permission_revoked',
  module_disabled: 'permission_revoked',
  permission_authority_unavailable: 'permission_revoked',
  manager_scope_missing: 'scope_denied',
  manager_scope_conflict: 'scope_denied',
  out_of_scope: 'scope_denied',
}

export function accessStateForError(error: unknown): OperatorAccessState {
  if (!(error instanceof ApiError)) return 'unknown_error'
  return codeMap[error.code] || 'unknown_error'
}

export function requiresMeRefresh(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  return [
    'action_forbidden',
    'feature_disabled',
    'module_disabled',
    'manager_scope_missing',
    'manager_scope_conflict',
    'out_of_scope',
    'stale_decision',
  ].includes(error.code)
}
