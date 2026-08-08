import * as SecureStore from 'expo-secure-store'

const ENABLED_KEY = 'wathefni.biometric.enabled'
const LEVEL_KEY = 'wathefni.biometric.enrolled_level'
const OFFERED_KEY = 'wathefni.biometric.offered'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED }

export async function isBiometricPreferenceEnabled(): Promise<boolean> {
  const raw = await SecureStore.getItemAsync(ENABLED_KEY)
  return raw === '1'
}

export async function getStoredBiometricLevel(): Promise<number | null> {
  const raw = await SecureStore.getItemAsync(LEVEL_KEY)
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

/** True after we have shown the one-time Face ID / Touch ID offer (enable or skip). */
export async function wasBiometricOffered(): Promise<boolean> {
  const raw = await SecureStore.getItemAsync(OFFERED_KEY)
  return raw === '1'
}

export async function markBiometricOffered(): Promise<void> {
  await SecureStore.setItemAsync(OFFERED_KEY, '1', STORE_OPTS)
}

export async function setBiometricPreference(enabled: boolean, enrolledLevel: number): Promise<void> {
  if (enabled) {
    await Promise.all([
      SecureStore.setItemAsync(ENABLED_KEY, '1', STORE_OPTS),
      SecureStore.setItemAsync(LEVEL_KEY, String(enrolledLevel), STORE_OPTS),
      SecureStore.setItemAsync(OFFERED_KEY, '1', STORE_OPTS),
    ])
    return
  }
  await Promise.all([
    SecureStore.deleteItemAsync(ENABLED_KEY),
    SecureStore.deleteItemAsync(LEVEL_KEY),
    // Keep offered=1 so we don't re-prompt after an explicit disable from Settings.
    SecureStore.setItemAsync(OFFERED_KEY, '1', STORE_OPTS),
  ])
}

/** Disable Face ID preference without forgetting that the one-time offer was shown. */
export async function disableBiometricPreference(): Promise<void> {
  await setBiometricPreference(false, 0)
}

/** Full wipe — logout / OTP reset / reinstall path. */
export async function clearBiometricPreference(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ENABLED_KEY),
    SecureStore.deleteItemAsync(LEVEL_KEY),
    SecureStore.deleteItemAsync(OFFERED_KEY),
  ])
}
