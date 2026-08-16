/** Auth Wave 2 Phase 1 — local PIN policy (no server involvement). */

export const PIN_LENGTH = 6
export const PIN_MAX_FAILED_ATTEMPTS = 5

/** Master flag — must be set at OTA/bundle time for canary. Off → Wave 1 unchanged. */
export function isLocalPinMasterEnabled(): boolean {
  return String(process.env.EXPO_PUBLIC_LOCAL_PIN_UNLOCK || '').trim() === '1'
}

/** Canary employees only (Aziz, Talal). */
export const LOCAL_PIN_CANARY_EMPLOYEE_KEYS = new Set([
  'WATHEFNI-96599338566',
  'WATHEFNI-96550252254',
])

export function isLocalPinEnabledFor(employeeKey: string | null | undefined): boolean {
  if (!isLocalPinMasterEnabled()) return false
  const key = String(employeeKey || '').trim()
  return Boolean(key) && LOCAL_PIN_CANARY_EMPLOYEE_KEYS.has(key)
}

export function isValidPinFormat(pin: string): boolean {
  return /^\d{6}$/.test(pin)
}
