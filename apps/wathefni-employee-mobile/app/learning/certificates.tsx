import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading } from '@/components/premium'
import { ErrorState, LoadingState } from '@/components/States'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Payload = {
  certificates?: Array<{
    certification_id?: string
    title_en?: string
    title_ar?: string
    expires_on?: string
    derived?: { status?: string; expiring?: boolean }
  }>
}

export default function LearningCertificatesScreen() {
  const { hasFeature } = useAuth()
  const { t, isRTL } = useI18n()
  const enabled = hasFeature('learning')
  const query = useAppQuery<Payload>(['learning', 'certificates'], '/app/learning/certificates', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })

  if (!enabled) return <FeatureUnavailableState feature="learning" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const rows = query.data?.certificates || []

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>{t('learning.certificates')}</EditorialHeading>
        {rows.length === 0 ? <QuietEmpty title={t('learning.emptyCertificates')} /> : null}
        {rows.map((row) => (
          <ListRow
            key={String(row.certification_id)}
            title={isRTL ? row.title_ar || row.title_en || '' : row.title_en || row.title_ar || ''}
            subtitle={
              row.derived?.expiring
                ? t('learning.expiring')
                : row.derived?.status === 'expired'
                  ? t('learning.expired')
                  : row.expires_on || t('learning.issued')
            }
          />
        ))}
      </PageScrollView>
    </PageScreen>
  )
}
