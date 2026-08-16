/** Auth Wave 2 Phase 2 — local biometric unlock (never server auth). */

import { isLocalPinEnabledFor, isLocalPinMasterEnabled } from './pinPolicy'

/**
 * Master flag.
 * Explicit `0` forces PIN-only. Explicit `1` enables.
 * Unset inherits PIN master (which defaults ON).
 */
export function isLocalBiometricMasterEnabled(): boolean {
  const raw = String(process.env.EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK ?? '').trim()
  if (raw === '0') return false
  if (raw === '1') return true
  return isLocalPinMasterEnabled()
}

/** Contiguous HBC marker — effective biometric master after defaults. */
export const BIOMETRIC_UNLOCK_BUILD_MARKER = isLocalBiometricMasterEnabled()
  ? 'bio-unlock-effective:on'
  : 'bio-unlock-effective:off'

/**
 * Biometric unlock when masters are on and the session has an employee key.
 * Hardware/enrollment gates live in biometricAuth — not employee allowlists.
 */
export function isLocalBiometricEnabledFor(employeeKey: string | null | undefined): boolean {
  if (!isLocalBiometricMasterEnabled()) return false
  if (!isLocalPinMasterEnabled()) return false
  return isLocalPinEnabledFor(employeeKey)
}
