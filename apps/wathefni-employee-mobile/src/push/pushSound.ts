/**
 * Default Wathefni push notification sound (normal priority).
 * Urgent/time-sensitive stays separate for a later wave.
 *
 * Native assets (bundled via expo-notifications plugin `sounds`):
 *   assets/sounds/push/wathefni_default.wav
 * Source master (not bundled for APNs):
 *   assets/sounds/push/source/universfield-new-notification-040-493469.mp3
 *
 * iOS APNs references the bundled filename including extension.
 * Android uses res/raw name without extension + a dedicated channel
 * (channel sound is immutable after first create — bump channel id when the
 * WAV content changes; never reuse `default`).
 */
export const WATHEFNI_PUSH_SOUND = 'wathefni_default' as const
export const WATHEFNI_PUSH_SOUND_IOS = 'wathefni_default.wav' as const
export const WATHEFNI_PUSH_CHANNEL_ID = 'wathefni_default_v2' as const
export const WATHEFNI_PUSH_CHANNEL_NAME = 'OctoHR' as const
