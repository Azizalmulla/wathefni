import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { BenefitsHubView } from '@/features/benefits/BenefitsHubView'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Workspace = {
  resource_state?: string
  plans?: Array<{ plan_id?: string; title_en?: string; title_ar?: string; code?: string; status?: string }> | null
  enrollments?: Array<{
    enrollment_id?: string
    plan_id?: string
    title_en?: string
    title_ar?: string
    status?: string
    elected?: boolean
    waived?: boolean
    coverage_active?: boolean
  }> | null
  coverage?: Array<{
    coverage_id?: string
    plan_id?: string
    title_en?: string
    title_ar?: string
    status?: string
    start_date?: string
    provider_confirmed?: boolean
  }> | null
}

export default function BenefitsScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('benefits')
  const query = useAppQuery<Workspace>(['benefits'], '/app/benefits', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [refreshing, setRefreshing] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="benefits" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }
  if (query.data?.resource_state === 'unavailable' || query.data?.plans == null) {
    return <FeatureUnavailableState feature="benefits" />
  }

  return (
    <BenefitsHubView
      plans={query.data.plans || []}
      enrollments={query.data.enrollments || []}
      coverage={query.data.coverage || []}
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true)
        void Promise.all([query.refetch(), refreshMe()]).finally(() => setRefreshing(false))
      }}
    />
  )
}
