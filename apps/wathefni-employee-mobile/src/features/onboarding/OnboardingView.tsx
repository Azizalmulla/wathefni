import { useState, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
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
  type PastelTone,
} from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { formatDate, formatNumber, statusTone } from '@/lib/format'
import { colors, font, layout, radius, spacing } from '@/theme'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'
import {
  completionNextActionMessage,
  completionStateLabel,
  onboardingStatusLabel,
  projectOnboardingLifecycle,
  type OnboardingLifecycleProjection,
} from '@/features/onboarding/lifecycleProjection'

type OnboardingViewProps = {
  data: OnboardingResponse
  canUploadDocuments: boolean
  uploadingId: string | null
  uploadProgress?: number
  failedUploadId?: string | null
  openingId?: string | null
  versionsByItem?: Record<string, VersionRow[]>
  versionsLoadingId?: string | null
  refreshing?: boolean
  onRefresh?: () => void
  onUpload: (item: OnboardingItem, part?: 'front' | 'back') => void
  onPreview?: (item: OnboardingItem, part?: 'front' | 'back') => void
  onViewVersions?: (item: OnboardingItem) => void
  onCancelUpload?: () => void
  onRetryUpload?: (item: OnboardingItem, part?: 'front' | 'back') => void
  /** Opens the bank ESS screen; bank values are never entered on the checklist. */
  onOpenBank?: () => void
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
  canUploadDocuments,
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
  onOpenBank,
  onBack,
}: OnboardingViewProps) {
  const { t, isRTL } = useI18n()
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
          {/* The contract version and machine reason still reach telemetry via
              projectOnboardingLifecycle; they are not put in front of the employee. */}
          <Text style={[styles.stateMessage, { textAlign: isRTL ? 'right' : 'left' }]}>
            {t('onboarding.contractErrorMessage')}
          </Text>
          {onRefresh ? <PremiumButton label={t('common.retry')} onPress={onRefresh} /> : null}
        </View>
      </SafeAreaView>
    )
  }

  return <LifecycleChecklistView projection={projection} {...{
    uploadingId,
    canUploadDocuments,
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
    onOpenBank,
    onBack,
  }} />
}

function LifecycleChecklistView({
  projection,
  canUploadDocuments,
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
  onOpenBank,
  onBack,
}: {
  projection: OnboardingLifecycleProjection
} & Omit<OnboardingViewProps, 'data'>) {
  const { t, isRTL, locale } = useI18n()
  const yourActions = projection.yourActions
  const beingReviewed = projection.beingReviewed
  const handledByOthers = projection.handledByOthers
  const completed = projection.completed
  const canUpload = projection.canUpload && canUploadDocuments
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const done = projection.acceptedCount
  const progress = projection.requiredTotal ? done / projection.requiredTotal : 1
  const hasAny = yourActions.length + beingReviewed.length + handledByOthers.length + completed.length > 0
  const completionState = projection.completionState
  const completionMessage = completionNextActionMessage(
    projection.completion,
    completionState,
    locale,
    t,
  )
  // The chip below states the completion state in words with a semantic colour.
  // The card itself keeps the joining flow's ambient identity so a pastel fill is
  // never the thing that tells the employee whether they are blocked.
  const completionChipTone =
    completionState === 'completed'
      ? 'success'
      : completionState === 'blocked'
        ? 'danger'
        : completionState === 'waiting_on_employee' || completionState === 'reopened'
          ? 'warning'
          : 'neutral'

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
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

        {/*
          One progress hierarchy.

          There used to be two stacked cards: the canonical completion state with
          its own chip and next-action sentence, and immediately below it a second
          card restating the same journey as a fraction, a percentage bubble and a
          bar. Both are true and both come from the same authority, so they belong
          in one place — state, count, bar, next action, in that order.
        */}
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
            {completionState ? (
              <StatusChip label={completionStateLabel(completionState, t)} tone={completionChipTone} />
            ) : null}
          </View>
          <MotionProgressBar value={progress} />
          {completionMessage ? (
            <Text style={[styles.taskDescription, align]}>{completionMessage}</Text>
          ) : null}
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
                tone="lilac"
                canUpload={canUpload}
                uploading={uploadingId === item.item_id || Boolean(item.item_id && uploadingId?.startsWith(`${item.item_id}:`))}
                uploadingId={uploadingId}
                uploadProgress={
                  uploadingId === item.item_id || (item.item_id && uploadingId?.startsWith(`${item.item_id}:`))
                    ? uploadProgress
                    : 0
                }
                uploadFailed={failedUploadId === item.item_id || Boolean(item.item_id && failedUploadId?.startsWith(`${item.item_id}:`))}
                failedUploadId={failedUploadId}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
                onOpenBank={onOpenBank}
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
                tone="cream"
                canUpload={canUpload}
                uploading={false}
                uploadingId={null}
                uploadProgress={0}
                uploadFailed={false}
                failedUploadId={null}
                opening={openingId === item.item_id}
                versions={item.item_id ? versionsByItem[item.item_id] : undefined}
                versionsLoading={Boolean(item.item_id && versionsLoadingId === item.item_id)}
                onUpload={onUpload}
                onPreview={onPreview}
                onViewVersions={onViewVersions}
                onOpenBank={onOpenBank}
              />
            ))}
          </Section>
        ) : null}

        {/*
          Work the employee does not own still has to be legible. A bare count
          ("3 items are handled by your team") told them something was outstanding
          without telling them what, so they could not tell whether HR was waiting
          on them. These are named, marked as HR's, and carry no action — which is
          the point.
        */}
        {handledByOthers.length ? (
          <View style={styles.list}>
            <SectionHeader title={t('onboarding.handledByOthers')} count={handledByOthers.length} />
            <Text style={[styles.taskDescription, align]}>{t('onboarding.handledByOthersNote')}</Text>
            {handledByOthers.map((item, index) => (
              <ListRow
                key={itemKey(item, index)}
                title={onboardingItemLabel(item, t)}
                trailing={
                  <StatusChip label={onboardingStatusLabel(item.status, t)} tone={statusTone(item.status)} />
                }
                accessibilityLabel={`${onboardingItemLabel(item, t)}. ${t('onboarding.handledByOthers')}`}
              />
            ))}
          </View>
        ) : null}

        {/* Finished work is a record, not a task list: compact rows, closed. */}
        {completed.length ? (
          <CompletedSection items={completed} />
        ) : null}

        <View style={[styles.securityRow, rowDirection]}>
          <Ionicons name="shield-checkmark-outline" size={16} color={colors.success} />
          <Text style={[styles.securityText, styles.flex, align]}>{t('onboarding.secureMessage')}</Text>
        </View>
      </PageScrollView>
    </PageScreen>
  )
}

function CompletedSection({ items }: { items: OnboardingItem[] }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <View style={styles.list}>
      <SectionHeader
        title={t('onboarding.completedSection')}
        count={items.length}
        collapsible
        expanded={open}
        onToggle={() => setOpen((value) => !value)}
      />
      {open
        ? items.map((item, index) => (
            <ListRow
              key={itemKey(item, index)}
              title={onboardingItemLabel(item, t)}
              trailing={
                <StatusChip label={onboardingStatusLabel(item.status, t)} tone={statusTone(item.status)} />
              }
            />
          ))
        : null}
    </View>
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
  uploadingId,
  uploadProgress,
  uploadFailed,
  failedUploadId,
  opening,
  versions,
  versionsLoading,
  onUpload,
  onPreview,
  onViewVersions,
  onCancelUpload,
  onRetryUpload,
  onOpenBank,
}: {
  item: OnboardingItem
  tone: PastelTone
  canUpload: boolean
  uploading: boolean
  uploadingId?: string | null
  uploadProgress: number
  uploadFailed: boolean
  failedUploadId?: string | null
  opening?: boolean
  versions?: VersionRow[]
  versionsLoading?: boolean
  onUpload: (item: OnboardingItem, part?: 'front' | 'back') => void
  onPreview?: (item: OnboardingItem, part?: 'front' | 'back') => void
  onViewVersions?: (item: OnboardingItem) => void
  onCancelUpload?: () => void
  onRetryUpload?: (item: OnboardingItem, part?: 'front' | 'back') => void
  onOpenBank?: () => void
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
  const dualParts =
    Boolean(item.civil_id_parts) &&
    !item.civil_id_parts?.legacy_single &&
    (actions.has('upload_front') ||
      actions.has('upload_back') ||
      actions.has('replace_front') ||
      actions.has('replace_back') ||
      actions.has('preview_front') ||
      actions.has('preview_back'))
  const allowUpload =
    canUpload &&
    isDocument &&
    Boolean(item.item_id) &&
    (actions.has('upload') || actions.has('replace') || actions.has('resubmit'))
  // Respect the API action list when it is present: offering Preview or History
  // for a file the backend will not serve is a dead end.
  const allowPreview = Boolean(item.file_id) && (actions.size ? actions.has('preview') : true)
  const allowVersions =
    Boolean(onViewVersions) && Boolean(item.file_id) && (actions.size ? actions.has('view_versions') : true)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const photo = (item.item_id || item.document_type) === 'personal_photo'
  const normalizedStatus = (item.status || 'pending').toLowerCase()
  const awaitingReview = ['submitted', 'processing', 'received'].includes(normalizedStatus)
  const isAccepted = normalizedStatus === 'accepted' || normalizedStatus === 'waived'
  // Backend open_bank action is the sole CTA gate — same eligibility as /app/bank.
  const canOpenBank =
    isBank && Boolean(onOpenBank) && !isAccepted && actions.has('open_bank')
  const needsReplacement = ['replacement_required', 'rejected'].includes(normalizedStatus)
  // One line per item, and never a restatement of the status chip. Every review
  // status shares the same sentence: "processing" used to claim we were still
  // preparing the file while the chip already said HR was reviewing it.
  const guidance = dualParts
    ? t('onboarding.civilId.bothRequired')
    : needsReplacement
      ? t('onboarding.rejectionTitle')
      : awaitingReview
        ? t('onboarding.reviewGuidance')
        : isAccepted
          ? t('onboarding.acceptedGuidance')
          : isBank
            ? canOpenBank
              ? t('onboarding.bankGuidance')
              : t('onboarding.bankHandledByHr')
            : allowUpload
              ? t('onboarding.uploadGuidance')
              : t('onboarding.uploadUnavailable')
  const dueLabel = item.due_date ? t('onboarding.dueDate', { date: formatDate(item.due_date, locale) }) : null
  // Resubmit/replace/upload only when API actions say so (no legacy fallback).
  const primaryAction = allowUpload
    ? actions.has('resubmit')
      ? 'resubmit'
      : actions.has('replace')
        ? 'replace'
        : actions.has('upload')
          ? 'upload'
          : null
    : null
  const uploadingFront = uploading && uploadingId?.endsWith(':front')
  const uploadingBack = uploading && uploadingId?.endsWith(':back')
  const failedFront = failedUploadId === `${item.item_id}:front`
  const failedBack = failedUploadId === `${item.item_id}:back`

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
          {dualParts ? (
            <View style={styles.dualParts}>
              {(['front', 'back'] as const).map((side) => {
                const slot = item.civil_id_parts?.[side]
                const present = Boolean(slot?.present || slot?.file_id)
                const canSideUpload =
                  canUpload &&
                  (actions.has(`upload_${side}`) || actions.has(`replace_${side}`))
                const canSidePreview = present && (actions.size ? actions.has(`preview_${side}`) : true)
                const sideUploading = side === 'front' ? uploadingFront : uploadingBack
                const sideFailed = side === 'front' ? failedFront : failedBack
                return (
                  <View key={side} style={styles.partSlot}>
                    <Text style={[styles.partTitle, align]}>
                      {side === 'front' ? t('onboarding.civilId.front') : t('onboarding.civilId.back')}
                    </Text>
                    <Text style={[styles.partHint, align]}>
                      {present
                        ? side === 'front'
                          ? t('onboarding.civilId.frontDone')
                          : t('onboarding.civilId.backDone')
                        : side === 'front'
                          ? t('onboarding.civilId.frontHint')
                          : t('onboarding.civilId.backHint')}
                    </Text>
                    {sideUploading ? (
                      <View style={styles.transfer}>
                        <MotionProgressBar value={uploadProgress} />
                      </View>
                    ) : (
                      <View style={styles.actionRow}>
                        {canSidePreview && onPreview ? (
                          <PremiumButton
                            label={
                              opening
                                ? t('common.loading')
                                : side === 'front'
                                  ? t('onboarding.civilId.previewFront')
                                  : t('onboarding.civilId.previewBack')
                            }
                            onPress={() => onPreview(item, side)}
                            disabled={Boolean(opening)}
                          />
                        ) : null}
                        {canSideUpload ? (
                          <PremiumButton
                            label={
                              sideFailed
                                ? t('common.retry')
                                : present
                                  ? side === 'front'
                                    ? t('onboarding.civilId.replaceFront')
                                    : t('onboarding.civilId.replaceBack')
                                  : side === 'front'
                                    ? t('onboarding.civilId.uploadFront')
                                    : t('onboarding.civilId.uploadBack')
                            }
                            onPress={() =>
                              sideFailed && onRetryUpload
                                ? onRetryUpload(item, side)
                                : onUpload(item, side)
                            }
                          />
                        ) : null}
                      </View>
                    )}
                  </View>
                )
              })}
            </View>
          ) : null}
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
          ) : versions ? (
            // Loaded and empty: say so rather than silently removing the control.
            <Text style={[styles.versionMeta, align]}>{t('onboarding.versionEmpty')}</Text>
          ) : null}
        </View>
        <View style={styles.taskArt}>
          <Ionicons name={photo ? 'person' : 'document-text-outline'} size={38} color={colors.ink} />
          {primaryAction || dualParts ? (
            <View style={styles.plusBadge}>
              <Ionicons name="add" size={16} color={colors.surface} />
            </View>
          ) : null}
        </View>
      </View>
      {!dualParts && uploading ? (
        <View style={styles.transfer}>
          <View style={[styles.transferHead, rowDirection]}>
            <Text style={[styles.transferText, align]}>{t('onboarding.uploading')}</Text>
            <Text style={styles.transferText}>
              {formatNumber(Math.round(uploadProgress * 100), locale, 0)}%
            </Text>
          </View>
          <MotionProgressBar value={uploadProgress} />
          {onCancelUpload ? (
            <Pressable accessibilityRole="button" onPress={onCancelUpload} style={styles.cancelTransfer}>
              <Text style={styles.cancelTransferText}>{t('common.cancel')}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : !dualParts ? (
        <View style={styles.actionRow}>
          {canOpenBank ? (
            <PremiumButton label={t('onboarding.openBankForm')} onPress={() => onOpenBank?.()} showDirection />
          ) : null}
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
      ) : allowVersions && !versions?.length ? (
        <View style={styles.actionRow}>
          <PremiumButton
            label={versionsLoading ? t('common.loading') : t('onboarding.versionHistory')}
            onPress={() => onViewVersions?.(item)}
            disabled={Boolean(versionsLoading)}
          />
        </View>
      ) : null}
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
    <PastelCard tone="pink" style={styles.completeCard}>
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
    'civil_id_dual_side_canary',
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
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    paddingBottom: layout.scrollBottom,
    gap: layout.sectionGap,
  },
  nav: { minHeight: layout.touchTarget, flexDirection: 'row', alignItems: 'center' },
  rowReverse: { flexDirection: 'row-reverse' },
  backButton: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navSpacer: { width: 44 },
  hero: { gap: spacing.sm },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  progressCard: { gap: spacing.md },
  progressHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  list: { gap: spacing.sm },
  progressCopy: { flex: 1, gap: 4 },
  progressLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressValue: { color: colors.text, fontSize: font.body, fontWeight: '700' },
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
  dualParts: { gap: spacing.sm, marginTop: spacing.sm },
  partSlot: {
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  partTitle: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  partHint: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
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
    backgroundColor: colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reviewedTitle: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  reviewedStatus: { color: colors.subtle, fontSize: font.tiny, marginTop: 2 },
  completeCard: { gap: spacing.sm },
  securityRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  securityText: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  errorWrap: { flex: 1, justifyContent: 'center', gap: spacing.md },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})
