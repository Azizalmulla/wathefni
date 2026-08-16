import { useState } from 'react'
import { Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useAppQuery } from '@/lib/hooks'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'

type Question = {
  question_id?: string
  question_type?: string
  prompt_en?: string
  prompt_ar?: string
  scale_min?: number
  scale_max?: number
  is_enps?: boolean
}

type Payload = {
  survey?: {
    title_en?: string
    title_ar?: string
    privacy_mode?: string
    privacy_mode_label_en?: string
    privacy_mode_label_ar?: string
    anonymous?: boolean
    identified?: boolean
    participation_status?: string
    status?: string
    privacy_disclosed_before_response?: boolean
  }
  questions?: Question[]
}

export default function EngagementSurveyScreen() {
  const { campaign_id: campaignId } = useLocalSearchParams<{ campaign_id?: string }>()
  const { hasFeature, can, request } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const enabled = hasFeature('engagement')
  const query = useAppQuery<Payload>(['engagement', 'survey', String(campaignId || '')], `/app/engagement/surveys/${campaignId}`, {
    enabled: enabled && Boolean(campaignId),
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [busy, setBusy] = useState(false)
  const [answers, setAnswers] = useState<Record<string, number>>({})

  if (!enabled) return <FeatureUnavailableState feature="engagement" />
  if (!campaignId) return <QuietEmpty title={t('engagement.empty')} />
  if (query.isPending && !query.data) return <LoadingState />
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />

  const survey = query.data?.survey
  const questions = query.data?.questions || []
  const submitted = survey?.participation_status === 'submitted'
  const closed = survey?.status === 'closed'
  const title = isRTL ? survey?.title_ar || survey?.title_en : survey?.title_en || survey?.title_ar
  const privacy = isRTL ? survey?.privacy_mode_label_ar : survey?.privacy_mode_label_en

  async function submit() {
    if (!campaignId || busy) return
    setBusy(true)
    try {
      await request(`/app/engagement/surveys/${campaignId}/start`, { method: 'POST', json: {} })
      await request(`/app/engagement/surveys/${campaignId}/submit`, {
        method: 'POST',
        json: {
          answers: questions.map((q) => ({
            question_id: q.question_id,
            value_number: answers[String(q.question_id)] ?? q.scale_min ?? 0,
          })),
        },
      })
      await query.refetch()
    } finally {
      setBusy(false)
    }
  }

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>{title || t('engagement.survey')}</EditorialHeading>
        <Text style={align}>{privacy}</Text>
        <Text style={align}>
          {survey?.anonymous ? t('engagement.anonymousPromise') : survey?.identified ? t('engagement.identifiedPromise') : t('engagement.privacy')}
        </Text>
        {closed ? <QuietEmpty title={t('engagement.closed')} /> : null}
        {submitted ? <QuietEmpty title={t('engagement.submitted')} /> : null}
        {!closed && !submitted
          ? questions.map((q) => (
              <View key={String(q.question_id)}>
                <ListRow
                  title={isRTL ? q.prompt_ar || q.prompt_en || '' : q.prompt_en || q.prompt_ar || ''}
                  subtitle={q.is_enps ? t('engagement.enpsScale') : `${q.scale_min ?? ''}–${q.scale_max ?? ''}`}
                />
                {(q.question_type === 'rating_scale' || q.question_type === 'enps_scale') && (
                  <View style={{ flexDirection: isRTL ? 'row-reverse' : 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                    {Array.from({ length: (q.scale_max ?? 5) - (q.scale_min ?? 1) + 1 }, (_, i) => (q.scale_min ?? 1) + i).map((n) => (
                      <PremiumButton
                        key={n}
                        label={String(n)}
                        onPress={() => setAnswers((prev) => ({ ...prev, [String(q.question_id)]: n }))}
                      />
                    ))}
                  </View>
                )}
              </View>
            ))
          : null}
        {!closed && !submitted && can('engagement', 'submit') ? (
          <PremiumButton label={t('engagement.submit')} disabled={busy} onPress={() => void submit()} />
        ) : null}
        <Text style={align}>{t('engagement.boundaries')}</Text>
      </PageScrollView>
    </PageScreen>
  )
}
