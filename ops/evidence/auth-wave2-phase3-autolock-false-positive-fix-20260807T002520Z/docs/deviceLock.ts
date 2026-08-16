/**
 * Device screen-lock probe. Uses expo-screen-detector when present in the native
 * binary; otherwise returns false so timeout-based auto-lock still applies.
 *
 * Callers must only invoke this while AppState is `background`. Probing during
 * `inactive` (Control Center, notification shade, Face ID system UI) produces
 * false positives on iOS (`isProtectedDataAvailable`).
 */

export async function isDeviceScreenLocked(): Promise<boolean> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('expo-screen-detector') as {
      isScreenLocked?: () => Promise<boolean>
      default?: { isScreenLocked?: () => Promise<boolean> }
    }
    const api = mod?.default ?? mod
    if (!api || typeof api.isScreenLocked !== 'function') return false
    return Boolean(await api.isScreenLocked())
  } catch {
    return false
  }
}
