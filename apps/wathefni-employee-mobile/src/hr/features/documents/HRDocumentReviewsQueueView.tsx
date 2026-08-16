import { useMemo } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { DocumentReview } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  buildDocumentsDemoQueue,
  docStatusLabelKey,
  docStatusTone,
  queueSubtitle,
} from '@hr/features/documents/documentsComposition'
import { documentsDemoEnabled } from '@hr/features/documents/documentsDemoGate'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * Document Reviews — needs_review compliance queue (not the full register).
 */
export function HRDocumentReviewsQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'documents')
  const demo = documentsDemoEnabled()

  const queue = useHrQueue<DocumentReview>({
    queryKey: ['documents', 'needs_review', me?.principal.user_id],
    enabled: Boolean(me) && permitted && !demo,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.documents(request, { status: 'needs_review', offset, limit, signal }),
  })

  const demoModel = useMemo(() => (demo ? buildDocumentsDemoQueue() : null), [demo])
  const compliance = demoModel?.compliance || queue.items.filter((row) => row.source !== 'onboarding')
  const onboardingFallback =
    demoModel?.onboardingFallback || queue.items.filter((row) => row.source === 'onboarding')

  const loading = !demo && queue.loading
  const error = !demo && queue.error

  const openItem = (item: DocumentReview) => {
    if (item.source === 'onboarding') {
      const key = item.employee?.employee_key
      if (!key) return
      router.push(toHrPath(`/onboarding/${encodeURIComponent(key)}`) as never)
      return
    }
    const key = item.employee?.employee_key
    const type = item.document_type
    if (!key || !type) return
    router.push(
      toHrPath(`/documents/${encodeURIComponent(key)}/${encodeURIComponent(type)}`) as never,
    )
  }

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
          <EditorialHeading>{t('hrDocuments.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrDocuments.subtitle')}
          </Text>
          {demo ? (
            <View style={styles.demoBanner}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrDocuments.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrDocuments.permissionTitle')}
            subtitle={t('hrDocuments.permissionBody')}
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
          <>
            <View style={styles.section}>
              <SectionHeader title={t('hrDocuments.queueTitle')} count={compliance.length} />
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                {t('hrDocuments.queueHint')}
              </Text>
              {compliance.length === 0 ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                  {t('hrDocuments.emptyQueue')}
                </Text>
              ) : (
                compliance.map((item) => (
                  <ListRow
                    key={item.document_id}
                    title={item.employee?.name || item.name}
                    subtitle={queueSubtitle(item, t)}
                    icon="document-text-outline"
                    iconTint={colors.surfaceMuted}
                    showChevron
                    onPress={() => openItem(item)}
                    trailing={
                      <StatusChip
                        label={t(docStatusLabelKey(item.status))}
                        tone={docStatusTone(item.status)}
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
            </View>

            {onboardingFallback.length > 0 ? (
              <View style={styles.section}>
                <SectionHeader
                  title={t('hrDocuments.onboardingFallbackTitle')}
                  count={onboardingFallback.length}
                />
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('hrDocuments.onboardingFallbackHint')}
                </Text>
                {onboardingFallback.map((item) => (
                  <ListRow
                    key={item.document_id}
                    title={item.employee?.name || item.name}
                    subtitle={queueSubtitle(item, t)}
                    icon="ribbon-outline"
                    iconTint={colors.surfaceMuted}
                    showChevron
                    onPress={() => openItem(item)}
                    trailing={
                      <StatusChip label={t('hrDocuments.chipOpenOnboarding')} tone="blue" />
                    }
                    style={styles.row}
                  />
                ))}
              </View>
            ) : null}
          </>
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
