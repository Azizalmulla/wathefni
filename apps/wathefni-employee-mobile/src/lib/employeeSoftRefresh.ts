/**
 * Shared soft refresh for Employee App surfaces.
 * Used after foreground resume and after PIN/Face ID unlock so /app/me and
 * active React Query screens catch up without a full remount or new realtime bus.
 */
import type { QueryClient } from '@tanstack/react-query'

export async function softRefreshEmployeeSurfaces(
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

/** High-churn screens must not contradict Home for 30s after HR decisions. */
export const HIGH_CHURN_STALE_MS = 0
