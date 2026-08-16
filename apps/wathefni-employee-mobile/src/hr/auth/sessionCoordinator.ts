/**
 * Global HR operator refresh coordinator.
 *
 * Survives AuthProvider remounts (OTA, Strict Mode, cold boot). Concurrent
 * 401 handlers await one in-flight refresh. Server-side refresh rotation /
 * replay protection is unchanged — this only prevents the client from
 * presenting a stale refresh after another flight already rotated it.
 */

import { ApiError } from '@hr/api/client'
import type { AuthResponse } from '@hr/api/types'
import {
  clearOperatorSession,
  isNewerOperatorSession,
  loadOperatorSession,
  saveOperatorSession,
  type StoredOperatorSession,
} from './session'

export type OperatorRefreshTransport = (refreshToken: string) => Promise<AuthResponse>

export type OperatorSessionListeners = {
  onRotated?: (session: StoredOperatorSession, me: AuthResponse['me']) => void
}

let inFlight: Promise<StoredOperatorSession> | null = null
let memorySession: StoredOperatorSession | null = null
let listeners: OperatorSessionListeners = {}

export function setOperatorSessionListeners(next: OperatorSessionListeners): void {
  listeners = next
}

/** Test / remount seam — does not clear SecureStore. */
export function resetOperatorSessionCoordinatorForTests(): void {
  inFlight = null
  memorySession = null
  listeners = {}
}

export function getOperatorSessionMemory(): StoredOperatorSession | null {
  return memorySession
}

export function bindOperatorSessionMemory(session: StoredOperatorSession | null): void {
  memorySession = session
}

export function storedOperatorSessionFromAuth(response: AuthResponse): StoredOperatorSession {
  return {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    companyCode: response.me.principal.company_code,
    expiresAt: response.expires_at,
  }
}

function isRefreshReplayError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === 'session_revoked'
}

function isRefreshTerminalError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (error.status !== 401 && error.status !== 403) return false
  return [
    'session_expired',
    'session_revoked',
    'operator_disabled',
    'company_disabled',
    'company_archived',
  ].includes(error.code)
}

/**
 * Resolve the freshest known session among memory, caller hint, and SecureStore.
 */
export async function resolveOperatorSession(
  hint?: StoredOperatorSession | null,
): Promise<StoredOperatorSession | null> {
  const stored = await loadOperatorSession()
  const candidates = [memorySession, hint ?? null, stored].filter(
    (row): row is StoredOperatorSession => Boolean(row),
  )
  if (!candidates.length) return null
  // Prefer the session whose refresh token matches SecureStore when present —
  // that is the durable source of truth across remounts.
  if (stored) {
    const matching = candidates.find((row) => row.refreshToken === stored.refreshToken)
    if (matching) {
      memorySession = stored
      return stored
    }
  }
  // Otherwise prefer the hint/memory that looks newest vs stored.
  let best = candidates[0]
  for (const row of candidates) {
    if (isNewerOperatorSession(best, row)) best = row
  }
  memorySession = best
  return best
}

/**
 * Single-flight refresh. All concurrent callers share one network rotation.
 * On `session_revoked`, reload SecureStore and adopt a newer session if another
 * flight already persisted it — never clear auth in that case.
 */
export async function rotateOperatorSession(
  hint: StoredOperatorSession | null | undefined,
  transport: OperatorRefreshTransport,
): Promise<StoredOperatorSession> {
  if (inFlight) return inFlight

  inFlight = (async () => {
    const presented = await resolveOperatorSession(hint)
    if (!presented?.refreshToken) {
      throw new ApiError(401, 'session_expired', 'Please sign in again.')
    }

    try {
      const response = await transport(presented.refreshToken)
      const next = storedOperatorSessionFromAuth(response)
      await saveOperatorSession(next)
      memorySession = next
      listeners.onRotated?.(next, response.me)
      return next
    } catch (error) {
      if (isRefreshReplayError(error)) {
        const reloaded = await loadOperatorSession()
        if (isNewerOperatorSession(presented, reloaded) && reloaded) {
          memorySession = reloaded
          return reloaded
        }
        // Memory may already hold the winner from a just-finished sibling that
        // wrote before this flight's SecureStore read completed.
        if (isNewerOperatorSession(presented, memorySession) && memorySession) {
          return memorySession
        }
      }
      throw error
    } finally {
      inFlight = null
    }
  })()

  try {
    return await inFlight
  } catch (error) {
    throw error
  }
}

/**
 * Clear local HR operator auth only when SecureStore has no newer valid session
 * than the one that failed. PIN/biometric material is not touched here.
 */
export async function clearOperatorAuthIfNoNewerSession(
  failedWith: StoredOperatorSession | null,
): Promise<'cleared' | 'adopted'> {
  const reloaded = await loadOperatorSession()
  if (isNewerOperatorSession(failedWith, reloaded) && reloaded) {
    memorySession = reloaded
    return 'adopted'
  }
  if (memorySession && isNewerOperatorSession(failedWith, memorySession)) {
    return 'adopted'
  }
  memorySession = null
  await clearOperatorSession()
  return 'cleared'
}

export function shouldClearOperatorAuthAfterRefreshFailure(error: unknown): boolean {
  return isRefreshTerminalError(error)
}
