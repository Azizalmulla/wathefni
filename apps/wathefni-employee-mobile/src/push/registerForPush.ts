import * as Device from 'expo-device'
import * as Notifications from 'expo-notifications'
import Constants from 'expo-constants'
import { Platform } from 'react-native'

import {
  WATHEFNI_PUSH_CHANNEL_ID,
  WATHEFNI_PUSH_CHANNEL_NAME,
  WATHEFNI_PUSH_SOUND,
} from './pushSound'

export const PUSH_REGISTRATION_ENABLED = process.env.EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED === '1'

export async function ensureDefaultPushChannel(): Promise<void> {
  if (Platform.OS !== 'android') return
  // New channel id required: Android freezes a channel's sound after first create.
  await Notifications.setNotificationChannelAsync(WATHEFNI_PUSH_CHANNEL_ID, {
    name: WATHEFNI_PUSH_CHANNEL_NAME,
    importance: Notifications.AndroidImportance.DEFAULT,
    sound: WATHEFNI_PUSH_SOUND,
    vibrationPattern: [0, 250],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
  })
}

/**
 * Returns Expo push token when permitted, or null.
 * requestPermission: ask the OS when status is undetermined (and canAskAgain).
 * Denied permission never blocks the app — Inbox remains available.
 */
export async function registerForPushToken({
  requestPermission = false,
}: {
  requestPermission?: boolean
} = {}): Promise<{ token: string; platform: string } | null> {
  if (!PUSH_REGISTRATION_ENABLED || !Device.isDevice) return null

  const existing = await Notifications.getPermissionsAsync()
  let granted = existing.granted || existing.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
  if (!granted && requestPermission && existing.canAskAgain) {
    const requested = await Notifications.requestPermissionsAsync({
      ios: {
        allowAlert: true,
        allowBadge: true,
        allowSound: true,
      },
    })
    granted = requested.granted || requested.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
  }
  if (!granted) return null

  await ensureDefaultPushChannel()

  const projectId = Constants.expoConfig?.extra?.eas?.projectId
  if (!projectId || projectId === 'REPLACE_WITH_EAS_PROJECT_ID') return null
  try {
    const tokenResponse = await Notifications.getExpoPushTokenAsync({ projectId })
    return { token: tokenResponse.data, platform: Platform.OS }
  } catch {
    return null
  }
}
