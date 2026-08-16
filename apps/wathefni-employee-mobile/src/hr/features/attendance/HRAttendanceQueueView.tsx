import { useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { AttendanceException } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import {
  exceptionChipTone,
  exceptionKindLabelKey,
  queueSubtitle,
  UNRESOLVED_LOOKBACK_DAYS,
  type AttendanceQueueTab,
} from '@hr/features/attendance/attendanceComposition'
import { buildAttendanceDemoQueue } from '@hr/features/attendance/attendanceDemoData'
import { attendanceDemoEnabled } from '@hr/features/attendance/attendanceDemoGate'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDate, formatNumber, kuwaitToday } from '@/lib/format'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

// Attendance exceptions arrive in bursts, so a wider page than the shared
// default keeps a normal day on one screen while staying paginated.
const ATTENDANCE_PAGE_SIZE = 100

function isoDaysAgo(days: number, today = kuwaitToday()): string {
  const d = new Date(`${today}T12:00:00`)
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

/**
 * Attendance — exception-first queue on shared Ops truth.
 * Today + Unresolved. No present-day board.
 */
export function HRAttendanceQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'attendance')
  const [tab, setTab] = useState<AttendanceQueueTab>('today')
  const demo = attendanceDemoEnabled()
  const today = kuwaitToday()
  const unresolvedEnd = isoDaysAgo(1, today)
  const unresolvedStart = isoDaysAgo(UNRESOLVED_LOOKBACK_DAYS, today)

  const todayQueue = useHrQueue<AttendanceException>({
    queryKey: ['attendance-exceptions', 'today', today, me?.principal.user_id],
    enabled: Boolean(me) && permitted && !demo,
    pageSize: ATTENDANCE_PAGE_SIZE,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.attendance(request, {
        start_date: today,
        end_date: today,
        status: 'exceptions',
        offset,
        limit,
        signal,
      }),
  })

  const unresolvedQueue = useHrQueue<AttendanceException>({
    queryKey: [
      'attendance-exceptions',
      'unresolved',
      unresolvedStart,
      unresolvedEnd,
      me?.principal.user_id,
    ],
    enabled: Boolean(me) && permitted && !demo,
    pageSize: ATTENDANCE_PAGE_SIZE,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.attendance(request, {
        start_date: unresolvedStart,
        end_date: unresolvedEnd,
        status: 'exceptions',
        offset,
        limit,
        signal,
      }),
  })

  const demoQueue = useMemo(() => (demo ? buildAttendanceDemoQueue(today) : null), [demo, today])

  const onlyExceptions = (rows: AttendanceException[]) => rows.filter((row) => row.is_exception)
  const todayItems = onlyExceptions(demoQueue?.today || todayQueue.items)
  const unresolvedItems = onlyExceptions(demoQueue?.unresolved || unresolvedQueue.items)
  const items = tab === 'today' ? todayItems : unresolvedItems
  const active = tab === 'today' ? todayQueue : unresolvedQueue

  const loading = !demo && active.loading
  const error = !demo && active.error

  const retry = () => {
    void refreshMe()
    todayQueue.refetch()
    unresolvedQueue.refetch()
  }

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={!demo && (todayQueue.refreshing || unresolvedQueue.refreshing)}
        onRefresh={retry}
      >
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrAttendance.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrAttendance.subtitle')}
          </Text>
          {demo ? (
            <View style={styles.demoBanner}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrAttendance.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrAttendance.permissionTitle')}
            subtitle={t('hrAttendance.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted ? (
          <View style={styles.tabs}>
            <TabChip
              label={t('hrAttendance.tabToday')}
              count={demo ? todayItems.length : Math.max(todayQueue.total, todayItems.length)}
              active={tab === 'today'}
              onPress={() => setTab('today')}
            />
            <TabChip
              label={t('hrAttendance.tabUnresolved')}
              count={
                demo ? unresolvedItems.length : Math.max(unresolvedQueue.total, unresolvedItems.length)
              }
              active={tab === 'unresolved'}
              onPress={() => setTab('unresolved')}
            />
          </View>
        ) : null}

        {permitted && loading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}

        {permitted && error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={retry}
          />
        ) : null}

        {permitted && !loading && !error ? (
          <View style={styles.section}>
            <SectionHeader
              title={tab === 'today' ? t('hrAttendance.tabToday') : t('hrAttendance.tabUnresolved')}
              count={demo ? items.length : Math.max(active.total, items.length)}
            />
            {items.length === 0 ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                {tab === 'today' ? t('hrAttendance.emptyToday') : t('hrAttendance.emptyUnresolved')}
              </Text>
            ) : (
              items.map((item) => (
                <ExceptionRow
                  key={item.attendance_id}
                  item={item}
                  onPress={() =>
                    router.push(
                      toHrPath(`/attendance/${encodeURIComponent(item.attendance_id)}`) as never,
                    )
                  }
                />
              ))
            )}
            {demo ? null : (
              <QueueContinuation
                loaded={active.loaded}
                total={active.total}
                hasMore={active.hasMore}
                loadingMore={active.loadingMore}
                onLoadMore={active.loadMore}
              />
            )}
            {tab === 'unresolved' ? (
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                {t('hrAttendance.unresolvedWindow', {
                  days: formatNumber(UNRESOLVED_LOOKBACK_DAYS, locale, 0),
                })}
              </Text>
            ) : null}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
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

function ExceptionRow({ item, onPress }: { item: AttendanceException; onPress: () => void }) {
  const { t, locale } = useI18n()
  const kindLabel = t(exceptionKindLabelKey(item.exception_kind))
  const date = item.attendance_date ? formatDate(item.attendance_date, locale) : null
  return (
    <ListRow
      title={item.employee.name}
      subtitle={[kindLabel, queueSubtitle(item, t), date].filter(Boolean).join(' · ')}
      icon="calendar-outline"
      iconTint={colors.surfaceMuted}
      showChevron
      onPress={onPress}
      trailing={<StatusChip label={kindLabel} tone={exceptionChipTone(item.exception_kind)} />}
      style={styles.row}
    />
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
  footnote: { color: colors.subtle, fontSize: font.tiny, marginTop: spacing.sm },
})
