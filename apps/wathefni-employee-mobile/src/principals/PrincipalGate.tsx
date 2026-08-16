import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ActivityIndicator, View } from 'react-native'
import { createContext, useContext } from 'react'

import { loadSession } from '@/auth/session'
import { loadOperatorSession } from '@hr/auth/session'
import { colors } from '@/theme'
import {
  hrWorkspaceEnabled,
  loadPrincipalModePreference,
  resolveShell,
  savePrincipalModePreference,
  type PrincipalMode,
  type ResolvedShell,
} from './mode'

type PrincipalGateValue = {
  ready: boolean
  shell: ResolvedShell | null
  employeeSession: boolean
  hrSession: boolean
  selectMode: (mode: PrincipalMode) => Promise<void>
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

  const selectMode = useCallback(async (mode: PrincipalMode) => {
    await savePrincipalModePreference(mode)
    setShell({ kind: mode })
  }, [])

  const value = useMemo(
    () => ({
      ready,
      shell,
      employeeSession,
      hrSession,
      selectMode,
      refreshAvailability,
    }),
    [ready, shell, employeeSession, hrSession, selectMode, refreshAvailability],
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
