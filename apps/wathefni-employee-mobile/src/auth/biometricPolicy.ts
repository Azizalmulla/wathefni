/** Auth Wave 2 Phase 2 — local biometric unlock (never server auth). */

import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'

/**
 * Master flag — set at native/OTA bundle time for canary.
 * Explicit `0` forces PIN-only. Explicit `1` enables.
 * If unset but PIN unlock is on, enable biometrics so a missing env cannot
 * silently skip Face ID on a PIN-enabled canary build.
 */
export function isLocalBiometricMasterEnabled(): boolean {
  const raw = String(process.env.EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK || '').trim()
  if (raw === '0') return false
  if (raw === '1') return true
  return isLocalPinMasterEnabled()
}

/** Same canary employees as PIN (Aziz, Talal). */
export const LOCAL_BIOMETRIC_CANARY_EMPLOYEE_KEYS = new Set([
  'WATHEFNI-96599338566',
  'WATHEFNI-96550252254',
])

export function isLocalBiometricEnabledFor(employeeKey: string | null | undefined): boolean {
  if (!isLocalBiometricMasterEnabled()) return false
  if (!isLocalPinMasterEnabled()) return false
  const key = String(employeeKey || '').trim()
  if (!key || !LOCAL_BIOMETRIC_CANARY_EMPLOYEE_KEYS.has(key)) return false
  return isLocalPinEnabledFor(key)
}
