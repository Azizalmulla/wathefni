/**
 * Canary diagnostics for Phase 3 overlay (visible in Settings).
 * Must not rely on console.* — production builds strip console via babel.
 */

import type { AutoLockTimeoutMs, LocalUnlockDecisionReason } from './autoLockPolicy'

export type AutoLockDiagnostics = {
  buildMarker: string
  updateId: string | null
  channel: string | null
  runtimeVersion: string | null
  masterFlagRaw: string
  masterEnabled: boolean
  featureEnabled: boolean
  overlayBiometricFlagRaw: string
  overlayBiometricEnabled: boolean
  employeeKey: string
  timeoutMs: AutoLockTimeoutMs
  lastAwayAt: number | null
  lastResumeAt: number | null
  lastElapsedMs: number | null
  lastDecision: LocalUnlockDecisionReason | 'n/a' | 'feature_off' | 'not_signed_in'
  lastAppState: string
  needsLocalUnlock: boolean
  enteredBackground: boolean
  /** Gate arm / prompt path for canary (Settings). */
  lastBioGateReason: string
  biometricFeatureOn: boolean
  biometricPreferenceOn: boolean | null
  biometricUsable: boolean | null
}

const listeners = new Set<() => void>()

let snapshot: AutoLockDiagnostics = {
  buildMarker: '',
  updateId: null,
  channel: null,
  runtimeVersion: null,
  masterFlagRaw: '',
  masterEnabled: false,
  featureEnabled: false,
  overlayBiometricFlagRaw: '',
  overlayBiometricEnabled: false,
  employeeKey: '',
  timeoutMs: 30_000,
  lastAwayAt: null,
  lastResumeAt: null,
  lastElapsedMs: null,
  lastDecision: 'n/a',
  lastAppState: 'unknown',
  needsLocalUnlock: false,
  enteredBackground: false,
  lastBioGateReason: 'n/a',
  biometricFeatureOn: false,
  biometricPreferenceOn: null,
  biometricUsable: null,
}

export function getAutoLockDiagnostics(): AutoLockDiagnostics {
  return { ...snapshot }
}

export function patchAutoLockDiagnostics(partial: Partial<AutoLockDiagnostics>): void {
  snapshot = { ...snapshot, ...partial }
  listeners.forEach((fn) => {
    try {
      fn()
    } catch {
      /* ignore */
    }
  })
}

export function subscribeAutoLockDiagnostics(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
