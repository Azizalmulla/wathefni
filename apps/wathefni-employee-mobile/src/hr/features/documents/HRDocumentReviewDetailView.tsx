import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { openAuthenticatedFile } from '@hr/api/files'
import { mobileApi } from '@hr/api/mobile'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import {
  buildDocumentsDemoQueue,
  docStatusLabelKey,
  docStatusTone,
  documentAttentionBodyKey,
  documentNeedsAttention,
} from '@hr/features/documents/documentsComposition'
import {
  documentsDemoEnabled,
  isDocumentsDemoEmployee,
} from '@hr/features/documents/documentsDemoGate'
import {
  ConfirmationSheet,
  type ConfirmationView,
} from '@hr/components/primitives'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDate, formatDateTime } from '@/lib/format'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

/** Unboxed fact — typography only (static metadata, not action rows). */
function Fact({ label, value }: { label: string; value?: string | null }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  if (!value) return null
  return (
    <View style={styles.fact}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.factLabel, align]}>
        {label}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.factValue, align]}>
        {value}
      </Text>
    </View>
  )
}

/**
 * Document review detail — Editorial Entity Detail (visual migration).
 * Contract unchanged: preview/download, client confirm + expected_status, no Send Reminder.
 */
export function HRDocumentReviewDetailView() {
  const { employeeKey = '', documentType = '' } = useLocalSearchParams<{
    employeeKey: string
    documentType: string
  }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = hasCapability(me, 'hr', 'document_review')
  const demo = documentsDemoEnabled() || isDocumentsDemoEmployee(employeeKey)
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)

  const live = useQuery({
    queryKey: ['document', employeeKey, documentType],
    queryFn: ({ signal }) =>
      mobileApi.documentDetail(request, employeeKey, documentType, signal),
    enabled: permitted && Boolean(employeeKey && documentType) && !demo,
  })

  const demoItem = demo
    ? buildDocumentsDemoQueue().compliance.find(
        (row) =>
          row.employee?.employee_key === employeeKey && row.document_type === documentType,
      )
    : null

  const item = demoItem || live.data?.item
  const review = useMutation({
    mutationFn: () =>
      mobileApi.documentReview(request, employeeKey, documentType, {
        expected_status: item?.status || 'needs_review',
      }),
    onSuccess: async () => {
      setConfirmation(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['document', employeeKey, documentType] }),
        client.invalidateQueries({ queryKey: ['documents'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
      ])
    },
  })

  const canReview =
    !demo && item?.allowed_actions.includes('review') === true && item.status === 'needs_review'

  const openFile = (download: boolean) => {
    if (demo) {
      Alert.alert(t('hrDocuments.demoPreviewTitle'), t('hrDocuments.demoPreviewBody'))
      return
    }
    const path = download ? item?.download_path : item?.preview_path
    if (!path) return
    void openAuthenticatedFile({
      request,
      path,
      filename: item?.name,
      download,
    }).catch(() => undefined)
  }

  const confidencePct =
    typeof item?.extraction_confidence === 'number'
      ? Math.round(item.extraction_confidence * 100)
      : null

  const employeeLine = item?.employee?.name
    ? [item.employee.name, item.employee.position_title, item.employee.department]
        .filter(Boolean)
        .join(' · ')
    : null

  const expiryLead = item?.expiry_date
    ? typeof item.days_until_expiry === 'number'
      ? `${formatDate(item.expiry_date, locale)} · ${t('hrDocuments.daysUntil', {
          count: item.days_until_expiry,
        })}`
      : formatDate(item.expiry_date, locale)
    : null

  const showAttention = item ? documentNeedsAttention(item) : false
  const hasRecord = Boolean(item?.last_checked_at || item?.last_reminded_at || confidencePct != null)

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: ambient.documents.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrDocuments.detailEyebrow')}
            </Text>
          </View>
          <EditorialHeading>{item?.name || t('hrDocuments.detailTitle')}</EditorialHeading>
          {item?.status ? (
            <StatusChip label={t(docStatusLabelKey(item.status))} tone={docStatusTone(item.status)} />
          ) : null}
          {employeeLine ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.identity, align]}>
              {employeeLine}
            </Text>
          ) : null}
          {expiryLead ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lead, align]}>
              {expiryLead}
            </Text>
          ) : null}
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrDocuments.demoDetailNote')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted && !demo ? (
          <ListRow
            title={t('hrDocuments.permissionTitle')}
            subtitle={t('hrDocuments.permissionBody')}
          />
        ) : null}

        {permitted && !demo && live.isLoading && !item ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {permitted && !demo && (live.error || review.error) && !item ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            emphasis="warning"
            showChevron
            onPress={() => void live.refetch()}
          />
        ) : null}

        {(permitted || demo) && item ? (
          <>
            {showAttention ? (
              <View style={styles.attention}>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.attentionLabel, align]}>
                  {t('hrDocuments.attentionTitle')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.attentionBody, align]}>
                  {t(documentAttentionBodyKey(item), {
                    count: typeof item.days_until_expiry === 'number' ? item.days_until_expiry : 0,
                  })}
                </Text>
              </View>
            ) : null}

            {hasRecord ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrDocuments.sectionRecord')} />
                <Fact
                  label={t('hrDocuments.lastChecked')}
                  value={item.last_checked_at ? formatDateTime(item.last_checked_at, locale) : null}
                />
                <Fact
                  label={t('hrDocuments.lastReminded')}
                  value={item.last_reminded_at ? formatDateTime(item.last_reminded_at, locale) : null}
                />
                <Fact
                  label={t('hrDocuments.confidence')}
                  value={
                    confidencePct != null
                      ? t('hrDocuments.confidenceValue', { percent: confidencePct })
                      : null
                  }
                />
              </View>
            ) : null}

            <View style={styles.group}>
              <SectionHeader title={t('hrDocuments.sectionFile')} />
              {item.preview_path || item.has_file ? (
                <ListRow
                  title={t('hrDocuments.openPreview')}
                  subtitle={t('hrDocuments.openPreviewSub')}
                  icon="eye-outline"
                  iconTint={ambient.documents.fill}
                  showChevron
                  onPress={() => openFile(false)}
                  style={styles.actionRow}
                />
              ) : (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                  {t('hrDocuments.noFile')}
                </Text>
              )}
              {item.download_path ? (
                <ListRow
                  title={t('hrDocuments.download')}
                  subtitle={item.name}
                  icon="download-outline"
                  iconTint={ambient.documents.fill}
                  showChevron
                  onPress={() => openFile(true)}
                  style={styles.actionRow}
                />
              ) : null}
            </View>

            {canReview ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrDocuments.sectionDecide')} />
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('hrDocuments.decideHint')}
                </Text>
                <Pressable
                  onPress={() =>
                    setConfirmation({
                      target: `${item.employee?.name || t('hrDocuments.detailTitle')} · ${item.name}`,
                      action: t('hrDocuments.markReviewed'),
                      consequence: t('hrDocuments.reviewConsequence'),
                      currentState: item.status || 'needs_review',
                    })
                  }
                  style={styles.btnPrimary}
                  accessibilityRole="button"
                  accessibilityLabel={t('hrDocuments.markReviewed')}
                >
                  <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnPrimaryText}>
                    {t('hrDocuments.markReviewed')}
                  </Text>
                </Pressable>
              </View>
            ) : null}

            {review.isSuccess ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.success, align]}>
                {t('hrDocuments.reviewSubmitted')}
              </Text>
            ) : null}

            {review.error ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.error, align]}>
                {t('hrDocuments.reviewFailed')}
              </Text>
            ) : null}
          </>
        ) : null}
      </PageScrollView>

      {/* Modal outside ScrollView so Confirm presses are not swallowed on iOS. */}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        loading={review.isPending}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => review.mutate()}
      />
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
  },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  identity: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  lead: {
    color: colors.ink,
    fontSize: font.h3,
    fontWeight: '600',
    lineHeight: 26,
    marginTop: spacing.xs,
    maxWidth: 360,
  },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  group: { gap: spacing.md },
  fact: { gap: 2 },
  factLabel: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  factValue: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  attention: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: ambient.schedule.fill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 6,
  },
  attentionLabel: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  attentionBody: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  actionRow: { backgroundColor: colors.surface },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  btnPrimary: {
    minHeight: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.ink,
  },
  btnPrimaryText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
  success: { color: colors.ink, fontSize: font.small, fontWeight: '600' },
  error: { color: colors.danger, fontSize: font.small },
})
