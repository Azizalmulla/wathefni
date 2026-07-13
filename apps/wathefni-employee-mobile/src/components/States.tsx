import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'

import { colors, font, radius, spacing } from '@/theme'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'

export function LoadingState() {
  const { t } = useI18n()
  return (
    <View style={styles.center} accessibilityLabel={t('common.loading')}>
      <ActivityIndicator color={colors.accent} />
      <Text style={styles.muted}>{t('common.loading')}</Text>
    </View>
  )
}

export function ErrorState({ error, message, onRetry }: { error?: unknown; message?: string; onRetry?: () => void }) {
  const { t } = useI18n()
  const approvedMessage = message || approvedErrorMessage(error, t)
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{t('common.error')}</Text>
      <Text style={styles.muted}>{approvedMessage}</Text>
      {onRetry ? (
        <Pressable style={styles.retry} onPress={onRetry} accessibilityRole="button">
          <Text style={styles.retryText}>{t('common.retry')}</Text>
        </Pressable>
      ) : null}
    </View>
  )
}

export function EmptyState({ message }: { message?: string }) {
  const { t } = useI18n()
  return (
    <View style={styles.center}>
      <Text style={styles.muted}>{message || t('common.empty')}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm, padding: spacing.xl },
  title: { fontSize: font.h3, fontWeight: '600', color: colors.text },
  muted: { fontSize: font.body, color: colors.subtle, textAlign: 'center' },
  retry: {
    marginTop: spacing.sm,
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
  },
  retryText: { color: colors.primaryText, fontWeight: '600' },
})
