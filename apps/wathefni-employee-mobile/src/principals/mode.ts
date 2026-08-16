/**
 * Dual-principal mode preference + shell resolution.
 *
 * Modes select which shell is active. They never merge tokens or imply identity
 * linking by email/phone. Preference is UX-only (AsyncStorage), not authority.
 *
 * Auth-path rule: never probe or guess which principal an identifier belongs to.
 * Unsigned users pick a sign-in *method* (phone OTP vs work email/password) on
 * one Wathefni screen; the authenticated session then selects the workspace.
 */
import AsyncStorage from '@react-native-async-storage/async-storage'
import Constants from 'expo-constants'

export type PrincipalMode = 'employee' | 'hr'

const MODE_KEY = 'wathefni.principal.mode'

/** When both principals are signed in and no preference exists, open Employee. */
export const DEFAULT_DUAL_MODE: PrincipalMode = 'employee'

/**
 * HR workspace gate for the unified Wathefni binary.
 *
 * Prefer EXPO_PUBLIC_* (inlined at bundle time). Fall back to
 * `extra.unifiedApp.hrWorkspace` from app.config so an `eas update` that
 * forgot the shell env still mounts UnsignedEntry (Phone | Work email).
 */
export function hrWorkspaceEnabled(): boolean {
  const fromEnv = String(process.env.EXPO_PUBLIC_HR_WORKSPACE_ENABLED || '').trim()
  if (fromEnv === '1') return true
  if (fromEnv === '0') return false
  const fromExtra = String(
    (Constants.expoConfig?.extra as { unifiedApp?: { hrWorkspace?: string } } | undefined)
      ?.unifiedApp?.hrWorkspace || '',
  ).trim()
  return fromExtra === '1'
}

export async function loadPrincipalModePreference(): Promise<PrincipalMode | null> {
  try {
    const value = await AsyncStorage.getItem(MODE_KEY)
    if (value === 'employee' || value === 'hr') return value
    return null
  } catch {
    return null
  }
}

export async function savePrincipalModePreference(mode: PrincipalMode): Promise<void> {
  await AsyncStorage.setItem(MODE_KEY, mode)
}

export async function clearPrincipalModePreference(): Promise<void> {
  await AsyncStorage.removeItem(MODE_KEY)
}

export type PrincipalAvailability = {
  employeeSession: boolean
  hrSession: boolean
}

export type ResolvedShell =
  | { kind: 'employee' }
  | { kind: 'hr' }
  | { kind: 'unsigned' }

/**
 * Resolve workspace from authenticated sessions only.
 * Never shows a startup principal chooser. Switcher is post-auth Settings only.
 */
export function resolveShell(
  availability: PrincipalAvailability,
  preference: PrincipalMode | null,
): ResolvedShell {
  const { employeeSession, hrSession } = availability
  if (employeeSession && !hrSession) return { kind: 'employee' }
  if (!employeeSession && hrSession) return { kind: 'hr' }
  if (!employeeSession && !hrSession) return { kind: 'unsigned' }
  // Both authenticated — prefer last workspace; otherwise silent default.
  if (preference === 'employee' || preference === 'hr') return { kind: preference }
  return { kind: DEFAULT_DUAL_MODE }
}
