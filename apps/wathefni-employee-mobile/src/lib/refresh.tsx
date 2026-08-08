import { useCallback, useEffect, useRef } from 'react'
import { AppState, type AppStateStatus } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { getAutoLockDiagnostics } from '@/auth/autoLockDiagnostics'
import { softRefreshEmployeeSurfaces } from '@/lib/employeeSoftRefresh'

/**
 * When the app returns to foreground, soft-refresh /app/me + active queries.
 * Keeps mounted screens' cached content visible (no remount / full-screen flash).
 * Skips while the local unlock overlay is up; unlock dismiss runs the same refresh.
 */
export function ForegroundQueryRefresh() {
  const queryClient = useQueryClient()
  const { refreshMe, status } = useAuth()
  const appState = useRef(AppState.currentState)
  const refreshMeRef = useRef(refreshMe)
  refreshMeRef.current = refreshMe

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      try {
        const wasBackground = appState.current === 'background' || appState.current === 'inactive'
        appState.current = next
        if (next === 'active' && wasBackground) {
          // Soft refetch — never throw into AppState. Skip while local unlock
          // overlay covers the app so nav/scroll under it stay still.
          if (getAutoLockDiagnostics().needsLocalUnlock) return
          if (status !== 'signedIn') return
          void softRefreshEmployeeSurfaces(queryClient, refreshMeRef.current)
        }
      } catch (error) {
        console.warn('[refresh] AppState handler error', error)
      }
    }
    const sub = AppState.addEventListener('change', onChange)
    return () => sub.remove()
  }, [queryClient, status])

  return null
}

/** Shared pull-to-refresh helper that keeps prior data on screen. */
export function usePullToRefresh(refetchers: Array<() => Promise<unknown>>) {
  const refreshingRef = useRef(false)
  const onRefresh = useCallback(async () => {
    if (refreshingRef.current) return
    refreshingRef.current = true
    try {
      await Promise.all(refetchers.map((fn) => fn()))
    } finally {
      refreshingRef.current = false
    }
  }, [refetchers])
  return onRefresh
}
