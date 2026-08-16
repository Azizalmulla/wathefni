import { Platform } from 'react-native'
import * as Notifications from 'expo-notifications'

/**
 * Keep the iOS app icon badge aligned with Inbox unread.
 * Android launcher badges are inconsistent; Expo still accepts the call safely.
 */
export async function syncInboxBadge(unread: number): Promise<void> {
  const count = Math.max(0, Math.floor(Number(unread) || 0))
  try {
    await Notifications.setBadgeCountAsync(count)
  } catch {
    // Simulators / denied permission — never block the UI.
  }
}

export async function clearInboxBadge(): Promise<void> {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return
  await syncInboxBadge(0)
}
