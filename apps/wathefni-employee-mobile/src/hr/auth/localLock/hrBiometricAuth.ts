/**
 * HR biometric attempt gate — device APIs shared with Employee; preference from HR store.
 */

import {
  getBiometricAvailability,
  promptBiometricUnlock,
  type BiometricAvailability,
  type BiometricPromptResult,
} from '@/auth/biometricAuth'
import {
  disableHrBiometricPreference,
  getHrStoredBiometricLevel,
  isHrBiometricPreferenceEnabled,
} from './hrBiometricStorage'

export { getBiometricAvailability, promptBiometricUnlock }
export type { BiometricAvailability, BiometricPromptResult }

export async function shouldAttemptHrBiometricUnlock(): Promise<{
  attempt: boolean
  preferred: boolean
  availability: BiometricAvailability
}> {
  const availability = await getBiometricAvailability()
  const preferred = await isHrBiometricPreferenceEnabled()
  if (!preferred) return { attempt: false, preferred: false, availability }
  if (availability.nativeModule && availability.hardware && !availability.enrolled) {
    await disableHrBiometricPreference()
    return { attempt: false, preferred: false, availability }
  }
  if (!availability.usable) {
    return { attempt: false, preferred: true, availability }
  }
  const storedLevel = await getHrStoredBiometricLevel()
  if (storedLevel != null && storedLevel > 0 && availability.enrolledLevel === 0) {
    await disableHrBiometricPreference()
    return { attempt: false, preferred: false, availability }
  }
  return { attempt: true, preferred: true, availability }
}
