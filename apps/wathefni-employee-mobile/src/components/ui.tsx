import { type ReactNode } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { colors, ambient, font, radius, scheduleComposition, spacing, typeScaling } from '@/theme'

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <Text accessibilityRole="header" maxFontSizeMultiplier={typeScaling.heading} style={styles.sectionTitle}>
      {children}
    </Text>
  )
}

export type StatusTone =
  | 'neutral'
  | 'success'
  | 'warning'
  | 'danger'
  | 'yellow'
  | 'blue'
  | 'pink'
  | 'green'

type ToneStyle = {
  fg: string
  bg: string
  border: string
  icon: keyof typeof Ionicons.glyphMap | null
  filled: boolean
}

const toneStyle: Record<StatusTone, ToneStyle> = {
  // Semantic outline chips (Employee lists / forms).
  neutral: { fg: colors.subtle, bg: colors.surface, border: colors.border, icon: null, filled: false },
  success: {
    fg: colors.success,
    bg: colors.surface,
    border: colors.success,
    icon: 'checkmark-circle-outline',
    filled: false,
  },
  warning: {
    fg: colors.warning,
    bg: colors.surface,
    border: colors.warning,
    icon: 'time-outline',
    filled: false,
  },
  danger: {
    fg: colors.danger,
    bg: colors.surface,
    border: colors.danger,
    icon: 'alert-circle-outline',
    filled: false,
  },
  // Home progress — filled Wathefni pastels (Employee dashboard colour language).
  yellow: {
    fg: colors.ink,
    bg: ambient.onboarding.fill,
    border: ambient.onboarding.fill,
    icon: null,
    filled: true,
  },
  blue: {
    fg: colors.ink,
    bg: scheduleComposition.planned.fill,
    border: scheduleComposition.planned.fill,
    icon: null,
    filled: true,
  },
  pink: {
    fg: colors.ink,
    bg: ambient.schedule.fill,
    border: ambient.schedule.fill,
    icon: null,
    filled: true,
  },
  green: {
    fg: colors.ink,
    bg: ambient.leave.fill,
    border: ambient.leave.fill,
    icon: null,
    filled: true,
  },
}

/**
 * Status chip.
 *
 * - `success` / `warning` / `danger` / `neutral`: bordered on surface (semantic).
 * - `yellow` / `blue` / `pink` / `green`: filled pastels for Home progress.
 */
export function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  const { fg, bg, border, icon, filled } = toneStyle[tone]
  return (
    <View
      style={[
        styles.chip,
        {
          backgroundColor: bg,
          borderColor: border,
          borderWidth: filled ? 0 : StyleSheet.hairlineWidth * 2,
        },
      ]}
    >
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
    paddingVertical: 4,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  chipText: { fontSize: font.tiny, fontWeight: '700', flexShrink: 1 },
})
