import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'

import { colors, font, radius, spacing } from '@/theme'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { EditorialHeading, PastelCard, WathefniBloom, Wordmark } from '@/components/premium'

export function LoadingState() {
  const { t } = useI18n()
  return (
    <View style={styles.screen} accessibilityLabel={t('common.loading')}>
      <Wordmark compact />
      <PastelCard tone="lilac" style={styles.card}>
        <ActivityIndicator color={colors.accent} size="large" />
        <Text style={styles.muted}>{t('common.loading')}</Text>
        <WathefniBloom variant="watermark" />
      </PastelCard>
    </View>
  )
}

export function ErrorState({ error, message, onRetry }: { error?: unknown; message?: string; onRetry?: () => void }) {
  const { t } = useI18n()
  const approvedMessage = message || approvedErrorMessage(error, t)
  return (
    <View style={styles.screen}>
      <Wordmark compact />
      <PastelCard tone="blush" style={styles.card}>
        <View style={styles.icon}><Ionicons name="cloud-offline-outline" size={30} color={colors.danger} /></View>
        <EditorialHeading size="medium">{t('common.error')}</EditorialHeading>
        <Text style={styles.muted}>{approvedMessage}</Text>
        {onRetry ? (
          <Pressable style={styles.retry} onPress={onRetry} accessibilityRole="button">
            <Text style={styles.retryText}>{t('common.retry')}</Text>
          </Pressable>
        ) : null}
        <WathefniBloom variant="watermark" />
      </PastelCard>
    </View>
  )
}

export function EmptyState({ message }: { message?: string }) {
  const { t } = useI18n()
  return (
    <View style={styles.screen}>
      <PastelCard tone="lilac" style={styles.card}>
        <View style={styles.icon}><Ionicons name="sparkles-outline" size={30} color={colors.ink} /></View>
        <Text style={styles.muted}>{message || t('common.empty')}</Text>
        <WathefniBloom variant="watermark" />
      </PastelCard>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, justifyContent: 'center', gap: spacing.xl, padding: spacing.xl, backgroundColor: colors.bg },
  card: { minHeight: 260, justifyContent: 'center', alignItems: 'flex-start', gap: spacing.lg, overflow: 'hidden' },
  icon: { width: 54, height: 54, borderRadius: radius.xl, backgroundColor: 'rgba(255,255,255,0.58)', alignItems: 'center', justifyContent: 'center' },
  muted: { fontSize: font.body, lineHeight: 22, color: colors.subtle },
  retry: {
    marginTop: spacing.sm,
    backgroundColor: colors.ink,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
  },
  retryText: { color: colors.primaryText, fontWeight: '600' },
})
