import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Props = {
  loaded: number
  total: number
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
}

/**
 * Honest end-of-queue marker.
 *
 * Whenever the server holds more than this screen has loaded, HR sees the real
 * count and a way to continue instead of a page that silently ends.
 */
export function QueueContinuation({ loaded, total, hasMore, loadingMore, onLoadMore }: Props) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const behind = total > loaded

  if (!hasMore && !behind) return null

  return (
    <View style={styles.wrap}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.count, align]}>
        {t('hrQueues.showingOf', { loaded: String(loaded), total: String(total) })}
      </Text>
      {loadingMore ? (
        <View style={styles.spinner}>
          <ActivityIndicator color={colors.subtle} />
        </View>
      ) : hasMore ? (
        <Pressable accessibilityRole="button" onPress={onLoadMore} style={styles.loadMore}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.loadMoreText}>
            {t('hrQueues.loadMore')}
          </Text>
        </Pressable>
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs, paddingTop: spacing.sm },
  count: { color: colors.subtle, fontSize: font.tiny },
  spinner: { paddingVertical: spacing.md, alignItems: 'center' },
  loadMore: { alignItems: 'center', paddingVertical: spacing.md },
  loadMoreText: { fontSize: font.small, fontWeight: '700', color: colors.subtle },
})
