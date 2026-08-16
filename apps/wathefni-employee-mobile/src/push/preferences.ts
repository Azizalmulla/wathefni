import AsyncStorage from '@react-native-async-storage/async-storage'

/**
 * Opt-out only. Core work push is on by default once OS permission is granted —
 * Settings is manage/disable, not a second consent wall.
 */
const PUSH_OPTED_OUT_KEY = 'wathefni.push.opted_out'
/** Legacy key from the opt-in era; migrated once to opted_out. */
const LEGACY_PUSH_ENABLED_KEY = 'wathefni.push.enabled'

let migrated = false

async function migrateLegacyPreference(): Promise<void> {
  if (migrated) return
  migrated = true
  try {
    const legacy = await AsyncStorage.getItem(LEGACY_PUSH_ENABLED_KEY)
    if (legacy === null) return
    // Legacy default was off (missing key). Only treat explicit '1' as previously enabled;
    // explicit absence of '1' after a user never opted in should not force opt-out —
    // wave default is on. Clear the legacy key either way.
    if (legacy !== '1') {
      // Prior builds required opt-in; employees who never toggled on have no key or '0'.
      // Do not invent an opt-out — allow auto-register after OS permission.
    }
    await AsyncStorage.removeItem(LEGACY_PUSH_ENABLED_KEY)
  } catch {
    // Best-effort migration.
  }
}

/** True when the employee explicitly disabled push in Settings. */
export async function isPushOptedOut(): Promise<boolean> {
  await migrateLegacyPreference()
  try {
    return (await AsyncStorage.getItem(PUSH_OPTED_OUT_KEY)) === '1'
  } catch {
    return false
  }
}

export async function setPushOptedOut(optedOut: boolean): Promise<void> {
  try {
    if (optedOut) await AsyncStorage.setItem(PUSH_OPTED_OUT_KEY, '1')
    else await AsyncStorage.removeItem(PUSH_OPTED_OUT_KEY)
    await AsyncStorage.removeItem(LEGACY_PUSH_ENABLED_KEY)
  } catch {
    // Backend registration remains authoritative; local preference is best-effort.
  }
}

/** @deprecated Prefer isPushOptedOut — returns true when push should attempt registration. */
export async function loadPushPreference(): Promise<boolean> {
  return !(await isPushOptedOut())
}

/** @deprecated Prefer setPushOptedOut — enabled=false means opted out. */
export async function savePushPreference(enabled: boolean): Promise<void> {
  await setPushOptedOut(!enabled)
}
