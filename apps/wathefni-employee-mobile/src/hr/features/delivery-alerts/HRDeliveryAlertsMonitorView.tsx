import { useMemo } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { DeliveryAlert } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { destinationAvailable, routeAvailable } from '@hr/capabilities'
import {
  alertStatusLabelKey,
  alertStatusTone,
  buildAlertsDemoQueue,
  queueSubtitle,
} from '@hr/features/delivery-alerts/alertsComposition'
import { alertsDemoEnabled } from '@hr/features/delivery-alerts/alertsDemoGate'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDateTime } from '@/lib/format'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * Delivery Alerts — quiet read-only More monitor (Editorial list language).
 * Non-task outbound states only (has_task rows deduped on the backend).
 * No resolve / resend / mutations — contract unchanged.
 */
export function HRDeliveryAlertsMonitorView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'deliveryAlerts')
  const demo = alertsDemoEnabled()

  const queue = useHrQueue<DeliveryAlert>({
    queryKey: ['delivery-alerts', me?.principal.user_id],
    enabled: Boolean(me) && permitted && !demo,
    fetchPage: ({ offset, limit, signal }) => mobileApi.alerts(request, { offset, limit, signal }),
  })

  const demoModel = useMemo(() => (demo ? buildAlertsDemoQueue() : null), [demo])
  const items: DeliveryAlert[] = (demoModel?.items || queue.items).filter((row) => !row.has_task)
  const total = demo ? items.length : Math.max(queue.total, items.length)

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
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: ambient.schedule.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrAlerts.monitorEyebrow')}
            </Text>
          </View>
          <EditorialHeading>{t('hrAlerts.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrAlerts.subtitle')}
          </Text>
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrAlerts.demoBanner')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrAlerts.permissionTitle')}
            subtitle={t('hrAlerts.permissionBody')}
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
            <SectionHeader title={t('hrAlerts.queueTitle')} count={total} />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
              {t('hrAlerts.queueHint')}
            </Text>
            {items.length === 0 ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                {t('hrAlerts.emptyQueue')}
              </Text>
            ) : (
              items.map((item) => {
                const when = item.occurred_at ? formatDateTime(item.occurred_at, locale) : null
                const reason = item.summary || item.suggested_action
                const meta = [queueSubtitle(item, t), when].filter(Boolean).join(' · ')
                const canOpen =
                  Boolean(item.destination?.startsWith('/')) &&
                  !item.destination?.includes('__demo_') &&
                  destinationAvailable(me, item.destination as string)
                return (
                  <Pressable
                    key={item.alert_id}
                    disabled={!canOpen}
                    onPress={
                      canOpen
                        ? () => router.push(toHrPath(item.destination as string) as never)
                        : undefined
                    }
                    style={styles.alertRow}
                    accessibilityRole={canOpen ? 'button' : 'text'}
                    accessibilityLabel={item.title}
                  >
                    <View style={styles.alertHeader}>
                      <Text
                        maxFontSizeMultiplier={typeScaling.body}
                        style={[styles.alertTitle, align]}
                      >
                        {item.title}
                      </Text>
                      <StatusChip
                        label={t(alertStatusLabelKey(item.status))}
                        tone={alertStatusTone(item.status)}
                      />
                    </View>
                    {meta ? (
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.alertMeta, align]}>
                        {meta}
                      </Text>
                    ) : null}
                    {reason ? (
                      <Text
                        maxFontSizeMultiplier={typeScaling.body}
                        style={[styles.alertReason, align]}
                      >
                        {reason}
                      </Text>
                    ) : null}
                  </Pressable>
                )
              })
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
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: { width: 8, height: 8, borderRadius: radius.pill },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  section: { gap: spacing.sm },
  alertRow: {
    gap: spacing.xs,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  alertHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  alertTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700', flex: 1 },
  alertMeta: { color: colors.subtle, fontSize: font.tiny },
  alertReason: { color: colors.ink, fontSize: font.small, lineHeight: 20, fontWeight: '500' },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny },
})
