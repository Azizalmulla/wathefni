import AsyncStorage from '@react-native-async-storage/async-storage'

import type { PrincipalMode } from './mode'

const DIAGNOSTICS_KEY = 'wathefni.principal.diagnostics.v1'
const MAX_EVENTS = 80

export type PrincipalDiagnosticEvent = {
  at: number
  event:
    | 'switch_tap'
    | 'transition_recovered'
    | 'transition_started'
    | 'route_observed'
    | 'route_replace'
    | 'provider_mount_ack'
    | 'lock_gate_rendered'
    | 'transition_completed'
    | 'transition_failed'
    | 'diagnostic_persist_failed'
  transitionId?: string
  target?: PrincipalMode
  route?: string
  employeeSession?: boolean
  hrSession?: boolean
  lockPrincipal?: PrincipalMode | null
  errorCode?: string
}

let events: PrincipalDiagnosticEvent[] = []

export function principalRouteLabel(segments: readonly string[]): string {
  return `/${segments.filter(Boolean).join('/')}` || '/'
}

export function recordPrincipalDiagnostic(
  event: Omit<PrincipalDiagnosticEvent, 'at'>,
): void {
  const entry: PrincipalDiagnosticEvent = { at: Date.now(), ...event }
  events = [...events.slice(-(MAX_EVENTS - 1)), entry]
  if (__DEV__) console.info('[principal-transition]', JSON.stringify(entry))
  void AsyncStorage.setItem(DIAGNOSTICS_KEY, JSON.stringify(events)).catch((error: unknown) => {
    const failure: PrincipalDiagnosticEvent = {
      at: Date.now(),
      event: 'diagnostic_persist_failed',
      errorCode: error instanceof Error ? error.message : 'diagnostic_persist_failed',
    }
    events = [...events.slice(-(MAX_EVENTS - 1)), failure]
  })
}

export async function loadPrincipalDiagnostics(): Promise<PrincipalDiagnosticEvent[]> {
  if (events.length) return [...events]
  try {
    const raw = await AsyncStorage.getItem(DIAGNOSTICS_KEY)
    const parsed = raw ? (JSON.parse(raw) as PrincipalDiagnosticEvent[]) : []
    events = Array.isArray(parsed) ? parsed.slice(-MAX_EVENTS) : []
  } catch (error) {
    recordPrincipalDiagnostic({
      event: 'diagnostic_persist_failed',
      errorCode: error instanceof Error ? error.message : 'diagnostic_load_failed',
    })
  }
  return [...events]
}

export function getPrincipalDiagnosticsSnapshot(): PrincipalDiagnosticEvent[] {
  return [...events]
}
