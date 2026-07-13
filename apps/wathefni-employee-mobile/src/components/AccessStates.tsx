import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import type { AppAccessState } from '@/capabilities'
import { useI18n } from '@/i18n'
import { Button } from '@/components/ui'
import { colors, font, spacing } from '@/theme'

export function AccessStateScreen({
  state,
  onRetry,
  onSignOut,
}: {
  state: Exclude<AppAccessState, 'active'>
  onRetry: () => void
  onSignOut: () => void
}) {
  const { t } = useI18n()
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{t(`access.${state}.title`)}</Text>
      <Text style={styles.message}>{t(`access.${state}.message`)}</Text>
      {state !== 'employee_inactive' && state !== 'session_expired' ? (
        <Button label={t('common.retry')} onPress={onRetry} />
      ) : null}
      <Button
        label={state === 'session_expired' ? t('access.signIn') : t('auth.signOut')}
        variant="secondary"
        onPress={onSignOut}
      />
    </View>
  )
}

export function FeatureUnavailableState({ onRefresh }: { onRefresh?: () => void }) {
  const { t } = useI18n()
  const router = useRouter()
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{t('feature.unavailable.title')}</Text>
      <Text style={styles.message}>{t('feature.unavailable.message')}</Text>
      {onRefresh ? <Button label={t('common.retry')} onPress={onRefresh} /> : null}
      <Button label={t('feature.backHome')} variant="secondary" onPress={() => router.replace('/(tabs)')} />
    </View>
  )
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  title: { fontSize: font.h2, fontWeight: '700', color: colors.text, textAlign: 'center' },
  message: { fontSize: font.body, color: colors.subtle, textAlign: 'center' },
})
