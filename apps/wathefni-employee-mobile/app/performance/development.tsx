import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading } from '@/components/premium'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { spacing } from '@/theme'

type Row = {
  action_id?: string
  plan_id?: string
  action_title_en?: string
  title_en?: string
  action_status?: string
  status?: string
}

export default function PerformanceDevelopmentScreen() {
  const { t } = useI18n()
  const { hasFeature } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<{ items?: Row[] }>(['performance', 'development'], '/app/performance/development', {
    enabled,
  })

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const rows = query.data?.items || []
  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('performance.development')}</EditorialHeading>
        {rows.length === 0 ? (
          <QuietEmpty title={t('performance.emptyDevelopment')} />
        ) : (
          rows.map((row, idx) => (
            <ListRow
              key={String(row.action_id || row.plan_id || idx)}
              title={row.action_title_en || row.title_en || t('performance.development')}
              subtitle={row.action_status || row.status || ''}
              icon="leaf-outline"
            />
          ))
        )}
      </PageScrollView>
    </PageScreen>
  )
}
