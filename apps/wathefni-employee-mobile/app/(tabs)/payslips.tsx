import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, BackHandler, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import * as FileSystem from 'expo-file-system/legacy'
import * as Sharing from 'expo-sharing'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { errorFeedback, successFeedback } from '@/native/haptics'
import { formatDate, formatMonthYear, formatNumber, yearOf } from '@/lib/format'
import { EditorialHeading, FadeIn, PastelCard, PremiumButton, Wordmark } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { PageBackButton, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { StatusChip } from '@/components/ui'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { PayslipDetailResponse, PayslipListItem, PayslipsResponse } from '@/api/types'

type PayslipLine = NonNullable<PayslipDetailResponse['lines']>[number]

export default function PayslipsScreen() {
  const { t, locale, isRTL } = useI18n()
  const { hasFeature, can, download, request } = useAuth()
  const router = useRouter()
  const params = useLocalSearchParams<{ payslip_id?: string }>()
  const enabled = hasFeature('payslips')
  const canDownload = can('payslips', 'download')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [extraPayslips, setExtraPayslips] = useState<PayslipListItem[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    const fromDeepLink = typeof params.payslip_id === 'string' ? params.payslip_id.trim() : ''
    if (fromDeepLink) setSelectedId(fromDeepLink)
  }, [params.payslip_id])

  // Android hardware back closes in-page detail before leaving the Payslips tab.
  useEffect(() => {
    if (!selectedId) return
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      setSelectedId(null)
      return true
    })
    return () => sub.remove()
  }, [selectedId])

  const list = useAppQuery<PayslipsResponse>(
    ['payslips', locale],
    `/app/payslips?locale=${encodeURIComponent(locale)}&limit=24`,
    { enabled, staleTime: HIGH_CHURN_STALE_MS },
  )

  // Sync first-page pagination metadata whenever the query payload changes.
  useEffect(() => {
    if (!list.data) return
    setNextCursor(list.data.next_cursor ?? null)
    setHasMore(Boolean(list.data.has_more))
    setExtraPayslips([])
  }, [list.data])

  const detail = useAppQuery<PayslipDetailResponse>(
    ['payslips', selectedId, locale],
    `/app/payslips/${encodeURIComponent(selectedId || '')}?locale=${encodeURIComponent(locale)}`,
    { enabled: enabled && Boolean(selectedId), staleTime: HIGH_CHURN_STALE_MS },
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      setExtraPayslips([])
      setNextCursor(null)
      setHasMore(false)
      await list.refetch()
      if (selectedId) await detail.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [detail, list, selectedId])

  const onLoadEarlier = useCallback(async () => {
    if (!hasMore || !nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await request<PayslipsResponse>(
        `/app/payslips?locale=${encodeURIComponent(locale)}&limit=24&cursor=${encodeURIComponent(nextCursor)}`,
      )
      const incoming = page.payslips ?? []
      setExtraPayslips((prev) => {
        const seen = new Set(prev.map((row) => row.payslip_id))
        const merged = [...prev]
        for (const row of incoming) {
          if (!seen.has(row.payslip_id)) merged.push(row)
        }
        return merged
      })
      setHasMore(Boolean(page.has_more))
      setNextCursor(page.next_cursor ?? null)
    } catch (err) {
      errorFeedback()
      Alert.alert(t('common.error'), approvedErrorMessage(err, t))
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loadingMore, locale, nextCursor, request, t])

  const onDownload = useCallback(async () => {
    if (!selectedId || !canDownload || downloading) return
    setDownloading(true)
    const target = `${FileSystem.cacheDirectory}payslip-${selectedId.replace(/[^\w-]+/g, '_')}.pdf`
    try {
      await download(`/app/payslips/${encodeURIComponent(selectedId)}/download?locale=${encodeURIComponent(locale)}`, target)
      successFeedback()
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(target, { mimeType: 'application/pdf', dialogTitle: t('payslips.download') })
      } else {
        Alert.alert(t('payslips.downloaded'), t('payslips.honestyShort'))
      }
    } catch (err) {
      errorFeedback()
      Alert.alert(t('common.error'), approvedErrorMessage(err, t))
    } finally {
      await FileSystem.deleteAsync(target, { idempotent: true }).catch(() => undefined)
      setDownloading(false)
    }
  }, [canDownload, download, downloading, locale, selectedId, t])

  const earnings = useMemo((): PayslipLine[] => {
    if (detail.data?.earnings?.length) {
      return detail.data.earnings.map((line: { line_kind: string; label?: string; amount: number | string; currency: string }) => ({
        line_kind: line.line_kind,
        label: line.label,
        amount: line.amount,
        currency: line.currency,
      }))
    }
    const lines: PayslipLine[] = detail.data?.lines ?? []
    return lines.filter((line: PayslipLine) => {
      const kind = String(line.line_kind || '').toLowerCase()
      if (kind.includes('deduct')) return false
      return kind.includes('earn') || kind.includes('allow') || kind === 'basic' || kind === 'one_time_earning' || !kind
    })
  }, [detail.data])

  const deductions = useMemo((): PayslipLine[] => {
    if (detail.data?.deductions?.length) {
      return detail.data.deductions.map((line: { line_kind: string; label?: string; amount: number | string; currency: string }) => ({
        line_kind: line.line_kind,
        label: line.label,
        amount: line.amount,
        currency: line.currency,
      }))
    }
    const lines: PayslipLine[] = detail.data?.lines ?? []
    return lines.filter((line: PayslipLine) => {
      const kind = String(line.line_kind || '').toLowerCase()
      return kind.includes('deduct')
    })
  }, [detail.data])

  const firstPage: PayslipListItem[] = list.data?.payslips ?? []
  const rows = useMemo(() => {
    if (!extraPayslips.length) return firstPage
    const seen = new Set(firstPage.map((row: PayslipListItem) => row.payslip_id))
    const merged = [...firstPage]
    for (const row of extraPayslips) {
      if (!seen.has(row.payslip_id)) merged.push(row)
    }
    return merged
  }, [extraPayslips, firstPage])

  if (!enabled) {
    return <FeatureUnavailableState feature="payslips" onRefresh={() => router.back()} />
  }
  if (list.isLoading && !list.data) return <LoadingState />
  if (list.isError && !list.data) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />

  const align = readingEdgeAlign(isRTL)
  const honesty = locale === 'ar' ? list.data?.honesty?.ar : list.data?.honesty?.en
  const payslip = detail.data?.payslip
  const currency = payslip?.currency || 'KWD'
  // Payroll owns the payment date. Show it only when payroll has actually
  // recorded one; the row is omitted otherwise rather than claiming
  // "Payment date: Not available" on every payslip, which it previously did
  // unconditionally because it never read `payment_date` at all.
  const paymentDate = String(payslip?.payment_date || '').trim()
  const releasedAt = String(payslip?.released_at || '').trim()

  return (
    <PageScreen>
      {/* Payslips is a tab root, so the only back step is out of a single
          payslip and into the list. */}
      <View style={styles.nav}>
        {selectedId ? (
          <PageBackButton onPress={() => setSelectedId(null)} accessibilityLabel={t('common.back')} />
        ) : (
          <Wordmark compact />
        )}
        {selectedId ? (
          <EditorialHeading size="medium">{t('payslips.detail')}</EditorialHeading>
        ) : null}
      </View>

      <PageScrollView refreshing={refreshing} onRefresh={() => void onRefresh()} gap={spacing.sm}>
        {!selectedId ? (
          <FadeIn style={styles.listRoot}>
            <View style={styles.hero}>
              <EditorialHeading>{t('payslips.title')}</EditorialHeading>
              {honesty ? <Text style={[styles.honesty, align]}>{honesty}</Text> : null}
            </View>
            {rows.length === 0 ? (
              <View style={styles.emptyBlock}>
                <CalmNote message={t('payslips.empty')} />
                <Text style={[styles.supporting, align]}>{t('payslips.emptyHint')}</Text>
              </View>
            ) : (
              <View style={styles.list}>
                <SectionHeader title={t('payslips.releasedList')} />
                {groupPayslipsByYear(rows).map((group, index, groups) => (
                  <PayslipYear
                    key={String(group.year ?? 'undated')}
                    year={group.year}
                    rows={group.rows}
                    initiallyOpen={index === 0}
                    // A lone year has nothing to collapse toward: the disclosure
                    // would only offer to empty the screen. The heading stays,
                    // because "2026" is still worth stating.
                    collapsible={groups.length > 1}
                    highlightNewest={index === 0}
                    onSelect={setSelectedId}
                  />
                ))}
                {hasMore ? (
                  <ShowMoreButton
                    label={loadingMore ? t('common.loading') : t('payslips.loadEarlier')}
                    onPress={() => {
                      if (!loadingMore) void onLoadEarlier()
                    }}
                  />
                ) : null}
              </View>
            )}
          </FadeIn>
        ) : detail.isLoading && !detail.data ? (
          <LoadingState />
        ) : detail.isError && !detail.data ? (
          <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
        ) : (
          <FadeIn>
            <PastelCard tone="butter" style={styles.detailCard}>
              <Text style={[styles.periodOverline, align]}>{t('payslips.period')}</Text>
              <Text style={[styles.period, align]}>
                {formatPeriod(String(payslip?.period_start || ''), String(payslip?.period_end || ''), locale)}
              </Text>
              <Text
                style={[styles.net, align]}
                accessibilityRole="header"
                maxFontSizeMultiplier={typeScaling.display}
              >
                {formatMoney(Number(payslip?.totals.net || 0), locale)} {currency}
              </Text>
              <Text style={[styles.netLabel, align]}>{t('payslips.net')}</Text>
              {paymentDate ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
                  {t('payslips.paymentDate')}: {formatDate(paymentDate, locale)}
                </Text>
              ) : releasedAt ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
                  {t('payslips.releasedOn', { date: formatDate(releasedAt, locale) })}
                </Text>
              ) : null}
              <View style={styles.statusRow}>
                <StatusChip label={t('payslips.released')} tone="success" />
              </View>
            </PastelCard>

            {earnings.length ? (
              <View style={styles.group}>
                <SectionHeader title={t('payslips.earnings')} />
                <Text style={[styles.groupTotal, align]}>
                  {formatMoney(Number(payslip?.totals.earnings || 0), locale)} {currency}
                </Text>
                {earnings.map((line, i) => (
                  <LineRow key={`e-${line.code || line.label}-${i}`} label={line.label || line.code || '—'} amount={line.amount} currency={line.currency || currency} />
                ))}
              </View>
            ) : null}

            {deductions.length ? (
              <View style={styles.group}>
                <SectionHeader title={t('payslips.deductions')} />
                <Text style={[styles.groupTotal, align]}>
                  {formatMoney(Number(payslip?.totals.deductions || 0), locale)} {currency}
                </Text>
                {deductions.map((line, i) => (
                  <LineRow key={`d-${line.code || line.label}-${i}`} label={line.label || line.code || '—'} amount={line.amount} currency={line.currency || currency} />
                ))}
              </View>
            ) : null}

            <Text style={[styles.honesty, align]}>
              {locale === 'ar' ? payslip?.honesty?.ar : payslip?.honesty?.en}
            </Text>

            {canDownload && payslip?.download_available ? (
              <>
                <PremiumButton
                  label={t('payslips.downloadPdf')}
                  onPress={() => void onDownload()}
                  busy={downloading}
                />
                {payslip?.official_document ? (
                  <Text style={[styles.footnote, align]}>{t('payslips.officialPdfNote')}</Text>
                ) : null}
              </>
            ) : (
              <Text style={[styles.footnote, align]}>{t('payslips.pdfUnavailable')}</Text>
            )}
          </FadeIn>
        )}
      </PageScrollView>
    </PageScreen>
  )
}

function formatPeriod(start: string, end: string, locale: string): string {
  if (!start && !end) return '—'
  return `${formatDate(start, locale)} → ${formatDate(end, locale)}`
}

function formatMoney(value: number, locale: string): string {
  return formatNumber(value, locale, 3)
}

/**
 * Payslip history grows by twelve rows a year forever, so it is grouped by year
 * with only the current year laid out, and paged inside a year. Each payslip used
 * to be a 130pt butter card showing the same three labels.
 */
const PAYSLIP_PAGE = 12

function groupPayslipsByYear(rows: PayslipListItem[]): Array<{ year: number | null; rows: PayslipListItem[] }> {
  const buckets = new Map<number | null, PayslipListItem[]>()
  for (const row of rows) {
    const year = yearOf(row.period_end || row.period_start)
    const bucket = buckets.get(year)
    if (bucket) bucket.push(row)
    else buckets.set(year, [row])
  }
  return [...buckets.entries()]
    .map(([year, group]) => ({ year, rows: group }))
    .sort((a, b) => {
      if (a.year === b.year) return 0
      if (a.year == null) return 1
      if (b.year == null) return -1
      return b.year - a.year
    })
}

function PayslipYear({
  year,
  rows,
  initiallyOpen,
  collapsible,
  highlightNewest,
  onSelect,
}: {
  year: number | null
  rows: PayslipListItem[]
  initiallyOpen: boolean
  collapsible: boolean
  highlightNewest?: boolean
  onSelect: (payslipId: string) => void
}) {
  const { t, locale, isRTL } = useI18n()
  const [open, setOpen] = useState(initiallyOpen)
  const page = usePagedList(rows, PAYSLIP_PAGE)
  const expanded = open || !collapsible
  const title = year == null ? t('payslips.undatedPeriod') : formatNumber(year, locale, 0)
  const label = `${title} (${rows.length})`
  const align = readingEdgeAlign(isRTL)

  return (
    <View style={styles.yearGroup}>
      {collapsible ? (
        <Pressable
          accessibilityRole="header"
          accessibilityState={{ expanded }}
          accessibilityLabel={label}
          onPress={() => setOpen((value) => !value)}
          hitSlop={6}
          style={({ pressed }) => [
            styles.yearHead,
            expanded ? styles.yearHeadOpen : styles.yearHeadClosed,
            pressed && styles.pressed,
          ]}
        >
          <Text
            maxFontSizeMultiplier={typeScaling.heading}
            style={[expanded ? styles.yearTitleOpen : styles.yearTitleClosed, align]}
          >
            {label}
          </Text>
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={16}
            color={expanded ? colors.ink : colors.subtle}
          />
        </Pressable>
      ) : (
        <View style={[styles.yearHead, styles.yearHeadOpen]}>
          <Text maxFontSizeMultiplier={typeScaling.heading} style={[styles.yearTitleOpen, align]}>
            {label}
          </Text>
        </View>
      )}
      {expanded ? (
        <View style={styles.ledger}>
          {page.visible.map((row, rowIndex) => (
            <PayslipRow
              key={row.payslip_id}
              row={row}
              newest={Boolean(highlightNewest && rowIndex === 0)}
              onPress={() => onSelect(row.payslip_id)}
            />
          ))}
          {page.hidden ? (
            <ShowMoreButton
              label={t('common.showMore', { count: formatNumber(page.hidden, locale, 0) })}
              onPress={page.showMore}
            />
          ) : null}
        </View>
      ) : null}
    </View>
  )
}

function PayslipRow({
  row,
  newest,
  onPress,
}: {
  row: PayslipListItem
  newest?: boolean
  onPress: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const month = formatMonthYear(row.period_end || row.period_start, locale)
  const amount = `${formatMoney(Number(row.net || 0), locale)} ${row.currency}`
  const period = formatPeriod(row.period_start, row.period_end, locale)
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${month}. ${period}. ${t('payslips.net')} ${amount}`}
      onPress={onPress}
      style={({ pressed }) => [styles.ledgerRow, pressed && styles.pressed]}
    >
      {newest ? <View style={styles.newestAccent} accessibilityElementsHidden /> : null}
      <View style={styles.ledgerMain}>
        <View style={styles.flex}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.ledgerTitle, align]}>
            {month}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={[styles.ledgerPeriod, align]}>
            {period}
          </Text>
        </View>
        <Text maxFontSizeMultiplier={typeScaling.body} numberOfLines={1} style={styles.rowAmount}>
          {amount}
        </Text>
        <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={16} color={colors.subtle} />
      </View>
    </Pressable>
  )
}

function LineRow({
  label,
  amount,
  currency,
}: {
  label: string
  amount: number | string
  currency: string
}) {
  const { locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View
      style={styles.lineRow}
      accessibilityLabel={`${label}: ${formatMoney(Number(amount || 0), locale)} ${currency}`}
    >
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lineLabel, styles.flex, align]}>
        {label}
      </Text>
      <Text
        maxFontSizeMultiplier={typeScaling.body}
        numberOfLines={1}
        style={[styles.lineAmount, styles.amountColumn]}
      >
        {formatMoney(Number(amount || 0), locale)} {currency}
      </Text>
    </View>
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
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    gap: spacing.sm,
    minHeight: layout.touchTarget,
  },
  back: { width: layout.touchTarget, height: layout.touchTarget, alignItems: 'center', justifyContent: 'center' },
  navSpacer: { width: layout.touchTarget },
  listRoot: { gap: spacing.md },
  hero: { gap: spacing.xs },
  honesty: { color: colors.subtle, fontSize: font.small, lineHeight: 18 },
  emptyBlock: { gap: spacing.xs, paddingVertical: spacing.sm },
  supporting: { color: colors.subtle, fontSize: font.small, lineHeight: 19 },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
  },
  list: { gap: spacing.md },
  yearGroup: { gap: spacing.xs },
  yearHead: {
    minHeight: layout.touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  yearHeadOpen: { borderBottomColor: colors.ink },
  yearHeadClosed: { borderBottomColor: colors.border },
  yearTitleOpen: { color: colors.ink, fontSize: font.h3, fontWeight: '800', letterSpacing: -0.2 },
  yearTitleClosed: { color: colors.subtle, fontSize: font.h3, fontWeight: '700' },
  pressed: { opacity: 0.82 },
  ledger: { gap: 0 },
  ledgerRow: {
    minHeight: layout.touchTarget,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  newestAccent: {
    width: 3,
    alignSelf: 'stretch',
    borderRadius: radius.pill,
    backgroundColor: colors.butter,
    marginEnd: spacing.xs,
  },
  ledgerMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  ledgerTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', lineHeight: 20 },
  ledgerPeriod: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 2 },
  rowAmount: { color: colors.ink, fontSize: font.body, fontWeight: '800', flexShrink: 0 },
  statusRow: { flexDirection: 'row', marginTop: spacing.xs },
  detailCard: { padding: spacing.lg, gap: 6, marginBottom: spacing.sm },
  periodOverline: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  period: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  net: { color: colors.ink, fontSize: font.display, fontWeight: '800', marginTop: 4 },
  netLabel: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  meta: { color: colors.subtle, fontSize: font.small },
  group: { gap: 4, marginBottom: spacing.sm },
  groupTotal: { color: colors.ink, fontSize: font.small, fontWeight: '800', marginBottom: 4 },
  lineRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: 44,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  lineLabel: { color: colors.ink, fontSize: font.body },
  lineAmount: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  // The amount is the point of the row: it keeps its width and the label wraps.
  amountColumn: { flexShrink: 0, marginStart: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 4 },
  flex: { flex: 1, minWidth: 0 },
})
