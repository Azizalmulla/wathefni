import { StyleSheet, Text, View } from 'react-native'

import { StatusChip } from '@/components/ui'
import { statusTone } from '@/lib/format'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * Leave workflow statuses as brand pills (not semantic outline chips):
 * Approved/Completed → green, Requested/Pending → yellow, Rejected/Cancelled → pink.
 * The label always carries the word. Separate from Schedule Present/Late/Absent.
 */
export type LeaveStatusKind = 'positive' | 'waiting' | 'negative'

export function leaveStatusKind(status: string | null | undefined): LeaveStatusKind | null {
  const s = String(status || '')
    .trim()
    .toLowerCase()
  if (!s) return null
  if (
    s === 'approved' ||
    s === 'completed' ||
    s === 'accepted' ||
    s === 'waived'
  ) {
    return 'positive'
  }
  if (
    s === 'requested' ||
    s === 'pending' ||
    s === 'needs_review' ||
    s === 'needs_info' ||
    s === 'in_progress' ||
    s === 'submitted' ||
    s === 'processing'
  ) {
    return 'waiting'
  }
  if (
    s === 'rejected' ||
    s === 'cancelled' ||
    s === 'canceled' ||
    s === 'denied' ||
    s === 'withdrawn' ||
    s === 'expired' ||
    s === 'blocked' ||
    s === 'replacement_required'
  ) {
    return 'negative'
  }
  return null
}

export function leaveStatusFill(kind: LeaveStatusKind): string {
  if (kind === 'positive') return ambient.leave.fill
  if (kind === 'waiting') return ambient.payslips.fill
  return ambient.schedule.fill
}

export function LeaveStatusMark({
  status,
  label,
}: {
  status: string | null | undefined
  label: string
}) {
  const kind = leaveStatusKind(status)
  if (!kind) return <StatusChip label={label} tone={statusTone(status)} />
  return (
    <View style={[styles.pill, { backgroundColor: leaveStatusFill(kind) }]}>
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.pillText}>
        {label}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 5,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  pillText: { color: colors.ink, fontSize: font.tiny, fontWeight: '800' },
})
