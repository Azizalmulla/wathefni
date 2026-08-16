import type { ReactNode } from 'react'
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n } from '@/i18n'
import { StatusChip } from '@/components/ui'
import {
  EditorialHeading,
  FadeIn,
  MotionProgressBar,
  PastelCard,
  PremiumButton,
  ContentSkeleton,
  Wordmark,
} from '@/components/premium'
import { formatDate, formatNumber, statusTone } from '@/lib/format'
import { colors, font, radius, shadows, spacing } from '@/theme'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'
import {
  onboardingStatusLabel,
  projectOnboardingLifecycle,
  type OnboardingLifecycleProjection,
} from '@/features/onboarding/lifecycleProjection'

type OnboardingViewProps = {
  data: OnboardingResponse
  uploadingId: string | null
  uploadProgress?: number
  failedUploadId?: string | null
  openingId?: string | null
  versionsByItem?: Record<string, VersionRow[]>
  versionsLoadingId?: string | null
  refreshing?: boolean
  onRefresh?: () => void
  onUpload: (item: OnboardingItem) => void
  onPreview?: (item: OnboardingItem) => void
  onViewVersions?: (item: OnboardingItem) => void
  onCancelUpload?: () => void
  onRetryUpload?: (item: OnboardingItem) => void
  onBack: () => void
}

export type VersionRow = {
  version_id?: string
  version_no?: number
  review_status?: string
  is_current?: boolean
  file_id?: string | null
  rejection_reason?: string | null
  created_at?: string | null
}

export function OnboardingView({
  data,
  uploadingId,
  uploadProgress = 0,
  failedUploadId = null,
  openingId = null,
  versionsByItem = {},
  versionsLoadingId = null,
  refreshing,
  onRefresh,
  onUpload,
  onPreview,
  onViewVersions,
  onCancelUpload,
  onRetryUpload,
  onBack,
}: OnboardingViewProps) {
  const { t, isRTL, locale } = useI18n()
  const projection = projectOnboardingLifecycle(data)

  if (!projection.contractOk) {
    return (
      <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
        <View style={styles.content}>
          <View style={[styles.nav, isRTL ? styles.rowReverse : undefined]}>
            <Pressable accessibilityRole="button" accessibilityLabel={t('common.back')} onPress={onBack} style={styles.backButton}>
              <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
            </Pressable>
            <Wordmark compact align="center" />
            <View style={styles.navSpacer} />
          </View>
          <Text style={[styles.taskTitle, { textAlign: isRTL ? 'right' : 'left' }]}>
            {t('onboarding.contractErrorTitle')}
          </Text>
          <Text style={[styles.stateMessage, { textAlign: isRTL ? 'right' : 'left' }]}>
            {t('onboarding.contractErrorMessage', {
              version: projection.lifecycleVersion || 'missing',
              reason: projection.reason,
            })}
          </Text>
          {onRefresh ? <PremiumButton label={t('common.retry')} onPress={onRefresh} /> : null}
        </View>
      </SafeAreaView>
    )
  }

  return <LifecycleChecklistView projection={projection} {...{
    uploadingId,
    uploadProgress,
    failedUploadId,
    openingId,
    versionsByItem,
    versionsLoadingId,
    refreshing,
    onRefresh,
    onUpload,
    onPreview,
    onViewVersions,
    onCancelUpload,
    onRetryUpload,
    onBack,
  }} />
}

function LifecycleChecklistView({
  projection,
  uploadingId,
  uploadProgress = 0,
  failedUploadId = null,
  openingId = null,
  versionsByItem = {},
  versionsLoadingId = null,
  refreshing,
  onRefresh,
  onUpload,
  onPreview,
  onViewVersions,
  onCancelUpload,
  onRetryUpload,
  onBack,
}: {
  projection: OnboardingLifecycleProjection
} & Omit<OnboardingViewProps, 'data'>) {
  const { t, isRTL, locale } = useI18n()
  const yourActions = projection.yourActions
  const beingReviewed = projection.beingReviewed
  const handledByOthers = projection.handledByOthers
  const completed = projection.completed
  const canUpload = projection.canUpload
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const done = projection.acceptedCount
  const progress = projection.requiredTotal ? done / projection.requiredTotal : 1
  const hasAny = yourActions.length + beingReviewed.length + handledByOthers.length + completed.length > 0

  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          onRefresh ? (
            <RefreshControl refreshing={Boolean(refreshing)} onRefresh={onRefresh} tintColor={colors.ink} />
          ) : undefined
        }
      >
        <View style={[styles.nav, rowDirection]}>
          <Pressable accessibilityRole="button" accessibilityLabel={t('common.back')} onPress={onBack} style={styles.backButton}>
            <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
          </Pressable>
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('onboarding.checklistTitle')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('onboarding.checklistSubtitle')}</Text>
        </FadeIn>

        <PastelCard tone="lilac" style={styles.progressCard}>
          <View style={[styles.progressHead, rowDirection]}>
            <View style={styles.progressCopy}>
              <Text style={[styles.progressLabel, align]}>{t('onboarding.progressLabel')}</Text>
              <Text style={[styles.progressValue, align]}>
                {t('onboarding.progress', {
                  done: formatNumber(done, locale, 0),
                  total: formatNumber(projection.requiredTotal, locale, 0),
                })}
              </Text>
            </View>
            <View style={styles.progressBubble}>
              <Text style={styles.progressPercent}>
                {formatNumber(Math.round(progress * 100), locale, 0)}%
              </Text>
            </View>
          </View>
          <MotionProgressBar value={progress} />
        </PastelCard>

        {!hasAny || (!yourActions.length && !beingReviewed.length && !handledByOthers.length && completed.length) ? (
          yourActions.length || beingReviewed.length || handledByOthers.length ? null : <CompletedChecklist />
        ) : null}

        {yourActions.length ? (
          <Section title={t('onboarding.yourActions')} align={align}>
            {yourActions.map((item, index) => (
              <ChecklistCard
                key={itemKey(item, index)}
                item={item}
                tone={index % 2 ? 'sky' : 'lilac'}
                canUpload={canUpload}
                uploading={uploadingId === item.item_id}
                uploadProgress={uploadingId === item.item_id ? uploadProgress : 0}
                uploadFailed={failedUploadId === item.item_id}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
                onCancelUpload={onCancelUpload}
                onRetryUpload={onRetryUpload}
              />
            ))}
          </Section>
        ) : null}

        {beingReviewed.length ? (
          <Section title={t('onboarding.beingReviewed')} align={align}>
            {beingReviewed.map((item, index) => (
              <ChecklistCard
                key={itemKey(item, index)}
                item={item}
                tone="blush"
                canUpload={canUpload}
                uploading={false}
                uploadProgress={0}
                uploadFailed={false}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
              />
            ))}
          </Section>
        ) : null}

        {handledByOthers.length ? (
          <Section title={t('onboarding.handledByOthers')} align={align}>
            {handledByOthers.map((item, index) => (
              <ChecklistCard
                key={itemKey(item, index)}
                item={item}
                tone={index % 2 ? 'sky' : 'lilac'}
                canUpload={false}
                uploading={false}
                uploadProgress={0}
                uploadFailed={false}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
              />
            ))}
          </Section>
        ) : null}

        {completed.length ? (
          <Section title={t('onboarding.completedSection')} align={align}>
            {completed.map((item, index) => (
              <ChecklistCard
                key={itemKey(item, index)}
                item={item}
                tone="sage"
                canUpload={false}
                uploading={false}
                uploadProgress={0}
                uploadFailed={false}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
              />
            ))}
          </Section>
        ) : null}

        <PastelCard tone="sage" style={styles.securityCard}>
          <View style={[styles.securityRow, rowDirection]}>
            <Ionicons name="shield-checkmark-outline" size={22} color={colors.success} />
            <View style={styles.flex}>
              <Text style={[styles.securityTitle, align]}>{t('onboarding.secureTitle')}</Text>
              <Text style={[styles.securityText, align]}>{t('onboarding.secureMessage')}</Text>
            </View>
          </View>
        </PastelCard>
      </ScrollView>
    </SafeAreaView>
  )
}

function Section({
  title,
  align,
  children,
}: {
  title: string
  align: { textAlign: 'left' | 'right' }
  children: ReactNode
}) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, align]}>{title}</Text>
      {children}
    </View>
  )
}

function ChecklistCard({
  item,
  tone,
  canUpload,
  uploading,
  uploadProgress,
  uploadFailed,
  opening,
  versions,
  versionsLoading,
  onUpload,
  onPreview,
  onViewVersions,
  onCancelUpload,
  onRetryUpload,
}: {
  item: OnboardingItem
  tone: 'lilac' | 'sky' | 'blush' | 'sage'
  canUpload: boolean
  uploading: boolean
  uploadProgress: number
  uploadFailed: boolean
  opening?: boolean
  versions?: VersionRow[]
  versionsLoading?: boolean
  onUpload: (item: OnboardingItem) => void
  onPreview?: (item: OnboardingItem) => void
  onViewVersions?: (item: OnboardingItem) => void
  onCancelUpload?: () => void
  onRetryUpload?: (item: OnboardingItem) => void
}) {
  const { t, isRTL, locale } = useI18n()
  const title = onboardingItemLabel(item, t)
  const description = onboardingItemDescription(item, t)
  const actions = new Set(item.actions || [])
  const isDocument =
    (item.item_type || '').toLowerCase() === 'document' ||
    Boolean(item.document_type) ||
    (item.collection_mode || '').toLowerCase() === 'document'
  const isBank =
    (item.item_id || '') === 'bank_details' || (item.collection_mode || '').toLowerCase() === 'ess_encrypted'
  const allowUpload =
    canUpload &&
    isDocument &&
    Boolean(item.item_id) &&
    (actions.has('upload') || actions.has('replace') || actions.has('resubmit'))
  const allowPreview = Boolean(item.file_id) && (actions.has('preview') || Boolean(item.file_id))
  const allowVersions = Boolean(onViewVersions) && (actions.has('view_versions') || Boolean(item.file_id))
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const photo = (item.item_id || item.document_type) === 'personal_photo'
  const normalizedStatus = (item.status || 'pending').toLowerCase()
  const awaitingReview = ['submitted', 'processing', 'received'].includes(normalizedStatus)
  const isAccepted = normalizedStatus === 'accepted' || normalizedStatus === 'waived'
  const needsReplacement = ['replacement_required', 'rejected'].includes(normalizedStatus)
  const guidance = needsReplacement
    ? t('onboarding.rejectionTitle')
    : normalizedStatus === 'processing'
      ? t('onboarding.processingGuidance')
      : awaitingReview
        ? t('onboarding.reviewGuidance')
        : isAccepted
          ? t('onboarding.acceptedGuidance')
          : isBank
            ? t('onboarding.bankComingSoon')
            : allowUpload
              ? t('onboarding.uploadGuidance')
              : t('onboarding.uploadUnavailable')
  const dueLabel = item.due_date ? t('onboarding.dueDate', { date: formatDate(item.due_date, locale) }) : null
  // Resubmit/replace/upload only when API actions say so (no legacy fallback).
  const primaryAction = actions.has('resubmit')
    ? 'resubmit'
    : actions.has('replace')
      ? 'replace'
      : actions.has('upload')
        ? 'upload'
        : null

  const cardBody = (
    <>
      <View style={[styles.taskTop, rowDirection]}>
        <View style={styles.flex}>
          <View style={[styles.requirementRow, rowDirection]}>
            <View style={[styles.requirementPill, item.required === false && styles.optionalPill]}>
              <Text style={[styles.requirementText, item.required === false && styles.optionalText]}>
                {item.required === false ? t('onboarding.optional') : t('onboarding.required')}
              </Text>
            </View>
            <StatusChip label={onboardingStatusLabel(item.status, t)} tone={statusTone(item.status)} />
          </View>
          <Text style={[styles.taskTitle, align]}>{title}</Text>
          <Text style={[styles.taskDescription, align]}>{description}</Text>
          {dueLabel ? <Text style={[styles.dueDate, align]}>{dueLabel}</Text> : null}
          {needsReplacement && item.rejection_reason ? (
            <Text style={[styles.rejectionReason, align]}>{item.rejection_reason}</Text>
          ) : (
            <Text
              style={[
                styles.guidance,
                awaitingReview && styles.guidanceReview,
                needsReplacement && styles.guidanceReject,
                align,
              ]}
            >
              {guidance}
            </Text>
          )}
          {versionsLoading ? (
            <Text style={[styles.versionMeta, align]}>{t('common.loading')}</Text>
          ) : versions?.length ? (
            <View style={styles.versionList}>
              <Text style={[styles.versionTitle, align]}>{t('onboarding.versionHistory')}</Text>
              {versions.slice(0, 6).map((v) => (
                <Text key={String(v.version_id || v.version_no)} style={[styles.versionMeta, align]}>
                  {t('onboarding.versionLine', {
                    no: formatNumber(Number(v.version_no || 0), locale, 0),
                    status: versionReviewLabel(v.review_status, t),
                  })}
                </Text>
              ))}
            </View>
          ) : null}
        </View>
        <View style={styles.taskArt}>
          <Ionicons name={photo ? 'person' : 'document-text-outline'} size={38} color={colors.ink} />
          {primaryAction ? (
            <View style={styles.plusBadge}>
              <Ionicons name="add" size={16} color={colors.surface} />
            </View>
          ) : null}
        </View>
      </View>
      {uploading ? (
        <View style={styles.transfer}>
          <View style={[styles.transferHead, rowDirection]}>
            <Text style={[styles.transferText, align]}>{t('onboarding.uploading')}</Text>
            <Text style={styles.transferText}>{Math.round(uploadProgress * 100)}%</Text>
          </View>
          <MotionProgressBar value={uploadProgress} />
          {onCancelUpload ? (
            <Pressable accessibilityRole="button" onPress={onCancelUpload} style={styles.cancelTransfer}>
              <Text style={styles.cancelTransferText}>{t('common.cancel')}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : (
        <View style={styles.actionRow}>
          {allowPreview && onPreview ? (
            <PremiumButton
              label={opening ? t('common.loading') : t('onboarding.preview')}
              onPress={() => onPreview(item)}
              disabled={Boolean(opening)}
            />
          ) : null}
          {allowVersions && !versions?.length ? (
            <PremiumButton
              label={versionsLoading ? t('common.loading') : t('onboarding.versionHistory')}
              onPress={() => onViewVersions?.(item)}
              disabled={Boolean(versionsLoading)}
            />
          ) : null}
          {primaryAction ? (
            <PremiumButton
              label={
                uploadFailed
                  ? t('common.retry')
                  : primaryAction === 'resubmit'
                    ? t('onboarding.resubmit')
                    : primaryAction === 'replace'
                      ? t('onboarding.replace')
                      : photo
                        ? t('onboarding.uploadPhoto')
                        : t('onboarding.upload')
              }
              onPress={() => (uploadFailed && onRetryUpload ? onRetryUpload(item) : onUpload(item))}
            />
          ) : null}
        </View>
      )}
    </>
  )

  if (allowPreview && onPreview && !primaryAction && !uploading) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t('onboarding.preview')}
        onPress={() => onPreview(item)}
      >
        <PastelCard tone={tone} style={styles.taskCard}>
          {cardBody}
        </PastelCard>
      </Pressable>
    )
  }

  return (
    <PastelCard tone={tone} style={styles.taskCard}>
      {cardBody}
    </PastelCard>
  )
}

function CompletedChecklist() {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <PastelCard tone="sage" style={styles.completeCard}>
      <EditorialHeading size="medium">{t('onboarding.completeTitle')}</EditorialHeading>
      <Text style={[styles.taskDescription, align]}>{t('onboarding.completeMessage')}</Text>
    </PastelCard>
  )
}

export function OnboardingLoadingView() {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.content}>
        <Wordmark compact align="center" />
        <ContentSkeleton />
      </View>
    </SafeAreaView>
  )
}

export function OnboardingErrorView({ onRetry }: { onRetry: () => void }) {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
      <View style={[styles.content, styles.errorWrap]}>
        <Text style={[styles.taskTitle, align]}>{t('common.error')}</Text>
        <Text style={[styles.stateMessage, align]}>{t('error.generic')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      </View>
    </SafeAreaView>
  )
}

function itemKey(item: OnboardingItem, index: number): string {
  return item.item_id || item.document_type || item.label || `onboarding-${index}`
}

function onboardingItemLabel(item: OnboardingItem, t: (key: string) => string): string {
  const key = item.item_id || item.document_type || ''
  const known = new Set([
    'personal_photo',
    'civil_id',
    'bank_details',
    'passport',
    'employment_contract',
    'offer_letter',
    'residence',
    'work_permit',
    'education_cert',
  ])
  if (known.has(key)) return t(`onboarding.item.${key}`)
  return item.label || t('onboarding.item.other')
}

function onboardingItemDescription(item: OnboardingItem, t: (key: string) => string): string {
  const key = item.item_id || item.document_type || ''
  if (key === 'personal_photo') return t('onboarding.itemDescription.personal_photo')
  return t('onboarding.item.genericDescription')
}

function versionReviewLabel(status: string | null | undefined, t: (key: string) => string): string {
  switch ((status || '').toLowerCase()) {
    case 'pending_hr_review':
      return t('status.processing')
    case 'hr_reviewed':
      return t('status.accepted')
    case 'rejected_reupload':
      return t('status.replacement_required')
    case 'superseded':
      return t('status.reviewed')
    default:
      return onboardingStatusLabel(status, t)
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1 },
  content: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxl,
    gap: spacing.lg,
  },
  nav: { minHeight: 44, flexDirection: 'row', alignItems: 'center' },
  rowReverse: { flexDirection: 'row-reverse' },
  backButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navSpacer: { width: 44 },
  hero: { gap: spacing.sm },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  progressCard: { gap: spacing.md },
  progressHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressCopy: { flex: 1, gap: 4 },
  progressLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressValue: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  progressBubble: {
    minWidth: 54,
    height: 54,
    borderRadius: radius.pill,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  progressPercent: { color: colors.ink, fontWeight: '800', fontSize: font.small },
  section: { gap: spacing.md },
  sectionTitle: { color: colors.text, fontSize: font.small, fontWeight: '800', letterSpacing: 0.2 },
  taskCard: { gap: spacing.md },
  taskTop: { flexDirection: 'row', gap: spacing.md },
  flex: { flex: 1 },
  requirementRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: 8, flexWrap: 'wrap' },
  requirementPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  optionalPill: { backgroundColor: colors.border },
  requirementText: { color: colors.surface, fontSize: font.tiny, fontWeight: '700' },
  optionalText: { color: colors.text },
  taskTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700', marginBottom: 4 },
  taskDescription: { color: colors.subtle, fontSize: font.small, lineHeight: 18 },
  dueDate: { color: colors.text, fontSize: font.tiny, marginTop: 6, fontWeight: '600' },
  rejectionReason: {
    marginTop: 8,
    color: colors.danger,
    fontSize: font.small,
    lineHeight: 18,
    fontWeight: '600',
  },
  guidance: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 8 },
  guidanceReview: { color: colors.text },
  guidanceReject: { color: colors.danger },
  versionList: { marginTop: 10, gap: 4 },
  versionTitle: { color: colors.text, fontSize: font.tiny, fontWeight: '700' },
  versionMeta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  taskArt: { width: 56, alignItems: 'center', justifyContent: 'center' },
  plusBadge: {
    position: 'absolute',
    right: -2,
    bottom: 4,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  transfer: { gap: spacing.sm },
  transferHead: { flexDirection: 'row', justifyContent: 'space-between' },
  transferText: { color: colors.text, fontSize: font.tiny, fontWeight: '700' },
  cancelTransfer: { minHeight: 40, alignItems: 'center', justifyContent: 'center' },
  cancelTransferText: { color: colors.text, fontWeight: '700', textDecorationLine: 'underline' },
  actionRow: { gap: spacing.sm },
  reviewedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  reviewedIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.successSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reviewedTitle: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  reviewedStatus: { color: colors.subtle, fontSize: font.tiny, marginTop: 2 },
  completeCard: { gap: spacing.sm },
  securityCard: {},
  securityRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  securityTitle: { color: colors.text, fontSize: font.small, fontWeight: '700', marginBottom: 4 },
  securityText: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  errorWrap: { flex: 1, justifyContent: 'center', gap: spacing.md },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})
