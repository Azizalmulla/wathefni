import { type ReactNode } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native'

import { colors, font, radius, spacing } from '@/theme'

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>
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
    success: { bg: '#DCFCE7', fg: colors.success },
    warning: { bg: '#FEF3C7', fg: colors.warning },
    danger: { bg: '#FEE2E2', fg: colors.danger },
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
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.pill, alignSelf: 'flex-start' },
  chipText: { fontSize: font.tiny, fontWeight: '600' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.xs },
  rowLabel: { fontSize: font.body, color: colors.subtle },
  rowValue: { fontSize: font.body, color: colors.text, fontWeight: '500', flexShrink: 1, textAlign: 'right' },
})
