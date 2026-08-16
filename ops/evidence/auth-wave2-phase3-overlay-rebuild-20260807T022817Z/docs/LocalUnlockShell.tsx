/**
 * Phase 3 overlay controller.
 * Keeps AuthGate / navigation / session mounted. Only toggles overlay flags.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AppState, type AppStateStatus, StyleSheet, View } from 'react-native'
import * as Updates from 'expo-updates'

import { useAuth } from '@/auth/AuthProvider'
import {
  decideLocalUnlockOnResume,
  isLocalAutoLockEnabledFor,
  isLocalAutoLockMasterEnabled,
} from '@/auth/autoLockPolicy'
import { LocalUnlockOverlay, PrivacyCover } from '@/features/pin/LocalUnlockOverlay'

type Props = { children: ReactNode }

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

  timeoutMsRef.current = autoLockTimeoutMs
  statusRef.current = status
  employeeKeyRef.current = String(
    me?.employee?.employee_key || profile?.employee_key || '',
  ).trim()

  const featureOn = useCallback(() => {
    return isLocalAutoLockMasterEnabled() && isLocalAutoLockEnabledFor(employeeKeyRef.current)
  }, [])

  const dismissUnlock = useCallback(() => {
    setNeedsLocalUnlock(false)
    console.warn('[autolock-overlay] unlocked — overlay dismissed (session/nav unchanged)')
  }, [])

  useEffect(() => {
    // Clear overlay if user signs out or leaves signedIn (cold PIN lock is separate).
    if (status !== 'signedIn') {
      setNeedsLocalUnlock(false)
      setPrivacyCover(false)
      awayStartedAtRef.current = null
      enteredBackgroundRef.current = false
    }
  }, [status])

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      try {
        const prev = appStateRef.current
        appStateRef.current = next

        console.warn('[autolock-overlay] appState', {
          prev,
          next,
          status: statusRef.current,
          featureOn: featureOn(),
          updateId: Updates.updateId ?? null,
        })

        // Privacy cover only — never an auth lock.
        if (next === 'inactive' || next === 'background') {
          if (statusRef.current === 'signedIn') setPrivacyCover(true)
        }
        if (next === 'active') {
          setPrivacyCover(false)
        }

        if (!featureOn() || statusRef.current !== 'signedIn') {
          if (next === 'active') {
            awayStartedAtRef.current = null
            enteredBackgroundRef.current = false
          }
          return
        }

        // Ignore inactive for locking (Control Center / shade / Face ID system UI).
        if (next === 'inactive') return

        if (next === 'background') {
          enteredBackgroundRef.current = true
          if (awayStartedAtRef.current == null) awayStartedAtRef.current = Date.now()
          console.warn('[autolock-overlay] background start', {
            awayStartedAt: awayStartedAtRef.current,
            timeoutMs: timeoutMsRef.current,
          })
          return
        }

        if (next !== 'active') return

        if (resumeInFlightRef.current) {
          console.warn('[autolock-overlay] resume skipped (in flight)')
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

          console.warn('[autolock-overlay] resume decision', {
            reason,
            awayStartedAt,
            resumeAt,
            elapsedMs,
            timeoutMs,
            enteredBackground,
          })

          awayStartedAtRef.current = null
          enteredBackgroundRef.current = false

          if (reason === 'timeout') {
            // Overlay only — never change AuthStatus / never remount AuthGate.
            setNeedsLocalUnlock(true)
          }
        } finally {
          resumeInFlightRef.current = false
        }
      } catch (error) {
        console.warn('[autolock-overlay] appState error', error)
        resumeInFlightRef.current = false
      }
    }

    const sub = AppState.addEventListener('change', onChange)
    return () => sub.remove()
    // Mount once — live values via refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <View style={styles.fill}>
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
