import AsyncStorage from '@react-native-async-storage/async-storage'

const PUSH_PREFERENCE_KEY = 'wathefni.push.enabled'

export async function loadPushPreference(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(PUSH_PREFERENCE_KEY)) === '1'
  } catch {
    return false
  }
}

export async function savePushPreference(enabled: boolean): Promise<void> {
  try {
    if (enabled) await AsyncStorage.setItem(PUSH_PREFERENCE_KEY, '1')
    else await AsyncStorage.removeItem(PUSH_PREFERENCE_KEY)
  } catch {
    // Backend registration remains authoritative; local preference is best-effort.
  }
}
