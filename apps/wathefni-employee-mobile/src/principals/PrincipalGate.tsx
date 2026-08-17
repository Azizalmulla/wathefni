import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'

import { loadSession } from '@/auth/session'
import { loadOperatorSession } from '@hr/auth/session'
import { colors } from '@/theme'
import {
  hrWorkspaceEnabled,
  clearPendingPrincipalTransition,
  clearPrincipalModePreference,
  loadPendingPrincipalTransition,
  loadPrincipalModePreference,
  resolveShell,
  savePendingPrincipalTransition,
  savePrincipalModePreference,
  type PendingPrincipalTransition,
  type PrincipalMode,
  type ResolvedShell,
} from './mode'
import { loadPrincipalDiagnostics, recordPrincipalDiagnostic } from './principalDiagnostics'

export type PrincipalTransitionErrorCode =
  | 'hr_workspace_disabled'
  | 'principal_transition_invalid_record'
  | 'principal_transition_exit_seal_failed'
  | 'principal_transition_persist_failed'
  | 'principal_transition_mount_timeout'
  | 'principal_transition_complete_failed'
  | 'principal_transition_rollback_failed'

export type PrincipalTransition =
  | { status: 'idle'; from: null; to: null; error: null; errorCode: null }
  | {
      status: 'switching'
      from: PrincipalMode | null
      to: PrincipalMode
      error: null
      errorCode: null
    }
  | {
      status: 'error'
      from: PrincipalMode | null
      to: PrincipalMode
      error: 'principal_transition_failed'
      errorCode: PrincipalTransitionErrorCode
    }

type MountDetails = {
  route: string
  lockPrincipal?: PrincipalMode | null
}

type PrincipalGateValue = {
  ready: boolean
  shell: ResolvedShell | null
  pendingTarget: PrincipalMode | null
  employeeSession: boolean
  hrSession: boolean
  transition: PrincipalTransition
  selectMode: (mode: PrincipalMode, prepareExit?: () => Promise<void>) => Promise<boolean>
  acknowledgePrincipalMounted: (mode: PrincipalMode, details: MountDetails) => void
  clearTransitionError: () => void
  refreshAvailability: () => Promise<void>
}

const PrincipalGateContext = createContext<PrincipalGateValue | null>(null)

export function usePrincipalGate(): PrincipalGateValue {
  const value = useContext(PrincipalGateContext)
  if (!value) throw new Error('usePrincipalGate requires PrincipalGateProvider')
  return value
}

function errorCode(error: unknown, fallback: PrincipalTransitionErrorCode): PrincipalTransitionErrorCode {
  const value = error instanceof Error ? error.message : String(error || '')
  if (
    value === 'hr_workspace_disabled' ||
    value === 'principal_transition_invalid_record' ||
    value === 'principal_transition_exit_seal_failed' ||
    value === 'principal_transition_persist_failed' ||
    value === 'principal_transition_mount_timeout' ||
    value === 'principal_transition_complete_failed' ||
    value === 'principal_transition_rollback_failed'
  ) {
    return value
  }
  return fallback
}

function transitionId(mode: PrincipalMode): string {
  return `${mode}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function PrincipalGateProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [employeeSession, setEmployeeSession] = useState(false)
  const [hrSession, setHrSession] = useState(false)
  const [shell, setShell] = useState<ResolvedShell | null>(null)
  const [pendingTarget, setPendingTarget] = useState<PrincipalMode | null>(null)
  const [transition, setTransition] = useState<PrincipalTransition>({
    status: 'idle',
    from: null,
    to: null,
    error: null,
    errorCode: null,
  })
  const shellRef = useRef<ResolvedShell | null>(null)
  const availabilityRef = useRef({ employeeSession: false, hrSession: false })
  const transactionRef = useRef<PendingPrincipalTransition | null>(null)
  const transitionPromiseRef = useRef<Promise<boolean> | null>(null)
  const transitionOutcomeRef = useRef<((result: boolean) => void) | null>(null)
  const mountTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const failureInFlightRef = useRef(false)

  shellRef.current = shell
  availabilityRef.current = { employeeSession, hrSession }

  const settleCaller = useCallback((result: boolean) => {
    const resolve = transitionOutcomeRef.current
    transitionOutcomeRef.current = null
    resolve?.(result)
  }, [])

  const rollbackTransition = useCallback(
    async (
      pending: PendingPrincipalTransition,
      code: PrincipalTransitionErrorCode,
    ): Promise<void> => {
      if (failureInFlightRef.current) return
      failureInFlightRef.current = true
      if (mountTimerRef.current) {
        clearTimeout(mountTimerRef.current)
        mountTimerRef.current = null
      }

      let rollbackCode = code
      try {
        await clearPendingPrincipalTransition()
      } catch (caught) {
        rollbackCode = errorCode(caught, 'principal_transition_rollback_failed')
      }
      try {
        if (pending.previousPreference) {
          await savePrincipalModePreference(pending.previousPreference)
        } else {
          await clearPrincipalModePreference()
        }
      } catch (caught) {
        rollbackCode = errorCode(caught, 'principal_transition_rollback_failed')
      }

      const fallback = pending.from
        ? ({ kind: pending.from } as ResolvedShell)
        : resolveShell(availabilityRef.current, pending.previousPreference)
      transactionRef.current = null
      setPendingTarget(null)
      setShell(fallback)
      setTransition({
        status: 'error',
        from: pending.from,
        to: pending.to,
        error: 'principal_transition_failed',
        errorCode: rollbackCode,
      })
      recordPrincipalDiagnostic({
        event: 'transition_failed',
        transitionId: pending.id,
        target: pending.to,
        employeeSession: availabilityRef.current.employeeSession,
        hrSession: availabilityRef.current.hrSession,
        errorCode: rollbackCode,
      })
      settleCaller(false)
      failureInFlightRef.current = false
    },
    [settleCaller],
  )

  const armMountTimeout = useCallback(
    (pending: PendingPrincipalTransition) => {
      if (mountTimerRef.current) clearTimeout(mountTimerRef.current)
      mountTimerRef.current = setTimeout(() => {
        if (transactionRef.current?.id !== pending.id) return
        void rollbackTransition(pending, 'principal_transition_mount_timeout')
      }, 15_000)
    },
    [rollbackTransition],
  )

  const refreshAvailability = useCallback(async () => {
    if (!hrWorkspaceEnabled()) {
      setEmployeeSession(false)
      setHrSession(false)
      setPendingTarget(null)
      setShell({ kind: 'employee' })
      setReady(true)
      return
    }

    const [employee, operator, preference, storedPending] = await Promise.all([
      loadSession(),
      loadOperatorSession(),
      loadPrincipalModePreference(),
      loadPendingPrincipalTransition().catch((caught: unknown) => {
        recordPrincipalDiagnostic({
          event: 'transition_failed',
          errorCode: errorCode(caught, 'principal_transition_invalid_record'),
        })
        return null
      }),
    ])
    const availability = {
      employeeSession: Boolean(employee?.token && employee?.refreshToken),
      hrSession: Boolean(operator?.accessToken && operator?.refreshToken),
    }
    availabilityRef.current = availability
    setEmployeeSession(availability.employeeSession)
    setHrSession(availability.hrSession)

    const pending = storedPending || transactionRef.current
    if (pending) {
      transactionRef.current = pending
      setPendingTarget(pending.to)
      setShell({ kind: pending.to })
      setTransition({
        status: 'switching',
        from: pending.from,
        to: pending.to,
        error: null,
        errorCode: null,
      })
      recordPrincipalDiagnostic({
        event: 'transition_recovered',
        transitionId: pending.id,
        target: pending.to,
        employeeSession: availability.employeeSession,
        hrSession: availability.hrSession,
      })
      armMountTimeout(pending)
    } else {
      setPendingTarget(null)
      setShell(resolveShell(availability, preference))
    }
    setReady(true)
  }, [armMountTimeout])

  useEffect(() => {
    void loadPrincipalDiagnostics().finally(() => {
      void refreshAvailability()
    })
  }, [refreshAvailability])

  useEffect(
    () => () => {
      if (mountTimerRef.current) clearTimeout(mountTimerRef.current)
      // A process/root shutdown is not a failed switch. The pending record is
      // intentionally retained so the same target resumes on the next mount.
      settleCaller(false)
    },
    [settleCaller],
  )

  const completeTransition = useCallback(
    async (mode: PrincipalMode, details: MountDetails): Promise<void> => {
      const pending = transactionRef.current
      if (!pending || pending.to !== mode || failureInFlightRef.current) return
      if (mountTimerRef.current) {
        clearTimeout(mountTimerRef.current)
        mountTimerRef.current = null
      }
      recordPrincipalDiagnostic({
        event: 'provider_mount_ack',
        transitionId: pending.id,
        target: mode,
        route: details.route,
        employeeSession: availabilityRef.current.employeeSession,
        hrSession: availabilityRef.current.hrSession,
        lockPrincipal: details.lockPrincipal ?? null,
      })
      try {
        await clearPendingPrincipalTransition()
      } catch (caught) {
        await rollbackTransition(
          pending,
          errorCode(caught, 'principal_transition_complete_failed'),
        )
        return
      }
      transactionRef.current = null
      setPendingTarget(null)
      setTransition({ status: 'idle', from: null, to: null, error: null, errorCode: null })
      recordPrincipalDiagnostic({
        event: 'transition_completed',
        transitionId: pending.id,
        target: mode,
        route: details.route,
        employeeSession: availabilityRef.current.employeeSession,
        hrSession: availabilityRef.current.hrSession,
        lockPrincipal: details.lockPrincipal ?? null,
      })
      settleCaller(true)
    },
    [rollbackTransition, settleCaller],
  )

  const acknowledgePrincipalMounted = useCallback(
    (mode: PrincipalMode, details: MountDetails) => {
      void completeTransition(mode, details)
    },
    [completeTransition],
  )

  const selectMode = useCallback(
    (mode: PrincipalMode, prepareExit?: () => Promise<void>): Promise<boolean> => {
      // Rapid repeated taps join the one authoritative transition.
      if (transitionPromiseRef.current) return transitionPromiseRef.current

      const currentShell = shellRef.current
      const currentMode =
        currentShell?.kind === 'employee' || currentShell?.kind === 'hr'
          ? currentShell.kind
          : null
      // Deliberately synchronous with the tap: the outgoing principal can
      // suppress its lock surface before storage reads or route replacement.
      setTransition({
        status: 'switching',
        from: currentMode,
        to: mode,
        error: null,
        errorCode: null,
      })

      const run = async (): Promise<boolean> => {
        const previousShell = shellRef.current
        const previousMode =
          previousShell?.kind === 'employee' || previousShell?.kind === 'hr'
            ? previousShell.kind
            : null
        let previousPreference: PrincipalMode | null = null
        let pending: PendingPrincipalTransition | null = null

        try {
          if (mode === 'hr' && !hrWorkspaceEnabled()) {
            throw new Error('hr_workspace_disabled')
          }
          if (prepareExit) {
            try {
              await prepareExit()
            } catch {
              throw new Error('principal_transition_exit_seal_failed')
            }
          }
          previousPreference = await loadPrincipalModePreference()
          const [employee, operator] = await Promise.all([loadSession(), loadOperatorSession()])
          const availability = {
            employeeSession: Boolean(employee?.token && employee?.refreshToken),
            hrSession: Boolean(operator?.accessToken && operator?.refreshToken),
          }
          availabilityRef.current = availability
          pending = {
            id: transitionId(mode),
            from: previousMode,
            to: mode,
            previousPreference,
            startedAt: Date.now(),
          }

          // Persist before changing route/shell. A root, navigator, or process
          // remount must continue toward this target instead of resolving from
          // the other principal's stored session.
          try {
            await savePendingPrincipalTransition(pending)
            await savePrincipalModePreference(mode)
          } catch (caught) {
            throw new Error(errorCode(caught, 'principal_transition_persist_failed'))
          }

          transactionRef.current = pending
          setEmployeeSession(availability.employeeSession)
          setHrSession(availability.hrSession)
          setPendingTarget(mode)
          setShell({ kind: mode })
          setTransition({
            status: 'switching',
            from: previousMode,
            to: mode,
            error: null,
            errorCode: null,
          })
          recordPrincipalDiagnostic({
            event: 'transition_started',
            transitionId: pending.id,
            target: mode,
            employeeSession: availability.employeeSession,
            hrSession: availability.hrSession,
          })
          armMountTimeout(pending)

          return await new Promise<boolean>((resolve) => {
            transitionOutcomeRef.current = resolve
          })
        } catch (caught) {
          const code = errorCode(caught, 'principal_transition_persist_failed')
          const failed =
            pending ||
            ({
              id: transitionId(mode),
              from: previousMode,
              to: mode,
              previousPreference,
              startedAt: Date.now(),
            } satisfies PendingPrincipalTransition)
          await rollbackTransition(failed, code)
          return false
        }
      }

      const promise = run().finally(() => {
        transitionPromiseRef.current = null
      })
      transitionPromiseRef.current = promise
      return promise
    },
    [armMountTimeout, rollbackTransition],
  )

  const clearTransitionError = useCallback(() => {
    setTransition((current) =>
      current.status === 'error'
        ? { status: 'idle', from: null, to: null, error: null, errorCode: null }
        : current,
    )
  }, [])

  const value = useMemo(
    () => ({
      ready,
      shell,
      pendingTarget,
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
      pendingTarget,
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

export function PrincipalMountAck({
  mode,
  ready = true,
  route,
  lockPrincipal = null,
}: {
  mode: PrincipalMode
  ready?: boolean
  route: string
  lockPrincipal?: PrincipalMode | null
}) {
  const { transition, acknowledgePrincipalMounted } = usePrincipalGate()
  useEffect(() => {
    if (ready && transition.status === 'switching' && transition.to === mode) {
      acknowledgePrincipalMounted(mode, { route, lockPrincipal })
    }
  }, [acknowledgePrincipalMounted, lockPrincipal, mode, ready, route, transition])
  return null
}

export function PrincipalBootSplash() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg }}>
      <ActivityIndicator testID="e2e.boot.principal" color={colors.accent} />
    </View>
  )
}
