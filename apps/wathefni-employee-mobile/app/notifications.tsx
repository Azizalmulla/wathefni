import { useCallback, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useRouter, type Href } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { HOME_ROUTE, openableHref } from '@/composition/employeeAppComposition'
import { ErrorState, LoadingState } from '@/components/States'
import { NotificationsView } from '@/features/remaining/RemainingViews'
import type { NotificationItem, NotificationsResponse } from '@/api/types'

export default function NotificationsScreen() {
  const { me, request } = useAuth()
  const { t, locale } = useI18n()
  const router = useRouter()
  const queryClient = useQueryClient()
  const query = useAppQuery<NotificationsResponse>(
    ['notifications', locale],
    `/app/notifications?locale=${encodeURIComponent(locale)}`,
    { staleTime: HIGH_CHURN_STALE_MS },
  )
  const [refreshing, setRefreshing] = useState(false)
  const markReadLocks = useRef(new Set<string>())

  const markRead = useCallback(
    async (item: NotificationItem) => {
      const id = String(item.id)
      if (!item.read && !markReadLocks.current.has(id)) {
        markReadLocks.current.add(id)
        try {
          await request(`/app/notifications/${item.id}/read`, { method: 'POST' })
          await queryClient.invalidateQueries({ queryKey: ['notifications'] })
        } catch (err) {
          Alert.alert(t('common.error'), approvedErrorMessage(err, t))
        } finally {
          markReadLocks.current.delete(id)
        }
      }
      // Deep links are resolved against the route registry, so an unknown path, a
      // parameter the destination does not read, or a removed entitlement all end in
      // the same calm outcome instead of a silent no-op.
      const payslipId = String(item.deep_link?.payslip_id || '')
      const candidate =
        String(item.deep_link?.path || '') ||
        (String(item.flow || '') === 'payroll' ? '/payslips' : '')
      if (!candidate) return
      const withParams =
        payslipId && candidate.startsWith('/payslips') && !candidate.includes('?')
          ? `${candidate}?payslip_id=${encodeURIComponent(payslipId)}`
          : candidate
      const href = openableHref(me, withParams)
      if (!href) {
        Alert.alert(t('notifications.title'), t('home.linkUnavailable'))
        return
      }
      router.push(href as Href)
    },
    [me, request, queryClient, router, t],
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  return (
    <NotificationsView
      data={query.data ?? { ok: true, unread: 0, notifications: [] }}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onMarkRead={(item) => void markRead(item)}
      // Inbox is entered from the Home bell rather than a tab, so it owns a back
      // control. A push tap can land here cold, hence the Home fallback.
      onBack={() => (router.canGoBack() ? router.back() : router.replace(HOME_ROUTE as Href))}
    />
  )
}
