import { Pressable, StyleSheet, Text, View } from 'react-native'

import type { PriorityItem, PrioritySection } from '@hr/api/types'
import { useLocale } from '@hr/i18n'
import { colors, font, layout, radius, spacing } from '@/theme'

/**
 * Sparse priority rows for Home / Inbox / Hiring foundation.
 * Uses Employee theme tokens — not the old HR giant ActionableCard grid.
 */
export function PrioritySectionList({
  sections,
  itemCap,
  onOpen,
  emptyTitle,
  emptyBody,
}: {
  sections: PrioritySection[]
  itemCap?: number
  onOpen: (destination: string) => void
  emptyTitle: string
  emptyBody: string
}) {
  const { isRTL } = useLocale()
  const align = { textAlign: isRTL ? ('right' as const) : ('left' as const) }
  const items: { section: PrioritySection; item: PriorityItem }[] = []
  for (const section of sections) {
    for (const item of section.items) {
      items.push({ section, item })
      if (itemCap != null && items.length >= itemCap) break
    }
    if (itemCap != null && items.length >= itemCap) break
  }

  if (items.length === 0) {
    return (
      <View style={styles.empty}>
        <Text style={[styles.emptyTitle, align]}>{emptyTitle}</Text>
        <Text style={[styles.emptyBody, align]}>{emptyBody}</Text>
      </View>
    )
  }

  let lastType: string | null = null
  return (
    <View style={styles.stack}>
      {items.map(({ section, item }) => {
        const showHeader = section.type !== lastType
        lastType = section.type
        return (
          <View key={`${item.type}-${item.target_id}`}>
            {showHeader ? (
              <View style={[styles.sectionHeader, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                <Text style={[styles.sectionTitle, align]}>{section.title}</Text>
                {section.total > 0 ? <Text style={styles.sectionCount}>{section.total}</Text> : null}
              </View>
            ) : null}
            <Pressable
              accessibilityRole="button"
              onPress={() => onOpen(item.destination)}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
            >
              <View style={{ flex: 1 }}>
                <Text style={[styles.rowTitle, align]} numberOfLines={2}>
                  {item.summary}
                </Text>
                <Text style={[styles.rowMeta, align]} numberOfLines={1}>
                  {item.status}
                  {item.severity ? ` · ${item.severity}` : ''}
                </Text>
              </View>
            </Pressable>
          </View>
        )
      })}
    </View>
  )
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  sectionHeader: {
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: font.h3,
    fontWeight: '700',
    flex: 1,
  },
  sectionCount: {
    color: colors.subtle,
    fontSize: font.small,
    fontWeight: '700',
    minWidth: 28,
    textAlign: 'center',
  },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 4,
  },
  rowPressed: { opacity: 0.92 },
  rowTitle: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  rowMeta: { color: colors.subtle, fontSize: font.small },
  empty: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.xl,
    gap: spacing.sm,
  },
  emptyTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700' },
  emptyBody: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})

export const shellPageStyles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    paddingBottom: layout.scrollBottom,
    gap: layout.sectionGap,
  },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.small,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  title: {
    color: colors.ink,
    fontSize: font.h1,
    fontWeight: '700',
  },
  subtitle: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
  },
  contextRow: {
    gap: 2,
  },
  contextLine: {
    color: colors.subtle,
    fontSize: font.small,
  },
  moreRow: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  moreRowTitle: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '600',
  },
  moreGroup: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginTop: spacing.sm,
  },
})
