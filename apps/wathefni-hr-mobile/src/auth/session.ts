import * as SecureStore from 'expo-secure-store'

const ACCESS_KEY = 'wathefni.hr.access_token'
const REFRESH_KEY = 'wathefni.hr.refresh_token'
const COMPANY_KEY = 'wathefni.hr.company_code'
const EXPIRY_KEY = 'wathefni.hr.access_expires_at'

export type StoredOperatorSession = {
  accessToken: string
  refreshToken: string
  companyCode: string
  expiresAt: string
}

const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }

export async function saveOperatorSession(session: StoredOperatorSession): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, session.accessToken, options),
    SecureStore.setItemAsync(REFRESH_KEY, session.refreshToken, options),
    SecureStore.setItemAsync(COMPANY_KEY, session.companyCode, options),
    SecureStore.setItemAsync(EXPIRY_KEY, session.expiresAt, options),
  ])
}

export async function loadOperatorSession(): Promise<StoredOperatorSession | null> {
  const [accessToken, refreshToken, companyCode, expiresAt] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_KEY),
    SecureStore.getItemAsync(REFRESH_KEY),
    SecureStore.getItemAsync(COMPANY_KEY),
    SecureStore.getItemAsync(EXPIRY_KEY),
  ])
  if (!accessToken || !refreshToken || !companyCode || !expiresAt) return null
  return { accessToken, refreshToken, companyCode, expiresAt }
}

export async function clearOperatorSession(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
    SecureStore.deleteItemAsync(COMPANY_KEY),
    SecureStore.deleteItemAsync(EXPIRY_KEY),
  ])
}
