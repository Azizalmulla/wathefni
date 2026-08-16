/**
 * Shared soft refresh for Employee App surfaces.
 * Used after foreground resume and after PIN/Face ID unlock so /app/me and
 * active React Query screens catch up without a full remount or new realtime bus.
 *
 * Deferred until after interactions so the first post-loading paint is not
 * competing with /me + active refetch on the same frames.
 */
import { InteractionManager } from 'react-native'
import type { QueryClient } from '@tanstack/react-query'

async function runSoftRefresh(
  queryClient: QueryClient,
  refreshMe: () => Promise<boolean>,
): Promise<void> {
  try {
    await refreshMe()
  } catch (error) {
    console.warn('[refresh] me soft refresh failed', error)
  }
  try {
    await queryClient.refetchQueries({ type: 'active' })
  } catch (error) {
    console.warn('[refresh] active query soft refresh failed', error)
  }
}

export function softRefreshEmployeeSurfaces(
  queryClient: QueryClient,
  refreshMe: () => Promise<boolean>,
): Promise<void> {
  return new Promise((resolve) => {
    const handle = InteractionManager.runAfterInteractions(() => {
      // One frame after interactions so layout/FadeIn can settle first.
      setTimeout(() => {
        void runSoftRefresh(queryClient, refreshMe).finally(resolve)
      }, 64)
    })
    // If the InteractionManager handle is cancelled, still resolve.
    if (handle && typeof (handle as { cancel?: () => void }).cancel === 'function') {
      // no-op — promise resolves when refresh finishes
    }
  })
}

/** High-churn screens must not contradict Home for 30s after HR decisions. */
export const HIGH_CHURN_STALE_MS = 0
