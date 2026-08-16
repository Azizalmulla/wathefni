import { Pressable } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading } from '@/components/premium'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { spacing } from '@/theme'

type Review = {
  review_id: string
  cycle_name_en?: string
  cycle_name_ar?: string
  reviewer_role?: string
  status?: string
}

export default function PerformanceReviewsScreen() {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const { hasFeature } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<{ reviews?: Review[] }>(['performance', 'reviews'], '/app/performance/reviews', {
    enabled,
  })

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const rows = query.data?.reviews || []
  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('performance.reviews')}</EditorialHeading>
        {rows.length === 0 ? (
          <QuietEmpty title={t('performance.emptyReviews')} />
        ) : (
          rows.map((row) => (
            <Pressable key={row.review_id} onPress={() => router.push(`/performance/reviews/${row.review_id}`)}>
            <ListRow
              title={isRTL ? row.cycle_name_ar || row.cycle_name_en || '' : row.cycle_name_en || ''}
              subtitle={`${row.reviewer_role || ''} · ${row.status || ''}`}
              icon="create-outline"
              showChevron
            />
            </Pressable>
          ))
        )}
      </PageScrollView>
    </PageScreen>
  )
}
