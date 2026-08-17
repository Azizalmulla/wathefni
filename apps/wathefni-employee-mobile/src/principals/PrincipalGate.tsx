import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { createContext, useContext } from 'react'
import { usePathname, useRouter } from 'expo-router'

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
  const router = useRouter()
  const pathname = usePathname()
  const shellRef = useRef<ResolvedShell | null>(null)
  const pathnameRef = useRef(pathname)
  const transitionPromiseRef = useRef<Promise<boolean> | null>(null)

  shellRef.current = shell
  pathnameRef.current = pathname

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
        const previousPath = pathnameRef.current
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
          setShell({ kind: mode })

          // Each target AuthProvider validates only its own SecureStore session.
          // Missing/stale sessions therefore land on that principal's sign-in;
          // valid sessions enter that principal's independent local-lock state.
          router.replace(
            (mode === 'hr'
              ? '/hr'
              : availability.employeeSession
                ? '/(tabs)'
                : '/(auth)/activate') as never,
          )
          setTransition({ status: 'idle', from: null, to: null, error: null })
          return true
        } catch {
          // Roll back shell, route and UX preference. Session/PIN material is
          // deliberately untouched and remains isolated in each namespace.
          setShell(previousShell)
          if (previousPath) router.replace(previousPath as never)
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
    [router],
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
      clearTransitionError,
      refreshAvailability,
    ],
  )

  return <PrincipalGateContext.Provider value={value}>{children}</PrincipalGateContext.Provider>
}

export function PrincipalBootSplash() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
      <ActivityIndicator testID="e2e.boot.principal" color={colors.accent} />
    </View>
  )
}
