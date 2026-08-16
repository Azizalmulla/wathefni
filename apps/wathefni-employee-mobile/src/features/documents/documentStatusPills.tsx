import { StyleSheet, Text, View } from 'react-native'

import { StatusChip } from '@/components/ui'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'
import type { ComplianceJourneyItem } from '@/api/types'

/**
 * Documents status as brand pills (Needs attention only):
 * Waiting on HR → butter · Action required → pink.
 * Healthy Current docs use QuietReviewedMark instead — no large green pills.
 */
export type DocumentStatusKind = 'healthy' | 'waiting' | 'action'

export function documentStatusKind(
  item: Pick<ComplianceJourneyItem, 'review_status' | 'renewal_required' | 'rejection_reason'>,
): DocumentStatusKind | null {
  const status = String(item.review_status || '')
    .trim()
    .toLowerCase()
  if (!status && !item.renewal_required && !item.rejection_reason) return null

  if (
    item.rejection_reason ||
    item.renewal_required ||
    status === 'expired' ||
    status === 'expiring_soon' ||
    status === 'rejected_reupload' ||
    status === 'missing' ||
    status === 'replacement_required'
  ) {
    return 'action'
  }
  if (status === 'pending_hr_review' || status === 'needs_review') {
    return 'waiting'
  }
  if (
    status === 'hr_reviewed' ||
    status === 'accepted' ||
    status === 'approved' ||
    status === 'valid'
  ) {
    return 'healthy'
  }
  return null
}

export function documentStatusFill(kind: DocumentStatusKind): string {
  if (kind === 'healthy') return ambient.documents.fill
  if (kind === 'waiting') return ambient.payslips.fill
  return ambient.schedule.fill // pink — action required only
}

/** Strong pill — Needs attention only. */
export function DocumentStatusMark({
  item,
  label,
}: {
  item: Pick<ComplianceJourneyItem, 'review_status' | 'renewal_required' | 'rejection_reason'>
  label: string
}) {
  const kind = documentStatusKind(item)
  if (!kind || kind === 'healthy') return <StatusChip label={label} tone="neutral" />
  return (
    <View style={[styles.pill, { backgroundColor: documentStatusFill(kind) }]}>
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.pillText}>
        {label}
      </Text>
    </View>
  )
}

/** Quiet green word for healthy Current rows — not a pill. */
export function QuietReviewedMark({ label }: { label: string }) {
  return (
    <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.quietReviewed}>
      {label}
    </Text>
  )
}

/**
 * Renewal is only offered when the employee actually needs to act
 * (and the capability callback is present). Healthy HR-reviewed docs stay clean.
 */
export function renewActionRelevant(
  item: Pick<ComplianceJourneyItem, 'review_status' | 'renewal_required' | 'rejection_reason' | 'can_renew'>,
  onRenew?: (documentType: string) => void,
): boolean {
  if (!onRenew) return false
  if (item.can_renew === false) return false
  if (item.renewal_required || item.rejection_reason) return true
  const status = String(item.review_status || '')
    .trim()
    .toLowerCase()
  return (
    status === 'expired' ||
    status === 'expiring_soon' ||
    status === 'rejected_reupload' ||
    status === 'missing' ||
    status === 'replacement_required'
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
  pillText: {
    color: colors.ink,
    fontSize: font.tiny,
    fontWeight: '800',
  },
  quietReviewed: {
    color: colors.success,
    fontSize: font.tiny,
    fontWeight: '700',
    flexShrink: 0,
  },
})
