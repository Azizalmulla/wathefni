import { useMemo } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { OnboardingEmployee } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import {
  buildOnboardingDemoModel,
  queueSubtitle,
} from '@hr/features/onboarding/onboardingComposition'
import { onboardingDemoEnabled } from '@hr/features/onboarding/onboardingDemoGate'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatNumber } from '@/lib/format'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * Onboarding — HR-actionable review queue only (not full in_progress OS).
 */
export function HROnboardingQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'onboarding')
  const demo = onboardingDemoEnabled()

  const queue = useHrQueue<OnboardingEmployee>({
    queryKey: ['onboarding', 'hr-actionable', me?.principal.user_id],
    enabled: Boolean(me) && permitted && !demo,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.onboarding(request, { offset, limit, signal }),
  })

  const demoModel = useMemo(() => (demo ? buildOnboardingDemoModel() : null), [demo])
  const items: OnboardingEmployee[] = demoModel?.queue || queue.items

  const loading = !demo && queue.loading
  const error = !demo && queue.error

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={!demo && queue.refreshing}
        onRefresh={() => {
          void refreshMe()
          queue.refetch()
        }}
      >
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrOnboarding.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrOnboarding.subtitle')}
          </Text>
          {demo ? (
            <View style={styles.demoBanner}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrOnboarding.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrOnboarding.permissionTitle')}
            subtitle={t('hrOnboarding.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted && loading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}
        {permitted && error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={() => queue.refetch()}
          />
        ) : null}

        {permitted && !loading && !error ? (
          <View style={styles.section}>
            <SectionHeader
              title={t('hrOnboarding.queueTitle')}
              count={demo ? items.length : Math.max(queue.total, items.length)}
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
              {t('hrOnboarding.queueHint')}
            </Text>
            {items.length === 0 ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                {t('hrOnboarding.emptyQueue')}
              </Text>
            ) : (
              items.map((item) => (
                <ListRow
                  key={item.employee_key}
                  title={item.employee.name}
                  subtitle={queueSubtitle(item, t)}
                  icon="ribbon-outline"
                  iconTint={colors.surfaceMuted}
                  showChevron
                  onPress={() =>
                    router.push(
                      toHrPath(`/onboarding/${encodeURIComponent(item.employee_key)}`) as never,
                    )
                  }
                  trailing={
                    <StatusChip
                      label={t('hrOnboarding.chipNeedsHr')}
                      tone="yellow"
                    />
                  }
                  style={styles.row}
                />
              ))
            )}
            {demo ? null : (
              <QueueContinuation
                loaded={queue.loaded}
                total={queue.total}
                hasMore={queue.hasMore}
                loadingMore={queue.loadingMore}
                onLoadMore={queue.loadMore}
              />
            )}
            {demo ? (
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                {t('hrOnboarding.demoFilterProof', {
                  excluded: formatNumber(
                    (demoModel?.all.length || 0) - (demoModel?.queue.length || 0),
                    'en',
                    0,
                  ),
                })}
              </Text>
            ) : null}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  nav: { minHeight: 42, justifyContent: 'center' },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  demoBanner: {
    alignSelf: 'flex-start',
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  demoBannerText: { color: colors.subtle, fontWeight: '700', fontSize: font.tiny },
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny },
})
