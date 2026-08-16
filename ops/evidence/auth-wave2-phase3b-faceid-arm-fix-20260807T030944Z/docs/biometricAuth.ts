/**
 * Thin local biometric wrapper around expo-local-authentication.
 * Biometrics never talk to the backend — they only unlock the local PIN/session gate.
 */

import {
  disableBiometricPreference,
  getStoredBiometricLevel,
  isBiometricPreferenceEnabled,
} from './biometricStorage'

export type BiometricKind = 'face' | 'fingerprint' | 'biometrics'

export type BiometricAvailability = {
  nativeModule: boolean
  hardware: boolean
  enrolled: boolean
  kind: BiometricKind
  enrolledLevel: number
  /** True when we can offer / use Face ID / Touch ID on this device. */
  usable: boolean
}

type LocalAuthModule = typeof import('expo-local-authentication')

function loadLocalAuth(): LocalAuthModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('expo-local-authentication') as LocalAuthModule & { default?: LocalAuthModule }
    return (mod as { default?: LocalAuthModule }).default ?? mod
  } catch (error) {
    console.warn('[biometric] native module unavailable', error)
    return null
  }
}

const UNAVAILABLE: BiometricAvailability = {
  nativeModule: false,
  hardware: false,
  enrolled: false,
  kind: 'biometrics',
  enrolledLevel: 0,
  usable: false,
}

export async function getBiometricAvailability(): Promise<BiometricAvailability> {
  const LocalAuthentication = loadLocalAuth()
  if (!LocalAuthentication) return UNAVAILABLE
  try {
    const [hardware, enrolled, types, enrolledLevel] = await Promise.all([
      LocalAuthentication.hasHardwareAsync(),
      LocalAuthentication.isEnrolledAsync(),
      LocalAuthentication.supportedAuthenticationTypesAsync(),
      LocalAuthentication.getEnrolledLevelAsync(),
    ])
    const hasFace = types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)
    const hasFinger = types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)
    let kind: BiometricKind = 'biometrics'
    if (hasFace && !hasFinger) kind = 'face'
    else if (hasFinger && !hasFace) kind = 'fingerprint'

    // Offer when the device has biometric hardware + enrollment.
    // Do not require BIOMETRIC_STRONG alone — iOS/Android level enums have shifted across
    // SDK revisions; hardware+enrolled is the reliable Face ID / Touch ID signal.
    const biometricLevelOk =
      enrolledLevel >= LocalAuthentication.SecurityLevel.BIOMETRIC_WEAK ||
      enrolledLevel >= 2 ||
      enrolled
    const usable = Boolean(hardware && enrolled && biometricLevelOk)

    console.warn('[biometric] availability', {
      hardware,
      enrolled,
      enrolledLevel,
      types,
      kind,
      usable,
    })

    return {
      nativeModule: true,
      hardware,
      enrolled,
      kind,
      enrolledLevel,
      usable,
    }
  } catch (error) {
    console.warn('[biometric] availability check failed', error)
    return UNAVAILABLE
  }
}

/**
 * Prefer biometric only when the user opted in and device biometrics still match.
 * If enrollment was removed, clear preference and fall back to PIN.
 */
export async function shouldAttemptBiometricUnlock(): Promise<{
  attempt: boolean
  preferred: boolean
  availability: BiometricAvailability
}> {
  const availability = await getBiometricAvailability()
  const preferred = await isBiometricPreferenceEnabled()
  if (!preferred) return { attempt: false, preferred: false, availability }
  // Only clear preference when enrollment is clearly gone — not on transient
  // availability failures during resume / Modal presentation.
  if (availability.nativeModule && availability.hardware && !availability.enrolled) {
    await disableBiometricPreference()
    return { attempt: false, preferred: false, availability }
  }
  if (!availability.usable) {
    return { attempt: false, preferred: true, availability }
  }
  const storedLevel = await getStoredBiometricLevel()
  if (storedLevel != null && storedLevel > 0 && availability.enrolledLevel === 0) {
    await disableBiometricPreference()
    return { attempt: false, preferred: false, availability }
  }
  return { attempt: true, preferred: true, availability }
}

export type BiometricPromptResult =
  | { ok: true }
  | { ok: false; reason: 'cancel' | 'fail' | 'unavailable' }

/** Local-only prompt. Never contacts the backend. PIN is the app fallback. */
export async function promptBiometricUnlock(opts: {
  promptMessage: string
  cancelLabel: string
}): Promise<BiometricPromptResult> {
  const LocalAuthentication = loadLocalAuth()
  if (!LocalAuthentication) return { ok: false, reason: 'unavailable' }
  const availability = await getBiometricAvailability()
  if (!availability.usable) return { ok: false, reason: 'unavailable' }
  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: opts.promptMessage,
      cancelLabel: opts.cancelLabel,
      // PIN is our canonical fallback — never bounce to device passcode.
      disableDeviceFallback: true,
      fallbackLabel: '',
      // Prefer strong when available; Android still accepts Class 3 fingerprints / Face.
      // Defaulting to weak would also work; strong matches Face ID / Touch ID intent.
      biometricsSecurityLevel: 'strong',
    })
    if (result.success) return { ok: true }
    const err = String(result.error || '')
    if (err === 'user_cancel' || err === 'system_cancel' || err === 'app_cancel') {
      return { ok: false, reason: 'cancel' }
    }
    // If strong fails as not available on some Android devices, retry once without strong.
    if (err === 'not_available' || err === 'not_enrolled') {
      const retry = await LocalAuthentication.authenticateAsync({
        promptMessage: opts.promptMessage,
        cancelLabel: opts.cancelLabel,
        disableDeviceFallback: true,
        fallbackLabel: '',
        biometricsSecurityLevel: 'weak',
      })
      if (retry.success) return { ok: true }
      const retryErr = String(retry.error || '')
      if (retryErr === 'user_cancel' || retryErr === 'system_cancel' || retryErr === 'app_cancel') {
        return { ok: false, reason: 'cancel' }
      }
      return { ok: false, reason: 'fail' }
    }
    return { ok: false, reason: 'fail' }
  } catch (error) {
    console.warn('[biometric] authenticate failed', error)
    return { ok: false, reason: 'fail' }
  }
}
