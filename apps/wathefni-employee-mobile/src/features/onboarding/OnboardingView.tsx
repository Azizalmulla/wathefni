import { useState, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
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
import { PageBackButton, SectionHeader } from '@/components/lists'
import { formatDate, formatNumber } from '@/lib/format'
import {
  colors,
  font,
  layout,
  radius,
  scheduleComposition,
  shadows,
  spacing,
  typeScaling,
} from '@/theme'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'
import {
  completionNextActionMessage,
  completionStateLabel,
  onboardingStatusLabel,
  projectOnboardingLifecycle,
  type OnboardingLifecycleProjection,
} from '@/features/onboarding/lifecycleProjection'
import { OnboardingLifeMark } from '@/features/onboarding/onboardingLifeMarks'

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

/** Soft powder blue — progress / review / calm company work. Not PastelCard pink. */
const SOFT_BLUE = scheduleComposition.planned.fill

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
          <View style={styles.nav}>
            <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
            <Wordmark compact align="center" />
            <View style={styles.navSpacer} />
          </View>
          <Text style={[styles.taskTitle, readingEdgeAlign(isRTL)]}>
            {t('onboarding.contractErrorTitle')}
          </Text>
          <Text style={[styles.stateMessage, readingEdgeAlign(isRTL)]}>
            {t('onboarding.contractErrorMessage')}
          </Text>
          {onRefresh ? <PremiumButton label={t('common.retry')} onPress={onRefresh} /> : null}
        </View>
      </SafeAreaView>
    )
  }

  return (
    <LifecycleChecklistView
      projection={projection}
      uploadingId={uploadingId}
      canUploadDocuments={canUploadDocuments}
      uploadProgress={uploadProgress}
      failedUploadId={failedUploadId}
      openingId={openingId}
      versionsByItem={versionsByItem}
      versionsLoadingId={versionsLoadingId}
      refreshing={refreshing}
      onRefresh={onRefresh}
      onUpload={onUpload}
      onPreview={onPreview}
      onViewVersions={onViewVersions}
      onCancelUpload={onCancelUpload}
      onRetryUpload={onRetryUpload}
      onOpenBank={onOpenBank}
      onBack={onBack}
    />
  )
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
  const align = readingEdgeAlign(isRTL)
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
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('onboarding.checklistTitle')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('onboarding.checklistSubtitle')}</Text>
        </FadeIn>

        {/*
          One progress hierarchy — soft blue card so pink stays reserved for
          needs-correction, not journey chrome.
        */}
        <SoftBlueCard style={styles.progressCard}>
          <View style={styles.progressHead}>
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
            <Text style={[styles.nextAction, align]}>{completionMessage}</Text>
          ) : null}
        </SoftBlueCard>

        {!hasAny || (!yourActions.length && !beingReviewed.length && !handledByOthers.length && completed.length) ? (
          yourActions.length || beingReviewed.length || handledByOthers.length ? null : <CompletedChecklist />
        ) : null}

        {yourActions.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('onboarding.yourActions')} />
            <View style={styles.cardStack}>
              {yourActions.map((item, index) => (
                <ActionItemCard
                  key={itemKey(item, index)}
                  item={item}
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
            </View>
          </View>
        ) : null}

        {beingReviewed.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('onboarding.beingReviewed')} />
            <View style={styles.cardStack}>
              {beingReviewed.map((item, index) => (
                <QuietItemCard
                  key={itemKey(item, index)}
                  item={item}
                  opening={openingId === item.item_id}
                  onPreview={onPreview}
                  density="review"
                />
              ))}
            </View>
          </View>
        ) : null}

        {handledByOthers.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('onboarding.handledByOthers')} count={handledByOthers.length} />
            <Text style={[styles.handledNote, align]}>{t('onboarding.handledByOthersNote')}</Text>
            <View style={styles.cardStack}>
              {handledByOthers.map((item, index) => (
                <QuietItemCard
                  key={itemKey(item, index)}
                  item={item}
                  density="handled"
                  accessibilityLabel={`${onboardingItemLabel(item, t)}. ${t('onboarding.handledByOthers')}`}
                />
              ))}
            </View>
          </View>
        ) : null}

        {completed.length ? <CompletedSection items={completed} /> : null}

        <View style={styles.securityRow}>
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
    <View style={styles.section}>
      <SectionHeader
        title={t('onboarding.completedSection')}
        count={items.length}
        collapsible
        expanded={open}
        onToggle={() => setOpen((value) => !value)}
      />
      {open ? (
        <View style={styles.cardStack}>
          {items.map((item, index) => (
            <QuietItemCard key={itemKey(item, index)} item={item} density="completed" />
          ))}
        </View>
      ) : null}
    </View>
  )
}

/**
 * Your-action card — warm yellow for ordinary work, pink only for
 * needs-correction / replacement. Primary CTA strong; Preview/History quiet.
 */
function ActionItemCard({
  item,
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
  const allowPreview = Boolean(item.file_id) && (actions.size ? actions.has('preview') : true)
  const allowVersions =
    Boolean(onViewVersions) && Boolean(item.file_id) && (actions.size ? actions.has('view_versions') : true)
  const align = readingEdgeAlign(isRTL)
  const photo = (item.item_id || item.document_type) === 'personal_photo'
  const normalizedStatus = (item.status || 'pending').toLowerCase()
  const awaitingReview = ['submitted', 'processing', 'received'].includes(normalizedStatus)
  const isAccepted = normalizedStatus === 'accepted' || normalizedStatus === 'waived'
  const canOpenBank = isBank && Boolean(onOpenBank) && !isAccepted && actions.has('open_bank')
  const needsReplacement = ['replacement_required', 'rejected'].includes(normalizedStatus)
  const cardTone: PastelTone = needsReplacement ? 'pink' : 'butter'
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

  const body = (
    <>
      <View style={styles.titleRow}>
        <Text
          maxFontSizeMultiplier={typeScaling.body}
          numberOfLines={2}
          style={[styles.actionTitle, styles.flex, align]}
        >
          {title}
        </Text>
        <OnboardingLifeMark
          label={onboardingStatusLabel(item.status, t)}
          status={item.status}
          emphasis={needsReplacement ? 'strong' : 'quiet'}
        />
      </View>
      <View style={styles.metaRow}>
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.metaRequired, align]}>
          {item.required === false ? t('onboarding.optional') : t('onboarding.required')}
        </Text>
        {dueLabel ? (
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.meta, align]}>
            {dueLabel}
          </Text>
        ) : null}
      </View>
      {description ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={2} style={[styles.meta, align]}>
          {description}
        </Text>
      ) : null}
      {needsReplacement && item.rejection_reason ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.rejectionReason, align]}>
          {item.rejection_reason}
        </Text>
      ) : (
        <Text
          maxFontSizeMultiplier={typeScaling.chip}
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
              canUpload && (actions.has(`upload_${side}`) || actions.has(`replace_${side}`))
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
                  <View style={styles.actionCluster}>
                    {canSidePreview && onPreview ? (
                      <QuietTextAction
                        label={
                          opening
                            ? t('common.loading')
                            : side === 'front'
                              ? t('onboarding.civilId.previewFront')
                              : t('onboarding.civilId.previewBack')
                        }
                        onPress={() => onPreview(item, side)}
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
                          sideFailed && onRetryUpload ? onRetryUpload(item, side) : onUpload(item, side)
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
        <Text style={[styles.versionMeta, align]}>{t('onboarding.versionEmpty')}</Text>
      ) : null}
      {!dualParts && uploading ? (
        <View style={styles.transfer}>
          <View style={styles.transferHead}>
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
        <View style={styles.actionCluster}>
          {allowPreview && onPreview ? (
            <QuietTextAction
              label={opening ? t('common.loading') : t('onboarding.preview')}
              onPress={() => onPreview(item)}
            />
          ) : null}
          {allowVersions && !versions?.length ? (
            <QuietTextAction
              label={versionsLoading ? t('common.loading') : t('onboarding.versionHistory')}
              onPress={() => onViewVersions?.(item)}
              disabled={Boolean(versionsLoading)}
            />
          ) : null}
          {canOpenBank ? (
            <PremiumButton label={t('onboarding.openBankForm')} onPress={() => onOpenBank?.()} showDirection />
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
        <View style={styles.actionCluster}>
          <QuietTextAction
            label={versionsLoading ? t('common.loading') : t('onboarding.versionHistory')}
            onPress={() => onViewVersions?.(item)}
            disabled={Boolean(versionsLoading)}
          />
        </View>
      ) : null}
    </>
  )

  const shell = (child: ReactNode) => (
    <PastelCard tone={cardTone} style={styles.taskCard}>
      {child}
    </PastelCard>
  )

  if (allowPreview && onPreview && !primaryAction && !uploading && !dualParts && !canOpenBank) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t('onboarding.preview')}
        onPress={() => onPreview(item)}
        style={({ pressed }) => (pressed ? styles.pressed : null)}
      >
        {shell(body)}
      </Pressable>
    )
  }

  return shell(body)
}

/** Quieter cards: soft blue (review/handled) or cream+green mark (completed). */
function QuietItemCard({
  item,
  opening,
  onPreview,
  density,
  accessibilityLabel,
}: {
  item: OnboardingItem
  opening?: boolean
  onPreview?: (item: OnboardingItem, part?: 'front' | 'back') => void
  density: 'review' | 'handled' | 'completed'
  accessibilityLabel?: string
}) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const title = onboardingItemLabel(item, t)
  const status = onboardingStatusLabel(item.status, t)
  const actions = new Set(item.actions || [])
  const allowPreview =
    density === 'review' && Boolean(item.file_id) && (actions.size ? actions.has('preview') : true) && Boolean(onPreview)
  const titleStyle =
    density === 'completed' ? styles.completedTitle : density === 'handled' ? styles.handledTitle : styles.reviewTitle

  const body = (
    <View style={styles.quietCardBody}>
      <View style={styles.titleRow}>
        <Text
          maxFontSizeMultiplier={typeScaling.body}
          numberOfLines={2}
          style={[titleStyle, styles.flex, align]}
        >
          {title}
        </Text>
        <OnboardingLifeMark label={status} status={item.status} emphasis="quiet" />
        {allowPreview ? <Ionicons name="chevron-forward" size={16} color={colors.navMuted} /> : null}
      </View>
      {density === 'review' && opening ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.meta, align]}>
          {t('common.loading')}
        </Text>
      ) : null}
    </View>
  )

  const card =
    density === 'completed' ? (
      <View accessibilityLabel={accessibilityLabel || `${title}. ${status}`}>
        <PastelCard tone="cream" style={styles.quietCard}>
          {body}
        </PastelCard>
      </View>
    ) : (
      <SoftBlueCard
        style={density === 'handled' ? styles.quietCardHandled : styles.quietCard}
        accessibilityLabel={accessibilityLabel || `${title}. ${status}`}
      >
        {body}
      </SoftBlueCard>
    )

  if (allowPreview && onPreview) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${title}. ${t('onboarding.preview')}`}
        onPress={() => onPreview(item)}
        style={({ pressed }) => (pressed ? styles.pressed : null)}
      >
        {card}
      </Pressable>
    )
  }
  return card
}

/** Soft powder-blue surface matching PastelCard geometry (progress / review / handled). */
function SoftBlueCard({
  children,
  style,
  accessibilityLabel,
}: {
  children: ReactNode
  style?: object
  accessibilityLabel?: string
}) {
  return (
    <View
      accessibilityLabel={accessibilityLabel}
      style={[styles.softBlueCard, style, { backgroundColor: SOFT_BLUE }]}
    >
      {children}
    </View>
  )
}

/** Inline secondary control — never a second giant black button. */
function QuietTextAction({
  label,
  onPress,
  disabled = false,
}: {
  label: string
  onPress: () => void
  disabled?: boolean
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.textAction, pressed && styles.pressed, disabled && styles.textActionDisabled]}
    >
      <Text maxFontSizeMultiplier={typeScaling.body} style={styles.textActionLabel}>
        {label}
      </Text>
    </Pressable>
  )
}

function CompletedChecklist() {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <PastelCard tone="olive" style={styles.completeCard}>
      <EditorialHeading size="medium">{t('onboarding.completeTitle')}</EditorialHeading>
      <Text style={[styles.meta, align]}>{t('onboarding.completeMessage')}</Text>
    </PastelCard>
  )
}

export function OnboardingLoadingView({ onBack }: { onBack?: () => void }) {
  const { t } = useI18n()
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.content}>
        {onBack ? (
          <View style={styles.pushedNav}>
            <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
            <Wordmark compact align="center" />
            <View style={styles.navSpacer} />
          </View>
        ) : (
          <Wordmark compact align="center" />
        )}
        <ContentSkeleton />
      </View>
    </SafeAreaView>
  )
}

export function OnboardingErrorView({ onRetry, onBack }: { onRetry: () => void; onBack?: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
      <View style={[styles.content, styles.errorWrap]}>
        {onBack ? (
          <View style={styles.pushedNav}>
            <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
            <Wordmark compact align="center" />
            <View style={styles.navSpacer} />
          </View>
        ) : null}
        <Text style={[styles.taskTitle, align]}>{t('common.error')}</Text>
        <Text style={[styles.stateMessage, align]}>{t('error.generic')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
        {onBack ? <PremiumButton label={t('common.back')} onPress={onBack} tone="secondary" /> : null}
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
  content: {
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    paddingBottom: layout.scrollBottom,
    gap: layout.sectionGap,
  },
  nav: { minHeight: layout.touchTarget, flexDirection: 'row', alignItems: 'center' },
  pushedNav: {
    minHeight: layout.touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  navSpacer: { width: 44 },
  hero: { gap: spacing.sm },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  progressCard: { gap: spacing.md },
  progressHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  progressCopy: { flex: 1, gap: 4 },
  progressLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressValue: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  nextAction: { color: colors.subtle, fontSize: font.small, lineHeight: 18 },
  section: { gap: spacing.sm },
  cardStack: { gap: spacing.md },
  taskCard: { gap: spacing.sm },
  softBlueCard: {
    borderRadius: radius.xl,
    padding: spacing.lg,
    overflow: 'hidden',
    ...shadows.card,
  },
  quietCard: { paddingVertical: spacing.md },
  quietCardHandled: { paddingVertical: spacing.md, opacity: 0.92 },
  quietCardBody: { gap: 2 },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: 2 },
  actionTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', lineHeight: 20 },
  reviewTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700', lineHeight: 19 },
  handledTitle: { color: colors.subtle, fontSize: font.small, fontWeight: '700', lineHeight: 18 },
  completedTitle: { color: colors.subtle, fontSize: font.small, fontWeight: '600', lineHeight: 18 },
  meta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  metaRequired: { color: colors.ink, fontSize: font.tiny, lineHeight: 16, fontWeight: '700' },
  handledNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginBottom: 2 },
  flex: { flex: 1 },
  taskTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700', marginBottom: 4 },
  completeCard: { gap: spacing.sm },
  rejectionReason: {
    marginTop: 4,
    color: colors.danger,
    fontSize: font.tiny,
    lineHeight: 16,
    fontWeight: '600',
  },
  guidance: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 2 },
  guidanceReview: { color: colors.text },
  guidanceReject: { color: colors.danger },
  versionList: { marginTop: 8, gap: 4 },
  versionTitle: { color: colors.text, fontSize: font.tiny, fontWeight: '700' },
  versionMeta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  transfer: { gap: spacing.sm, marginTop: spacing.sm },
  transferHead: { flexDirection: 'row', justifyContent: 'space-between' },
  transferText: { color: colors.text, fontSize: font.tiny, fontWeight: '700' },
  cancelTransfer: { minHeight: 40, alignItems: 'center', justifyContent: 'center' },
  cancelTransferText: { color: colors.text, fontWeight: '700', textDecorationLine: 'underline' },
  actionCluster: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  textAction: {
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    paddingVertical: spacing.xs,
  },
  textActionDisabled: { opacity: 0.45 },
  textActionLabel: {
    color: colors.ink,
    fontSize: font.small,
    fontWeight: '700',
    textDecorationLine: 'underline',
  },
  dualParts: { gap: spacing.sm, marginTop: spacing.sm },
  partSlot: {
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  partTitle: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  partHint: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  securityRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  securityText: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  errorWrap: { flex: 1, justifyContent: 'center', gap: spacing.md },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  pressed: { opacity: 0.85 },
})
