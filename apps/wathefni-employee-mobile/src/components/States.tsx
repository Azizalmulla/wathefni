import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { EditorialHeading, Wordmark } from '@/components/premium'

/**
 * Calm full-screen wait on cream — centered cluster only.
 * No wordmark: compact Wordmark self-aligns start and reads as a stray left label.
 */
export function LoadingState() {
  const { t } = useI18n()
  return (
    <View style={styles.screen} accessibilityLabel={t('common.loading')}>
      <View style={styles.loadingCluster}>
        <ActivityIndicator color={colors.accent} />
        <Text maxFontSizeMultiplier={typeScaling.body} style={styles.loadingLabel}>
          {t('common.loading')}
        </Text>
      </View>
    </View>
  )
}

export function ErrorState({ error, message, onRetry }: { error?: unknown; message?: string; onRetry?: () => void }) {
  const { t } = useI18n()
  const approvedMessage = message || approvedErrorMessage(error, t)
  return (
    <View style={styles.screen} accessibilityRole="summary">
      <Wordmark compact />
      {/* An error is a status, so it is drawn on neutral surface with a semantic
          edge rather than in an ambient brand tone. */}
      <View style={styles.errorCard}>
        <View style={styles.icon} accessible={false}>
          <Ionicons name="cloud-offline-outline" size={28} color={colors.danger} />
        </View>
        <EditorialHeading size="medium" accessibilityRole="header">
          {t('common.error')}
        </EditorialHeading>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.muted, styles.mutedStart]}>
          {approvedMessage}
        </Text>
        {onRetry ? (
          <Pressable
            style={styles.retry}
            onPress={onRetry}
            accessibilityRole="button"
            accessibilityLabel={t('common.retry')}
            hitSlop={8}
          >
            <Text style={styles.retryText}>{t('common.retry')}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  )
}

export function EmptyState({ message }: { message?: string }) {
  const { t } = useI18n()
  return (
    <View style={styles.screen}>
      <View style={styles.emptyCluster}>
        <View style={styles.icon} accessible={false}>
          <Ionicons name="file-tray-outline" size={26} color={colors.subtle} />
        </View>
        <Text maxFontSizeMultiplier={typeScaling.body} style={styles.muted}>
          {message || t('common.empty')}
        </Text>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.xl,
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  loadingCluster: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
  loadingLabel: {
    fontSize: font.small,
    lineHeight: 20,
    color: colors.subtle,
    fontWeight: '600',
    textAlign: 'center',
  },
  emptyCluster: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    maxWidth: 280,
  },
  errorCard: {
    alignSelf: 'stretch',
    justifyContent: 'center',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: colors.danger,
  },
  icon: {
    width: 48,
    height: 48,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  muted: {
    fontSize: font.body,
    lineHeight: 22,
    color: colors.subtle,
    fontWeight: '600',
    textAlign: 'center',
  },
  mutedStart: { textAlign: 'left', alignSelf: 'stretch' },
  retry: {
    marginTop: spacing.xs,
    backgroundColor: colors.ink,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    minHeight: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  retryText: { color: colors.primaryText, fontWeight: '600' },
})
