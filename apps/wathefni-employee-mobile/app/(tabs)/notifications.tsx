import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { NotificationsView } from '@/features/remaining/RemainingViews'
import type { NotificationItem, NotificationsResponse } from '@/api/types'

export default function NotificationsScreen() {
  const { request } = useAuth()
  const queryClient = useQueryClient()
  const query = useAppQuery<NotificationsResponse>(['notifications'], '/app/notifications')

  const markRead = useCallback(
    async (item: NotificationItem) => {
      if (item.read) return
      try {
        await request(`/app/notifications/${item.id}/read`, { method: 'POST' })
        await queryClient.invalidateQueries({ queryKey: ['notifications'] })
      } catch {
        // Non-critical: the unread dot simply stays until the next refresh.
      }
    },
    [request, queryClient],
  )

  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  return <NotificationsView data={query.data ?? { ok: true, unread: 0, notifications: [] }} onMarkRead={(item) => void markRead(item)} />
}
