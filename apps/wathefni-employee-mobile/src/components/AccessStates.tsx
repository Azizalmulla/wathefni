import { StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'

import type { AppAccessState } from '@/capabilities'
import { useI18n } from '@/i18n'
import { EditorialHeading, PastelCard, PremiumButton, WathefniBloom, Wordmark, type PastelTone } from '@/components/premium'
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
  const { t, isRTL } = useI18n()
  const presentation = accessPresentation(state)
  return (
    <AccessShell
      tone={presentation.tone}
      icon={presentation.icon}
      eyebrow={t('remaining.stateEyebrow')}
      title={t(`access.${state}.title`)}
      message={t(`access.${state}.message`)}
      isRTL={isRTL}
    >
      {state !== 'employee_inactive' && state !== 'session_expired' ? (
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      ) : null}
      <SecondaryAction
        label={state === 'session_expired' ? t('access.signIn') : t('auth.signOut')}
        onPress={onSignOut}
      />
    </AccessShell>
  )
}

export function FeatureUnavailableState({ onRefresh }: { onRefresh?: () => void }) {
  const { t, isRTL } = useI18n()
  const router = useRouter()
  return (
    <AccessShell
      tone="lilac"
      icon="apps-outline"
      eyebrow={t('remaining.featureEyebrow')}
      title={t('feature.unavailable.title')}
      message={t('feature.unavailable.message')}
      isRTL={isRTL}
    >
      {onRefresh ? <PremiumButton label={t('common.retry')} onPress={onRefresh} /> : null}
      <SecondaryAction label={t('feature.backHome')} onPress={() => router.replace('/(tabs)')} />
    </AccessShell>
  )
}

function AccessShell({
  tone,
  icon,
  eyebrow,
  title,
  message,
  isRTL,
  children,
}: {
  tone: PastelTone
  icon: keyof typeof Ionicons.glyphMap
  eyebrow: string
  title: string
  message: string
  isRTL: boolean
  children: React.ReactNode
}) {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.wrap}>
        <Wordmark compact />
        <PastelCard tone={tone} style={styles.card}>
          <View style={styles.icon}>
            <Ionicons name={icon} size={35} color={colors.ink} />
          </View>
          <Text style={[styles.eyebrow, { textAlign: isRTL ? 'right' : 'left' }]}>{eyebrow}</Text>
          <EditorialHeading size="medium">{title}</EditorialHeading>
          <Text style={[styles.message, { textAlign: isRTL ? 'right' : 'left' }]}>{message}</Text>
          <View style={styles.actions}>{children}</View>
          <WathefniBloom variant="watermark" />
        </PastelCard>
      </View>
    </SafeAreaView>
  )
}

function SecondaryAction({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Text accessibilityRole="button" onPress={onPress} style={styles.secondary}>
      {label}
    </Text>
  )
}

function accessPresentation(state: Exclude<AppAccessState, 'active'>): {
  tone: PastelTone
  icon: keyof typeof Ionicons.glyphMap
} {
  switch (state) {
    case 'offline':
      return { tone: 'sky', icon: 'cloud-offline-outline' }
    case 'session_expired':
      return { tone: 'butter', icon: 'time-outline' }
    case 'employee_inactive':
      return { tone: 'blush', icon: 'person-remove-outline' }
    case 'company_disabled':
      return { tone: 'butter', icon: 'pause-circle-outline' }
    case 'company_archived':
      return { tone: 'lilac', icon: 'archive-outline' }
    case 'company_app_disabled':
      return { tone: 'lilac', icon: 'apps-outline' }
    case 'app_disabled':
      return { tone: 'sky', icon: 'construct-outline' }
    default:
      return { tone: 'blush', icon: 'alert-circle-outline' }
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  wrap: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.xl,
  },
  card: { minHeight: 390, justifyContent: 'center', gap: spacing.lg, overflow: 'hidden' },
  icon: { width: 62, height: 62, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.58)', alignItems: 'center', justifyContent: 'center' },
  eyebrow: { color: colors.accent, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.9, textTransform: 'uppercase' },
  message: { fontSize: font.body, lineHeight: 23, color: colors.subtle },
  actions: { gap: spacing.md, marginTop: spacing.sm },
  secondary: { color: colors.ink, fontSize: font.small, fontWeight: '700', textAlign: 'center', paddingVertical: spacing.sm },
})
