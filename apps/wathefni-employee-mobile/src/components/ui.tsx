import { type ReactNode } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native'

import { colors, font, radius, spacing } from '@/theme'

export function Card({
  children,
  style,
  tone = 'default',
}: {
  children: ReactNode
  style?: ViewStyle
  tone?: 'default' | 'accent' | 'muted'
}) {
  return <View style={[styles.card, tone === 'accent' && styles.cardAccent, tone === 'muted' && styles.cardMuted, style]}>{children}</View>
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>
}

export function PageIntro({ eyebrow, title, subtitle }: { eyebrow?: string; title: string; subtitle?: string }) {
  return (
    <View style={styles.pageIntro}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text style={styles.pageTitle}>{title}</Text>
      {subtitle ? <Text style={styles.pageSubtitle}>{subtitle}</Text> : null}
    </View>
  )
}

export function FeatureMark({ glyph }: { glyph: string }) {
  return (
    <View style={styles.featureMark}>
      <Text style={styles.featureMarkText}>{glyph}</Text>
    </View>
  )
}

export function ProgressBar({ value }: { value: number }) {
  const normalized = Math.max(0, Math.min(1, value))
  return (
    <View style={styles.progressTrack} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(normalized * 100) }}>
      <View style={[styles.progressFill, { width: `${normalized * 100}%` }]} />
    </View>
  )
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  busy,
}: {
  label: string
  onPress: () => void
  variant?: 'primary' | 'secondary' | 'danger'
  disabled?: boolean
  busy?: boolean
}) {
  const bg = variant === 'primary' ? colors.primary : variant === 'danger' ? colors.danger : colors.surface
  const fg = variant === 'secondary' ? colors.text : colors.primaryText
  const border = variant === 'secondary' ? colors.border : 'transparent'
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
      ]}
    >
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{label}</Text>}
    </Pressable>
  )
}

export function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'success' | 'warning' | 'danger' }) {
  const map = {
    neutral: { bg: colors.chip, fg: colors.subtle },
    success: { bg: colors.successSoft, fg: colors.success },
    warning: { bg: colors.warningSoft, fg: colors.warning },
    danger: { bg: colors.dangerSoft, fg: colors.danger },
  }[tone]
  return (
    <View style={[styles.chip, { backgroundColor: map.bg }]}>
      <Text style={[styles.chipText, { color: map.fg }]}>{label}</Text>
    </View>
  )
}

export function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardAccent: {
    backgroundColor: colors.accentSoft,
    borderColor: colors.accentSoft,
  },
  cardMuted: {
    backgroundColor: colors.surfaceMuted,
    borderColor: colors.surfaceMuted,
  },
  pageIntro: { gap: spacing.xs },
  eyebrow: {
    color: colors.accent,
    fontSize: font.tiny,
    fontWeight: '800',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  pageTitle: { color: colors.text, fontSize: font.display, fontWeight: '800', letterSpacing: -0.5 },
  pageSubtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  sectionTitle: {
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: colors.subtle,
  },
  button: {
    minHeight: 48,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  buttonText: { fontSize: font.body, fontWeight: '600' },
  featureMark: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft,
  },
  featureMarkText: { color: colors.primary, fontSize: font.h3, fontWeight: '800' },
  progressTrack: {
    height: 7,
    overflow: 'hidden',
    borderRadius: radius.pill,
    backgroundColor: colors.chip,
  },
  progressFill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.accent },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.pill, alignSelf: 'flex-start' },
  chipText: { fontSize: font.tiny, fontWeight: '600' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.xs },
  rowLabel: { fontSize: font.body, color: colors.subtle },
  rowValue: { fontSize: font.body, color: colors.text, fontWeight: '500', flexShrink: 1, textAlign: 'right' },
})
