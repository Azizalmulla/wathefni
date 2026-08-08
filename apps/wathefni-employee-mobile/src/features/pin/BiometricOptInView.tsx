import { Pressable, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { useI18n, readingEdgeAlign } from '@/i18n'
import type { BiometricKind } from '@/auth/biometricAuth'
import { EditorialHeading, FadeIn, PremiumButton, Wordmark } from '@/components/premium'
import { colors, font, layout, spacing } from '@/theme'

type BiometricOptInViewProps = {
  kind: BiometricKind
  busy?: boolean
  onEnable: () => void
  onSkip: () => void
}

function titleKey(kind: BiometricKind): string {
  if (kind === 'face') return 'biometric.optInTitleFace'
  if (kind === 'fingerprint') return 'biometric.optInTitleFingerprint'
  return 'biometric.optInTitle'
}

function enableKey(kind: BiometricKind): string {
  if (kind === 'face') return 'biometric.enableFace'
  if (kind === 'fingerprint') return 'biometric.enableFingerprint'
  return 'biometric.enable'
}

export function BiometricOptInView({ kind, busy = false, onEnable, onSkip }: BiometricOptInViewProps) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)

  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} key={`bio-opt-${locale}`}>
      <View style={styles.content}>
        <View style={styles.wordmarkRow}>
          <Wordmark />
        </View>
        <FadeIn style={styles.hero}>
          <Text style={[styles.eyebrow, align]}>{t('pin.eyebrow')}</Text>
          <EditorialHeading>{t(titleKey(kind))}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('biometric.optInSubtitle')}</Text>
        </FadeIn>
        <FadeIn delay={80} style={styles.actions}>
          <PremiumButton label={t(enableKey(kind))} onPress={onEnable} busy={busy} showDirection />
          <Pressable
            onPress={onSkip}
            disabled={busy}
            style={styles.skip}
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
          >
            <Text style={styles.skipText}>{t('biometric.notNow')}</Text>
          </Pressable>
        </FadeIn>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { flex: 1, paddingHorizontal: layout.focusMargin, paddingTop: spacing.lg, paddingBottom: spacing.xxl },
  wordmarkRow: { marginBottom: spacing.xl },
  hero: { gap: spacing.sm, marginBottom: spacing.xl },
  eyebrow: { color: colors.subtle, fontSize: font.small, letterSpacing: 0.4 },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22, marginTop: spacing.xs },
  actions: { gap: spacing.md, marginTop: spacing.lg },
  skip: { alignItems: 'center', paddingVertical: spacing.sm },
  skipText: { color: colors.subtle, fontSize: font.body },
})
