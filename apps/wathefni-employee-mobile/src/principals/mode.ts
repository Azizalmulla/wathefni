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
const PENDING_TRANSITION_KEY = 'wathefni.principal.pending-transition.v1'

export type PendingPrincipalTransition = {
  id: string
  from: PrincipalMode | null
  to: PrincipalMode
  previousPreference: PrincipalMode | null
  startedAt: number
}

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
  } catch (error) {
    // Preference is presentation-only; auth/session authority remains intact.
    void error
    return null
  }
}

export async function savePrincipalModePreference(mode: PrincipalMode): Promise<void> {
  await AsyncStorage.setItem(MODE_KEY, mode)
}

export async function clearPrincipalModePreference(): Promise<void> {
  await AsyncStorage.removeItem(MODE_KEY)
}

export async function loadPendingPrincipalTransition(): Promise<PendingPrincipalTransition | null> {
  const raw = await AsyncStorage.getItem(PENDING_TRANSITION_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<PendingPrincipalTransition>
    if (
      typeof parsed.id !== 'string' ||
      !parsed.id ||
      (parsed.from !== null && parsed.from !== 'employee' && parsed.from !== 'hr') ||
      (parsed.to !== 'employee' && parsed.to !== 'hr') ||
      (parsed.previousPreference !== null &&
        parsed.previousPreference !== 'employee' &&
        parsed.previousPreference !== 'hr') ||
      typeof parsed.startedAt !== 'number' ||
      !Number.isFinite(parsed.startedAt)
    ) {
      throw new Error('principal_transition_invalid_record')
    }
    return parsed as PendingPrincipalTransition
  } catch (error) {
    await AsyncStorage.removeItem(PENDING_TRANSITION_KEY)
    throw error
  }
}

export async function savePendingPrincipalTransition(
  transition: PendingPrincipalTransition,
): Promise<void> {
  await AsyncStorage.setItem(PENDING_TRANSITION_KEY, JSON.stringify(transition))
}

export async function clearPendingPrincipalTransition(): Promise<void> {
  await AsyncStorage.removeItem(PENDING_TRANSITION_KEY)
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
