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
  resource_state?: string
  events?: Array<{ audit_id?: string; action?: string; created_at?: string }>
  enrollments?: Array<{ enrollment_id?: string; status?: string; plan_version?: number; title_en?: string; title_ar?: string }>
  coverage?: Array<{ coverage_id?: string; start_date?: string; end_date?: string; plan_version?: number; title_en?: string; title_ar?: string }>
}

export default function BenefitsHistoryScreen() {
  const { hasFeature } = useAuth()
  const { t, isRTL } = useI18n()
  const enabled = hasFeature('benefits')
  const query = useAppQuery<Payload>(['benefits', 'history'], '/app/benefits/history', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })

  if (!enabled) return <FeatureUnavailableState feature="benefits" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }
  if (query.data?.resource_state === 'unavailable') {
    return <FeatureUnavailableState feature="benefits" />
  }

  const events = query.data?.events || []
  const enrollments = query.data?.enrollments || []
  const coverage = query.data?.coverage || []
  const empty = events.length + enrollments.length + coverage.length === 0

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>{t('benefits.history')}</EditorialHeading>
        {empty ? <QuietEmpty title={t('benefits.emptyHistory')} /> : null}
        {enrollments.map((row) => (
          <ListRow
            key={String(row.enrollment_id)}
            title={isRTL ? row.title_ar || row.title_en || t('benefits.enrolled') : row.title_en || row.title_ar || t('benefits.enrolled')}
            subtitle={`${row.status || ''} · ${t('benefits.version')} ${row.plan_version ?? ''}`}
          />
        ))}
        {coverage.map((row) => (
          <ListRow
            key={String(row.coverage_id)}
            title={isRTL ? row.title_ar || row.title_en || t('benefits.coverage') : row.title_en || row.title_ar || t('benefits.coverage')}
            subtitle={[row.start_date, row.end_date, `${t('benefits.version')} ${row.plan_version ?? ''}`].filter(Boolean).join(' · ')}
          />
        ))}
        {events.map((row) => (
          <ListRow key={String(row.audit_id || row.action)} title={String(row.action || '')} subtitle={row.created_at} />
        ))}
      </PageScrollView>
    </PageScreen>
  )
}
