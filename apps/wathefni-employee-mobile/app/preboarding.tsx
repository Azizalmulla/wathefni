import { useCallback, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { PageBackButton } from '@/components/navigation/PageBackButton'
import { colors, font, spacing, typeScaling } from '@/theme'

type PreboardingResponse = {
  empty?: boolean
  joining_date?: string | null
  progress?: { percent?: number }
  items?: Array<{
    item_key: string
    title_en?: string
    title_ar?: string
    status?: string
    required?: boolean
    overdue?: boolean
    row_version?: number
  }>
}

export default function PreboardingScreen() {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const onBack = useEmployeeSafeBack()
  const { hasFeature, can, request } = useAuth()
  const enabled = hasFeature('preboarding')
  const canComplete = can('preboarding', 'complete_item')
  const query = useAppQuery<PreboardingResponse>(['preboarding'], '/app/preboarding', {
    enabled,
    staleTime: 0,
  })
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const complete = useCallback(
    async (itemKey: string, rowVersion?: number) => {
      if (!canComplete) return
      setBusyKey(itemKey)
      try {
        await request(`/app/preboarding/items/${encodeURIComponent(itemKey)}`, {
          method: 'POST',
          json: { to_status: 'done', expected_row_version: rowVersion },
        })
        await query.refetch()
      } finally {
        setBusyKey(null)
      }
    },
    [canComplete, query, request],
  )

  if (!enabled) {
    return <FeatureUnavailableState feature="preboarding" onBack={onBack} />
  }

  const data = query.data
  const items = data?.items || []

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={query.isFetching}
        onRefresh={() => void query.refetch()}
      >
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
        </View>
        <FadeIn>
          <EditorialHeading>{t('employeePreboarding.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('employeePreboarding.welcome')}
          </Text>
          {data?.joining_date ? (
            <Text style={[styles.joining, align]}>
              {t('employeePreboarding.joiningDate')}: {String(data.joining_date)}
            </Text>
          ) : null}
          <Text style={[styles.progress, align]}>
            {t('employeePreboarding.progress')}: {Number(data?.progress?.percent || 0)}%
          </Text>
        </FadeIn>

        {query.isLoading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}
        {query.error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={() => void query.refetch()}
          />
        ) : null}
        {!query.isLoading && !query.error && data?.empty ? (
          <ListRow title={t('employeePreboarding.empty')} icon="checkmark-circle-outline" />
        ) : null}

        {!query.isLoading && !query.error && !data?.empty ? (
          <View>
            <SectionHeader title={t('employeePreboarding.checklist')} />
            {items.map((item) => (
              <View key={item.item_key} style={styles.card}>
                <Text style={[styles.itemTitle, align]}>
                  {locale === 'ar' ? item.title_ar || item.title_en : item.title_en || item.item_key}
                </Text>
                <View style={styles.row}>
                  <StatusChip
                    label={String(item.status || 'pending')}
                    tone={item.overdue ? 'warning' : 'neutral'}
                  />
                  {item.required ? (
                    <Text style={styles.meta}>{t('employeePreboarding.required')}</Text>
                  ) : null}
                </View>
                {canComplete && item.status !== 'done' && item.status !== 'waived' ? (
                  <Pressable
                    onPress={() => void complete(item.item_key, item.row_version)}
                    style={styles.actionBtn}
                  >
                    <Text style={styles.actionText}>
                      {busyKey === item.item_key ? '…' : t('employeePreboarding.markDone')}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  nav: { marginBottom: spacing.sm },
  subtitle: { ...font.body, color: colors.textSecondary, marginTop: spacing.sm },
  joining: { ...font.bodyStrong, color: colors.textPrimary, marginTop: spacing.md },
  progress: { ...font.caption, color: colors.textSecondary, marginTop: spacing.xs },
  card: {
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  itemTitle: { ...font.bodyStrong, color: colors.textPrimary },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.sm },
  meta: { ...font.caption, color: colors.textSecondary },
  actionBtn: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surfaceMuted,
    borderRadius: 999,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  actionText: { ...font.captionStrong, color: colors.textPrimary },
})
