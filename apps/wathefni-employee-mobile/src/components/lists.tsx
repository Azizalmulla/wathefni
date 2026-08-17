import { useState, type ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import { type StatusTone } from '@/components/ui'

/**
 * Compact employee list row.
 *
 * Lists used to be built from full `PastelCard`s: an inbox message, a superseded
 * document and a two-year-old payslip each occupied a 110–150pt coloured card, so
 * a screen showed four items and scrolled forever. The quality reference is
 * Schedule's recorded-attendance row — a surface row, one strong line, quiet
 * supporting lines, status on the trailing edge.
 *
 * Card treatment is reserved for items that earn emphasis: something the employee
 * must act on, the current state of a module, or a problem. Everything else is a
 * row.
 */
export function ListRow({
  title,
  subtitle,
  meta,
  /** Small ambient tint square. Opt-in: most rows do not need an icon at all. */
  icon,
  iconTint,
  /** Semantic edge for rows that genuinely need emphasis (action required, error). */
  emphasis,
  /** Unread/attention marker drawn as a dot — always paired with a text label. */
  marked,
  trailing,
  showChevron,
  onPress,
  accessibilityLabel,
  accessibilityHint,
  testID,
  disabled = false,
  children,
  style,
}: {
  title: string
  subtitle?: string | null
  meta?: string | null
  icon?: keyof typeof Ionicons.glyphMap
  iconTint?: string
  emphasis?: Exclude<StatusTone, 'neutral'>
  marked?: boolean
  trailing?: ReactNode
  showChevron?: boolean
  onPress?: () => void
  accessibilityLabel?: string
  accessibilityHint?: string
  testID?: string
  disabled?: boolean
  children?: ReactNode
  style?: StyleProp<ViewStyle>
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const edge =
    emphasis === 'danger' ? colors.danger : emphasis === 'warning' ? colors.warning : emphasis === 'success' ? colors.success : null

  const body = (
    <View style={[styles.row, edge ? { borderColor: edge, borderWidth: StyleSheet.hairlineWidth * 2 } : null, style]}>
      <View style={styles.rowMain}>
        {icon ? (
          <View style={[styles.iconTile, iconTint ? { backgroundColor: iconTint } : null]}>
            <Ionicons name={icon} size={17} color={colors.ink} />
          </View>
        ) : null}
        {marked ? <View style={styles.mark} accessibilityElementsHidden /> : null}
        <View style={styles.grow}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.title, align]}>
            {title}
          </Text>
          {subtitle ? (
            <Text maxFontSizeMultiplier={typeScaling.body} numberOfLines={2} style={[styles.subtitle, align]}>
              {subtitle}
            </Text>
          ) : null}
          {meta ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {meta}
            </Text>
          ) : null}
        </View>
        {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
        {showChevron ? (
          <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={16} color={colors.subtle} />
        ) : null}
      </View>
      {children}
    </View>
  )

  if (!onPress) return body
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [pressed && styles.pressed, disabled && styles.disabled]}
    >
      {body}
    </Pressable>
  )
}

/**
 * Section heading with an optional item count and an optional disclosure.
 *
 * Long-tenure history is the reason this exists: years of documents, payslips and
 * messages must be reachable without every one of them being laid out on first
 * paint.
 */
export function SectionHeader({
  title,
  count,
  collapsible,
  expanded,
  onToggle,
}: {
  title: string
  count?: number | string
  collapsible?: boolean
  expanded?: boolean
  onToggle?: () => void
}) {
  const { isRTL } = useI18n()
  const label = count != null ? `${title} (${count})` : title
  const content = (
    <View style={styles.sectionHead}>
      <Text
        accessibilityRole={collapsible ? undefined : 'header'}
        maxFontSizeMultiplier={typeScaling.heading}
        style={[styles.sectionTitle, readingEdgeAlign(isRTL)]}
      >
        {label}
      </Text>
      {collapsible ? (
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.subtle} />
      ) : null}
    </View>
  )
  if (!collapsible || !onToggle) return content
  return (
    <Pressable
      accessibilityRole="header"
      accessibilityState={{ expanded: Boolean(expanded) }}
      accessibilityLabel={label}
      onPress={onToggle}
      style={({ pressed }) => (pressed ? styles.pressed : undefined)}
      hitSlop={6}
    >
      {content}
    </Pressable>
  )
}

/** Text action used to grow a bounded list one page at a time. */
export function ShowMoreButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { isRTL } = useI18n()
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.showMore, pressed && styles.pressed]}
    >
      <Text
        maxFontSizeMultiplier={typeScaling.body}
        style={[styles.showMoreText, readingEdgeAlign(isRTL)]}
      >
        {label}
      </Text>
    </Pressable>
  )
}

/**
 * Flat back control shared by pushed screens (history, settings, documents).
 * No elevated pill — the page already has enough chrome.
 */
export function PageBackButton({
  onPress,
  accessibilityLabel,
}: {
  onPress?: () => void
  accessibilityLabel?: string
} = {}) {
  const router = useRouter()
  const { isRTL, t } = useI18n()
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || t('common.back')}
      onPress={onPress || router.back}
      hitSlop={8}
      style={({ pressed }) => [styles.back, pressed && styles.pressed]}
    >
      <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
    </Pressable>
  )
}

/**
 * In-page empty / calm notice — surface, not a pastel hero.
 * Full-screen Loading/Access may still use stronger chrome; list empties should not.
 */
export function QuietEmpty({
  message,
  title,
  icon,
}: {
  message?: string
  /** Compatibility alias used by the feature modules. */
  title?: string
  icon?: keyof typeof Ionicons.glyphMap
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View style={styles.quietEmpty} accessibilityRole="summary">
      {icon ? (
        <View style={styles.quietIcon} accessible={false}>
          <Ionicons name={icon} size={20} color={colors.subtle} />
        </View>
      ) : null}
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.quietText, align]}>
        {message || title || ''}
      </Text>
    </View>
  )
}

/**
 * Page a long list instead of laying all of it out at once.
 *
 * A ScrollView plus `.map()` over every payslip an employee has ever received
 * mounts the whole history on first paint. Nesting a virtualized list inside the
 * page scroller trades that for a worse bug, so the list is paged: only the first
 * `pageSize` items exist until the employee asks for more.
 */
export function usePagedList<T>(items: T[], pageSize: number) {
  const [limit, setLimit] = useState(pageSize)
  const visible = items.length > limit ? items.slice(0, limit) : items
  return {
    visible,
    hidden: Math.max(0, items.length - visible.length),
    showMore: () => setLimit((current) => current + pageSize),
  }
}

const styles = StyleSheet.create({
  row: {
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    gap: spacing.sm,
  },
  rowMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  grow: { flex: 1, minWidth: 0, gap: 1 },
  iconTile: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted,
  },
  mark: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  title: { color: colors.ink, fontSize: font.small, fontWeight: '700', lineHeight: 19 },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 18 },
  meta: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  trailing: { alignItems: 'flex-end' },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.55 },
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    minHeight: 24,
  },
  sectionTitle: {
    flex: 1,
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  showMore: {
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    paddingHorizontal: spacing.xs,
  },
  showMoreText: { color: colors.accent, fontSize: font.small, fontWeight: '700' },
  back: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quietEmpty: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  quietIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted,
  },
  quietText: { flex: 1, color: colors.ink, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
})
