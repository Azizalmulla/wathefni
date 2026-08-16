import { StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import type { Shift } from '@hr/api/types'
import { useServerConfirmation } from '@hr/api/useServerConfirmation'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import {
  buildShiftsDemoModel,
  formatShiftLine,
  swapStatusLabelKey,
  swapStatusTone,
} from '@hr/features/shifts/shiftsComposition'
import { isShiftsDemoSwapId, shiftsDemoEnabled } from '@hr/features/shifts/shiftsDemoGate'
import { ConfirmationSheet } from '@hr/components/primitives'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDate, formatDateTime, formatTimeRange, kuwaitToday } from '@/lib/format'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * Shift swap detail — both assignment sides + governed approve/reject.
 */
export function HRShiftSwapDetailView() {
  const { swapId = '' } = useLocalSearchParams<{ swapId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = hasCapability(me, 'hr', 'shift_swap_decisions')
  const demo = shiftsDemoEnabled() || isShiftsDemoSwapId(swapId)

  const live = useQuery({
    queryKey: ['shift-swap', swapId],
    queryFn: ({ signal }) => mobileApi.swapDetail(request, swapId, signal),
    enabled: permitted && Boolean(swapId) && !demo,
  })

  const demoSwap = demo
    ? buildShiftsDemoModel(kuwaitToday()).attention.find((row) => row.id === swapId)?.swap
    : null

  const item = demoSwap || live.data?.item
  const confirmation = useServerConfirmation<{ action: 'approve' | 'reject' }>({
    keyPrefix: 'shift-swap',
    execute: (input, fields) =>
      mobileApi.swapDecision(request, swapId, {
        action: input.action,
        ...fields,
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['shift-swap', swapId] }),
        client.invalidateQueries({ queryKey: ['shift-swaps'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
      ])
    },
  })

  const canDecide =
    !demo &&
    permitted &&
    item?.status === 'requested' &&
    (item.allowed_actions.includes('approve') || item.allowed_actions.includes('reject'))

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
            {t('hrShifts.swapEyebrow')}
          </Text>
          <EditorialHeading>{item?.requester.name || t('hrShifts.swapTitle')}</EditorialHeading>
          {item?.status ? (
            <StatusChip label={t(swapStatusLabelKey(item.status))} tone={swapStatusTone(item.status)} />
          ) : null}
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrShifts.demoDetailNote')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted && !demo ? (
          <ListRow title={t('hrShifts.permissionTitle')} subtitle={t('hrShifts.permissionBody')} />
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
            <View style={styles.section}>
              <SectionHeader title={t('hrShifts.sectionPeople')} />
              <Fact label={t('hrShifts.requester')} value={item.requester.name} />
              <Fact
                label={t('hrShifts.target')}
                value={item.replacement?.name || t('hrShifts.targetMissing')}
              />
              {item.reason ? <Fact label={t('hrShifts.reason')} value={item.reason} /> : null}
              {item.requested_at ? (
                <Fact label={t('hrShifts.requestedAt')} value={formatDateTime(item.requested_at, locale)} />
              ) : null}
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrShifts.sectionRequesterShift')} />
              <ShiftSideCard shift={item.requester_shift} />
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrShifts.sectionTargetShift')} />
              <ShiftSideCard shift={item.target_shift} />
            </View>

            {canDecide ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrShifts.actionsTitle')} />
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.actionHint, align]}>
                  {t('hrShifts.actionsHint')}
                </Text>
                {item.allowed_actions.includes('approve') ? (
                  <ListRow
                    title={t('hrShifts.approve')}
                    subtitle={t('hrShifts.approveSub')}
                    icon="checkmark-circle-outline"
                    iconTint={colors.surfaceMuted}
                    showChevron
                    onPress={() => void confirmation.prepare({ action: 'approve' }).catch(() => undefined)}
                    style={styles.row}
                  />
                ) : null}
                {item.allowed_actions.includes('reject') ? (
                  <ListRow
                    title={t('hrShifts.reject')}
                    subtitle={t('hrShifts.rejectSub')}
                    icon="close-circle-outline"
                    iconTint={colors.surfaceMuted}
                    showChevron
                    onPress={() => void confirmation.prepare({ action: 'reject' }).catch(() => undefined)}
                    style={styles.row}
                  />
                ) : null}
              </View>
            ) : null}

            {confirmation.succeeded ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.success, align]}>
                {t('hrShifts.decisionSubmitted')}
              </Text>
            ) : null}
          </>
        ) : null}

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
      </PageScrollView>
    </PageScreen>
  )
}

function ShiftSideCard({ shift }: { shift: Shift | null | undefined }) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  if (!shift) {
    return (
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptySide, align]}>
        {t('hrShifts.shiftUnavailable')}
      </Text>
    )
  }
  const date = shift.shift_date || (shift.starts_at ? shift.starts_at.slice(0, 10) : null)
  return (
    <View style={styles.sideCard}>
      <Fact label={t('hrShifts.employee')} value={shift.employee.name} />
      <Fact label={t('hrShifts.workDate')} value={date ? formatDate(date, locale) : '—'} />
      <Fact
        label={t('hrShifts.time')}
        value={formatTimeRange(shift.starts_at || null, shift.ends_at || null, locale) || '—'}
      />
      <Fact label={t('hrShifts.location')} value={shift.location || '—'} />
      <Fact label={t('hrShifts.role')} value={shift.role || '—'} />
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.sideSummary, align]}>
        {formatShiftLine(shift, locale, formatDate, formatTimeRange)}
      </Text>
    </View>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
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

const styles = StyleSheet.create({
  nav: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navSpacer: { width: 44 },
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  section: { gap: spacing.sm },
  fact: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 4,
  },
  factLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  factValue: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  sideCard: { gap: spacing.sm },
  sideSummary: { color: colors.subtle, fontSize: font.tiny, paddingHorizontal: spacing.sm },
  emptySide: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  actionHint: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  row: { backgroundColor: colors.surface },
  success: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
})
