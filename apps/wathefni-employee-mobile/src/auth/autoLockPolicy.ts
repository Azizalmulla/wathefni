/** Auth Wave 2 Phase 3 — timeout-only local unlock overlay policy (never server auth). */

import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'

/**
 * Baked into the JS bundle so Settings / HBC inspection can prove which env shipped.
 * Example after inline: `al-overlay-v3:1`
 */
export const AUTO_LOCK_BUILD_MARKER = `al-overlay-v3:${String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || 'unset')}`

/**
 * Explicit `1` required. Default off until overlay architecture is proven.
 * Does not inherit PIN master (avoids accidental enable on canary PIN builds).
 */
export function isLocalAutoLockMasterEnabled(): boolean {
  return String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || '').trim() === '1'
}

/**
 * Face ID on the overlay — separate gate from auto-lock master.
 * Requires explicit `1` after PIN-only overlay is proven crash-free.
 */
export function isLocalAutoLockBiometricEnabled(): boolean {
  return String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC || '').trim() === '1'
}

export const LOCAL_AUTO_LOCK_CANARY_EMPLOYEE_KEYS = new Set([
  'WATHEFNI-96599338566',
  'WATHEFNI-96550252254',
])

export function isLocalAutoLockEnabledFor(employeeKey: string | null | undefined): boolean {
  if (!isLocalAutoLockMasterEnabled()) return false
  if (!isLocalPinMasterEnabled()) return false
  const key = String(employeeKey || '').trim()
  if (!key || !LOCAL_AUTO_LOCK_CANARY_EMPLOYEE_KEYS.has(key)) return false
  return isLocalPinEnabledFor(key)
}

/** Timeout options in milliseconds. `null` = Never (time-based lock off). */
export type AutoLockTimeoutMs = 0 | 30_000 | 60_000 | 300_000 | null

export const AUTO_LOCK_DEFAULT_TIMEOUT_MS: AutoLockTimeoutMs = 30_000

export const AUTO_LOCK_TIMEOUT_OPTIONS: Array<{
  value: AutoLockTimeoutMs
  labelKey: string
}> = [
  { value: 0, labelKey: 'autoLock.immediate' },
  { value: 30_000, labelKey: 'autoLock.seconds30' },
  { value: 60_000, labelKey: 'autoLock.minute1' },
  { value: 300_000, labelKey: 'autoLock.minutes5' },
  { value: null, labelKey: 'autoLock.never' },
]

/**
 * Auto-lock diagnostics panel (update id, raw flags, employee key, gate reasons,
 * timing internals). Debug affordance only — explicit `1` required, so shipped
 * canary/production builds never expose internals to an ordinary employee.
 */
export function isAutoLockDiagnosticsEnabled(): boolean {
  return String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK_DIAGNOSTICS || '').trim() === '1'
}

/** Company policy may disable "Never". Explicit 0 hides it; unset/1 keeps it. */
export function isAutoLockNeverOptionAllowed(): boolean {
  return String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK_ALLOW_NEVER || '').trim() !== '0'
}

export function listAutoLockTimeoutOptions(): Array<{ value: AutoLockTimeoutMs; labelKey: string }> {
  if (isAutoLockNeverOptionAllowed()) return AUTO_LOCK_TIMEOUT_OPTIONS
  return AUTO_LOCK_TIMEOUT_OPTIONS.filter((opt) => opt.value !== null)
}

export function parseAutoLockTimeout(raw: string | null | undefined): AutoLockTimeoutMs {
  if (raw == null || raw === '') return AUTO_LOCK_DEFAULT_TIMEOUT_MS
  if (raw === 'never') {
    return isAutoLockNeverOptionAllowed() ? null : AUTO_LOCK_DEFAULT_TIMEOUT_MS
  }
  const n = Number(raw)
  if (n === 0) return 0
  if (n === 30_000 || n === 60_000 || n === 300_000) return n as AutoLockTimeoutMs
  return AUTO_LOCK_DEFAULT_TIMEOUT_MS
}

export function serializeAutoLockTimeout(value: AutoLockTimeoutMs): string {
  if (value == null) return 'never'
  return String(value)
}

export function clampAutoLockTimeout(value: AutoLockTimeoutMs): AutoLockTimeoutMs {
  if (value == null && !isAutoLockNeverOptionAllowed()) return AUTO_LOCK_DEFAULT_TIMEOUT_MS
  return value
}

export type LocalUnlockDecisionReason = 'timeout' | 'none'

/** Timeout-only. Device screen-lock detector is out of scope for this rebuild. */
export function decideLocalUnlockOnResume(opts: {
  elapsedMs: number
  timeoutMs: AutoLockTimeoutMs
  enteredBackground: boolean
}): LocalUnlockDecisionReason {
  if (!opts.enteredBackground) return 'none'
  if (opts.timeoutMs == null) return 'none'
  if (opts.elapsedMs >= opts.timeoutMs) return 'timeout'
  return 'none'
}
