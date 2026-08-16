import { dashboardQueryClient } from '@/lib/query/client'
import { invalidate } from '@/lib/query/invalidation'
import type { DashboardAccess } from '@/types'

/** Call after post-hire mutations that change dates projected onto Calendar. */
export function touchCalendarProjections(access: DashboardAccess) {
  void invalidate.afterPostHireProjectionTouch(dashboardQueryClient, access)
}
