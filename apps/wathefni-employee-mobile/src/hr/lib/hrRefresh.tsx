/**
 * HR freshness: keep mounted HR screens converged with the canonical backend
 * after HR Web or the Employee App mutates the same records.
 *
 * Targeted refetch only — no polling. A mounted screen catches up when the app
 * returns to the foreground, when the operator navigates back to it, and when
 * the local-unlock overlay is dismissed.
 */

import { useCallback, useEffect, useRef } from 'react'
import { AppState, InteractionManager, type AppStateStatus } from 'react-native'
import { useFocusEffect } from 'expo-router'
import { focusManager, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { useAuth } from '@hr/auth/AuthProvider'

/** Two foreground events inside this window run one refresh, not two. */
const REFRESH_THROTTLE_MS = 3_000

async function runSoftRefresh(
  queryClient: QueryClient,
  refreshMe: () => Promise<boolean>,
): Promise<void> {
  try {
    await refreshMe()
  } catch (error) {
    console.warn('[hr-refresh] me soft refresh failed', error)
  }
  try {
    await queryClient.refetchQueries({ type: 'active' })
  } catch (error) {
    console.warn('[hr-refresh] active query soft refresh failed', error)
  }
}

/**
 * Refetch the mounted HR screens without a remount, deferred past interactions
 * so the resume animation is not competing with network work.
 */
export function softRefreshHrSurfaces(
  queryClient: QueryClient,
  refreshMe: () => Promise<boolean>,
): Promise<void> {
  return new Promise((resolve) => {
    InteractionManager.runAfterInteractions(() => {
      setTimeout(() => {
        void runSoftRefresh(queryClient, refreshMe).finally(resolve)
      }, 64)
    })
  })
}

/**
 * Mount once inside the HR AuthProvider. Also teaches React Query what
 * "focused" means on native, which is otherwise a web-only concept.
 */
export function HrForegroundQueryRefresh() {
  const queryClient = useQueryClient()
  const { refreshMe, status } = useAuth()
  const appState = useRef(AppState.currentState)
  const lastRefreshAt = useRef(0)
  const refreshMeRef = useRef(refreshMe)
  refreshMeRef.current = refreshMe

  useEffect(() => {
    focusManager.setEventListener((handleFocus) => {
      const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
        handleFocus(next === 'active')
      })
      return () => sub.remove()
    })
  }, [])

  useEffect(() => {
    const onChange = (next: AppStateStatus) => {
      try {
        const wasBackground = appState.current === 'background' || appState.current === 'inactive'
        appState.current = next
        if (next !== 'active' || !wasBackground) return
        if (status !== 'signedIn') return
        const now = Date.now()
        if (now - lastRefreshAt.current < REFRESH_THROTTLE_MS) return
        lastRefreshAt.current = now
        void softRefreshHrSurfaces(queryClient, refreshMeRef.current)
      } catch (error) {
        console.warn('[hr-refresh] AppState handler error', error)
      }
    }
    const sub = AppState.addEventListener('change', onChange)
    return () => sub.remove()
  }, [queryClient, status])

  return null
}

/**
 * Refetch when the operator navigates back to a screen that stayed mounted.
 * Skips the first focus because mounting already fetched.
 */
export function useRefetchOnScreenFocus(refetch: () => void, enabled = true) {
  const refetchRef = useRef(refetch)
  refetchRef.current = refetch
  const mounted = useRef(false)
  const lastAt = useRef(0)

  useFocusEffect(
    useCallback(() => {
      if (!mounted.current) {
        mounted.current = true
        return
      }
      if (!enabled) return
      const now = Date.now()
      if (now - lastAt.current < REFRESH_THROTTLE_MS) return
      lastAt.current = now
      refetchRef.current()
    }, [enabled]),
  )
}
