import type { ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { readingEdgeAlign, useI18n } from '@/i18n'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'

/**
 * Employee Inbox ledger primitives — flat cream rows, unread ink accent,
 * title / body / relative time. Shared by Employee Notifications and HR Inbox
 * so HR does not invent a separate design system.
 */

export function InboxLedgerSection({ children }: { children: ReactNode }) {
  return <View style={styles.inboxSection}>{children}</View>
}

export function InboxLedger({ children }: { children: ReactNode }) {
  return <View style={styles.inboxLedger}>{children}</View>
}

export function InboxLedgerRow({
  title,
  body,
  when,
  emphasized = false,
  quiet = false,
  accentColor,
  onPress,
  accessibilityLabel,
  accessibilityHint,
}: {
  title: string
  body?: string | null
  when?: string | null
  /** Unread / needs-action — left accent bar. */
  emphasized?: boolean
  quiet?: boolean
  /** Wathefni palette color for the accent bar (never black/ink). */
  accentColor?: string
  onPress: () => void
  accessibilityLabel: string
  accessibilityHint?: string
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const barColor = accentColor || colors.butter
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      style={({ pressed }) => [styles.inboxRow, pressed && styles.pressed]}
    >
      {emphasized ? (
        <View
          style={[styles.inboxUnreadAccent, { backgroundColor: barColor }]}
          accessibilityElementsHidden
        />
      ) : (
        <View style={styles.inboxAccentSpacer} />
      )}
      <View style={styles.inboxRowMain}>
        <View style={styles.flex}>
          <Text
            maxFontSizeMultiplier={typeScaling.body}
            numberOfLines={2}
            style={[quiet ? styles.inboxTitleQuiet : styles.inboxTitle, align]}
          >
            {title}
          </Text>
          {body ? (
            <Text
              maxFontSizeMultiplier={typeScaling.chip}
              numberOfLines={2}
              style={[styles.inboxBody, align]}
            >
              {body}
            </Text>
          ) : null}
        </View>
        {when ? (
          <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.inboxWhen}>
            {when}
          </Text>
        ) : null}
      </View>
    </Pressable>
  )
}

/** Cream-ground empty — same as Employee Notifications CalmNote. */
export function InboxCalmNote({ message }: { message: string }) {
  const { isRTL } = useI18n()
  return (
    <Text
      maxFontSizeMultiplier={typeScaling.body}
      style={[styles.calmNote, readingEdgeAlign(isRTL)]}
      accessibilityRole="summary"
    >
      {message}
    </Text>
  )
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  pressed: { opacity: 0.82 },
  inboxSection: { gap: spacing.sm },
  inboxLedger: { gap: 0 },
  inboxRow: {
    minHeight: layout.touchTarget,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  inboxUnreadAccent: {
    width: 3,
    alignSelf: 'stretch',
    borderRadius: radius.pill,
    marginEnd: spacing.xs,
  },
  inboxAccentSpacer: {
    width: 3,
    alignSelf: 'stretch',
    marginEnd: spacing.xs,
    opacity: 0,
  },
  inboxRowMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  inboxTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', lineHeight: 20 },
  inboxTitleQuiet: { color: colors.subtle, fontSize: font.body, fontWeight: '700', lineHeight: 20 },
  inboxBody: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16, marginTop: 2 },
  inboxWhen: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '600',
    flexShrink: 0,
    paddingTop: 2,
  },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    paddingVertical: spacing.lg,
  },
})
