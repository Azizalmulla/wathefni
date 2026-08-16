import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useRouter, type Href } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { EmployeePushedEscape } from '@/components/EmployeePushedEscape'
import { NotificationsView } from '@/features/remaining/RemainingViews'
import { inboxOpenableHref } from '@/features/inbox/inboxNavigation'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import type { NotificationItem, NotificationsResponse } from '@/api/types'
import { syncInboxBadge } from '@/push/syncInboxBadge'

function optimisticMarkRead(
  previous: NotificationsResponse | undefined,
  messageId: string,
): NotificationsResponse | undefined {
  if (!previous) return previous
  let flipped = false
  const notifications = previous.notifications.map((row) => {
    if (String(row.id) !== messageId || row.read) return row
    flipped = true
    return { ...row, read: true }
  })
  if (!flipped) return previous
  return {
    ...previous,
    notifications,
    unread: Math.max(0, Number(previous.unread || 0) - 1),
  }
}

export default function NotificationsScreen() {
  const { me, request } = useAuth()
  const { t, locale } = useI18n()
  const router = useRouter()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()
  const query = useAppQuery<NotificationsResponse>(
    ['notifications', locale],
    `/app/notifications?locale=${encodeURIComponent(locale)}`,
    { staleTime: HIGH_CHURN_STALE_MS },
  )
  const [refreshing, setRefreshing] = useState(false)
  const markReadLocks = useRef(new Set<string>())
  /** Latest press wins — older in-flight taps do not navigate after a newer one. */
  const pressGeneration = useRef(0)

  useEffect(() => {
    if (query.data?.unread == null) return
    void syncInboxBadge(query.data.unread)
  }, [query.data?.unread])

  const openItem = useCallback(
    (item: NotificationItem) => {
      const generation = ++pressGeneration.current
      const id = String(item.id)
      const href = inboxOpenableHref(me, item)

      // Navigate on the next frame so press feedback paints, then start the
      // route immediately. Latest press wins — older frames no-op.
      requestAnimationFrame(() => {
        if (generation !== pressGeneration.current) return
        if (href) {
          router.push(href as Href)
        } else if (item.deep_link?.path) {
          Alert.alert(t('notifications.title'), t('home.linkUnavailable'))
        }
        // Flip read after navigation starts so Unread→Updates reordering does
        // not steal a frame on this screen before the push.
        if (!item.read) {
          queryClient.setQueriesData<NotificationsResponse>(
            { queryKey: ['notifications'] },
            (prev: NotificationsResponse | undefined) => {
              const next = optimisticMarkRead(prev, id)
              if (next) void syncInboxBadge(next.unread)
              return next
            },
          )
        }
      })

      // Mark-read in the background — never blocks navigation.
      if (!item.read && !markReadLocks.current.has(id)) {
        markReadLocks.current.add(id)
        void (async () => {
          try {
            await request(`/app/notifications/${item.id}/read`, { method: 'POST' })
            void queryClient.invalidateQueries({ queryKey: ['notifications'] })
          } catch (err) {
            void queryClient.invalidateQueries({ queryKey: ['notifications'] })
            Alert.alert(t('common.error'), approvedErrorMessage(err, t))
          } finally {
            markReadLocks.current.delete(id)
          }
        })()
      }
    },
    [me, queryClient, request, router, t],
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (query.isLoading && !query.data) {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <LoadingState />
      </EmployeePushedEscape>
    )
  }
  if (query.isError && !query.data) {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </EmployeePushedEscape>
    )
  }
  return (
    <NotificationsView
      data={query.data ?? { ok: true, unread: 0, notifications: [] }}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onMarkRead={openItem}
      // Inbox is entered from the Home bell rather than a tab, so it owns a back
      // control. A push tap can land here cold, hence the Home fallback.
      onBack={onBack}
    />
  )
}
