/**
 * Auth Wave 2 Phase 1 hardening — single classifier for session wipe vs soft-block.
 *
 * Never wipe SecureStore tokens/PIN on ambiguous failures.
 * Wipe only after a definitive server auth signal (or failed refresh proving invalid).
 */

import { ApiError } from '@/api/client'
import type { AppAccessState } from '@/capabilities'

export type AuthFailurePhase =
  | 'boot'
  | 'refresh_me'
  | 'after_refresh_failed'
  | 'api'
  | 'unlock'
  | 'activate'

export type AuthFailureDecision = {
  /** UI access state to present when blocking. */
  accessState: AppAccessState
  /** True only when local tokens + PIN must be destroyed and OTP required. */
  wipeLocalSession: boolean
  /** Stable machine reason for logging before any wipe. */
  reason: string
  /** When true, AuthProvider may set status=blocked. API business errors stay false. */
  blockApp: boolean
}

const REFRESH_FAILED_MARK = '__wathefniAuthRefreshFailed'

/** Tag an error thrown after access 401 + refresh attempt failed. */
export function markRefreshFailed(error: unknown): unknown {
  if (error && typeof error === 'object') {
    try {
      Object.defineProperty(error, REFRESH_FAILED_MARK, { value: true, configurable: true })
    } catch {
      ;(error as Record<string, unknown>)[REFRESH_FAILED_MARK] = true
    }
  }
  return error
}

export function isRefreshFailedError(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && (error as Record<string, unknown>)[REFRESH_FAILED_MARK])
}

/** 401 codes that must wipe immediately — do not attempt refresh first. */
const DEFINITIVE_WIPE_CODES = new Set([
  'account_inactive',
  'stale_session_epoch',
  'app_access_revoked',
])

export function isDefinitiveAuthWipeError(error: unknown): boolean {
  return error instanceof ApiError && DEFINITIVE_WIPE_CODES.has(error.code)
}

const SOFT_ACCESS_CODES: Record<string, AppAccessState> = {
  network_error: 'offline',
  employee_app_disabled: 'app_disabled',
  company_disabled: 'company_disabled',
  company_archived: 'company_archived',
  employee_app_not_enabled_for_company: 'company_app_disabled',
  employee_app_not_allowlisted: 'not_allowlisted',
}

function isServerTransient(error: ApiError): boolean {
  if (error.code === 'network_error') return true
  if (error.status >= 500) return true
  if (error.status === 0) return true
  // Malformed/non-JSON gateway bodies often land as generic "error".
  if (error.status >= 400 && error.code === 'error' && error.status !== 401 && error.status !== 403) {
    return true
  }
  return false
}

function resolvePhase(error: unknown, phase: AuthFailurePhase): AuthFailurePhase {
  if (isRefreshFailedError(error)) return 'after_refresh_failed'
  return phase
}

/**
 * Classify an auth-related failure.
 *
 * `after_refresh_failed` means access token was rejected (401) and refresh was attempted
 * and failed — only then is `app_auth_failed` treated as definitive session death.
 */
export function classifyAuthFailure(
  error: unknown,
  phase: AuthFailurePhase,
): AuthFailureDecision {
  const effectivePhase = resolvePhase(error, phase)

  if (!(error instanceof ApiError)) {
    return {
      accessState: 'unknown_error',
      wipeLocalSession: false,
      reason: `non_api_error:${effectivePhase}`,
      blockApp: effectivePhase !== 'api',
    }
  }

  const soft = SOFT_ACCESS_CODES[error.code]
  if (soft) {
    return {
      accessState: soft,
      wipeLocalSession: false,
      reason: `${error.code}:${effectivePhase}`,
      // Incidental API network blips must not hijack the whole app shell.
      blockApp: !(effectivePhase === 'api' && soft === 'offline'),
    }
  }

  if (isServerTransient(error)) {
    return {
      accessState: error.code === 'network_error' ? 'offline' : 'unknown_error',
      wipeLocalSession: false,
      reason: `transient:${error.status}:${error.code}:${effectivePhase}`,
      blockApp: effectivePhase !== 'api',
    }
  }

  if (error.code === 'account_inactive') {
    return {
      accessState: 'employee_inactive',
      wipeLocalSession: true,
      reason: `account_inactive:${effectivePhase}`,
      blockApp: true,
    }
  }

  // Phase 5 — HR revoke / new-device replacement (server reason hr_revoked|reactivated_via_invite).
  // Never used for network/5xx — those are handled above as soft/transient.
  if (error.code === 'app_access_revoked') {
    return {
      accessState: 'access_reset',
      wipeLocalSession: true,
      reason: `app_access_revoked:${effectivePhase}`,
      blockApp: true,
    }
  }

  if (error.code === 'stale_session_epoch') {
    return {
      accessState: 'session_expired',
      wipeLocalSession: true,
      reason: `stale_session_epoch:${effectivePhase}`,
      blockApp: true,
    }
  }

  if (error.code === 'app_auth_failed' || error.status === 401) {
    // Ambiguous first 401 — callers must refresh first. Only wipe after refresh failed.
    if (effectivePhase === 'after_refresh_failed') {
      return {
        accessState: 'session_expired',
        wipeLocalSession: true,
        reason: `refresh_rejected:${error.code}`,
        blockApp: true,
      }
    }
    return {
      accessState: 'unknown_error',
      wipeLocalSession: false,
      reason: `ambiguous_401:${error.code}:${effectivePhase}`,
      blockApp: effectivePhase !== 'api',
    }
  }

  // Business / feature errors — never wipe, never takeover auth shell.
  return {
    accessState: 'unknown_error',
    wipeLocalSession: false,
    reason: `business_or_unknown:${error.status}:${error.code}:${effectivePhase}`,
    blockApp: false,
  }
}
