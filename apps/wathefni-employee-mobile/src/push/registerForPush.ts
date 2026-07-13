import * as Device from 'expo-device'
import * as Notifications from 'expo-notifications'
import Constants from 'expo-constants'
import { Platform } from 'react-native'

// Asks for push permission (with a JIT prompt the caller gates behind a rationale)
// and returns the Expo push token, or null if unavailable/denied. The app stays
// fully usable without push — the in-app inbox is always available.
export async function registerForPushToken(): Promise<{ token: string; platform: string } | null> {
  if (!Device.isDevice) return null

  const existing = await Notifications.getPermissionsAsync()
  let granted = existing.granted || existing.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
  if (!granted && existing.canAskAgain) {
    const requested = await Notifications.requestPermissionsAsync()
    granted = requested.granted
  }
  if (!granted) return null

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Default',
      importance: Notifications.AndroidImportance.DEFAULT,
    })
  }

  const projectId = Constants.expoConfig?.extra?.eas?.projectId
  if (!projectId || projectId === 'REPLACE_WITH_EAS_PROJECT_ID') return null
  try {
    const tokenResponse = await Notifications.getExpoPushTokenAsync({ projectId })
    return { token: tokenResponse.data, platform: Platform.OS }
  } catch {
    return null
  }
}
