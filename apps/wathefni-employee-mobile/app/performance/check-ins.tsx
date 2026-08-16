import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading } from '@/components/premium'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { spacing } from '@/theme'

type Row = { check_in_id: string; kind?: string; status?: string; scheduled_for?: string }

export default function PerformanceCheckInsScreen() {
  const { t } = useI18n()
  const { hasFeature } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<{ check_ins?: Row[] }>(['performance', 'check-ins'], '/app/performance/check-ins', {
    enabled,
  })

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const rows = query.data?.check_ins || []
  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('performance.checkIns')}</EditorialHeading>
        {rows.length === 0 ? (
          <QuietEmpty title={t('performance.emptyCheckIns')} />
        ) : (
          rows.map((row) => (
            <ListRow
              key={row.check_in_id}
              title={row.kind || t('performance.checkIns')}
              subtitle={`${row.status || ''} · ${row.scheduled_for || ''}`}
              icon="chatbubble-ellipses-outline"
            />
          ))
        )}
      </PageScrollView>
    </PageScreen>
  )
}
