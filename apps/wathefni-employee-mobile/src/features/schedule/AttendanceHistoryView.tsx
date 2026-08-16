import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { approvedErrorMessage } from '@/api/errors'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { PageBackButton, QuietEmpty, ShowMoreButton } from '@/components/lists'
import { formatClockTime, formatDate, formatNumber, formatTimeRange, statusLabel } from '@/lib/format'
import { asModuleDataState, isModuleFactual } from '@/lib/moduleState'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { ScheduleHistoryRecord, ScheduleHistoryResponse } from '@/api/types'

import { AttendanceStatusMark } from './attendancePills'

/** Months offered in the chip strip (including the current month). */
const MONTH_CHIP_COUNT = 6
const PAGE_LIMIT = 30

type MonthFilter =
  | { kind: 'all' }
  | { kind: 'month'; year: number; month: number; dateFrom: string; dateTo: string }

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** Inclusive month bounds as ISO dates (calendar, not timezone-shifted). */
export function monthDateBounds(year: number, month1to12: number): { dateFrom: string; dateTo: string } {
  const lastDay = new Date(Date.UTC(year, month1to12, 0)).getUTCDate()
  return {
    dateFrom: `${year}-${pad2(month1to12)}-01`,
    dateTo: `${year}-${pad2(month1to12)}-${pad2(lastDay)}`,
  }
}

export function buildMonthFilters(todayISO: string, count = MONTH_CHIP_COUNT): MonthFilter[] {
  const [y, m] = todayISO.slice(0, 10).split('-').map(Number)
  const filters: MonthFilter[] = [{ kind: 'all' }]
  let year = y
  let month = m
  for (let i = 0; i < count; i += 1) {
    const bounds = monthDateBounds(year, month)
    filters.push({ kind: 'month', year, month, ...bounds })
    month -= 1
    if (month < 1) {
      month = 12
      year -= 1
    }
  }
  return filters
}

function monthChipLabel(filter: MonthFilter, locale: string, allLabel: string): string {
  if (filter.kind === 'all') return allLabel
  const tag = locale === 'ar' ? 'ar' : 'en-GB'
  return new Intl.DateTimeFormat(tag, { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(filter.year, filter.month - 1, 1)),
  )
}

function historyPath(locale: string, filter: MonthFilter, cursor?: string | null): string {
  const params = new URLSearchParams()
  params.set('locale', locale)
  params.set('limit', String(PAGE_LIMIT))
  if (filter.kind === 'month') {
    params.set('date_from', filter.dateFrom)
    params.set('date_to', filter.dateTo)
  }
  if (cursor) params.set('cursor', cursor)
  return `/app/schedule/history?${params.toString()}`
}

function recordKey(row: ScheduleHistoryRecord, index: number): string {
  return row.recorded.attendance_id || `${row.recorded.date}-${index}`
}

export function AttendanceHistoryView({
  today,
  onBack,
}: {
  today: string
  onBack: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const { hasFeature, request, refreshMe } = useAuth()
  const align = readingEdgeAlign(isRTL)
  const enabled = hasFeature('attendance')

  const monthFilters = useMemo(() => buildMonthFilters(today), [today])
  const [filter, setFilter] = useState<MonthFilter>(monthFilters[0])
  const [extra, setExtra] = useState<ScheduleHistoryRecord[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const firstPath = historyPath(locale, filter)
  const query = useAppQuery<ScheduleHistoryResponse>(['schedule-history', locale, firstPath], firstPath, {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })

  useEffect(() => {
    if (!query.data) return
    setExtra([])
    setHasMore(Boolean(query.data.has_more))
    setNextCursor(query.data.next_cursor ?? null)
  }, [query.data])

  const firstPage: ScheduleHistoryRecord[] = query.data?.records ?? []
  const rows = useMemo((): ScheduleHistoryRecord[] => {
    if (!extra.length) return firstPage
    const seen = new Set(firstPage.map((row: ScheduleHistoryRecord) => row.recorded.attendance_id).filter(Boolean))
    const merged = [...firstPage]
    for (const row of extra) {
      const id = row.recorded.attendance_id
      if (id && seen.has(id)) continue
      if (id) seen.add(id)
      merged.push(row)
    }
    return merged
  }, [extra, firstPage])

  const onSelectFilter = useCallback((next: MonthFilter) => {
    setFilter(next)
    setExtra([])
    setHasMore(false)
    setNextCursor(null)
  }, [])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      setExtra([])
      setNextCursor(null)
      setHasMore(false)
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  const onLoadOlder = useCallback(async () => {
    if (!hasMore || !nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await request<ScheduleHistoryResponse>(historyPath(locale, filter, nextCursor))
      const incoming = page.records ?? []
      setExtra((prev) => {
        const seen = new Set(prev.map((row) => row.recorded.attendance_id).filter(Boolean))
        const merged = [...prev]
        for (const row of incoming) {
          const id = row.recorded.attendance_id
          if (id && seen.has(id)) continue
          if (id) seen.add(id)
          merged.push(row)
        }
        return merged
      })
      setHasMore(Boolean(page.has_more))
      setNextCursor(page.next_cursor ?? null)
    } catch (err) {
      Alert.alert(t('common.error'), approvedErrorMessage(err, t))
    } finally {
      setLoadingMore(false)
    }
  }, [filter, hasMore, loadingMore, locale, nextCursor, request, t])

  if (!enabled) {
    return <FeatureUnavailableState feature="attendance" onRefresh={() => void refreshMe()} />
  }
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const attendanceState = asModuleDataState(query.data?.authority.attendance)
  const honesty =
    locale === 'ar' ? query.data?.read_only?.authority_ar : query.data?.read_only?.authority

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={() => void onRefresh()}>
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
          <EditorialHeading size="medium">{t('schedule.history.title')}</EditorialHeading>
        </View>

        <FadeIn style={styles.hero}>
          <Text style={[styles.subtitle, align]}>{t('schedule.history.subtitle')}</Text>
          {honesty ? <Text style={[styles.honesty, align]}>{honesty}</Text> : null}
        </FadeIn>

        <View
          style={styles.monthStrip}
          accessibilityRole="tablist"
          accessibilityLabel={t('schedule.history.monthNav')}
        >
          {monthFilters.map((item) => {
            const selected =
              item.kind === 'all'
                ? filter.kind === 'all'
                : filter.kind === 'month' && filter.year === item.year && filter.month === item.month
            const label = monthChipLabel(item, locale, t('schedule.history.allTime'))
            return (
              <Pressable
                key={item.kind === 'all' ? 'all' : `${item.year}-${item.month}`}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                accessibilityLabel={label}
                onPress={() => onSelectFilter(item)}
                style={[styles.monthChip, selected && styles.monthChipSelected]}
              >
                <Text
                  maxFontSizeMultiplier={typeScaling.chip}
                  style={[styles.monthChipText, selected && styles.monthChipTextSelected]}
                >
                  {label}
                </Text>
              </Pressable>
            )
          })}
        </View>

        {!isModuleFactual(attendanceState) ? (
          <QuietEmpty
            icon={attendanceState === 'error' ? 'cloud-offline-outline' : 'time-outline'}
            message={attendanceState === 'error' ? t('home.dataUnavailable') : t('home.dataLoading')}
          />
        ) : rows.length === 0 ? (
          <QuietEmpty icon="time-outline" message={t('schedule.history.empty')} />
        ) : (
          <View style={styles.list}>
            {rows.map((row, index) => (
              <HistoryRow key={recordKey(row, index)} row={row} />
            ))}
            {hasMore ? (
              <ShowMoreButton
                label={loadingMore ? t('common.loading') : t('schedule.history.loadOlder')}
                onPress={() => {
                  if (!loadingMore) void onLoadOlder()
                }}
              />
            ) : null}
          </View>
        )}
      </PageScrollView>
    </PageScreen>
  )
}

function HistoryRow({ row }: { row: ScheduleHistoryRecord }) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const { recorded, scheduled } = row
  const hasTimes = Boolean(recorded.check_in_at || recorded.check_out_at)
  const a11yParts = [
    formatDate(recorded.date, locale),
    statusLabel(recorded.status, t),
    hasTimes
      ? `${formatClockTime(recorded.check_in_at, locale)} – ${formatClockTime(recorded.check_out_at, locale)}`
      : null,
    scheduled
      ? `${t('schedule.expected')} ${formatTimeRange(scheduled.start_time, scheduled.end_time, locale)}`
      : null,
  ].filter(Boolean)

  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={a11yParts.join('. ')}
    >
      <View style={styles.rowMain}>
        <View style={styles.rowHead}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowDate, align]}>
            {formatDate(recorded.date, locale)}
          </Text>
          <AttendanceStatusMark status={recorded.status} label={statusLabel(recorded.status, t)} />
        </View>
        {hasTimes ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowMeta, align]}>
            {`${formatClockTime(recorded.check_in_at, locale)} – ${formatClockTime(recorded.check_out_at, locale)}`}
          </Text>
        ) : (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowMeta, align]}>
            {t('schedule.noTimesRecorded')}
          </Text>
        )}
        {recorded.late_minutes > 0 ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowMeta, align]}>
            {t('schedule.lateBy', { minutes: formatNumber(recorded.late_minutes, locale, 0) })}
          </Text>
        ) : null}
        {recorded.early_leave_minutes > 0 ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowMeta, align]}>
            {t('schedule.leftEarlyBy', { minutes: formatNumber(recorded.early_leave_minutes, locale, 0) })}
          </Text>
        ) : null}
        {recorded.notes ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.rowMeta, align]}>
            {recorded.notes}
          </Text>
        ) : null}
        {scheduled ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.scheduledLine, align]}>
            {`${t('schedule.expected')} · ${formatTimeRange(scheduled.start_time, scheduled.end_time, locale)}`}
            {scheduled.location ? ` · ${scheduled.location}` : ''}
          </Text>
        ) : null}
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: layout.touchTarget,
  },
  back: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  honesty: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  monthStrip: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  monthChip: {
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceMuted,
  },
  monthChipSelected: { backgroundColor: colors.ink },
  monthChipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  monthChipTextSelected: { color: colors.bg },
  list: { gap: spacing.xs },
  row: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
  },
  rowMain: { gap: 2 },
  rowHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  rowDate: { flex: 1, color: colors.ink, fontSize: font.small, fontWeight: '700' },
  rowMeta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  scheduledLine: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17, fontWeight: '600', marginTop: 2 },
  empty: { color: colors.subtle, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
})
