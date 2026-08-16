import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { TalentHubView } from '@/features/talent/TalentHubView'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Workspace = {
  facts?: unknown[]
  skills?: unknown[]
  mobility?: { preferences?: unknown[] }
}

export default function TalentScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('talent')
  const query = useAppQuery<Workspace>(['talent'], '/app/talent', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [refreshing, setRefreshing] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="talent" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  return (
    <TalentHubView
      facts={(query.data?.facts || []).length}
      skills={(query.data?.skills || []).length}
      mobility={(query.data?.mobility?.preferences || []).length}
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true)
        void Promise.all([query.refetch(), refreshMe()]).finally(() => setRefreshing(false))
      }}
    />
  )
}
