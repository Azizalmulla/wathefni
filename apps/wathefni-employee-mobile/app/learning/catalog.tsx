import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { ErrorState, LoadingState } from '@/components/States'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Catalog = {
  items?: Array<{ item_id?: string; title_en?: string; title_ar?: string; item_type?: string }>
}

export default function LearningCatalogScreen() {
  const { hasFeature, can, request } = useAuth()
  const { t, isRTL } = useI18n()
  const enabled = hasFeature('learning')
  const query = useAppQuery<Catalog>(['learning', 'catalog'], '/app/learning/catalog', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [busy, setBusy] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="learning" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const items = query.data?.items || []

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>{t('learning.catalog')}</EditorialHeading>
        {items.length === 0 ? <QuietEmpty title={t('learning.emptyCatalog')} /> : null}
        {items.map((item) => (
          <ListRow
            key={String(item.item_id)}
            title={isRTL ? item.title_ar || item.title_en || '' : item.title_en || item.title_ar || ''}
            subtitle={item.item_type}
          />
        ))}
        {can('learning', 'request') && items[0]?.item_id ? (
          <PremiumButton
            label={t('learning.request')}
            disabled={busy}
            onPress={() => {
              setBusy(true)
              void request('/app/learning/requests', {
                method: 'POST',
                json: { item_id: String(items[0].item_id), reason: 'employee request' },
              }).finally(() => setBusy(false))
            }}
          />
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}
