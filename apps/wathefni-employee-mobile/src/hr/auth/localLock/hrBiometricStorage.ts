import * as SecureStore from 'expo-secure-store'

const ENABLED_KEY = 'wathefni.hr.biometric.enabled'
const LEVEL_KEY = 'wathefni.hr.biometric.enrolled_level'
const OFFERED_KEY = 'wathefni.hr.biometric.offered'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }

export async function isHrBiometricPreferenceEnabled(): Promise<boolean> {
  const raw = await SecureStore.getItemAsync(ENABLED_KEY)
  return raw === '1'
}

export async function getHrStoredBiometricLevel(): Promise<number | null> {
  const raw = await SecureStore.getItemAsync(LEVEL_KEY)
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export async function wasHrBiometricOffered(): Promise<boolean> {
  const raw = await SecureStore.getItemAsync(OFFERED_KEY)
  return raw === '1'
}

export async function markHrBiometricOffered(): Promise<void> {
  await SecureStore.setItemAsync(OFFERED_KEY, '1', STORE_OPTS)
}

export async function setHrBiometricPreference(enabled: boolean, enrolledLevel: number): Promise<void> {
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
    SecureStore.setItemAsync(OFFERED_KEY, '1', STORE_OPTS),
  ])
}

export async function disableHrBiometricPreference(): Promise<void> {
  await setHrBiometricPreference(false, 0)
}

export async function clearHrBiometricPreference(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ENABLED_KEY),
    SecureStore.deleteItemAsync(LEVEL_KEY),
    SecureStore.deleteItemAsync(OFFERED_KEY),
  ])
}
