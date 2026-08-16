import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

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
  const insets = useSafeAreaInsets()
  const align = readingEdgeAlign(isRTL)

  return (
    <View
      style={[
        styles.root,
        {
          direction: isRTL ? 'rtl' : 'ltr',
          paddingTop: insets.top + spacing.xxl,
          paddingBottom: Math.max(insets.bottom, spacing.md),
        },
      ]}
      key={`bio-opt-${locale}`}
      testID="e2e.biometric.optIn"
    >
      <View style={styles.column}>
        <View style={styles.topBreath} />
        <View style={styles.block}>
          <View style={styles.wordmarkRow}>
            <Wordmark />
          </View>
          <FadeIn style={styles.hero}>
            <Text style={[styles.eyebrow, align]} maxFontSizeMultiplier={1.2}>
              {t('pin.eyebrow')}
            </Text>
            <EditorialHeading>{t(titleKey(kind))}</EditorialHeading>
            <Text style={[styles.subtitle, align]} maxFontSizeMultiplier={1.25}>
              {t('biometric.optInSubtitle')}
            </Text>
          </FadeIn>
          <FadeIn delay={80} style={styles.actions}>
            <PremiumButton label={t(enableKey(kind))} onPress={onEnable} busy={busy} showDirection />
            <Pressable
              onPress={onSkip}
              disabled={busy}
              style={styles.skip}
              accessibilityRole="button"
              accessibilityState={{ disabled: busy }}
              testID="e2e.biometric.notNow"
              accessibilityLabel={t('biometric.notNow')}
            >
              <Text style={styles.skipText} maxFontSizeMultiplier={1.2}>
                {t('biometric.notNow')}
              </Text>
            </Pressable>
          </FadeIn>
        </View>
        <View style={styles.bottomBreath} />
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  column: {
    flex: 1,
    paddingHorizontal: layout.focusMargin,
  },
  topBreath: { flexGrow: 0.35, flexShrink: 1, minHeight: spacing.md },
  bottomBreath: { flexGrow: 1, flexShrink: 1, minHeight: spacing.lg },
  block: {
    flexShrink: 0,
    gap: spacing.xl,
  },
  wordmarkRow: {
    marginBottom: spacing.xs,
  },
  hero: {
    gap: spacing.md,
  },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.small,
    letterSpacing: 0.4,
    marginBottom: spacing.xs,
  },
  subtitle: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    marginTop: spacing.xs,
  },
  actions: { gap: spacing.md },
  skip: { alignItems: 'center', paddingVertical: spacing.sm },
  skipText: { color: colors.subtle, fontSize: font.body },
})
