import * as SecureStore from 'expo-secure-store'

import {
  AUTO_LOCK_DEFAULT_TIMEOUT_MS,
  parseAutoLockTimeout,
  serializeAutoLockTimeout,
  type AutoLockTimeoutMs,
} from './autoLockPolicy'

const TIMEOUT_KEY = 'wathefni.autolock.timeout_ms'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED }

export async function loadAutoLockTimeout(): Promise<AutoLockTimeoutMs> {
  try {
    const raw = await SecureStore.getItemAsync(TIMEOUT_KEY)
    return parseAutoLockTimeout(raw)
  } catch {
    return AUTO_LOCK_DEFAULT_TIMEOUT_MS
  }
}

export async function saveAutoLockTimeout(value: AutoLockTimeoutMs): Promise<void> {
  await SecureStore.setItemAsync(TIMEOUT_KEY, serializeAutoLockTimeout(value), STORE_OPTS)
}
