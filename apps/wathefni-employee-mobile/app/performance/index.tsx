import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PerformanceHubView } from '@/features/performance/PerformanceHubView'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Workspace = {
  goals?: unknown[]
  reviews?: unknown[]
  check_ins?: unknown[]
  development?: unknown[]
  active_okr_cycle?: { name_en?: string; name_ar?: string } | null
}

export default function PerformanceScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const { isRTL } = useI18n()
  const enabled = hasFeature('performance')
  const query = useAppQuery<Workspace>(['performance'], '/app/performance', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [refreshing, setRefreshing] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  return (
    <PerformanceHubView
      goals={(query.data?.goals || []).length}
      reviews={(query.data?.reviews || []).length}
      checkIns={(query.data?.check_ins || []).length}
      development={(query.data?.development || []).length}
      okrCycleName={
        isRTL
          ? query.data?.active_okr_cycle?.name_ar || query.data?.active_okr_cycle?.name_en || null
          : query.data?.active_okr_cycle?.name_en || query.data?.active_okr_cycle?.name_ar || null
      }
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true)
        void Promise.all([query.refetch(), refreshMe()]).finally(() => setRefreshing(false))
      }}
    />
  )
}
