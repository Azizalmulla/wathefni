import AsyncStorage from '@react-native-async-storage/async-storage'

/**
 * One-shot resume after an intentional RTL layout restart (language switch).
 * Survives process reload; consumed on next boot. Not a security credential.
 */
const SKIP_UNLOCK_ONCE_KEY = 'wathefni.pin.skip_unlock_once'

export async function markSkipUnlockOnce(): Promise<void> {
  try {
    await AsyncStorage.setItem(SKIP_UNLOCK_ONCE_KEY, '1')
  } catch {
    // Best-effort — worst case user unlocks with PIN after restart.
  }
}

export async function consumeSkipUnlockOnce(): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(SKIP_UNLOCK_ONCE_KEY)
    if (raw !== '1') return false
    await AsyncStorage.removeItem(SKIP_UNLOCK_ONCE_KEY)
    return true
  } catch {
    return false
  }
}
