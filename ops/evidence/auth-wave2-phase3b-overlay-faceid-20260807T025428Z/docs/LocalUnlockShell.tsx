/**
 * Phase 3 overlay controller.
 * Keeps AuthGate / navigation / session mounted. Only toggles overlay flags.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AppState, type AppStateStatus, StyleSheet, View } from 'react-native'
import * as Updates from 'expo-updates'

import { useAuth } from '@/auth/AuthProvider'
import {
  AUTO_LOCK_BUILD_MARKER,
  decideLocalUnlockOnResume,
  isLocalAutoLockBiometricEnabled,
  isLocalAutoLockEnabledFor,
  isLocalAutoLockMasterEnabled,
} from '@/auth/autoLockPolicy'
import { patchAutoLockDiagnostics } from '@/auth/autoLockDiagnostics'
import { LocalUnlockOverlay, PrivacyCover } from '@/features/pin/LocalUnlockOverlay'

type Props = { children: ReactNode }

function employeeKeyFromAuth(
  me: { employee_key?: string; employee?: { employee_key?: string } } | null,
  profile: { employee_key?: string } | null,
): string {
  return String(
    me?.employee?.employee_key || me?.employee_key || profile?.employee_key || '',
  ).trim()
}

export function LocalUnlockShell({ children }: Props) {
  const { status, profile, me, autoLockTimeoutMs } = useAuth()
  const [needsLocalUnlock, setNeedsLocalUnlock] = useState(false)
  const [privacyCover, setPrivacyCover] = useState(false)

  const appStateRef = useRef<AppStateStatus>(AppState.currentState)
  const awayStartedAtRef = useRef<number | null>(null)
  const enteredBackgroundRef = useRef(false)
  const resumeInFlightRef = useRef(false)
  const timeoutMsRef = useRef(autoLockTimeoutMs)
  const statusRef = useRef(status)
  const employeeKeyRef = useRef('')
  const needsUnlockRef = useRef(false)

  timeoutMsRef.current = autoLockTimeoutMs
  statusRef.current = status
  employeeKeyRef.current = employeeKeyFromAuth(me, profile)
  needsUnlockRef.current = needsLocalUnlock

  const syncDiagnostics = useCallback(
    (partial: Parameters<typeof patchAutoLockDiagnostics>[0] = {}) => {
      const key = employeeKeyRef.current
      const master = isLocalAutoLockMasterEnabled()
      const feature = isLocalAutoLockEnabledFor(key)
      patchAutoLockDiagnostics({
        buildMarker: AUTO_LOCK_BUILD_MARKER,
        updateId: Updates.updateId ?? null,
        channel: Updates.channel ?? null,
        runtimeVersion: Updates.runtimeVersion ?? null,
        masterFlagRaw: String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK || 'unset'),
        masterEnabled: master,
        featureEnabled: feature,
        overlayBiometricFlagRaw: String(process.env.EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC || 'unset'),
        overlayBiometricEnabled: isLocalAutoLockBiometricEnabled(),
        employeeKey: key || '(empty)',
        timeoutMs: timeoutMsRef.current,
        needsLocalUnlock: needsUnlockRef.current,
        enteredBackground: enteredBackgroundRef.current,
        lastAwayAt: awayStartedAtRef.current,
        lastAppState: String(appStateRef.current),
        ...partial,
      })
    },
    [],
  )

  // Keep diagnostics fresh when auth/timeout identity changes.
  useEffect(() => {
    syncDiagnostics()
  }, [status, me, profile, autoLockTimeoutMs, needsLocalUnlock, syncDiagnostics])

  const dismissUnlock = useCallback(() => {
    needsUnlockRef.current = false
    setNeedsLocalUnlock(false)
    syncDiagnostics({ needsLocalUnlock: false, lastDecision: 'none' })
  }, [syncDiagnostics])

  useEffect(() => {
    if (status !== 'signedIn') {
      needsUnlockRef.current = false
      setNeedsLocalUnlock(false)
      setPrivacyCover(false)
      awayStartedAtRef.current = null
      enteredBackgroundRef.current = false
      syncDiagnostics({
        needsLocalUnlock: false,
        enteredBackground: false,
        lastAwayAt: null,
        lastDecision: status === 'loading' ? 'n/a' : 'not_signed_in',
      })
    }
  }, [status, syncDiagnostics])

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      try {
        const prev = appStateRef.current
        appStateRef.current = next
        const key = employeeKeyRef.current
        const master = isLocalAutoLockMasterEnabled()
        const feature = isLocalAutoLockEnabledFor(key)

        // Privacy cover only — never an auth lock.
        if (next === 'inactive' || next === 'background') {
          if (statusRef.current === 'signedIn') setPrivacyCover(true)
        }
        if (next === 'active') {
          setPrivacyCover(false)
        }

        if (!feature || statusRef.current !== 'signedIn') {
          if (next === 'active') {
            awayStartedAtRef.current = null
            enteredBackgroundRef.current = false
          }
          syncDiagnostics({
            lastAppState: `${prev}->${next}`,
            lastDecision: !master || !feature ? 'feature_off' : 'not_signed_in',
            masterEnabled: master,
            featureEnabled: feature,
            employeeKey: key || '(empty)',
            enteredBackground: enteredBackgroundRef.current,
            lastAwayAt: awayStartedAtRef.current,
          })
          return
        }

        // Ignore inactive for locking (Control Center / shade / system UI).
        if (next === 'inactive') {
          syncDiagnostics({ lastAppState: `${prev}->${next}` })
          return
        }

        if (next === 'background') {
          enteredBackgroundRef.current = true
          if (awayStartedAtRef.current == null) awayStartedAtRef.current = Date.now()
          syncDiagnostics({
            lastAppState: `${prev}->${next}`,
            enteredBackground: true,
            lastAwayAt: awayStartedAtRef.current,
          })
          return
        }

        if (next !== 'active') return

        if (resumeInFlightRef.current) {
          syncDiagnostics({ lastAppState: `${prev}->${next}`, lastDecision: 'n/a' })
          return
        }
        resumeInFlightRef.current = true
        try {
          const awayStartedAt = awayStartedAtRef.current
          const enteredBackground = enteredBackgroundRef.current
          const resumeAt = Date.now()
          const elapsedMs = awayStartedAt != null ? resumeAt - awayStartedAt : null
          const timeoutMs = timeoutMsRef.current
          const reason = decideLocalUnlockOnResume({
            elapsedMs: elapsedMs ?? 0,
            timeoutMs,
            enteredBackground,
          })

          awayStartedAtRef.current = null
          enteredBackgroundRef.current = false

          if (reason === 'timeout') {
            needsUnlockRef.current = true
            setNeedsLocalUnlock(true)
          }

          syncDiagnostics({
            lastAppState: `${prev}->${next}`,
            lastAwayAt: awayStartedAt,
            lastResumeAt: resumeAt,
            lastElapsedMs: elapsedMs,
            lastDecision: reason,
            enteredBackground: false,
            needsLocalUnlock: needsUnlockRef.current,
            timeoutMs,
            featureEnabled: true,
            masterEnabled: true,
            employeeKey: key || '(empty)',
          })
        } finally {
          resumeInFlightRef.current = false
        }
      } catch {
        resumeInFlightRef.current = false
        syncDiagnostics({ lastDecision: 'n/a', lastAppState: 'error' })
      }
    }

    const sub = AppState.addEventListener('change', onChange)
    syncDiagnostics({ lastAppState: String(AppState.currentState) })
    return () => sub.remove()
    // Mount once — live values via refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <View style={styles.fill} collapsable={false} testID={AUTO_LOCK_BUILD_MARKER}>
      {children}
      {privacyCover ? <PrivacyCover /> : null}
      {needsLocalUnlock && status === 'signedIn' ? (
        <LocalUnlockOverlay onUnlocked={dismissUnlock} />
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
})
