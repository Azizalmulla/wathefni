/**
 * Semantic native feedback for the Employee App.
 *
 * Screens call these events — never raw expo-haptics / Vibration.
 * iOS: UIKit feedback generators via expo-haptics.
 * Android: platform VibrationEffect mappings from expo-haptics.
 *
 * In-app interactions are haptics only. Push notification audio is separate
 * (`assets/sounds/push/wathefni_default.wav` via expo-notifications) — never
 * play custom UI tones for schedule/tabs/CTA/success/warning/error.
 *
 * Feedback is fire-and-forget: never awaited, never blocks navigation/UI.
 * Per-kind throttle + no queue prevents overlapping buzz on rapid taps.
 */
import * as Haptics from 'expo-haptics'
import { Platform } from 'react-native'

export type FeedbackKind =
  | 'selection'
  | 'weekSnap'
  | 'tab'
  | 'lightImpact'
  | 'success'
  | 'warning'
  | 'error'

const MIN_INTERVAL_MS: Record<FeedbackKind, number> = {
  selection: 70,
  weekSnap: 140,
  tab: 100,
  lightImpact: 100,
  success: 260,
  warning: 260,
  error: 260,
}

const lastFiredAt: Record<FeedbackKind, number> = {
  selection: 0,
  weekSnap: 0,
  tab: 0,
  lightImpact: 0,
  success: 0,
  warning: 0,
  error: 0,
}

function canFire(kind: FeedbackKind): boolean {
  if (Platform.OS === 'web') return false
  const now = Date.now()
  if (now - lastFiredAt[kind] < MIN_INTERVAL_MS[kind]) return false
  lastFiredAt[kind] = now
  return true
}

function run(kind: FeedbackKind, work: () => Promise<unknown>): void {
  if (!canFire(kind)) return
  try {
    void work().catch(() => undefined)
  } catch {
    // Native module missing / denied — never surface to UI.
  }
}

/**
 * Schedule day tap / compact selectors / toggles.
 * Soft impact is clearly more perceptible than selection-only on modern iPhones.
 */
export function selectionFeedback(): void {
  run('selection', () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Soft))
}

/** Week strip snap when the new week settles — stronger than a day tick. */
export function weekSnapFeedback(): void {
  run('weekSnap', () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium))
}

/** Bottom-tab selection — Soft impact: subtle but definitely felt. */
export function tabFeedback(): void {
  run('tab', () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Soft))
}

/** Primary CTA press-in — light tactile only. */
export function lightImpactFeedback(): void {
  run('lightImpact', () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light))
}

/** Primary successful submit / upload / request. */
export function successFeedback(): void {
  run('success', async () => {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Soft)
  })
}

/** Consequential confirmations / soft warnings. */
export function warningFeedback(): void {
  run('warning', async () => {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
  })
}

/** Failed transfers / blocking errors. */
export function errorFeedback(): void {
  run('error', async () => {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy)
  })
}

/** Namespaced map for call sites that prefer `feedback.selection()`. */
export const feedback = {
  selection: selectionFeedback,
  weekSnap: weekSnapFeedback,
  tab: tabFeedback,
  lightImpact: lightImpactFeedback,
  success: successFeedback,
  warning: warningFeedback,
  error: errorFeedback,
} as const

// --- Compatibility aliases ---

export function selectionHaptic(): void {
  selectionFeedback()
}

/** @deprecated Prefer lightImpactFeedback / semantic events. */
export function actionHaptic(): void {
  lightImpactFeedback()
}

export function successHaptic(): void {
  successFeedback()
}
