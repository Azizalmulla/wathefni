import { useLocalSearchParams } from 'expo-router'

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
  session?: { title_en?: string; title_ar?: string; capacity?: number; enrolled_count?: number }
  participants?: Array<{ assignment_id?: string; status?: string; attended?: boolean; completed?: boolean }>
}

export default function LearningSessionScreen() {
  const { hasFeature } = useAuth()
  const { t, isRTL } = useI18n()
  const params = useLocalSearchParams<{ session_id?: string }>()
  const sessionId = String(params.session_id || '')
  const enabled = hasFeature('learning')
  const query = useAppQuery<Payload>(['learning', 'session', sessionId], `/app/learning/sessions/${sessionId}`, {
    enabled: enabled && Boolean(sessionId),
    staleTime: HIGH_CHURN_STALE_MS,
  })

  if (!enabled) return <FeatureUnavailableState feature="learning" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const session = query.data?.session
  const mine = query.data?.participants || []

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>
          {isRTL ? session?.title_ar || session?.title_en || t('learning.session') : session?.title_en || session?.title_ar || t('learning.session')}
        </EditorialHeading>
        {mine.length === 0 ? <QuietEmpty title={t('learning.emptySession')} /> : null}
        {mine.map((row) => (
          <ListRow
            key={String(row.assignment_id)}
            title={t('learning.evidenceStatus')}
            subtitle={[
              row.attended ? t('learning.attended') : t('learning.enrolled'),
              row.completed ? t('learning.completed') : t('learning.notCompleted'),
            ].join(' · ')}
          />
        ))}
      </PageScrollView>
    </PageScreen>
  )
}
