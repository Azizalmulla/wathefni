/**
 * HR local-lock eligibility — same EXPO_PUBLIC masters as Employee Wave 2,
 * bound to operator principal key (never employee_key).
 */

import {
  isLocalAutoLockBiometricEnabled,
  isLocalAutoLockMasterEnabled,
} from '@/auth/autoLockPolicy'
import { isLocalBiometricMasterEnabled } from '@/auth/biometricPolicy'
import { isLocalPinMasterEnabled } from '@/auth/pinPolicy'

export function isHrLocalPinEnabledFor(principalKey: string | null | undefined): boolean {
  if (!isLocalPinMasterEnabled()) return false
  return Boolean(String(principalKey || '').trim())
}

export function isHrLocalBiometricEnabledFor(principalKey: string | null | undefined): boolean {
  if (!isLocalBiometricMasterEnabled()) return false
  if (!isLocalPinMasterEnabled()) return false
  return isHrLocalPinEnabledFor(principalKey)
}

export function isHrLocalAutoLockEnabledFor(principalKey: string | null | undefined): boolean {
  if (!isLocalAutoLockMasterEnabled()) return false
  if (!isLocalPinMasterEnabled()) return false
  return isHrLocalPinEnabledFor(principalKey)
}

export { isLocalAutoLockBiometricEnabled, isLocalAutoLockMasterEnabled }
