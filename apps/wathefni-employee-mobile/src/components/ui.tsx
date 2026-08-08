import { type ReactNode } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { colors, font, radius, spacing, typeScaling } from '@/theme'

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <Text accessibilityRole="header" maxFontSizeMultiplier={typeScaling.heading} style={styles.sectionTitle}>
      {children}
    </Text>
  )
}

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger'

const toneStyle: Record<StatusTone, { fg: string; icon: keyof typeof Ionicons.glyphMap | null }> = {
  neutral: { fg: colors.subtle, icon: null },
  success: { fg: colors.success, icon: 'checkmark-circle-outline' },
  warning: { fg: colors.warning, icon: 'time-outline' },
  danger: { fg: colors.danger, icon: 'alert-circle-outline' },
}

/**
 * Status is a bordered chip on `surface`, never an ambient pastel fill.
 *
 * The app uses soft green, pink and butter decoratively, so a soft green blob
 * cannot also mean "approved". Drawing status as outline + semantic text + icon
 * keeps it legible on top of any ambient card and keeps meaning off colour
 * alone: the label always carries the state in words.
 */
export function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  const { fg, icon } = toneStyle[tone]
  return (
    <View style={[styles.chip, { borderColor: tone === 'neutral' ? colors.border : fg }]}>
      {icon ? <Ionicons name={icon} size={12} color={fg} /> : null}
      <Text
        maxFontSizeMultiplier={typeScaling.chip}
        numberOfLines={2}
        style={[styles.chipText, { color: fg }]}
      >
        {label}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  sectionTitle: {
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: colors.subtle,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
    backgroundColor: colors.surface,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  chipText: { fontSize: font.tiny, fontWeight: '700', flexShrink: 1 },
})
