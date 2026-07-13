import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Ionicons } from '@expo/vector-icons'

import { useI18n } from '@/i18n'
import { StatusChip } from '@/components/ui'
import {
  EditorialHeading,
  FadeIn,
  MotionProgressBar,
  PastelCard,
  PremiumButton,
  PreviewSkeleton,
  Wordmark,
} from '@/components/premium'
import { formatNumber, statusLabel, statusTone } from '@/lib/format'
import { colors, font, radius, shadows, spacing } from '@/theme'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'

type OnboardingViewProps = {
  data: OnboardingResponse
  uploadingId: string | null
  onUpload: (item: OnboardingItem) => void
  onBack: () => void
}

export function OnboardingView({ data, uploadingId, onUpload, onBack }: OnboardingViewProps) {
  const { t, isRTL, locale } = useI18n()
  const pending = data.pending ?? []
  const received = data.received ?? []
  const canUpload = Boolean(data.can_upload)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const progress = data.required_total ? data.received_count / data.required_total : 1

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
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
                  done: formatNumber(data.received_count, locale, 0),
                  total: formatNumber(data.required_total, locale, 0),
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

        {pending.length ? (
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, align]}>{t('onboarding.pending')}</Text>
            {pending.map((item, index) => (
              <ChecklistCard
                key={itemKey(item, index)}
                item={item}
                tone={(item.status || '').toLowerCase() === 'rejected' ? 'blush' : index % 2 ? 'sky' : 'lilac'}
                canUpload={canUpload}
                uploading={uploadingId === item.item_id}
                onUpload={onUpload}
              />
            ))}
          </View>
        ) : (
          <CompletedChecklist />
        )}

        {received.length ? (
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, align]}>{t('onboarding.received')}</Text>
            {received.map((item, index) => (
              <ReviewedRow key={itemKey(item, index)} item={item} />
            ))}
          </View>
        ) : null}

        <PastelCard tone="butter" style={styles.securityCard}>
          <View style={[styles.securityRow, rowDirection]}>
            <View style={styles.securityIcon}>
              <Ionicons name="shield-checkmark-outline" size={21} color={colors.warning} />
            </View>
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

export function OnboardingLoadingView() {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.stateContent}>
        <Wordmark compact />
        <EditorialHeading>{t('onboarding.checklistTitle')}</EditorialHeading>
        <PastelCard tone="lilac" style={styles.loadingCard}>
          <PreviewSkeleton rows={3} />
        </PastelCard>
        <Text style={[styles.stateMessage, align]}>{t('common.loading')}</Text>
      </View>
    </SafeAreaView>
  )
}

export function OnboardingErrorView({ onRetry }: { onRetry: () => void }) {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.stateContent}>
        <Wordmark compact />
        <PastelCard tone="blush" style={styles.errorCard}>
          <Ionicons name="cloud-offline-outline" size={34} color={colors.danger} />
          <EditorialHeading size="medium">{t('common.error')}</EditorialHeading>
          <Text style={[styles.stateMessage, align]}>{t('error.generic')}</Text>
          <PremiumButton label={t('common.retry')} onPress={onRetry} />
        </PastelCard>
      </View>
    </SafeAreaView>
  )
}

function ChecklistCard({
  item,
  tone,
  canUpload,
  uploading,
  onUpload,
}: {
  item: OnboardingItem
  tone: 'lilac' | 'sky' | 'blush'
  canUpload: boolean
  uploading: boolean
  onUpload: (item: OnboardingItem) => void
}) {
  const { t, isRTL } = useI18n()
  const title = onboardingItemLabel(item, t)
  const description = onboardingItemDescription(item, t)
  const isDocument = (item.item_type || '').toLowerCase() === 'document' || Boolean(item.document_type)
  const allowUpload = canUpload && isDocument && Boolean(item.item_id)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const photo = (item.item_id || item.document_type) === 'personal_photo'
  const normalizedStatus = (item.status || 'pending').toLowerCase()
  const rejected = normalizedStatus === 'rejected'
  const awaitingReview = Boolean(item.file_id) && !rejected && !['completed', 'approved', 'reviewed'].includes(normalizedStatus)
  const guidance = rejected
    ? t('onboarding.rejectedGuidance')
    : awaitingReview
      ? t('onboarding.reviewGuidance')
      : allowUpload
        ? t('onboarding.uploadGuidance')
        : t('onboarding.uploadUnavailable')

  return (
    <PastelCard tone={tone} style={styles.taskCard}>
      <View style={[styles.taskTop, rowDirection]}>
        <View style={styles.flex}>
          <View style={[styles.requirementRow, rowDirection]}>
            <View style={[styles.requirementPill, item.required === false && styles.optionalPill]}>
              <Text style={[styles.requirementText, item.required === false && styles.optionalText]}>
                {item.required === false ? t('onboarding.optional') : t('onboarding.required')}
              </Text>
            </View>
            <StatusChip label={statusLabel(item.status || 'pending', t)} tone={statusTone(item.status)} />
          </View>
          <Text style={[styles.taskTitle, align]}>{title}</Text>
          <Text style={[styles.taskDescription, align]}>{description}</Text>
          <Text
            style={[
              styles.guidance,
              rejected && styles.guidanceRejected,
              awaitingReview && styles.guidanceReview,
              align,
            ]}
          >
            {guidance}
          </Text>
        </View>
        <View style={styles.taskArt}>
          <Ionicons name={photo ? 'person' : 'document-text-outline'} size={38} color={colors.ink} />
          {allowUpload ? (
            <View style={styles.plusBadge}>
              <Ionicons name="add" size={16} color={colors.surface} />
            </View>
          ) : null}
        </View>
      </View>
      {allowUpload && !awaitingReview ? (
        <PremiumButton
          label={item.file_id || rejected ? t('onboarding.replace') : photo ? t('onboarding.uploadPhoto') : t('onboarding.upload')}
          busy={uploading}
          onPress={() => onUpload(item)}
        />
      ) : null}
    </PastelCard>
  )
}

function ReviewedRow({ item }: { item: OnboardingItem }) {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <View style={[styles.reviewedRow, isRTL && styles.rowReverse]}>
      <View style={styles.reviewedIcon}>
        <Ionicons name="checkmark" size={19} color={colors.success} />
      </View>
      <View style={styles.flex}>
        <Text style={[styles.reviewedTitle, align]}>{onboardingItemLabel(item, t)}</Text>
        <Text style={[styles.reviewedStatus, align]}>{statusLabel(item.status || 'received', t)}</Text>
      </View>
    </View>
  )
}

function CompletedChecklist() {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <PastelCard tone="sage" style={styles.completedCard}>
      <View style={styles.completedIcon}>
        <Ionicons name="checkmark" size={30} color={colors.surface} />
      </View>
      <EditorialHeading size="medium">{t('onboarding.completeTitle')}</EditorialHeading>
      <Text style={[styles.taskDescription, align]}>{t('onboarding.completeMessage')}</Text>
    </PastelCard>
  )
}

function itemKey(item: OnboardingItem, index: number): string {
  return item.item_id || item.document_type || item.label || `onboarding-${index}`
}

function onboardingItemLabel(item: OnboardingItem, t: (key: string) => string): string {
  const key = item.item_id || item.document_type || ''
  const known = new Set(['personal_photo', 'civil_id', 'bank_details', 'passport', 'employment_contract'])
  if (known.has(key)) return t(`onboarding.item.${key}`)
  return item.label || t('onboarding.item.other')
}

function onboardingItemDescription(item: OnboardingItem, t: (key: string) => string): string {
  const key = item.item_id || item.document_type || ''
  if (key === 'personal_photo') return t('onboarding.itemDescription.personal_photo')
  return t('onboarding.item.genericDescription')
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.xl },
  rowReverse: { flexDirection: 'row-reverse' },
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 52 },
  backButton: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  navSpacer: { width: 44 },
  hero: { gap: spacing.sm },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22, maxWidth: 330 },
  progressCard: { gap: spacing.md },
  progressHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  progressCopy: { flex: 1, gap: 2 },
  progressLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressValue: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  progressBubble: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.68)',
  },
  progressPercent: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  section: { gap: spacing.md },
  sectionTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '800' },
  taskCard: { gap: spacing.lg, padding: spacing.lg },
  taskTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  requirementRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md, flexWrap: 'wrap' },
  requirementPill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  optionalPill: { backgroundColor: 'rgba(255,255,255,0.72)' },
  requirementText: { color: colors.surface, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  optionalText: { color: colors.ink },
  taskTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '800', marginBottom: spacing.xs },
  taskDescription: { color: colors.subtle, fontSize: font.small, lineHeight: 19 },
  guidance: { color: colors.ink, fontSize: font.tiny, lineHeight: 17, marginTop: spacing.sm, fontWeight: '600' },
  guidanceRejected: { color: colors.danger },
  guidanceReview: { color: colors.warning },
  taskArt: {
    width: 88,
    height: 88,
    borderRadius: radius.pill,
    borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.82)',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.32)',
  },
  plusBadge: {
    position: 'absolute',
    right: 0,
    bottom: 3,
    width: 27,
    height: 27,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ink,
  },
  reviewedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  reviewedIcon: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.successSoft,
  },
  reviewedTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  reviewedStatus: { color: colors.success, fontSize: font.tiny, fontWeight: '700', marginTop: 2 },
  securityCard: { padding: spacing.lg },
  securityRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  securityIcon: {
    width: 42,
    height: 42,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.66)',
  },
  securityTitle: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  securityText: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17, marginTop: 2 },
  completedCard: { alignItems: 'center', gap: spacing.md, paddingVertical: spacing.xl },
  completedIcon: {
    width: 58,
    height: 58,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.success,
  },
  flex: { flex: 1 },
  stateContent: { flex: 1, padding: spacing.xl, gap: spacing.xl, backgroundColor: colors.bg },
  loadingCard: { gap: spacing.lg, paddingVertical: spacing.xl },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  errorCard: { gap: spacing.lg, padding: spacing.xl, marginTop: spacing.xl },
})
