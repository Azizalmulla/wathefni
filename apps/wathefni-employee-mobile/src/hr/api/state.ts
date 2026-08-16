import { ApiError } from './client'

export type ResourceState =
  | 'ready'
  | 'loading'
  | 'empty'
  | 'error'
  | 'offline'
  | 'stale'
  | 'success'
  | 'permission'
  | 'revoked'
  | 'company_disabled'
  | 'company_archived'
  | 'session_expired'

export function stateForError(error: unknown): ResourceState {
  if (!(error instanceof ApiError)) return 'error'
  if (error.status === 0 || error.code === 'network_error') return 'offline'
  if (error.code === 'session_expired' || error.code === 'session_revoked') return 'session_expired'
  if (error.code === 'company_disabled') return 'company_disabled'
  if (error.code === 'company_archived') return 'company_archived'
  if (error.code === 'operator_disabled') return 'revoked'
  if (
    [
      'action_forbidden',
      'feature_disabled',
      'module_disabled',
      'permission_authority_unavailable',
      'manager_scope_missing',
      'manager_scope_conflict',
      'out_of_scope',
    ].includes(error.code)
  ) {
    return 'permission'
  }
  if (error.code === 'stale_decision') return 'stale'
  return 'error'
}

export function resourceState({
  loading,
  error,
  empty,
  stale,
  success,
}: {
  loading?: boolean
  error?: unknown
  empty?: boolean
  stale?: boolean
  success?: boolean
}): ResourceState {
  if (loading) return 'loading'
  if (error) return stateForError(error)
  if (success) return 'success'
  if (stale) return 'stale'
  if (empty) return 'empty'
  return 'ready'
}
