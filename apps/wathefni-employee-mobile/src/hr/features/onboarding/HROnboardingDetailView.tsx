import { Alert, Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { openAuthenticatedFile } from '@hr/api/files'
import { mobileApi } from '@hr/api/mobile'
import type { OnboardingChecklistItem } from '@hr/api/types'
import { useServerConfirmation } from '@hr/api/useServerConfirmation'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  buildOnboardingDemoModel,
  itemStatusLabelKey,
  itemStatusTone,
} from '@hr/features/onboarding/onboardingComposition'
import {
  isOnboardingDemoKey,
  onboardingDemoEnabled,
} from '@hr/features/onboarding/onboardingDemoGate'
import { ConfirmationSheet } from '@hr/components/primitives'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

type Outcome = 'accepted' | 'waived'

/**
 * Onboarding detail — Editorial Entity Detail (visual migration).
 * Contract unchanged: Accept/Waive via prepare→confirm, bank handoff, preview before decide.
 */
export function HROnboardingDetailView() {
  const { employeeKey = '' } = useLocalSearchParams<{ employeeKey: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'onboarding')
  const demo = onboardingDemoEnabled() || isOnboardingDemoKey(employeeKey)

  const live = useQuery({
    queryKey: ['onboarding', employeeKey],
    queryFn: ({ signal }) => mobileApi.onboardingDetail(request, employeeKey, signal),
    enabled: permitted && Boolean(employeeKey) && !demo,
  })

  const demoItem = demo
    ? buildOnboardingDemoModel().all.find((row) => row.employee_key === employeeKey)
    : null

  const item = demoItem || live.data?.item
  const confirmation = useServerConfirmation<{ itemId: string; outcome: Outcome }>({
    keyPrefix: 'onboarding-review',
    execute: (input, fields) =>
      mobileApi.onboardingReview(request, employeeKey, {
        item_id: input.itemId,
        outcome: input.outcome,
        ...fields,
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['onboarding', employeeKey] }),
        client.invalidateQueries({ queryKey: ['onboarding'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
        client.invalidateQueries({ queryKey: ['documents'] }),
      ])
    },
  })

  const hrItems = item?.hr_actionable_items || item?.items || []
  const waiting = item?.waiting_on_employee_items || []
  const canMutate = !demo && item?.hr_mutate_enabled === true && item.allowed_actions.includes('review')
  const lead = item
    ? [item.employee.position_title, item.employee.department].filter(Boolean).join(' · ') || null
    : null
  const needsHrLead =
    hrItems.length > 0
      ? t('hrOnboarding.actionableCount', { count: hrItems.length })
      : t('hrOnboarding.emptyHrItems')

  const openPreview = (checklistItem: OnboardingChecklistItem) => {
    if (demo) {
      Alert.alert(t('hrOnboarding.demoPreviewTitle'), t('hrOnboarding.demoPreviewBody'))
      return
    }
    const path = checklistItem.preview_path || checklistItem.download_path
    if (!path) return
    void openAuthenticatedFile({
      request,
      path,
      filename: checklistItem.label,
    }).catch(() => undefined)
  }

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: ambient.onboarding.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrOnboarding.detailEyebrow')}
            </Text>
          </View>
          <EditorialHeading>{item?.employee.name || t('hrOnboarding.detailTitle')}</EditorialHeading>
          {(permitted || demo) && item && hrItems.length > 0 ? (
            <StatusChip label={t('hrOnboarding.statusNeedsHr')} tone="yellow" />
          ) : null}
          {lead ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.identity, align]}>
              {lead}
            </Text>
          ) : null}
          {(permitted || demo) && item ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lead, align]}>
              {needsHrLead}
            </Text>
          ) : null}
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrOnboarding.demoDetailNote')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted && !demo ? (
          <ListRow title={t('hrOnboarding.permissionTitle')} subtitle={t('hrOnboarding.permissionBody')} />
        ) : null}

        {permitted && !demo && live.isLoading && !item ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {permitted && !demo && live.error && !item ? (
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
            <View style={styles.group}>
              <SectionHeader title={t('hrOnboarding.sectionNeedsHr')} count={hrItems.length} />
              {hrItems.length === 0 ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                  {t('hrOnboarding.emptyHrItems')}
                </Text>
              ) : (
                hrItems.map((checklistItem) => (
                  <ItemWork
                    key={checklistItem.item_id}
                    checklistItem={checklistItem}
                    canMutate={canMutate}
                    onPreview={() => openPreview(checklistItem)}
                    onAccept={() =>
                      void confirmation
                        .prepare({ itemId: checklistItem.item_id, outcome: 'accepted' })
                        .catch(() => undefined)
                    }
                    onWaive={() =>
                      void confirmation
                        .prepare({ itemId: checklistItem.item_id, outcome: 'waived' })
                        .catch(() => undefined)
                    }
                  />
                ))
              )}
            </View>

            {waiting.length > 0 ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrOnboarding.sectionWaiting')} count={waiting.length} />
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('hrOnboarding.waitingHint')}
                </Text>
                {waiting.map((checklistItem) => (
                  <View key={checklistItem.item_id} style={styles.waitingRow}>
                    <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.waitingTitle, align]}>
                      {checklistItem.label}
                    </Text>
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.waitingMeta, align]}>
                      {t(itemStatusLabelKey(checklistItem.status))}
                    </Text>
                  </View>
                ))}
              </View>
            ) : null}

            {confirmation.succeeded ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.success, align]}>
                {t('hrOnboarding.decisionSubmitted')}
              </Text>
            ) : null}
          </>
        ) : null}
      </PageScrollView>

      <ConfirmationSheet
        visible={confirmation.visible}
        value={confirmation.view}
        loading={confirmation.loading}
        error={
          confirmation.error instanceof Error
            ? confirmation.error.message
            : confirmation.error
              ? t('confirm.errorGeneric')
              : null
        }
        onCancel={confirmation.cancel}
        onConfirm={() => void confirmation.confirm().catch(() => undefined)}
      />
    </PageScreen>
  )
}

/** Interaction container for one HR-actionable checklist item. */
function ItemWork({
  checklistItem,
  canMutate,
  onPreview,
  onAccept,
  onWaive,
}: {
  checklistItem: OnboardingChecklistItem
  canMutate: boolean
  onPreview: () => void
  onAccept: () => void
  onWaive: () => void
}) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const actions = checklistItem.allowed_actions
  const isBank = checklistItem.is_bank_ess || actions.includes('review_bank')
  const meta = [
    checklistItem.required ? t('hrOnboarding.required') : t('hrOnboarding.optional'),
    checklistItem.document_type || checklistItem.item_type,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <View style={styles.workCard}>
      <View style={styles.workHeader}>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.workTitle, align]}>
          {checklistItem.label}
        </Text>
        <StatusChip
          label={t(itemStatusLabelKey(checklistItem.status))}
          tone={itemStatusTone(checklistItem.status)}
        />
      </View>
      {meta ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.workMeta, align]}>
          {meta}
        </Text>
      ) : null}

      {isBank ? (
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.bankNote, align]}>
          {t('hrOnboarding.bankHandoff')}
        </Text>
      ) : null}

      {(actions.includes('preview') || checklistItem.preview_path) && !isBank ? (
        <ListRow
          title={t('hrOnboarding.openFile')}
          subtitle={t('hrOnboarding.openFileSub')}
          icon="document-text-outline"
          iconTint={ambient.onboarding.fill}
          showChevron
          onPress={onPreview}
          style={styles.actionRow}
        />
      ) : null}

      {!isBank && canMutate && actions.includes('accept') ? (
        <Pressable
          onPress={onAccept}
          style={styles.btnPrimary}
          accessibilityRole="button"
          accessibilityLabel={t('hrOnboarding.accept')}
        >
          <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnPrimaryText}>
            {t('hrOnboarding.accept')}
          </Text>
        </Pressable>
      ) : null}

      {!isBank && canMutate && actions.includes('waive') ? (
        <Pressable
          onPress={onWaive}
          style={styles.btnSecondary}
          accessibilityRole="button"
          accessibilityLabel={t('hrOnboarding.waive')}
        >
          <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnSecondaryText}>
            {t('hrOnboarding.waive')}
          </Text>
        </Pressable>
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: { width: 8, height: 8, borderRadius: 4 },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  identity: { color: colors.subtle, fontSize: font.small },
  lead: { color: colors.ink, fontSize: font.body, fontWeight: '600', marginTop: spacing.xs },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  group: { gap: spacing.sm },
  workCard: {
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  workHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  workTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700', flex: 1 },
  workMeta: { color: colors.subtle, fontSize: font.tiny },
  bankNote: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  actionRow: { backgroundColor: colors.surface },
  btnPrimary: {
    backgroundColor: colors.ink,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
  },
  btnPrimaryText: { color: colors.primaryText, fontSize: font.small, fontWeight: '700' },
  btnSecondary: {
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  btnSecondaryText: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  waitingRow: { gap: 2, paddingVertical: spacing.xs },
  waitingTitle: { color: colors.ink, fontSize: font.small, fontWeight: '600' },
  waitingMeta: { color: colors.subtle, fontSize: font.tiny },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny },
  success: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
})
