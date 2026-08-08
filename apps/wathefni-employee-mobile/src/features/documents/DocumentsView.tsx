import { useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n } from '@/i18n'
import { EditorialHeading, FadeIn, IconBadge, PastelCard, WathefniBloom, Wordmark } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { StatusChip, type StatusTone } from '@/components/ui'
import { formatDate, formatNumber } from '@/lib/format'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { ComplianceJourneyItem, EmployeeDocument } from '@/api/types'
import {
  documentsHierarchy,
  groupHistoryByYear,
  type DocumentHistoryEntry,
} from './documentsHierarchy'

type Props = {
  documents: EmployeeDocument[]
  compliance?: ComplianceJourneyItem[]
  openingId: string | null
  downloadProgress?: number
  renewingType?: string | null
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
  onRenew?: (documentType: string) => void
  refreshing?: boolean
  onRefresh?: () => void
  onBack: () => void
}

/** One year of superseded files renders at a time; the rest wait behind a tap. */
const HISTORY_PAGE = 10

/**
 * Documents is the employee-facing compliance surface, and the three sections
 * mean genuinely different things:
 *
 *   Needs attention  something is expired, rejected or waiting on the employee.
 *                    Card treatment, semantic edge, actions on the card.
 *   Current          the live version of each document. Calm compact rows.
 *   History          superseded files, grouped by year and collapsed. Nothing an
 *                    employee acts on, so nothing that competes for their eye.
 *
 * The same current file is never rendered twice.
 */
export function DocumentsView({
  documents,
  compliance = [],
  openingId,
  downloadProgress = 0,
  renewingType,
  onOpen,
  onCancel,
  onRenew,
  refreshing,
  onRefresh,
  onBack,
}: Props) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const hierarchy = documentsHierarchy(compliance, documents)
  const historyYears = groupHistoryByYear(hierarchy.history)
  const empty =
    !hierarchy.attention.length && !hierarchy.current.length && !hierarchy.history.length

  /**
   * A backend review-status key is never printed. If we have no translation and
   * the API's own label still looks like an enum, we say the status is
   * unavailable rather than showing `pending_hr_review` to an employee.
   */
  const statusLabel = (reviewStatus: string | null | undefined) => {
    const raw = String(reviewStatus || '').trim()
    if (raw) {
      const key = `documents.status.${raw}`
      const translated = t(key)
      if (translated !== key) return translated
    }
    return t('status.unknown')
  }

  /** Same rule for names: i18n name, else the API's human label, else generic. */
  const resolveLabel = (documentType: string | null | undefined, apiLabel?: string | null) => {
    const type = String(documentType || '').trim()
    if (type) {
      const key = `documents.item.${type}`
      const translated = t(key)
      if (translated !== key) return translated
    }
    const label = String(apiLabel || '').trim()
    if (label && !isBackendKey(label)) return label
    return t('documents.item.other')
  }
  const docLabel = (item: ComplianceJourneyItem) => {
    if (locale.startsWith('ar') && item.label_ar) return item.label_ar
    return resolveLabel(item.document_type, item.label)
  }

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={[styles.nav, isRTL && styles.rowReverse]}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('common.back')}
            onPress={onBack}
            style={styles.backButton}
            hitSlop={8}
          >
            <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
          </Pressable>
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('documents.title')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('documents.subtitle')}</Text>
        </FadeIn>

        {hierarchy.complianceUnavailable ? (
          <View style={styles.noticeCard}>
            <Text style={[styles.supporting, align]}>{t('documents.compliancePartial')}</Text>
          </View>
        ) : null}

        {hierarchy.attention.length ? (
          <View style={styles.list}>
            <SectionHeader title={t('documents.needsAttention')} count={hierarchy.attention.length} />
            {hierarchy.attention.map((item, index) => (
              <AttentionCard
                key={`attention-${item.document_type}-${index}`}
                item={item}
                label={docLabel(item)}
                status={statusLabel(item.review_status)}
                statusTone={complianceTone(item)}
                openingId={openingId}
                downloadProgress={downloadProgress}
                renewingType={renewingType}
                onOpen={onOpen}
                onCancel={onCancel}
                onRenew={onRenew}
              />
            ))}
          </View>
        ) : null}

        {hierarchy.current.length ? (
          <View style={styles.list}>
            <SectionHeader title={t('documents.current')} count={hierarchy.current.length} />
            {hierarchy.current.map((item, index) => (
              <CurrentRow
                key={`current-${item.document_type}-${index}`}
                item={item}
                label={docLabel(item)}
                status={statusLabel(item.review_status)}
                statusTone={complianceTone(item)}
                openingId={openingId}
                downloadProgress={downloadProgress}
                renewingType={renewingType}
                onOpen={onOpen}
                onCancel={onCancel}
                onRenew={onRenew}
              />
            ))}
          </View>
        ) : null}

        {historyYears.length ? (
          <View style={styles.list}>
            <SectionHeader title={t('documents.history')} count={hierarchy.history.length} />
            {historyYears.map((group, index, groups) => (
              <HistoryYear
                key={String(group.year ?? 'undated')}
                title={
                  group.year == null
                    ? t('documents.historyUndated')
                    : formatNumber(group.year, locale, 0)
                }
                entries={group.entries}
                // Only the most recent year is laid out on arrival; older years
                // stay closed so a decade of renewals cannot flood the screen.
                initiallyOpen={index === 0}
                // With one year there is nothing to collapse toward, so the
                // heading keeps its context without offering an empty screen.
                collapsible={groups.length > 1}
                resolveLabel={resolveLabel}
                openingId={openingId}
                downloadProgress={downloadProgress}
                onOpen={onOpen}
                onCancel={onCancel}
              />
            ))}
          </View>
        ) : null}

        {empty ? (
          <PastelCard tone="lilac" style={styles.emptyCard}>
            <IconBadge name="documents-outline" />
            <Text style={[styles.emptyText, align]}>{t('documents.empty')}</Text>
            <WathefniBloom variant="watermark" />
          </PastelCard>
        ) : null}

        <Text style={[styles.footnote, align]}>{t('documents.legitimacyNote')}</Text>
      </PageScrollView>
    </PageScreen>
  )
}

/** snake_case / dotted keys are backend identifiers, not names an employee reads. */
function isBackendKey(value: string): boolean {
  return /^[a-z0-9]+([._-][a-z0-9]+)+$/.test(value)
}

/** Review status drives the semantic chip tone; ambient card colour never does. */
function complianceTone(item: ComplianceJourneyItem): StatusTone {
  const status = String(item.review_status || '').toLowerCase()
  if (item.rejection_reason || status === 'rejected_reupload' || status === 'expired' || status === 'missing') {
    return 'danger'
  }
  if (item.renewal_required || status === 'expiring_soon' || status === 'pending_hr_review' || status === 'replacement_required') {
    return 'warning'
  }
  if (status === 'hr_reviewed' || status === 'accepted' || status === 'approved') return 'success'
  return 'neutral'
}

type ComplianceItemProps = {
  item: ComplianceJourneyItem
  label: string
  status: string
  statusTone: StatusTone
  openingId: string | null
  downloadProgress: number
  renewingType?: string | null
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
  onRenew?: (documentType: string) => void
}

/**
 * Something is wrong or waiting on the employee. This is the one place in
 * Documents that earns a card, a semantic edge and inline actions.
 */
function AttentionCard({
  item,
  label,
  status,
  statusTone,
  openingId,
  downloadProgress,
  renewingType,
  onOpen,
  onCancel,
  onRenew,
}: ComplianceItemProps) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const fileId = item.current_file_id || null
  const opening = fileId != null && openingId === fileId
  // HR sometimes stores a machine reason code; only show a reason a human wrote.
  const rawReason = String(item.rejection_reason || '').trim()
  const reason = rawReason && !isBackendKey(rawReason) ? rawReason : null
  const edge = statusTone === 'danger' ? colors.danger : colors.warning

  return (
    <View style={[styles.attentionCard, { borderColor: edge }]} accessibilityLabel={`${label}. ${status}`}>
      <View style={[styles.attentionHead, isRTL && styles.rowReverse]}>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.itemTitle, styles.flex, align]}>
          {label}
        </Text>
        <StatusChip label={status} tone={statusTone} />
      </View>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
        {item.expiry_date
          ? `${t('documents.expiry')}: ${formatDate(item.expiry_date, locale)}`
          : t('documents.noExpiry')}
      </Text>
      {item.renewal_required ? (
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align, styles.metaWarning]}>
          {t('documents.renewalRequired')}
        </Text>
      ) : null}
      {reason ? (
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
          {t('documents.rejectionReason')}: {reason}
        </Text>
      ) : null}
      <DocumentActions
        item={item}
        label={label}
        fileId={fileId}
        opening={opening}
        renewingType={renewingType}
        onOpen={onOpen}
        onCancel={onCancel}
        onRenew={onRenew}
      />
      {opening ? <DownloadProgress progress={downloadProgress} labelled /> : null}
    </View>
  )
}

/** A current document is calm: name, status, expiry, and the same two actions. */
function CurrentRow({
  item,
  label,
  status,
  statusTone,
  openingId,
  downloadProgress,
  renewingType,
  onOpen,
  onCancel,
  onRenew,
}: ComplianceItemProps) {
  const { t, locale } = useI18n()
  const fileId = item.current_file_id || null
  const opening = fileId != null && openingId === fileId
  const expiry = item.expiry_date
    ? `${t('documents.expiry')}: ${formatDate(item.expiry_date, locale)}`
    : t('documents.noExpiry')
  return (
    <ListRow
      title={label}
      meta={expiry}
      trailing={<StatusChip label={status} tone={statusTone} />}
      accessibilityLabel={`${label}. ${status}. ${expiry}`}
    >
      <DocumentActions
        item={item}
        label={label}
        fileId={fileId}
        opening={opening}
        renewingType={renewingType}
        onOpen={onOpen}
        onCancel={onCancel}
        onRenew={onRenew}
      />
      {opening ? <DownloadProgress progress={downloadProgress} /> : null}
    </ListRow>
  )
}

function DocumentActions({
  item,
  label,
  fileId,
  opening,
  renewingType,
  onOpen,
  onCancel,
  onRenew,
}: {
  item: ComplianceJourneyItem
  label: string
  fileId: string | null
  opening: boolean
  renewingType?: string | null
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
  onRenew?: (documentType: string) => void
}) {
  const { t, isRTL } = useI18n()
  const canRenew = item.can_renew !== false && Boolean(onRenew)
  if (!fileId && !canRenew) return null
  const renewing = renewingType === item.document_type
  return (
    <View style={[styles.actionRow, isRTL && styles.rowReverse]}>
      {fileId ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${opening ? t('common.cancel') : t('documents.view')}: ${label}`}
          onPress={() => (opening ? onCancel?.() : onOpen(fileId, label))}
          style={({ pressed }) => [styles.textAction, pressed && styles.pressed]}
          hitSlop={6}
        >
          <Text style={styles.textActionLabel}>{opening ? t('common.cancel') : t('documents.view')}</Text>
        </Pressable>
      ) : null}
      {canRenew ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${t('documents.renew')}: ${label}`}
          accessibilityState={{ disabled: renewing }}
          disabled={renewing}
          onPress={() => onRenew?.(item.document_type)}
          style={({ pressed }) => [styles.textAction, pressed && styles.pressed]}
          hitSlop={6}
        >
          {renewing ? (
            <ActivityIndicator size="small" color={colors.ink} />
          ) : (
            <Text style={styles.textActionLabel}>{t('documents.renew')}</Text>
          )}
        </Pressable>
      ) : null}
    </View>
  )
}

function DownloadProgress({ progress, labelled }: { progress: number; labelled?: boolean }) {
  const { t } = useI18n()
  const percent = Math.round(progress * 100)
  return (
    <View
      style={styles.documentProgress}
      accessibilityLabel={labelled ? t('documents.downloadProgress', { percent }) : undefined}
    >
      <ActivityIndicator size="small" color={colors.ink} />
      <View style={styles.documentProgressTrack}>
        <View style={[styles.documentProgressFill, { width: `${percent}%` }]} />
      </View>
      <Text style={styles.meta}>{percent}%</Text>
    </View>
  )
}

function HistoryYear({
  title,
  entries,
  initiallyOpen,
  collapsible,
  resolveLabel,
  openingId,
  downloadProgress,
  onOpen,
  onCancel,
}: {
  title: string
  entries: DocumentHistoryEntry[]
  initiallyOpen: boolean
  collapsible: boolean
  resolveLabel: (documentType: string | null | undefined, apiLabel?: string | null) => string
  openingId: string | null
  downloadProgress: number
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
}) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(initiallyOpen)
  const page = usePagedList(entries, HISTORY_PAGE)
  const expanded = open || !collapsible
  return (
    <View style={styles.historyGroup}>
      <SectionHeader
        title={title}
        count={entries.length}
        collapsible={collapsible}
        expanded={expanded}
        onToggle={() => setOpen((value) => !value)}
      />
      {expanded ? (
        <>
          {page.visible.map((entry) => {
            const label = resolveLabel(entry.documentType, entry.label)
            const opening = entry.fileId != null && openingId === entry.fileId
            return (
              <ListRow
                key={entry.id}
                title={label}
                meta={entry.date ? formatDate(entry.date, locale) : t('documents.previousVersion')}
                onPress={
                  entry.fileId ? () => (opening ? onCancel?.() : onOpen(entry.fileId!, label)) : undefined
                }
                accessibilityLabel={`${label}. ${t('documents.previousVersion')}`}
                trailing={
                  entry.fileId ? (
                    <Text style={styles.textActionLabel}>
                      {opening ? t('common.cancel') : t('documents.view')}
                    </Text>
                  ) : null
                }
              >
                {opening ? <DownloadProgress progress={downloadProgress} /> : null}
              </ListRow>
            )
          })}
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

const styles = StyleSheet.create({
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  backButton: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  navSpacer: { width: layout.touchTarget },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  list: { gap: spacing.sm },
  historyGroup: { gap: spacing.sm },
  rowReverse: { flexDirection: 'row-reverse' },
  attentionCard: {
    gap: spacing.xs,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  attentionHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  itemTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  meta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  metaWarning: { color: colors.warning, fontWeight: '700' },
  supporting: { color: colors.subtle, fontSize: font.small, lineHeight: 19 },
  flex: { flex: 1 },
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginTop: spacing.xs },
  textAction: { minHeight: layout.touchTarget, justifyContent: 'center' },
  textActionLabel: { color: colors.accent, fontSize: font.small, fontWeight: '700' },
  pressed: { opacity: 0.85 },
  documentProgress: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  documentProgressTrack: {
    flex: 1,
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    overflow: 'hidden',
  },
  documentProgressFill: { height: 6, backgroundColor: colors.ink },
  noticeCard: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  emptyCard: { gap: spacing.md, paddingVertical: spacing.xl, alignItems: 'flex-start' },
  emptyText: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
})
