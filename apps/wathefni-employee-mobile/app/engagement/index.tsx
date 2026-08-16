import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { EngagementHubView } from '@/features/engagement/EngagementHubView'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Workspace = {
  resource_state?: string
  surveys?: Array<{
    campaign_id?: string
    title_en?: string
    title_ar?: string
    privacy_mode?: string
    privacy_mode_label_en?: string
    privacy_mode_label_ar?: string
    anonymous?: boolean
    identified?: boolean
    participation_status?: string
    state?: string
  }> | null
}

export default function EngagementScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('engagement')
  const query = useAppQuery<Workspace>(['engagement'], '/app/engagement', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })

  if (!enabled) return <FeatureUnavailableState feature="engagement" />
  if (query.isPending && !query.data) return <LoadingState />
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />
  if (query.data?.resource_state === 'unavailable' || query.data?.surveys == null) {
    return <FeatureUnavailableState feature="engagement" />
  }

  return (
    <EngagementHubView
      surveys={query.data.surveys || []}
      refreshing={query.isRefetching}
      onRefresh={() => {
        void refreshMe()
        void query.refetch()
      }}
    />
  )
}
