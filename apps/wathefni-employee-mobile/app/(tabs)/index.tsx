import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter, type Href } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { LoadingState } from '@/components/States'
import { HomeErrorView, HomeView } from '@/features/home/HomeView'
import { canFetchEmployeeHome } from '@/features/home/homeQueryPolicy'
import {
  HOME_ROUTE,
  compositionFromMe,
  homeTasksFromServer,
  openableHref,
} from '@/composition/employeeAppComposition'
import type { HomeResponse } from '@/api/types'
import { syncInboxBadge } from '@/push/syncInboxBadge'

export default function HomeScreen() {
  const { me, profile, refreshMe, status } = useAuth()
  const { locale } = useI18n()
  const router = useRouter()
  const [refreshing, setRefreshing] = useState(false)

  // One server-owned projection. Home presents what the owning modules report; it does
  // not re-query each module and re-derive workflow rules from status strings.
  const home = useAppQuery<HomeResponse>(
    ['home', locale],
    `/app/home?locale=${encodeURIComponent(locale)}`,
    {
      enabled: canFetchEmployeeHome(status),
      staleTime: HIGH_CHURN_STALE_MS,
    },
  )
  const data = home.data

  useEffect(() => {
    if (data?.inbox?.unread == null) return
    void syncInboxBadge(data.inbox.unread)
  }, [data?.inbox?.unread])

  const composition = useMemo(
    () =>
      compositionFromMe(
        me,
        data?.onboarding
          ? {
              featureEnabled: data.modules.onboarding !== 'disabled',
              requiredPending: data.onboarding.pending_count,
              pendingCount: data.onboarding.pending_count,
              requiredTotal: data.onboarding.required_total,
            }
          : null,
      ),
    [me, data?.onboarding, data?.modules.onboarding],
  )

  const tasks = useMemo(() => homeTasksFromServer(me, data?.tasks), [me, data?.tasks])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await Promise.all([refreshMe(), home.refetch()])
    } finally {
      setRefreshing(false)
    }
  }, [refreshMe, home])

  const onNavigate = useCallback(
    (path: string) => {
      const href = openableHref(me, path)
      if (!href) {
        router.replace(HOME_ROUTE as Href)
        return
      }
      router.push(href as Href)
    },
    [me, router],
  )

  if (!data && home.isLoading) return <LoadingState />
  if (!data && home.isError) return <HomeErrorView onRetry={() => void home.refetch()} />
  if (!data) return <LoadingState />

  return (
    <HomeView
      profile={profile}
      composition={composition}
      home={data}
      tasks={tasks}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onNavigate={onNavigate}
    />
  )
}
