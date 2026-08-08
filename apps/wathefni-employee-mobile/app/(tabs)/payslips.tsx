import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams, useRouter } from 'expo-router'
import * as FileSystem from 'expo-file-system'
import * as Sharing from 'expo-sharing'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { formatDate, formatNumber, yearOf } from '@/lib/format'
import { EditorialHeading, FadeIn, PastelCard, PremiumButton } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { StatusChip } from '@/components/ui'
import { colors, font, layout, spacing, typeScaling } from '@/theme'
import type { PayslipDetailResponse, PayslipListItem, PayslipsResponse } from '@/api/types'

type PayslipLine = NonNullable<PayslipDetailResponse['lines']>[number]

export default function PayslipsScreen() {
  const { t, locale, isRTL } = useI18n()
  const { hasFeature, can, download } = useAuth()
  const router = useRouter()
  const params = useLocalSearchParams<{ payslip_id?: string }>()
  const enabled = hasFeature('payslips')
  const canDownload = can('payslips', 'download')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    const fromDeepLink = typeof params.payslip_id === 'string' ? params.payslip_id.trim() : ''
    if (fromDeepLink) setSelectedId(fromDeepLink)
  }, [params.payslip_id])

  const list = useAppQuery<PayslipsResponse>(
    ['payslips', locale],
    `/app/payslips?locale=${encodeURIComponent(locale)}`,
    { enabled, staleTime: HIGH_CHURN_STALE_MS },
  )
  const detail = useAppQuery<PayslipDetailResponse>(
    ['payslips', selectedId, locale],
    `/app/payslips/${encodeURIComponent(selectedId || '')}?locale=${encodeURIComponent(locale)}`,
    { enabled: enabled && Boolean(selectedId), staleTime: HIGH_CHURN_STALE_MS },
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await list.refetch()
      if (selectedId) await detail.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [detail, list, selectedId])

  const onDownload = useCallback(async () => {
    if (!selectedId || !canDownload || downloading) return
    setDownloading(true)
    const target = `${FileSystem.cacheDirectory}payslip-${selectedId.replace(/[^\w-]+/g, '_')}.pdf`
    try {
      await download(`/app/payslips/${encodeURIComponent(selectedId)}/download?locale=${encodeURIComponent(locale)}`, target)
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(target, { mimeType: 'application/pdf', dialogTitle: t('payslips.download') })
      } else {
        Alert.alert(t('payslips.downloaded'), t('payslips.honestyShort'))
      }
    } catch (err) {
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

  if (!enabled) {
    return <FeatureUnavailableState feature="payslips" onRefresh={() => router.back()} />
  }
  if (list.isLoading && !list.data) return <LoadingState />
  if (list.isError && !list.data) return <ErrorState error={list.error} onRetry={() => void list.refetch()} />

  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rows: PayslipListItem[] = list.data?.payslips ?? []
  const honesty = locale === 'ar' ? list.data?.honesty?.ar : list.data?.honesty?.en
  const payslip = detail.data?.payslip
  const currency = payslip?.currency || 'KWD'
  // Payroll owns the payment date. Show it only when payroll has actually
  // recorded one; the row is omitted otherwise rather than claiming
  // "Payment date: Not available" on every payslip, which it previously did
  // unconditionally because it never read `payment_date` at all.
  const paymentDate = String(payslip?.payment_date || '').trim()

  return (
    <PageScreen>
      {/* Payslips is a tab root, so the only back step is out of a single
          payslip and into the list. */}
      <View style={[styles.nav, isRTL && styles.rowReverse]}>
        {selectedId ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('common.back')}
            onPress={() => setSelectedId(null)}
            style={styles.back}
            hitSlop={8}
          >
            <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
          </Pressable>
        ) : null}
        <EditorialHeading size="medium">{selectedId ? t('payslips.detail') : t('payslips.title')}</EditorialHeading>
      </View>

      <PageScrollView refreshing={refreshing} onRefresh={() => void onRefresh()} gap={spacing.sm}>
        {!selectedId ? (
          <FadeIn>
            {honesty ? <Text style={[styles.honesty, align]}>{honesty}</Text> : null}
            {rows.length === 0 ? (
              <PastelCard tone="cream" style={styles.empty}>
                <Text style={[styles.emptyTitle, align]}>{t('payslips.empty')}</Text>
                <Text style={[styles.supporting, align]}>{t('payslips.emptyHint')}</Text>
              </PastelCard>
            ) : (
              <View style={styles.list}>
                <Text style={[styles.sectionLabel, align]}>{t('payslips.releasedList')}</Text>
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
                    onSelect={setSelectedId}
                  />
                ))}
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
              ) : null}
              <View style={styles.statusRow}>
                <StatusChip label={t('payslips.released')} tone="success" />
              </View>
            </PastelCard>

            {earnings.length ? (
              <View style={styles.group}>
                <Text style={[styles.sectionLabel, align]}>{t('payslips.earnings')}</Text>
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
                <Text style={[styles.sectionLabel, align]}>{t('payslips.deductions')}</Text>
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
              <PremiumButton
                label={t('payslips.downloadPdf')}
                onPress={() => void onDownload()}
                busy={downloading}
              />
            ) : (
              <Text style={[styles.footnote, align]}>{t('payslips.pdfUnavailable')}</Text>
            )}
            <Text style={[styles.footnote, align]}>
              {payslip?.official_document ? t('payslips.officialPdfNote') : t('payslips.noOfficialPdf')}
            </Text>
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
  onSelect,
}: {
  year: number | null
  rows: PayslipListItem[]
  initiallyOpen: boolean
  collapsible: boolean
  onSelect: (payslipId: string) => void
}) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(initiallyOpen)
  const page = usePagedList(rows, PAYSLIP_PAGE)
  const expanded = open || !collapsible
  return (
    <View style={styles.yearGroup}>
      <SectionHeader
        title={year == null ? t('payslips.undatedPeriod') : formatNumber(year, locale, 0)}
        count={rows.length}
        collapsible={collapsible}
        expanded={expanded}
        onToggle={() => setOpen((value) => !value)}
      />
      {expanded ? (
        <>
          {page.visible.map((row) => (
            <PayslipRow key={row.payslip_id} row={row} onPress={() => onSelect(row.payslip_id)} />
          ))}
          {page.hidden ? (
            <ShowMoreButton
              label={t('common.showMore', { count: formatNumber(page.hidden, locale, 0) })}
              onPress={page.showMore}
            />
          ) : null}
        </>
      ) : null}
    </View>
  )
}

function PayslipRow({ row, onPress }: { row: PayslipListItem; onPress: () => void }) {
  const { t, locale } = useI18n()
  const period = formatPeriod(row.period_start, row.period_end, locale)
  const amount = `${formatMoney(Number(row.net || 0), locale)} ${row.currency}`
  return (
    <ListRow
      title={period}
      meta={t('payslips.net')}
      showChevron
      onPress={onPress}
      accessibilityLabel={`${period}. ${t('payslips.net')} ${amount}`}
      trailing={
        <Text maxFontSizeMultiplier={typeScaling.body} numberOfLines={1} style={styles.rowAmount}>
          {amount}
        </Text>
      }
    />
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
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <View
      style={[styles.lineRow, isRTL && styles.rowReverse]}
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

const styles = StyleSheet.create({
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    gap: spacing.sm,
  },
  rowReverse: { flexDirection: 'row-reverse' },
  back: { width: layout.touchTarget, height: layout.touchTarget, alignItems: 'center', justifyContent: 'center' },
  navSpacer: { width: layout.touchTarget },
  honesty: { color: colors.subtle, fontSize: font.small, lineHeight: 18, marginBottom: spacing.sm },
  empty: { padding: spacing.lg, gap: spacing.xs },
  emptyTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700' },
  supporting: { color: colors.subtle, fontSize: font.body },
  sectionLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.4, marginTop: spacing.sm },
  list: { gap: spacing.sm },
  yearGroup: { gap: spacing.sm },
  rowAmount: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  statusRow: { flexDirection: 'row', marginTop: spacing.xs },
  detailCard: { padding: spacing.lg, gap: 6, marginBottom: spacing.sm },
  periodOverline: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  period: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  net: { color: colors.ink, fontSize: 28, fontWeight: '800', marginTop: 4 },
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
  flex: { flex: 1 },
})
