import { StyleSheet, Text, View } from 'react-native'

import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'
import type { BankSubmissionState } from '@/api/types'

/**
 * Employee-facing Bank lifecycle marks — quiet, never competing with the
 * salary-account ambient surface.
 *
 * Action required → pink fill
 * Being reviewed → quiet ink (no yellow — yellow is reserved for the account card)
 * Settled → quiet green word
 */
export type BankLifeKind = 'action' | 'review' | 'settled' | 'neutral'

export function bankLifeKind(state: string | null | undefined): BankLifeKind {
  switch (String(state || '').trim()) {
    case 'rejected':
    case 'needs_correction':
    case 'draft':
      return 'action'
    case 'pending_hr':
    case 'pending_review':
    case 'pending_payroll':
    case 'approved':
      return 'review'
    case 'applied':
      return 'settled'
    default:
      return 'neutral'
  }
}

export function bankLifeFill(kind: BankLifeKind): string | null {
  // Review intentionally has no fill — yellow ambient is reserved for the
  // salary-account card, so a review chip must stay quieter.
  if (kind === 'action') return ambient.schedule.fill
  return null
}

export function BankLifeMark({ label, state }: { label: string; state: string }) {
  const kind = bankLifeKind(state)
  const fill = bankLifeFill(kind)
  if (kind === 'review') {
    return <QuietReviewMark label={label} />
  }
  if (!fill) {
    return (
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.neutral}>
        {label}
      </Text>
    )
  }
  return (
    <View style={[styles.mark, { backgroundColor: fill }]}>
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.markText}>
        {label}
      </Text>
    </View>
  )
}

/** Settled account chip — quiet green word, not a bordered status chip. */
export function QuietSettledMark({ label }: { label: string }) {
  return (
    <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.settled}>
      {label}
    </Text>
  )
}

/** Being reviewed — ink weight only, never a yellow pill. */
export function QuietReviewMark({ label }: { label: string }) {
  return (
    <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.review}>
      {label}
    </Text>
  )
}

export function isActiveBankSubmission(state: BankSubmissionState | string): boolean {
  return (
    state === 'pending_hr' ||
    state === 'pending_review' ||
    state === 'pending_payroll' ||
    state === 'approved' ||
    state === 'draft' ||
    state === 'rejected' ||
    state === 'needs_correction'
  )
}

const styles = StyleSheet.create({
  mark: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  markText: { color: colors.ink, fontSize: font.tiny, fontWeight: '800' },
  settled: { color: colors.success, fontSize: font.tiny, fontWeight: '700', flexShrink: 0 },
  review: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', flexShrink: 0 },
  neutral: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', flexShrink: 0 },
})
