import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { LearningHubView } from '@/features/learning/LearningHubView'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Workspace = {
  resource_state?: string
  required?: unknown[]
  assignments?: unknown[]
  upcoming?: unknown[]
  completed?: unknown[]
  certifications?: unknown[]
  catalog?: unknown[]
}

export default function LearningScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('learning')
  const query = useAppQuery<Workspace>(['learning'], '/app/learning', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [refreshing, setRefreshing] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="learning" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }
  if (query.data?.resource_state === 'unavailable') {
    return <FeatureUnavailableState feature="learning" />
  }

  return (
    <LearningHubView
      required={(query.data?.required || []).length}
      assigned={(query.data?.assignments || []).length}
      upcoming={(query.data?.upcoming || []).length}
      completed={(query.data?.completed || []).length}
      certificates={(query.data?.certifications || []).length}
      catalog={(query.data?.catalog || []).length}
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true)
        void Promise.all([query.refetch(), refreshMe()]).finally(() => setRefreshing(false))
      }}
    />
  )
}
