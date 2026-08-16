import { useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { EditorialHeading, FadeIn, Wordmark } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { PageBackButton, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { formatDate, formatNumber } from '@/lib/format'
import { ambient, colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { ComplianceJourneyItem, EmployeeDocument } from '@/api/types'
import {
  DocumentStatusMark,
  QuietReviewedMark,
  renewActionRelevant,
} from './documentStatusPills'
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
 *                    Compact cream row + pink accent only — never a dashboard card.
 *   Current          the live version of each document. Calm cream ledger rows.
 *   History          superseded files, grouped by year and collapsed. Quieter type.
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
  const align = readingEdgeAlign(isRTL)
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
      if (translated !== key && !isMissingTranslation(translated)) return translated
    }
    return t('status.unknown')
  }

  /** Same rule for names: i18n name, else the API's human label, else generic. */
  const resolveLabel = (documentType: string | null | undefined, apiLabel?: string | null) => {
    const type = String(documentType || '').trim()
    if (type) {
      const key = `documents.item.${type}`
      const translated = t(key)
      if (translated !== key && !isMissingTranslation(translated)) return translated
    }
    const label = String(apiLabel || '').trim()
    if (label && !isBackendKey(label) && !isMissingTranslation(label)) return label
    return t('documents.item.other')
  }
  const docLabel = (item: ComplianceJourneyItem) => {
    if (locale.startsWith('ar') && item.label_ar) return item.label_ar
    return resolveLabel(item.document_type, item.label)
  }

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('documents.title')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('documents.subtitle')}</Text>
        </FadeIn>

        {hierarchy.complianceUnavailable ? (
          <Text style={[styles.calmNote, align]}>{t('documents.compliancePartial')}</Text>
        ) : null}

        {hierarchy.attention.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('documents.needsAttention')} count={hierarchy.attention.length} />
            <View style={styles.ledger}>
              {hierarchy.attention.map((item, index) => (
                <AttentionRow
                  key={`attention-${item.document_type}-${index}`}
                  item={item}
                  label={docLabel(item)}
                  status={statusLabel(item.review_status)}
                  openingId={openingId}
                  downloadProgress={downloadProgress}
                  renewingType={renewingType}
                  onOpen={onOpen}
                  onCancel={onCancel}
                  onRenew={onRenew}
                />
              ))}
            </View>
          </View>
        ) : null}

        {hierarchy.current.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('documents.current')} count={hierarchy.current.length} />
            <View style={styles.ledger}>
              {hierarchy.current.map((item, index) => (
                <CurrentRow
                  key={`current-${item.document_type}-${index}`}
                  item={item}
                  label={docLabel(item)}
                  status={statusLabel(item.review_status)}
                  openingId={openingId}
                  downloadProgress={downloadProgress}
                  renewingType={renewingType}
                  onOpen={onOpen}
                  onCancel={onCancel}
                  onRenew={onRenew}
                />
              ))}
            </View>
          </View>
        ) : null}

        {historyYears.length ? (
          <View style={styles.section}>
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
                initiallyOpen={index === 0}
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
          <Text style={[styles.calmNote, align]} accessibilityRole="summary">
            {t('documents.empty')}
          </Text>
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

/** i18n-js missing-key sentinel — never show `[missing "en.…"]` as a document name. */
function isMissingTranslation(value: string): boolean {
  return /\[missing\s+"/i.test(value)
}

type ComplianceItemProps = {
  item: ComplianceJourneyItem
  label: string
  status: string
  openingId: string | null
  downloadProgress: number
  renewingType?: string | null
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
  onRenew?: (documentType: string) => void
}

/**
 * Action-required row: cream ledger + pink accent only.
 * Status, expiry and renew stay; no white card stack.
 */
function AttentionRow({
  item,
  label,
  status,
  openingId,
  downloadProgress,
  renewingType,
  onOpen,
  onCancel,
  onRenew,
}: ComplianceItemProps) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const fileId = item.current_file_id || null
  const opening = fileId != null && openingId === fileId
  const rawReason = String(item.rejection_reason || '').trim()
  const reason = rawReason && !isBackendKey(rawReason) ? rawReason : null
  const expiry = item.expiry_date
    ? `${t('documents.expiry')}: ${formatDate(item.expiry_date, locale)}`
    : t('documents.noExpiry')

  return (
    <View style={styles.ledgerRow} accessibilityLabel={`${label}. ${status}. ${expiry}`}>
      <View style={styles.attentionAccent} accessibilityElementsHidden />
      <View style={styles.ledgerMain}>
        <View style={styles.flex}>
          <View style={styles.titleRow}>
            <Text
              maxFontSizeMultiplier={typeScaling.body}
              numberOfLines={2}
              style={[styles.title, styles.flex, align]}
            >
              {label}
            </Text>
            <DocumentStatusMark item={item} label={status} />
          </View>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.meta, align]}>
            {expiry}
          </Text>
          {item.renewal_required ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.metaAction, align]}>
              {t('documents.renewalRequired')}
            </Text>
          ) : null}
          {reason ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.meta, align]}>
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
      </View>
    </View>
  )
}

/** Current document: dense name → expiry → quiet Reviewed → chevron. Whole row opens. */
function CurrentRow({
  item,
  label,
  openingId,
  downloadProgress,
  onOpen,
  onCancel,
}: ComplianceItemProps) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const fileId = item.current_file_id || null
  const opening = fileId != null && openingId === fileId
  const expiry = item.expiry_date
    ? `${t('documents.expiry')}: ${formatDate(item.expiry_date, locale)}`
    : t('documents.noExpiry')
  const canOpen = Boolean(fileId)
  const quietStatus = t('documents.reviewedQuiet')

  return (
    <Pressable
      accessibilityRole={canOpen ? 'button' : undefined}
      accessibilityLabel={`${label}. ${quietStatus}. ${expiry}`}
      accessibilityHint={canOpen ? t('documents.view') : undefined}
      disabled={!canOpen && !opening}
      onPress={() => {
        if (!fileId) return
        if (opening) onCancel?.()
        else onOpen(fileId, label)
      }}
      style={({ pressed }) => [styles.currentRow, pressed && canOpen && styles.pressed]}
    >
      <View style={styles.currentMain}>
        <View style={styles.flex}>
          <Text
            maxFontSizeMultiplier={typeScaling.body}
            numberOfLines={1}
            style={[styles.currentTitle, align]}
          >
            {label}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={[styles.currentMeta, align]}>
            {expiry}
          </Text>
          {opening ? <DownloadProgress progress={downloadProgress} /> : null}
        </View>
        <QuietReviewedMark label={quietStatus} />
        {canOpen || opening ? (
          opening ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.cancelInline}>
              {t('common.cancel')}
            </Text>
          ) : (
            <Ionicons
              name={isRTL ? 'chevron-back' : 'chevron-forward'}
              size={16}
              color={colors.navMuted}
              accessibilityElementsHidden
            />
          )
        ) : null}
      </View>
    </Pressable>
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
  hideView = false,
}: {
  item: ComplianceJourneyItem
  label: string
  fileId: string | null
  opening: boolean
  renewingType?: string | null
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
  onRenew?: (documentType: string) => void
  /** When the whole row opens the file, skip the duplicate View control. */
  hideView?: boolean
}) {
  const { t } = useI18n()
  const canRenew = renewActionRelevant(item, onRenew)
  const showView = Boolean(fileId) && !hideView
  if (!showView && !canRenew && !(opening && hideView)) return null
  const renewing = renewingType === item.document_type
  return (
    <View style={styles.actionRow}>
      {showView ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${opening ? t('common.cancel') : t('documents.view')}: ${label}`}
          onPress={() => (opening ? onCancel?.() : onOpen(fileId!, label))}
          style={({ pressed }) => [styles.textAction, pressed && styles.pressed]}
          hitSlop={6}
        >
          <Text style={styles.textActionLabel}>{opening ? t('common.cancel') : t('documents.view')}</Text>
        </Pressable>
      ) : null}
      {opening && hideView ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${t('common.cancel')}: ${label}`}
          onPress={() => onCancel?.()}
          style={({ pressed }) => [styles.textAction, pressed && styles.pressed]}
          hitSlop={6}
        >
          <Text style={styles.textActionLabel}>{t('common.cancel')}</Text>
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
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
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
        <View style={styles.ledger}>
          {page.visible.map((entry) => {
            const label = resolveLabel(entry.documentType, entry.label)
            const opening = entry.fileId != null && openingId === entry.fileId
            const when = entry.date ? formatDate(entry.date, locale) : t('documents.previousVersion')
            const canOpen = Boolean(entry.fileId)
            return (
              <Pressable
                key={entry.id}
                accessibilityRole={canOpen ? 'button' : undefined}
                accessibilityLabel={`${label}. ${t('documents.previousVersion')}. ${when}`}
                disabled={!canOpen && !opening}
                onPress={() => {
                  if (!entry.fileId) return
                  if (opening) onCancel?.()
                  else onOpen(entry.fileId, label)
                }}
                style={({ pressed }) => [styles.historyRow, pressed && canOpen && styles.pressed]}
              >
                <View style={styles.historyMain}>
                  <View style={styles.flex}>
                    <Text
                      maxFontSizeMultiplier={typeScaling.body}
                      numberOfLines={1}
                      style={[styles.historyTitle, align]}
                    >
                      {label}
                    </Text>
                    <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={[styles.historyMeta, align]}>
                      {when}
                    </Text>
                    {opening ? <DownloadProgress progress={downloadProgress} /> : null}
                  </View>
                  {opening ? (
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.cancelInline}>
                      {t('common.cancel')}
                    </Text>
                  ) : canOpen ? (
                    <Ionicons
                      name={isRTL ? 'chevron-back' : 'chevron-forward'}
                      size={15}
                      color={colors.navMuted}
                      accessibilityElementsHidden
                    />
                  ) : null}
                </View>
              </Pressable>
            )
          })}
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

const styles = StyleSheet.create({
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navSpacer: { width: layout.touchTarget },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  section: { gap: spacing.sm },
  ledger: { gap: 0 },
  ledgerRow: {
    minHeight: layout.touchTarget,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  currentRow: {
    minHeight: 44,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  currentMain: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  currentTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700', lineHeight: 19 },
  currentMeta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 15, marginTop: 1 },
  historyRow: {
    minHeight: 40,
    paddingVertical: spacing.sm - 2,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  historyMain: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  historyTitle: { color: colors.subtle, fontSize: font.small, fontWeight: '600', lineHeight: 18 },
  historyMeta: { color: colors.navMuted, fontSize: font.tiny, lineHeight: 14, marginTop: 1 },
  cancelInline: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  attentionAccent: {
    width: 3,
    alignSelf: 'stretch',
    borderRadius: radius.pill,
    backgroundColor: ambient.schedule.fill,
    marginEnd: spacing.xs,
  },
  accentSpacer: {
    width: 3,
    alignSelf: 'stretch',
    marginEnd: spacing.xs,
    opacity: 0,
  },
  ledgerMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  title: { color: colors.ink, fontSize: font.body, fontWeight: '800', lineHeight: 20 },
  meta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 2 },
  metaAction: { color: colors.ink, fontSize: font.tiny, lineHeight: 16, marginTop: 2, fontWeight: '700' },
  flex: { flex: 1 },
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginTop: spacing.xs },
  textAction: { minHeight: layout.touchTarget, justifyContent: 'center' },
  textActionLabel: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  pressed: { opacity: 0.85 },
  documentProgress: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.xs },
  documentProgressTrack: {
    flex: 1,
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    overflow: 'hidden',
  },
  documentProgressFill: { height: 6, backgroundColor: colors.ink },
  historyGroup: { gap: spacing.xs },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
    paddingVertical: spacing.sm,
  },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
})
