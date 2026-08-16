import { useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { Shift, ShiftSwap } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability, routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import {
  composeNeedsAttention,
  buildShiftsDemoModel,
  swapListSubtitle,
  swapStatusLabelKey,
  swapStatusTone,
  type ShiftsAttentionItem,
  type ShiftsHomeTab,
} from '@hr/features/shifts/shiftsComposition'
import { shiftsDemoEnabled } from '@hr/features/shifts/shiftsDemoGate'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDate, formatNumber, formatTimeRange, kuwaitToday } from '@/lib/format'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

const SWAPS_PAGE_SIZE = 50

/**
 * Shifts — decision-first companion to web Schedule / Requests / Planning.
 * Tabs: Needs Attention (primary) · Today (read-only Kuwait day).
 */
export function HRShiftsHomeView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const routeOk = routeAvailable(me, 'shifts')
  const canSwaps = hasCapability(me, 'hr', 'shift_swap_decisions')
  const canToday = hasCapability(me, 'hr', 'today_shifts')
  const [tab, setTab] = useState<ShiftsHomeTab>('needs_attention')
  const demo = shiftsDemoEnabled()
  const today = kuwaitToday()

  const swapsQueue = useHrQueue<ShiftSwap>({
    queryKey: ['shift-swaps', 'requested', me?.principal.user_id],
    enabled: Boolean(me) && canSwaps && !demo,
    pageSize: SWAPS_PAGE_SIZE,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.swaps(request, { status: 'requested', offset, limit, signal }),
  })

  const todayQuery = useQuery({
    queryKey: ['shifts', 'today', today, me?.principal.user_id],
    queryFn: ({ signal }) => mobileApi.shifts(request, today, signal),
    enabled: Boolean(me) && canToday && !demo,
  })

  const demoModel = useMemo(() => (demo ? buildShiftsDemoModel(today) : null), [demo, today])

  const attention = demoModel ? demoModel.attention : composeNeedsAttention(swapsQueue.items)
  const todayItems = demoModel?.today || todayQuery.data?.items || []

  const loadingAttention = !demo && canSwaps && swapsQueue.loading
  const errorAttention = !demo && canSwaps && swapsQueue.error
  const loadingToday = !demo && canToday && todayQuery.isLoading && !todayQuery.data
  const errorToday = !demo && canToday && todayQuery.error && !todayQuery.data

  const retry = () => {
    void refreshMe()
    swapsQueue.refetch()
    void todayQuery.refetch()
  }

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={!demo && (swapsQueue.refreshing || todayQuery.isRefetching)}
        onRefresh={retry}
      >
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrShifts.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrShifts.subtitle')}
          </Text>
          {demo ? (
            <View style={styles.demoBanner}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrShifts.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!routeOk ? (
          <ListRow
            title={t('hrShifts.permissionTitle')}
            subtitle={t('hrShifts.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {routeOk ? (
          <View style={styles.tabs}>
            <TabChip
              label={t('hrShifts.tabNeedsAttention')}
              count={
                demo ? attention.length : canSwaps ? Math.max(swapsQueue.total, attention.length) : 0
              }
              active={tab === 'needs_attention'}
              onPress={() => setTab('needs_attention')}
            />
            <TabChip
              label={t('hrShifts.tabToday')}
              count={canToday || demo ? todayItems.length : 0}
              active={tab === 'today'}
              onPress={() => setTab('today')}
            />
          </View>
        ) : null}

        {routeOk && tab === 'needs_attention' ? (
          <NeedsAttentionPanel
            canSwaps={canSwaps || demo}
            loading={loadingAttention}
            error={Boolean(errorAttention)}
            items={attention}
            onRetry={retry}
            onOpen={(item) =>
              router.push(toHrPath(`/shift-swaps/${encodeURIComponent(item.id)}`) as never)
            }
            continuation={
              demo ? null : (
                <QueueContinuation
                  loaded={swapsQueue.loaded}
                  total={swapsQueue.total}
                  hasMore={swapsQueue.hasMore}
                  loadingMore={swapsQueue.loadingMore}
                  onLoadMore={swapsQueue.loadMore}
                />
              )
            }
          />
        ) : null}

        {routeOk && tab === 'today' ? (
          <TodayPanel
            canToday={canToday || demo}
            loading={loadingToday}
            error={Boolean(errorToday)}
            items={todayItems}
            todayIso={today}
            onRetry={retry}
          />
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

function NeedsAttentionPanel({
  canSwaps,
  loading,
  error,
  items,
  onRetry,
  onOpen,
  continuation,
}: {
  canSwaps: boolean
  loading: boolean
  error: boolean
  items: ShiftsAttentionItem[]
  onRetry: () => void
  onOpen: (item: ShiftsAttentionItem) => void
  continuation?: React.ReactNode
}) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)

  if (!canSwaps) {
    return (
      <ListRow
        title={t('hrShifts.swapsUnavailableTitle')}
        subtitle={t('hrShifts.swapsUnavailableBody')}
        icon="lock-closed-outline"
      />
    )
  }
  if (loading) return <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
  if (error) {
    return (
      <ListRow
        title={t('home.dataUnavailable')}
        subtitle={t('home.dataUnavailableHint')}
        icon="cloud-offline-outline"
        emphasis="warning"
        showChevron
        onPress={onRetry}
      />
    )
  }

  return (
    <View style={styles.section}>
      <SectionHeader title={t('hrShifts.tabNeedsAttention')} count={items.length} />
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
        {t('hrShifts.needsAttentionHint')}
      </Text>
      {items.length === 0 ? (
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
          {t('hrShifts.emptyAttention')}
        </Text>
      ) : (
        items.map((item) => {
          if (item.kind !== 'shift_swap') return null
          const { swap } = item
          return (
            <ListRow
              key={item.id}
              title={`${t('hrShifts.swap')} · ${swap.requester.name}`}
              subtitle={swapListSubtitle(swap, t)}
              icon="swap-horizontal-outline"
              iconTint={colors.surfaceMuted}
              showChevron
              onPress={() => onOpen(item)}
              trailing={
                <StatusChip
                  label={t(swapStatusLabelKey(swap.status))}
                  tone={swapStatusTone(swap.status)}
                />
              }
              style={styles.row}
            />
          )
        })
      )}
      {continuation}
    </View>
  )
}

function TodayPanel({
  canToday,
  loading,
  error,
  items,
  todayIso,
  onRetry,
}: {
  canToday: boolean
  loading: boolean
  error: boolean
  items: Shift[]
  todayIso: string
  onRetry: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)

  if (!canToday) {
    return (
      <ListRow
        title={t('hrShifts.todayUnavailableTitle')}
        subtitle={t('hrShifts.todayUnavailableBody')}
        icon="lock-closed-outline"
      />
    )
  }
  if (loading) return <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
  if (error) {
    return (
      <ListRow
        title={t('home.dataUnavailable')}
        subtitle={t('home.dataUnavailableHint')}
        icon="cloud-offline-outline"
        emphasis="warning"
        showChevron
        onPress={onRetry}
      />
    )
  }

  return (
    <View style={styles.section}>
      <SectionHeader title={t('hrShifts.tabToday')} count={items.length} />
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
        {t('hrShifts.todayHint', { date: formatDate(todayIso, locale) })}
      </Text>
      {items.length === 0 ? (
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
          {t('hrShifts.emptyToday')}
        </Text>
      ) : (
        items.map((item) => (
          <ListRow
            key={item.shift_id}
            title={item.employee.name}
            subtitle={[
              formatTimeRange(item.starts_at || null, item.ends_at || null, locale),
              item.location,
              item.role,
              t('hrShifts.readOnly'),
            ]
              .filter(Boolean)
              .join(' · ')}
            icon="calendar-outline"
            iconTint={colors.surfaceMuted}
            style={styles.row}
          />
        ))
      )}
    </View>
  )
}

function TabChip({
  label,
  count,
  active,
  onPress,
}: {
  label: string
  count: number
  active: boolean
  onPress: () => void
}) {
  const { locale } = useI18n()
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[styles.tabChip, active ? styles.tabChipActive : null]}
    >
      <Text style={[styles.tabChipText, active ? styles.tabChipTextActive : null]}>
        {label}
        {count > 0 ? ` · ${formatNumber(count, locale, 0)}` : ''}
      </Text>
    </Pressable>
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
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  tabChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  tabChipActive: { backgroundColor: colors.ink },
  tabChipText: { fontSize: font.tiny, fontWeight: '700', color: colors.subtle },
  tabChipTextActive: { color: colors.primaryText },
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny },
})
