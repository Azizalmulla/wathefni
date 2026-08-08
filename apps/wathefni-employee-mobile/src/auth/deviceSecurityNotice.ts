import AsyncStorage from '@react-native-async-storage/async-storage'

/**
 * Phase 5 — one-time new-device confirmation after activate replaced a prior session.
 * Cleared after shown. Never exposes server revoke reasons.
 */
const KEY = 'wathefni.device.replacedNoticePending'

export async function markReplacedDeviceNoticePending(): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, '1')
  } catch {
    // Best-effort — missing notice is preferable to blocking activation.
  }
}

export async function consumeReplacedDeviceNoticePending(): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(KEY)
    if (raw !== '1') return false
    await AsyncStorage.removeItem(KEY)
    return true
  } catch {
    return false
  }
}
