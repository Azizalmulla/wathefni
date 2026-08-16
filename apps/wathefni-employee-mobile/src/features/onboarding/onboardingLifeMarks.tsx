/**
 * Onboarding lifecycle marks — selective colour, never a pill on every row.
 *
 * Needs correction / replacement (Your actions, strong) → pink fill
 * Being reviewed → quiet ink word
 * Completed / settled → quiet green word
 * Ordinary pending action → quiet ink word (pink reserved for correction)
 */
import { StyleSheet, Text, View } from 'react-native'

import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

export type OnboardingLifeKind = 'action' | 'correction' | 'review' | 'settled' | 'neutral'

export function onboardingLifeKind(status: string | null | undefined): OnboardingLifeKind {
  switch (String(status || '').trim().toLowerCase()) {
    case 'rejected':
    case 'replacement_required':
      return 'correction'
    case 'blocked':
      // System/company-owned hold — not employee attention pink.
      return 'neutral'
    case 'submitted':
    case 'processing':
    case 'received':
      return 'review'
    case 'accepted':
    case 'waived':
      return 'settled'
    case 'pending':
    case 'in_progress':
      return 'action'
    default:
      return 'neutral'
  }
}

export function OnboardingLifeMark({
  label,
  status,
  emphasis = 'quiet',
}: {
  label: string
  status: string | null | undefined
  /** `strong` only for urgent Your-action correction — pink pill. */
  emphasis?: 'strong' | 'quiet'
}) {
  const kind = onboardingLifeKind(status)
  if (kind === 'correction' && emphasis === 'strong') {
    return (
      <View style={[styles.mark, { backgroundColor: ambient.schedule.fill }]}>
        <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.markText}>
          {label}
        </Text>
      </View>
    )
  }
  if (kind === 'settled') {
    return (
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.settled}>
        {label}
      </Text>
    )
  }
  if (kind === 'review') {
    return (
      <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.review}>
        {label}
      </Text>
    )
  }
  return (
    <Text maxFontSizeMultiplier={typeScaling.chip} numberOfLines={1} style={styles.neutral}>
      {label}
    </Text>
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
