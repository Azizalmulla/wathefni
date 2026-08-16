import { useEffect, useState } from 'react'
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Detail = {
  review?: {
    review_id?: string
    reviewer_role?: string
    status?: string
    subject_employee_key?: string
    row_version?: number
  }
  layers?: { layers?: Record<string, unknown> }
}

export function HRPerformanceReviewDetailView() {
  const { reviewId } = useLocalSearchParams<{ reviewId: string }>()
  const onBack = useHrSafeBack()
  const { request } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rating, setRating] = useState(3)

  const load = async () => {
    if (!reviewId) return
    setError(false)
    try {
      setDetail(await request<Detail>(`/dashboard/mobile/performance/reviews/${reviewId}`))
    } catch {
      setError(true)
      setDetail(null)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId])

  const review = detail?.review
  const canSubmit = review?.status === 'not_started' || review?.status === 'draft'

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} onRefresh={() => void load()}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <EditorialHeading>{t('hrPerformance.detail')}</EditorialHeading>
        {error ? (
          <ListRow title={t('home.dataUnavailable')} icon="cloud-offline-outline" emphasis="warning" onPress={() => void load()} />
        ) : null}
        {review ? (
          <>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {`${review.reviewer_role || ''} · ${review.status || ''}`}
            </Text>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {review.subject_employee_key || ''}
            </Text>
            {canSubmit ? (
              <>
                <View style={[styles.ratings, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                  {[1, 2, 3, 4].map((n) => (
                    <Pressable key={n} onPress={() => setRating(n)} style={[styles.rate, rating === n && styles.rateOn]}>
                      <Text style={styles.rateText}>{n}</Text>
                    </Pressable>
                  ))}
                </View>
              <PremiumButton
                label={t('hrPerformance.submit')}
                disabled={saving}
                onPress={() => {
                  Alert.alert(t('hrPerformance.submit'), t('hrPerformance.submitHint'), [
                    { text: t('common.cancel'), style: 'cancel' },
                    {
                      text: t('hrPerformance.submit'),
                      onPress: async () => {
                        setSaving(true)
                        try {
                          await request(`/dashboard/mobile/performance/reviews/${reviewId}/submit`, {
                            method: 'POST',
                            json: {
                              overall_rating_value: rating,
                              rationale: t('hrPerformance.submitHint'),
                              expected_version: review.row_version,
                            },
                          })
                          await load()
                        } catch {
                          setError(true)
                        } finally {
                          setSaving(false)
                        }
                      },
                    },
                  ])
                }}
              />
              </>
            ) : null}
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: {
    color: colors.textSecondary,
    fontSize: font.body,
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
})
