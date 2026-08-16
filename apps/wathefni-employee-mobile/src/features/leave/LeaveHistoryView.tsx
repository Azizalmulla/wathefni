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
import { ListRow, PageBackButton, ShowMoreButton } from '@/components/lists'
import { isLeaveCancellableStatus } from '@/features/leave/leaveRequests'
import { LeaveStatusMark } from '@/features/leave/leaveStatusPills'
import { formatDateRange, kuwaitToday, statusLabel } from '@/lib/format'
import { selectionFeedback } from '@/native/haptics'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { LeaveHistoryResponse, LeaveRequestRow } from '@/api/types'

const PAGE_LIMIT = 30
const YEAR_CHIP_COUNT = 5

/** Status chips kept small — allowlisted backend values only, no invented labels. */
const STATUS_FILTERS = [
  { key: 'all', status: null as string | null },
  { key: 'cancelled', status: 'cancelled' },
  { key: 'rejected', status: 'rejected' },
  { key: 'completed', status: 'completed' },
  { key: 'approved', status: 'approved' },
] as const

type YearFilter = { kind: 'all' } | { kind: 'year'; year: number }

function buildYearFilters(todayISO: string, count = YEAR_CHIP_COUNT): YearFilter[] {
  const year = Number(todayISO.slice(0, 4))
  const filters: YearFilter[] = [{ kind: 'all' }]
  for (let i = 0; i < count; i += 1) {
    filters.push({ kind: 'year', year: year - i })
  }
  return filters
}

function historyPath(
  locale: string,
  year: YearFilter,
  status: string | null,
  cursor?: string | null,
): string {
  const params = new URLSearchParams()
  params.set('locale', locale)
  params.set('limit', String(PAGE_LIMIT))
  if (year.kind === 'year') params.set('year', String(year.year))
  if (status) params.set('status', status)
  if (cursor) params.set('cursor', cursor)
  return `/app/leave/history?${params.toString()}`
}

function leaveTypeLabel(type: string, t: (key: string) => string): string {
  if (type === 'annual') return t('leave.typeAnnual')
  if (type === 'sick') return t('leave.typeSick')
  return t('leave.typeOther')
}

export function LeaveHistoryView({
  canCancel,
  cancelingId,
  onCancel,
  onBack,
}: {
  canCancel: boolean
  cancelingId?: string | null
  onCancel: (leaveId: string) => void
  onBack: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const { hasFeature, request, refreshMe } = useAuth()
  const align = readingEdgeAlign(isRTL)
  const enabled = hasFeature('leave')

  const yearFilters = useMemo(() => buildYearFilters(kuwaitToday()), [])
  const [yearFilter, setYearFilter] = useState<YearFilter>(yearFilters[0])
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [extra, setExtra] = useState<LeaveRequestRow[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const firstPath = historyPath(locale, yearFilter, statusFilter)
  const query = useAppQuery<LeaveHistoryResponse>(['leave-history', locale, firstPath], firstPath, {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })

  useEffect(() => {
    if (!query.data) return
    setExtra([])
    setHasMore(Boolean(query.data.has_more))
    setNextCursor(query.data.next_cursor ?? null)
  }, [query.data])

  const firstPage: LeaveRequestRow[] = query.data?.requests ?? []
  const rows = useMemo((): LeaveRequestRow[] => {
    if (!extra.length) return firstPage
    const seen = new Set(firstPage.map((row) => row.leave_id).filter(Boolean))
    const merged = [...firstPage]
    for (const row of extra) {
      if (row.leave_id && seen.has(row.leave_id)) continue
      if (row.leave_id) seen.add(row.leave_id)
      merged.push(row)
    }
    return merged
  }, [extra, firstPage])

  const onSelectYear = useCallback((next: YearFilter) => {
    selectionFeedback()
    setYearFilter(next)
    setExtra([])
    setHasMore(false)
    setNextCursor(null)
  }, [])

  const onSelectStatus = useCallback((next: string | null) => {
    selectionFeedback()
    setStatusFilter(next)
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
      const page = await request<LeaveHistoryResponse>(
        historyPath(locale, yearFilter, statusFilter, nextCursor),
      )
      const incoming = page.requests ?? []
      setExtra((prev) => {
        const seen = new Set(prev.map((row) => row.leave_id).filter(Boolean))
        const merged = [...prev]
        for (const row of incoming) {
          if (row.leave_id && seen.has(row.leave_id)) continue
          if (row.leave_id) seen.add(row.leave_id)
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
  }, [hasMore, loadingMore, locale, nextCursor, request, statusFilter, t, yearFilter])

  if (!enabled) {
    return <FeatureUnavailableState feature="leave" onRefresh={() => void refreshMe()} />
  }
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={() => void onRefresh()}>
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
          <EditorialHeading size="medium">{t('leave.historyAll.title')}</EditorialHeading>
        </View>

        <FadeIn style={styles.hero}>
          <Text style={[styles.subtitle, align]}>{t('leave.historyAll.subtitle')}</Text>
        </FadeIn>

        <View
          style={styles.chipStrip}
          accessibilityRole="tablist"
          accessibilityLabel={t('leave.historyAll.yearNav')}
        >
          {yearFilters.map((item) => {
            const selected =
              item.kind === 'all' ? yearFilter.kind === 'all' : yearFilter.kind === 'year' && yearFilter.year === item.year
            const label = item.kind === 'all' ? t('leave.historyAll.allYears') : String(item.year)
            return (
              <Pressable
                key={item.kind === 'all' ? 'all-years' : `y-${item.year}`}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                accessibilityLabel={label}
                onPress={() => onSelectYear(item)}
                style={[styles.chip, selected && styles.chipSelected]}
              >
                <Text
                  maxFontSizeMultiplier={typeScaling.chip}
                  style={[styles.chipText, selected && styles.chipTextSelected]}
                >
                  {label}
                </Text>
              </Pressable>
            )
          })}
        </View>

        <View
          style={styles.chipStrip}
          accessibilityRole="tablist"
          accessibilityLabel={t('leave.historyAll.statusNav')}
        >
          {STATUS_FILTERS.map((item) => {
            const selected = statusFilter === item.status
            const label =
              item.key === 'all'
                ? t('leave.historyAll.allStatuses')
                : statusLabel(item.status, t)
            return (
              <Pressable
                key={item.key}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                accessibilityLabel={label}
                onPress={() => onSelectStatus(item.status)}
                style={[styles.chip, selected && styles.chipSelected]}
              >
                <Text
                  maxFontSizeMultiplier={typeScaling.chip}
                  style={[styles.chipText, selected && styles.chipTextSelected]}
                >
                  {label}
                </Text>
              </Pressable>
            )
          })}
        </View>

        {rows.length === 0 ? (
          <CalmNote message={t('leave.historyAll.empty')} />
        ) : (
          <View style={styles.list}>
            {rows.map((request) => {
              const dates = formatDateRange(request.start_date, request.end_date, locale)
              const type = request.leave_type ? leaveTypeLabel(request.leave_type, t) : null
              const status = statusLabel(request.status, t)
              const cancellable = canCancel && isLeaveCancellableStatus(request.status)
              return (
                <ListRow
                  key={request.leave_id}
                  title={type || dates}
                  subtitle={type ? dates : null}
                  meta={request.reason}
                  trailing={<LeaveStatusMark status={request.status} label={status} />}
                  accessibilityLabel={`${type ? `${type}. ` : ''}${dates}. ${status}`}
                >
                  {cancellable ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityState={{ disabled: cancelingId === request.leave_id }}
                      disabled={cancelingId === request.leave_id}
                      onPress={() => onCancel(request.leave_id)}
                      style={[styles.textAction, cancelingId === request.leave_id && styles.disabled]}
                    >
                      <Text style={[styles.dangerAction, align]}>
                        {cancelingId === request.leave_id ? t('common.loading') : t('leave.cancel')}
                      </Text>
                    </Pressable>
                  ) : null}
                </ListRow>
              )
            })}
            {hasMore ? (
              <ShowMoreButton
                label={loadingMore ? t('common.loading') : t('leave.historyAll.loadOlder')}
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

/** Cream-ground empty — no bordered white panel. */
function CalmNote({ message }: { message: string }) {
  const { isRTL } = useI18n()
  return (
    <Text
      maxFontSizeMultiplier={typeScaling.body}
      style={[styles.calmNote, readingEdgeAlign(isRTL)]}
      accessibilityRole="summary"
    >
      {message}
    </Text>
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
  chipStrip: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  chip: {
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceMuted,
  },
  chipSelected: { backgroundColor: colors.ink },
  chipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  chipTextSelected: { color: colors.bg },
  list: { gap: spacing.sm },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
    paddingVertical: spacing.sm,
  },
  empty: { color: colors.subtle, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  textAction: { paddingTop: spacing.xs, minHeight: layout.touchTarget, justifyContent: 'center' },
  dangerAction: { color: colors.danger, fontSize: font.small, fontWeight: '700' },
  disabled: { opacity: 0.5 },
})
