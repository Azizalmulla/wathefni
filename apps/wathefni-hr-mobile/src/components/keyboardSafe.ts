import { Platform } from 'react-native'

/** Shared R7 keyboard contract — never leave Android without avoidance. */
export const KEYBOARD_SAFE_BEHAVIOR = 'padding' as const

export function keyboardSafeBehavior(): 'padding' {
  return KEYBOARD_SAFE_BEHAVIOR
}

export function keyboardSafeOffset(topInset: number): number {
  return Platform.OS === 'ios' ? Math.max(0, topInset) : 0
}
