import { useCallback, useEffect, useRef } from 'react'
import { AppState, type AppStateStatus } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { getAutoLockDiagnostics } from '@/auth/autoLockDiagnostics'

/**
 * When the app returns to foreground, refetch active queries in the background.
 * Keeps mounted screens' cached content visible (no remount / full-screen flash).
 */
export function ForegroundQueryRefresh() {
  const queryClient = useQueryClient()
  const appState = useRef(AppState.currentState)

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      try {
        const wasBackground = appState.current === 'background' || appState.current === 'inactive'
        appState.current = next
        if (next === 'active' && wasBackground) {
          // Soft refetch — never throw into AppState. Skip while local unlock
          // overlay covers the app so nav/scroll under it stay still.
          if (getAutoLockDiagnostics().needsLocalUnlock) return
          void queryClient.refetchQueries({ type: 'active' }).catch((error) => {
            console.warn('[refresh] foreground refetch failed', error)
          })
        }
      } catch (error) {
        console.warn('[refresh] AppState handler error', error)
      }
    }
    const sub = AppState.addEventListener('change', onChange)
    return () => sub.remove()
  }, [queryClient])

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
