import * as SecureStore from 'expo-secure-store'

// Session tokens are kept ONLY in the OS keystore (iOS Keychain / Android
// Keystore) via expo-secure-store — never AsyncStorage or plain files.
const ACCESS_KEY = 'wathefni.session.token'
const REFRESH_KEY = 'wathefni.session.refresh'

export type StoredSession = {
  token: string
  refreshToken: string
}

export async function saveSession(session: StoredSession): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, session.token, { keychainAccessible: SecureStore.WHEN_UNLOCKED }),
    SecureStore.setItemAsync(REFRESH_KEY, session.refreshToken, { keychainAccessible: SecureStore.WHEN_UNLOCKED }),
  ])
}

export async function loadSession(): Promise<StoredSession | null> {
  const [token, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_KEY),
    SecureStore.getItemAsync(REFRESH_KEY),
  ])
  if (!token || !refreshToken) return null
  return { token, refreshToken }
}

export async function clearSession(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ])
}
