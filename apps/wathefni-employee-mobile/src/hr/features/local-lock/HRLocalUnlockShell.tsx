/**
 * HR auto-lock overlay host — mirrors Employee LocalUnlockShell.
 * Uses HR AuthProvider + HR-namespaced PIN material only.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AppState, type AppStateStatus, StyleSheet, View } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@hr/auth/AuthProvider'
import { decideLocalUnlockOnResume } from '@/auth/autoLockPolicy'
import {
  isHrLocalAutoLockEnabledFor,
  isLocalAutoLockMasterEnabled,
} from '@hr/auth/localLock/hrPolicy'
import { operatorPrincipalKey } from '@hr/auth/localLock/principalKey'
import { softRefreshHrSurfaces } from '@hr/lib/hrRefresh'
import { HRLocalUnlockOverlay, HRPrivacyCover } from '@hr/features/local-lock/HRLocalUnlockOverlay'

type Props = { children: ReactNode }

export function HRLocalUnlockShell({ children }: Props) {
  const { status, me, autoLockTimeoutMs, refreshMe } = useAuth()
  const queryClient = useQueryClient()
  const [needsLocalUnlock, setNeedsLocalUnlock] = useState(false)
  const [privacyCover, setPrivacyCover] = useState(false)
  const refreshMeRef = useRef(refreshMe)
  refreshMeRef.current = refreshMe

  const appStateRef = useRef<AppStateStatus>(AppState.currentState)
  const awayStartedAtRef = useRef<number | null>(null)
  const enteredBackgroundRef = useRef(false)
  const resumeInFlightRef = useRef(false)
  const timeoutMsRef = useRef(autoLockTimeoutMs)
  const statusRef = useRef(status)
  const principalKeyRef = useRef('')
  const needsUnlockRef = useRef(false)

  timeoutMsRef.current = autoLockTimeoutMs
  statusRef.current = status
  principalKeyRef.current = operatorPrincipalKey(me)
  needsUnlockRef.current = needsLocalUnlock

  const dismissUnlock = useCallback(() => {
    needsUnlockRef.current = false
    setNeedsLocalUnlock(false)
    // Mark everything stale, then refetch only what is on screen — the same
    // catch-up the foreground path runs, without a full-screen reload flash.
    void queryClient.invalidateQueries({ refetchType: 'none' })
    void softRefreshHrSurfaces(queryClient, refreshMeRef.current)
  }, [queryClient])

  useEffect(() => {
    if (status !== 'signedIn') {
      needsUnlockRef.current = false
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
        void prev
        const key = principalKeyRef.current
        const master = isLocalAutoLockMasterEnabled()
        const feature = isHrLocalAutoLockEnabledFor(key)

        if (next === 'inactive' || next === 'background') {
          if (statusRef.current === 'signedIn' && !needsUnlockRef.current) setPrivacyCover(true)
        }
        if (next === 'active') {
          setPrivacyCover(false)
        }

        if (!feature || statusRef.current !== 'signedIn') {
          if (next === 'active') {
            awayStartedAtRef.current = null
            enteredBackgroundRef.current = false
          }
          void master
          return
        }

        if (next === 'inactive') return

        if (next === 'background') {
          enteredBackgroundRef.current = true
          if (awayStartedAtRef.current == null) awayStartedAtRef.current = Date.now()
          return
        }

        if (next !== 'active') return

        if (resumeInFlightRef.current) return
        resumeInFlightRef.current = true
        try {
          const awayStartedAt = awayStartedAtRef.current
          const enteredBackground = enteredBackgroundRef.current
          const elapsedMs = awayStartedAt != null ? Date.now() - awayStartedAt : 0
          const reason = decideLocalUnlockOnResume({
            elapsedMs,
            timeoutMs: timeoutMsRef.current,
            enteredBackground,
          })

          awayStartedAtRef.current = null
          enteredBackgroundRef.current = false

          if (reason === 'timeout') {
            needsUnlockRef.current = true
            setPrivacyCover(false)
            setNeedsLocalUnlock(true)
          }
        } finally {
          resumeInFlightRef.current = false
        }
      } catch {
        resumeInFlightRef.current = false
      }
    }

    const sub = AppState.addEventListener('change', onChange)
    return () => sub.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <View style={styles.fill} collapsable={false} testID="hr-local-unlock-shell">
      {children}
      {privacyCover && !needsLocalUnlock ? <HRPrivacyCover /> : null}
      {needsLocalUnlock && status === 'signedIn' ? (
        <HRLocalUnlockOverlay onUnlocked={dismissUnlock} />
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
})
