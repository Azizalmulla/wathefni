import { useCallback, useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ScheduleView } from '@/features/schedule/ScheduleView'
import type { WorkdayResponse } from '@/api/types'

export default function ScheduleScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const { locale } = useI18n()
  // Schedule combines existing authorities, so either entitlement opens it. The
  // projection then reports which of them it could actually read.
  const enabled = hasFeature('shifts') || hasFeature('attendance')
  const query = useAppQuery<WorkdayResponse>(
    ['workday', locale],
    `/app/workday?locale=${encodeURIComponent(locale)}`,
    { enabled, staleTime: HIGH_CHURN_STALE_MS },
  )
  const [refreshing, setRefreshing] = useState(false)

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (!enabled) {
    return (
      <FeatureUnavailableState
        feature={['shifts', 'attendance']}
        onRefresh={() => void refreshMe()}
      />
    )
  }
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  if (!query.data) return <LoadingState />

  return <ScheduleView data={query.data} refreshing={refreshing} onRefresh={() => void onRefresh()} />
}
