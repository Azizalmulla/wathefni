import { useState } from 'react'
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { colors, font, spacing, typeScaling } from '@/theme'

type Detail = {
  review?: {
    review_id?: string
    reviewer_role?: string
    status?: string
    row_version?: number
    overall_rating_value?: number
  }
  layers?: { layers?: Record<string, { overall_rating_value?: number | null; status?: string } | null> }
}

export default function PerformanceReviewDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const { t, isRTL } = useI18n()
  const { hasFeature, can, request } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<Detail>(['performance', 'review', id], `/app/performance/reviews/${id}`, {
    enabled: enabled && Boolean(id),
  })
  const align = readingEdgeAlign(isRTL)
  const [rating, setRating] = useState(3)
  const [rationale, setRationale] = useState('')
  const [busy, setBusy] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const review = query.data?.review
  const layers = query.data?.layers?.layers || {}
  const pending = review?.status === 'not_started' || review?.status === 'draft'
  const canSubmit = pending && can('performance', 'submit') && review?.reviewer_role !== 'manager'

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('performance.reviews')}</EditorialHeading>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
          {`${review?.reviewer_role || ''} · ${review?.status || ''}`}
        </Text>
        <ListRow
          title={t('performance.finalOutcome')}
          subtitle={layers.final?.overall_rating_value == null ? '—' : String(layers.final.overall_rating_value)}
          icon="ribbon-outline"
        />
        {canSubmit ? (
          <View style={styles.form}>
            <View style={[styles.ratings, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              {[1, 2, 3, 4].map((n) => (
                <Pressable key={n} onPress={() => setRating(n)} style={[styles.rate, rating === n && styles.rateOn]}>
                  <Text style={styles.rateText}>{n}</Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              value={rationale}
              onChangeText={setRationale}
              placeholder={t('performance.rationale')}
              placeholderTextColor={colors.navMuted}
              multiline
              style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
            />
            <PremiumButton
              label={t('performance.submit')}
              disabled={busy || !rationale.trim()}
              busy={busy}
              onPress={async () => {
                setBusy(true)
                try {
                  await request(`/app/performance/reviews/${id}/submit`, {
                    method: 'POST',
                    json: {
                      overall_rating_value: rating,
                      rationale: rationale.trim(),
                      expected_version: review?.row_version,
                    },
                  })
                  await query.refetch()
                } finally {
                  setBusy(false)
                }
              }}
            />
          </View>
        ) : null}
        <Text maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
          {t('performance.talentOff')}
        </Text>
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: {
    color: colors.textSecondary,
    fontSize: font.body,
  },
  form: {
    gap: spacing.md,
  },
  ratings: {
    gap: spacing.sm,
  },
  rate: {
    minWidth: 48,
    minHeight: 48,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rateOn: {
    backgroundColor: colors.surface,
  },
  rateText: {
    color: colors.text,
    fontSize: font.body,
  },
  input: {
    minHeight: 96,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.text,
    fontSize: font.body,
  },
})
