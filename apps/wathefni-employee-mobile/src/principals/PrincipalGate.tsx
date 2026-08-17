import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { createContext, useContext } from 'react'

import { loadSession } from '@/auth/session'
import { loadOperatorSession } from '@hr/auth/session'
import { colors } from '@/theme'
import {
  hrWorkspaceEnabled,
  clearPrincipalModePreference,
  loadPrincipalModePreference,
  resolveShell,
  savePrincipalModePreference,
  type PrincipalMode,
  type ResolvedShell,
} from './mode'

export type PrincipalTransition =
  | { status: 'idle'; from: null; to: null; error: null }
  | { status: 'switching'; from: PrincipalMode | null; to: PrincipalMode; error: null }
  | { status: 'error'; from: PrincipalMode | null; to: PrincipalMode; error: 'principal_transition_failed' }

type PrincipalGateValue = {
  ready: boolean
  shell: ResolvedShell | null
  employeeSession: boolean
  hrSession: boolean
  transition: PrincipalTransition
  selectMode: (mode: PrincipalMode) => Promise<boolean>
  acknowledgePrincipalMounted: (mode: PrincipalMode) => void
  clearTransitionError: () => void
  refreshAvailability: () => Promise<void>
}

const PrincipalGateContext = createContext<PrincipalGateValue | null>(null)

export function usePrincipalGate(): PrincipalGateValue {
  const value = useContext(PrincipalGateContext)
  if (!value) throw new Error('usePrincipalGate requires PrincipalGateProvider')
  return value
}

export function PrincipalGateProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [employeeSession, setEmployeeSession] = useState(false)
  const [hrSession, setHrSession] = useState(false)
  const [shell, setShell] = useState<ResolvedShell | null>(null)
  const [transition, setTransition] = useState<PrincipalTransition>({
    status: 'idle',
    from: null,
    to: null,
    error: null,
  })
  const shellRef = useRef<ResolvedShell | null>(null)
  const transitionPromiseRef = useRef<Promise<boolean> | null>(null)
  const mountAckRef = useRef<{
    mode: PrincipalMode
    resolve: () => void
    reject: (error: Error) => void
    timer: ReturnType<typeof setTimeout>
  } | null>(null)

  shellRef.current = shell

  const refreshAvailability = useCallback(async () => {
    if (!hrWorkspaceEnabled()) {
      setEmployeeSession(false)
      setHrSession(false)
      // Employee-only binary: shell resolution stays inside AuthGate (signed out → activate).
      setShell({ kind: 'employee' })
      setReady(true)
      return
    }
    const [employee, operator, preference] = await Promise.all([
      loadSession(),
      loadOperatorSession(),
      loadPrincipalModePreference(),
    ])
    const availability = {
      employeeSession: Boolean(employee?.token && employee?.refreshToken),
      hrSession: Boolean(operator?.accessToken && operator?.refreshToken),
    }
    setEmployeeSession(availability.employeeSession)
    setHrSession(availability.hrSession)
    setShell(resolveShell(availability, preference))
    setReady(true)
  }, [])

  useEffect(() => {
    void refreshAvailability()
  }, [refreshAvailability])

  useEffect(
    () => () => {
      if (!mountAckRef.current) return
      clearTimeout(mountAckRef.current.timer)
      mountAckRef.current.reject(new Error('principal_transition_unmounted'))
      mountAckRef.current = null
    },
    [],
  )

  const waitForPrincipalMount = useCallback((mode: PrincipalMode): Promise<void> => {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (mountAckRef.current?.mode !== mode) return
        mountAckRef.current = null
        reject(new Error('principal_transition_mount_timeout'))
      }, 10_000)
      mountAckRef.current = { mode, resolve, reject, timer }
    })
  }, [])

  const acknowledgePrincipalMounted = useCallback((mode: PrincipalMode) => {
    const pending = mountAckRef.current
    if (!pending || pending.mode !== mode) return
    clearTimeout(pending.timer)
    mountAckRef.current = null
    pending.resolve()
  }, [])

  const selectMode = useCallback(
    (mode: PrincipalMode): Promise<boolean> => {
      // Rapid repeated taps join the one authoritative transition. They never
      // start competing SecureStore reads, preference writes, or router moves.
      if (transitionPromiseRef.current) return transitionPromiseRef.current

      const run = async (): Promise<boolean> => {
        const previousShell = shellRef.current
        const previousMode =
          previousShell?.kind === 'employee' || previousShell?.kind === 'hr'
            ? previousShell.kind
            : null
        let previousPreference: PrincipalMode | null = null
        let preferenceLoaded = false

        // ModeRedirect replaces the active principal tree with a neutral splash
        // immediately. Both local-lock hosts also observe this flag, so the
        // outgoing principal cannot raise its PIN overlay during the handoff.
        setTransition({ status: 'switching', from: previousMode, to: mode, error: null })

        try {
          if (mode === 'hr' && !hrWorkspaceEnabled()) {
            throw new Error('hr_workspace_disabled')
          }

          previousPreference = await loadPrincipalModePreference()
          preferenceLoaded = true
          const [employee, operator] = await Promise.all([loadSession(), loadOperatorSession()])
          const availability = {
            employeeSession: Boolean(employee?.token && employee?.refreshToken),
            hrSession: Boolean(operator?.accessToken && operator?.refreshToken),
          }

          // Preference is UX-only, but it is part of the transaction: if it
          // cannot be persisted, leave the original principal mounted.
          await savePrincipalModePreference(mode)

          setEmployeeSession(availability.employeeSession)
          setHrSession(availability.hrSession)
          const mounted = waitForPrincipalMount(mode)
          setShell({ kind: mode })

          // ModeRedirect owns the route declaratively while the transition is
          // active. Do not report success until the target AuthProvider has
          // actually mounted under its own session/PIN namespace.
          await mounted
          setTransition({ status: 'idle', from: null, to: null, error: null })
          return true
        } catch {
          if (mountAckRef.current) {
            clearTimeout(mountAckRef.current.timer)
            mountAckRef.current = null
          }
          // Roll back shell, route and UX preference. Session/PIN material is
          // deliberately untouched and remains isolated in each namespace.
          setShell(previousShell)
          if (preferenceLoaded) {
            try {
              if (previousPreference) await savePrincipalModePreference(previousPreference)
              else await clearPrincipalModePreference()
            } catch {
              // The visible shell/route rollback is authoritative. A failed UX
              // preference restore cannot grant access or merge principals.
            }
          }
          setTransition({
            status: 'error',
            from: previousMode,
            to: mode,
            error: 'principal_transition_failed',
          })
          return false
        }
      }

      const promise = run().finally(() => {
        transitionPromiseRef.current = null
      })
      transitionPromiseRef.current = promise
      return promise
    },
    [waitForPrincipalMount],
  )

  const clearTransitionError = useCallback(() => {
    setTransition((current) =>
      current.status === 'error'
        ? { status: 'idle', from: null, to: null, error: null }
        : current,
    )
  }, [])

  const value = useMemo(
    () => ({
      ready,
      shell,
      employeeSession,
      hrSession,
      transition,
      selectMode,
      acknowledgePrincipalMounted,
      clearTransitionError,
      refreshAvailability,
    }),
    [
      ready,
      shell,
      employeeSession,
      hrSession,
      transition,
      selectMode,
      acknowledgePrincipalMounted,
      clearTransitionError,
      refreshAvailability,
    ],
  )

  return <PrincipalGateContext.Provider value={value}>{children}</PrincipalGateContext.Provider>
}

export function PrincipalMountAck({ mode }: { mode: PrincipalMode }) {
  const { transition, acknowledgePrincipalMounted } = usePrincipalGate()
  useEffect(() => {
    if (transition.status === 'switching' && transition.to === mode) {
      acknowledgePrincipalMounted(mode)
    }
  }, [acknowledgePrincipalMounted, mode, transition])
  return null
}

export function PrincipalBootSplash() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
      <ActivityIndicator testID="e2e.boot.principal" color={colors.accent} />
    </View>
  )
}
