import * as Haptics from 'expo-haptics'
import { Platform } from 'react-native'

export function selectionHaptic(): void {
  if (Platform.OS === 'web') return
  void Haptics.selectionAsync().catch(() => undefined)
}

export function actionHaptic(): void {
  if (Platform.OS === 'web') return
  void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined)
}

export function successHaptic(): void {
  if (Platform.OS === 'web') return
  void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined)
}
