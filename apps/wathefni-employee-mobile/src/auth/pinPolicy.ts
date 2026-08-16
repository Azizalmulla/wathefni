/** Auth Wave 2 Phase 1 — local PIN policy (no server involvement). */

export const PIN_LENGTH = 6
export const PIN_MAX_FAILED_ATTEMPTS = 5

/**
 * Master flag.
 * Explicit `0` disables. Explicit `1` enables.
 * Unset/empty defaults ON so a missed OTA env cannot silently remove Auth Wave 2.
 */
export function isLocalPinMasterEnabled(): boolean {
  const raw = String(process.env.EXPO_PUBLIC_LOCAL_PIN_UNLOCK ?? '').trim()
  if (raw === '0') return false
  if (raw === '1') return true
  return true
}

/** Contiguous HBC marker — effective PIN master after defaults. */
export const PIN_UNLOCK_BUILD_MARKER = isLocalPinMasterEnabled()
  ? 'pin-unlock-effective:on'
  : 'pin-unlock-effective:off'

/**
 * PIN unlock for any signed-in Employee App session when the master flag is on.
 * No employee-key allowlist — device/session eligibility only.
 */
export function isLocalPinEnabledFor(employeeKey: string | null | undefined): boolean {
  if (!isLocalPinMasterEnabled()) return false
  return Boolean(String(employeeKey || '').trim())
}

export function isValidPinFormat(pin: string): boolean {
  return /^\d{6}$/.test(pin)
}
