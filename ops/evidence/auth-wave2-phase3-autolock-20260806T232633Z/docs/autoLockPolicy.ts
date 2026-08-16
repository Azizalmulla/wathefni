/** Auth Wave 2 Phase 3 — local auto-lock policy (never server auth). */

import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'

/** Explicit 0 forces off. Explicit 1 on. Unset inherits PIN master (canary builds). */
export function isLocalAutoLockMasterEnabled(): boolean {
  const raw = String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || '').trim()
  if (raw === '0') return false
  if (raw === '1') return true
  return isLocalPinMasterEnabled()
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

/**
 * Whether returning from background should require local unlock.
 * Device screen-lock always requires unlock (when feature on).
 * Time-based lock uses the employee timeout setting.
 */
export function shouldAutoLockOnResume(opts: {
  elapsedMs: number
  timeoutMs: AutoLockTimeoutMs
  deviceWasLocked: boolean
}): boolean {
  if (opts.deviceWasLocked) return true
  if (opts.timeoutMs == null) return false
  return opts.elapsedMs >= opts.timeoutMs
}
