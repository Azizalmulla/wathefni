import { useMemo, useState } from 'react'
import { StyleSheet, Text, TextInput, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import type { LeaveRequest } from '@/api/types'
import { useLocale } from '@/i18n'
import {
  ActionButton,
  Card,
  ConfirmationSheet,
  EditorialHeading,
  IdentityRow,
  Screen,
  Skeleton,
  StatePanel,
  StatusBadge,
  WorkspaceHeader,
  type ConfirmationView,
} from '@/components/primitives'
import { colors, radius, spacing, type as typography } from '@/theme'

export type LeaveViewState =
  | 'ready'
  | 'loading'
  | 'stale'
  | 'success'
  | 'revoked'
  | 'already_decided'
  | 'error'

export function LeaveApprovalView({
  request,
  state = 'ready',
  company = 'WATHEFNI',
  onPrepareDecision,
  onConfirmDecision,
  onRetry,
  onLocale,
}: {
  request: LeaveRequest
  state?: LeaveViewState
  company?: string
  onPrepareDecision?: (action: 'approve' | 'reject', reason?: string) => Promise<ConfirmationView>
  onConfirmDecision?: () => Promise<void>
  onRetry?: () => void
  onLocale?: () => void
}) {
  const { t, isRTL } = useLocale()
  const [reason, setReason] = useState('')
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const dateText = useMemo(
    () => `${request.start_date} — ${request.end_date} · ${request.duration_days ?? '—'} days`,
    [request],
  )

  const prepare = async (action: 'approve' | 'reject') => {
    if (action === 'reject' && !reason.trim()) return
    setPreparing(true)
    try {
      const fallback: ConfirmationView = {
        target: request.employee.name,
        action: action === 'approve' ? t('leave.approve') : t('leave.reject'),
        consequence:
          action === 'approve'
            ? `Approve ${request.employee.name}'s leave and notify the employee.`
            : `Reject ${request.employee.name}'s leave and notify the employee.`,
        currentState: request.status,
        reason: reason.trim() || undefined,
      }
      setConfirmation((await onPrepareDecision?.(action, reason.trim())) || fallback)
    } finally {
      setPreparing(false)
    }
  }

  const confirm = async () => {
    setConfirming(true)
    try {
      await onConfirmDecision?.()
      setConfirmation(null)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <Screen>
      <WorkspaceHeader company={company} onLocale={onLocale} />
      <EditorialHeading eyebrow={t('leave.eyebrow')}>{t('leave.title')}</EditorialHeading>
      {state === 'loading' ? (
        <View style={styles.stack}>
          <Skeleton lines={4} />
          <Skeleton lines={5} />
        </View>
      ) : state === 'stale' ? (
        <StatePanel title={t('state.staleTitle')} body={t('state.staleBody')} action={t('common.retry')} onAction={onRetry} icon="refresh-circle-outline" />
      ) : state === 'success' ? (
        <StatePanel title={t('state.successTitle')} body={t('state.successBody')} icon="checkmark-done-circle-outline" />
      ) : state === 'revoked' ? (
        <StatePanel title={t('state.revokedTitle')} body={t('state.revokedBody')} action={t('common.retry')} onAction={onRetry} icon="lock-closed-outline" />
      ) : state === 'already_decided' ? (
        <StatePanel title={t('leave.alreadyDecided')} body={t('state.staleBody')} action={t('common.retry')} onAction={onRetry} icon="time-outline" />
      ) : state === 'error' ? (
        <StatePanel title={t('state.errorTitle')} body={t('state.errorBody')} action={t('common.retry')} onAction={onRetry} icon="alert-circle-outline" />
      ) : (
        <>
          <Card tone="cream">
            <View style={[styles.topRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              <StatusBadge label={request.status} tone="attention" />
              <Text style={styles.requestId}>#{request.leave_id.slice(0, 8)}</Text>
            </View>
            <IdentityRow
              name={request.employee.name}
              subtitle={request.employee.position_title}
              meta={request.employee.department}
            />
            <View style={styles.rule} />
            <FactRow icon="calendar-outline" label={request.leave_type || 'Leave'} value={dateText} />
            {request.reason ? <FactRow icon="chatbubble-ellipses-outline" label={t('leave.reason')} value={request.reason} /> : null}
          </Card>

          {request.shift_conflict_count > 0 ? (
            <Card tone="amber">
              <FactRow
                icon="warning-outline"
                label={t('leave.conflicts')}
                value={`${request.shift_conflict_count} scheduled shift${request.shift_conflict_count === 1 ? '' : 's'} overlap this leave.`}
              />
            </Card>
          ) : null}

          {request.balance ? (
            <Card tone="sky">
              <FactRow icon="pie-chart-outline" label={t('leave.balance')} value="Authoritative balance context is available for this request." />
            </Card>
          ) : null}

          {request.allowed_actions.includes('reject') ? (
            <View style={styles.reasonWrap}>
              <Text style={[styles.label, { textAlign: isRTL ? 'right' : 'left' }]}>{t('leave.rejectionReason')}</Text>
              <TextInput
                value={reason}
                onChangeText={setReason}
                placeholder={t('leave.rejectionReason')}
                placeholderTextColor={colors.faint}
                multiline
                maxLength={500}
                accessibilityLabel={t('leave.rejectionReason')}
                style={[styles.reasonInput, { textAlign: isRTL ? 'right' : 'left', writingDirection: isRTL ? 'rtl' : 'ltr' }]}
              />
            </View>
          ) : null}

          <View style={[styles.actions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
            {request.allowed_actions.includes('reject') ? (
              <View style={styles.flex}>
                <ActionButton
                  label={t('leave.reject')}
                  tone="secondary"
                  disabled={!reason.trim()}
                  loading={preparing}
                  onPress={() => void prepare('reject')}
                />
              </View>
            ) : null}
            {request.allowed_actions.includes('approve') ? (
              <View style={styles.flex}>
                <ActionButton
                  label={t('leave.approve')}
                  loading={preparing}
                  onPress={() => void prepare('approve')}
                />
              </View>
            ) : null}
          </View>
        </>
      )}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void confirm()}
        loading={confirming}
      />
    </Screen>
  )
}

function FactRow({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap
  label: string
  value: string
}) {
  const { isRTL } = useLocale()
  return (
    <View style={[styles.factRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
      <View style={styles.factIcon}>
        <Ionicons name={icon} size={17} color={colors.plum} />
      </View>
      <View style={styles.factText}>
        <Text style={[styles.factLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
        <Text style={[styles.factValue, { textAlign: isRTL ? 'right' : 'left' }]}>{value}</Text>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  stack: { gap: spacing.xl },
  topRow: { justifyContent: 'space-between', alignItems: 'center' },
  requestId: { color: colors.faint, fontSize: typography.micro, fontWeight: '700' },
  rule: { height: 1, backgroundColor: colors.line },
  factRow: { gap: spacing.md, alignItems: 'flex-start' },
  factIcon: { width: 34, height: 34, borderRadius: 12, backgroundColor: colors.plumSoft, alignItems: 'center', justifyContent: 'center' },
  factText: { flex: 1, gap: 3 },
  factLabel: { color: colors.muted, fontSize: typography.label, fontWeight: '800' },
  factValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  reasonWrap: { gap: spacing.sm },
  label: { color: colors.ink, fontSize: typography.label, fontWeight: '800' },
  reasonInput: { minHeight: 94, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, padding: spacing.md, color: colors.ink, fontSize: typography.body, textAlignVertical: 'top' },
  actions: { gap: spacing.md },
  flex: { flex: 1 },
})
