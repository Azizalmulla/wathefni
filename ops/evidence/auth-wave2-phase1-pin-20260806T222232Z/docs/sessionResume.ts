import AsyncStorage from '@react-native-async-storage/async-storage'
import * as SecureStore from 'expo-secure-store'

/**
 * Intentional RTL language restart markers.
 * Survive Updates.reloadAsync(). Must never be treated as logout.
 *
 * Dual-write AsyncStorage + SecureStore so a flaky store cannot drop the marker
 * while Wave 1 tokens (SecureStore) remain.
 */
const SKIP_UNLOCK_ONCE_KEY = 'wathefni.pin.skip_unlock_once'
const LOCALE_RESTART_PRESERVE_KEY = 'wathefni.auth.locale_restart_preserve'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED }

async function setBoth(key: string, value: string): Promise<void> {
  await Promise.all([
    AsyncStorage.setItem(key, value).catch(() => undefined),
    SecureStore.setItemAsync(key, value, STORE_OPTS).catch(() => undefined),
  ])
}

async function readEither(key: string): Promise<string | null> {
  try {
    const secure = await SecureStore.getItemAsync(key)
    if (secure) return secure
  } catch {
    // fall through
  }
  try {
    return await AsyncStorage.getItem(key)
  } catch {
    return null
  }
}

async function clearBoth(key: string): Promise<void> {
  await Promise.all([
    AsyncStorage.removeItem(key).catch(() => undefined),
    SecureStore.deleteItemAsync(key).catch(() => undefined),
  ])
}

/** Call immediately before an intentional language RTL reload while signed in. */
export async function markLocaleRestartPreserveAuth(): Promise<void> {
  await setBoth(LOCALE_RESTART_PRESERVE_KEY, '1')
  await setBoth(SKIP_UNLOCK_ONCE_KEY, '1')
}

export async function isLocaleRestartPreserveAuth(): Promise<boolean> {
  return (await readEither(LOCALE_RESTART_PRESERVE_KEY)) === '1'
}

export async function clearLocaleRestartPreserveAuth(): Promise<void> {
  await clearBoth(LOCALE_RESTART_PRESERVE_KEY)
  await clearBoth(SKIP_UNLOCK_ONCE_KEY)
}

/** @deprecated use markLocaleRestartPreserveAuth */
export async function markSkipUnlockOnce(): Promise<void> {
  await setBoth(SKIP_UNLOCK_ONCE_KEY, '1')
}

export async function consumeSkipUnlockOnce(): Promise<boolean> {
  const raw = await readEither(SKIP_UNLOCK_ONCE_KEY)
  if (raw !== '1') return false
  await clearBoth(SKIP_UNLOCK_ONCE_KEY)
  return true
}
