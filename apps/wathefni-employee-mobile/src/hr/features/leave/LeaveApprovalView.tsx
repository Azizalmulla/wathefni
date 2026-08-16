import { useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native'

import type { LeaveRequest } from '@hr/api/types'
import type { ResourceState } from '@hr/api/state'
import {
  formatLeaveDays,
  leaveStatusLabelKey,
  leaveStatusTone,
  leaveTypeLabelKey,
  parseLeaveBalances,
} from '@hr/features/leave/leaveComposition'
import {
  ConfirmationSheet,
  type ConfirmationView,
} from '@hr/components/primitives'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDateRange } from '@hr/i18n/date'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

export type LeaveViewState = ResourceState | 'already_decided'

/**
 * HR Leave decision detail — cream system, honest balance/conflict, SOD confirm.
 */
export function LeaveApprovalView({
  request,
  state = 'ready',
  onPrepareDecision,
  onConfirmDecision,
  onRetry,
  onBack,
}: {
  request: LeaveRequest
  state?: LeaveViewState
  company?: string
  onPrepareDecision?: (action: 'approve' | 'reject', reason?: string) => Promise<ConfirmationView>
  onConfirmDecision?: () => Promise<void>
  onRetry?: () => void
  onLocale?: () => void
  onBack?: () => void
}) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const [reason, setReason] = useState('')
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  const balances = useMemo(() => parseLeaveBalances(request.balance), [request.balance])
  const canApprove = request.allowed_actions.includes('approve')
  const canReject = request.allowed_actions.includes('reject')
  const actionable = state === 'ready' && (canApprove || canReject)

  const dateText = useMemo(() => {
    const range = formatDateRange(request.start_date, request.end_date, locale === 'ar' ? 'ar' : 'en')
    const days = request.duration_days
    if (days == null) return range
    return `${range} · ${t('hrLeave.daysCount', { count: formatLeaveDays(days) })}`
  }, [locale, request.duration_days, request.end_date, request.start_date, t])

  const prepare = async (action: 'approve' | 'reject') => {
    if (action === 'reject' && !reason.trim()) return
    setPreparing(true)
    setConfirmError(null)
    try {
      const view = await onPrepareDecision?.(action, reason.trim())
      if (view) setConfirmation(view)
    } catch (cause) {
      const message =
        cause instanceof Error && cause.message
          ? cause.message
          : t('confirm.errorGeneric')
      setConfirmError(message)
      // Keep a minimal sheet so the error is visible even when prepare fails mid-flight.
      setConfirmation({
        target: request.employee?.name || t('hrLeave.title'),
        action: action === 'approve' ? t('hrLeave.approve') : t('hrLeave.reject'),
        consequence: t('confirm.errorGeneric'),
        currentState: request.status || '—',
        reason: reason.trim() || null,
      })
    } finally {
      setPreparing(false)
    }
  }

  const confirm = async () => {
    setConfirming(true)
    setConfirmError(null)
    try {
      await onConfirmDecision?.()
      setConfirmation(null)
    } catch (cause) {
      const message =
        cause instanceof Error && cause.message
          ? cause.message
          : t('confirm.errorGeneric')
      setConfirmError(message)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} keyboardInsets>
        <HrPushedNav onBack={onBack || (() => undefined)} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
            {t('hrLeave.eyebrow')}
          </Text>
          <EditorialHeading>{request.employee?.name || t('hrLeave.title')}</EditorialHeading>
          {request.status ? (
            <StatusChip
              label={
                leaveStatusLabelKey(request.status) === 'hrLeave.statusOther'
                  ? request.status
                  : t(leaveStatusLabelKey(request.status))
              }
              tone={leaveStatusTone(request.status)}
            />
          ) : null}
        </FadeIn>

        {state === 'loading' ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {state === 'permission' ? (
          <ListRow title={t('hrLeave.permissionTitle')} subtitle={t('hrLeave.permissionBody')} />
        ) : null}

        {state === 'error' || state === 'offline' ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            emphasis="warning"
            showChevron
            onPress={onRetry}
          />
        ) : null}

        {state === 'already_decided' ? (
          <ListRow
            title={t('hrLeave.alreadyDecided')}
            subtitle={t('hrLeave.alreadyDecidedBody')}
            icon="checkmark-done-outline"
          />
        ) : null}

        {state === 'success' ? (
          <ListRow title={t('hrLeave.successTitle')} subtitle={t('hrLeave.successBody')} icon="checkmark-circle-outline" />
        ) : null}

        {state === 'stale' ? (
          <ListRow
            title={t('hrLeave.staleTitle')}
            subtitle={t('hrLeave.staleBody')}
            emphasis="warning"
            showChevron
            onPress={onRetry}
          />
        ) : null}

        {state === 'revoked' ? (
          <ListRow title={t('hrLeave.revokedTitle')} subtitle={t('hrLeave.revokedBody')} emphasis="warning" />
        ) : null}

        {(state === 'ready' || state === 'already_decided') && request.leave_id ? (
          <>
            <View style={styles.section}>
              <SectionHeader title={t('hrLeave.sectionRequest')} />
              <Fact
                label={t('hrLeave.leaveType')}
                value={
                  leaveTypeLabelKey(request.leave_type) === 'hrLeave.typeFallback'
                    ? request.leave_type || t('hrLeave.typeFallback')
                    : t(leaveTypeLabelKey(request.leave_type))
                }
              />
              <Fact label={t('hrLeave.dates')} value={dateText || '—'} />
              {request.employee?.position_title ? (
                <Fact label={t('hrLeave.position')} value={request.employee.position_title} />
              ) : null}
              {request.employee?.department ? (
                <Fact label={t('hrLeave.department')} value={request.employee.department} />
              ) : null}
              {request.reason ? <Fact label={t('hrLeave.employeeReason')} value={request.reason} /> : null}
            </View>

            {request.shift_conflict_count > 0 ? (
              <View style={styles.conflict}>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.conflictLabel, align]}>
                  {t('hrLeave.conflicts')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.conflictBody, align]}>
                  {request.shift_conflict_count === 1
                    ? t('hrLeave.conflictBodyOne')
                    : t('hrLeave.conflictBodyMany', { count: request.shift_conflict_count })}
                </Text>
              </View>
            ) : null}

            {balances.length > 0 ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrLeave.balance')} />
                {balances.map((row) => {
                  const available =
                    row.available != null ? row.available : row.current_balance
                  const typeLabel =
                    leaveTypeLabelKey(row.leave_type) === 'hrLeave.typeFallback'
                      ? row.leave_type || t('hrLeave.typeFallback')
                      : t(leaveTypeLabelKey(row.leave_type))
                  return (
                    <Fact
                      key={`${row.leave_type}-${row.current_balance}`}
                      label={typeLabel}
                      value={t('hrLeave.balanceLine', {
                        available: formatLeaveDays(available),
                        current: formatLeaveDays(row.current_balance),
                        entitlement: formatLeaveDays(row.entitlement_days),
                      })}
                    />
                  )
                })}
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.observeNote, align]}>
                  {t('hrLeave.balanceObserveOnly')}
                </Text>
              </View>
            ) : null}

            {actionable ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrLeave.sectionDecide')} />
                {canReject ? (
                  <View style={styles.reasonWrap}>
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.reasonLabel, align]}>
                      {t('hrLeave.rejectionReason')}
                    </Text>
                    <TextInput
                      value={reason}
                      onChangeText={setReason}
                      placeholder={t('hrLeave.rejectionReasonPlaceholder')}
                      placeholderTextColor={colors.navMuted}
                      multiline
                      maxLength={500}
                      accessibilityLabel={t('hrLeave.rejectionReason')}
                      testID="e2e.hr.leave.rejectReason"
                      style={[
                        styles.reasonInput,
                        align,
                        { writingDirection: isRTL ? 'rtl' : 'ltr' },
                      ]}
                    />
                  </View>
                ) : null}

                <View style={[styles.actions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                  {canReject ? (
                    <Pressable
                      testID="e2e.hr.leave.reject"
                      onPress={() => void prepare('reject')}
                      disabled={!reason.trim() || preparing}
                      style={[styles.btn, styles.btnQuiet, (!reason.trim() || preparing) && styles.btnDisabled]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrLeave.reject')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                        {preparing ? t('common.loading') : t('hrLeave.reject')}
                      </Text>
                    </Pressable>
                  ) : null}
                  {canApprove ? (
                    <Pressable
                      testID="e2e.hr.leave.approve"
                      onPress={() => void prepare('approve')}
                      disabled={preparing}
                      style={[styles.btn, styles.btnPrimary, preparing && styles.btnDisabled]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrLeave.approve')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnPrimaryText}>
                        {preparing ? t('common.loading') : t('hrLeave.approve')}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ) : null}
          </>
        ) : null}
      </PageScrollView>

      {/* Modal must sit outside ScrollView so Confirm presses are not swallowed on iOS. */}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        error={confirmError}
        onCancel={() => {
          setConfirmation(null)
          setConfirmError(null)
        }}
        onConfirm={() => void confirm()}
        loading={confirming}
      />
    </PageScreen>
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
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  section: { gap: spacing.sm },
  fact: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 4,
  },
  factLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  factValue: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  conflict: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.warning,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 6,
  },
  conflictLabel: { color: colors.warning, fontSize: font.tiny, fontWeight: '700' },
  conflictBody: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  observeNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  reasonWrap: { gap: spacing.sm },
  reasonLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  reasonInput: {
    minHeight: 96,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    color: colors.ink,
    fontSize: font.body,
    textAlignVertical: 'top',
  },
  actions: { gap: spacing.sm },
  btn: {
    flex: 1,
    minHeight: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  btnPrimary: { backgroundColor: colors.ink },
  btnPrimaryText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
  btnQuiet: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  btnQuietText: { color: colors.ink, fontWeight: '700', fontSize: font.small },
  btnDisabled: { opacity: 0.45 },
})
