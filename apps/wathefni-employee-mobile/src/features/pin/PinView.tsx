import { useEffect, useRef, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { keyboardSafeBehavior, keyboardSafeOffset } from '@/components/keyboardSafe'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { EditorialHeading, FadeIn, PremiumButton, Wordmark } from '@/components/premium'
import { PIN_LENGTH } from '@/auth/pinPolicy'
import { colors, font, layout, radius, spacing } from '@/theme'

export type PinMode = 'create' | 'confirm' | 'unlock' | 'changeCurrent' | 'changeNext' | 'changeConfirm'

type PinViewProps = {
  mode: PinMode
  busy?: boolean
  error?: string | null
  onSubmit: (pin: string) => void
  onCancel?: () => void
  onForgotPin?: () => void
}

export function PinView({ mode, busy = false, error = null, onSubmit, onCancel, onForgotPin }: PinViewProps) {
  const { t, isRTL, locale } = useI18n()
  const insets = useSafeAreaInsets()
  const [pin, setPin] = useState('')
  const inputRef = useRef<TextInput>(null)
  const align = readingEdgeAlign(isRTL)

  useEffect(() => {
    setPin('')
    const id = setTimeout(() => inputRef.current?.focus(), 250)
    return () => clearTimeout(id)
  }, [mode])

  const titleKey =
    mode === 'create'
      ? 'pin.createTitle'
      : mode === 'confirm' || mode === 'changeConfirm'
        ? 'pin.confirmTitle'
        : mode === 'changeCurrent'
          ? 'pin.changeCurrentTitle'
          : mode === 'changeNext'
            ? 'pin.changeNextTitle'
            : 'pin.unlockTitle'

  const subtitleKey =
    mode === 'create'
      ? 'pin.createSubtitle'
      : mode === 'confirm' || mode === 'changeConfirm'
        ? 'pin.confirmSubtitle'
        : mode === 'changeCurrent'
          ? 'pin.changeCurrentSubtitle'
          : mode === 'changeNext'
            ? 'pin.changeNextSubtitle'
            : 'pin.unlockSubtitle'

  const ready = pin.length === PIN_LENGTH && !busy

  return (
    <View
      style={[
        styles.root,
        {
          direction: isRTL ? 'rtl' : 'ltr',
          // Explicit insets + breathing — FullWindowOverlay can skip nested SafeArea.
          paddingTop: insets.top + spacing.xxl,
          paddingBottom: Math.max(insets.bottom, spacing.md),
        },
      ]}
      key={`pin-${locale}-${mode}`}
      testID="e2e.pin.root"
    >
    <KeyboardAvoidingView
        behavior={keyboardSafeBehavior()}
        style={styles.flex}
        keyboardVerticalOffset={keyboardSafeOffset(insets.top)}
      >
        <View style={styles.column}>
          {/* Larger bottom flex absorbs keyboard height so the block does not jump upward hard. */}
          <View style={styles.topBreath} />
          <View style={styles.block}>
            <View style={styles.wordmarkRow}>
              <Wordmark />
            </View>

            <FadeIn style={styles.hero}>
              <Text style={[styles.eyebrow, align]} maxFontSizeMultiplier={1.2}>
                {t('pin.eyebrow')}
              </Text>
              <EditorialHeading>{t(titleKey)}</EditorialHeading>
              <Text style={[styles.subtitle, align]} maxFontSizeMultiplier={1.25}>
                {t(subtitleKey)}
              </Text>
            </FadeIn>

            <FadeIn delay={80} style={styles.pinSurface}>
              <Text style={[styles.label, align]} maxFontSizeMultiplier={1.2}>
                {t('pin.label')}
              </Text>
              <Pressable
                onPress={() => inputRef.current?.focus()}
                style={styles.dotsRow}
                accessibilityRole="button"
              >
                {Array.from({ length: PIN_LENGTH }).map((_, i) => (
                  <View key={i} style={[styles.dot, i < pin.length && styles.dotFilled]} />
                ))}
              </Pressable>
              <TextInput
                ref={inputRef}
                value={pin}
                onChangeText={(v) => setPin(v.replace(/\D/g, '').slice(0, PIN_LENGTH))}
                keyboardType="number-pad"
                textContentType="password"
                secureTextEntry
                maxLength={PIN_LENGTH}
                style={styles.hiddenInput}
                caretHidden
                editable={!busy}
                accessibilityLabel={t('pin.label')}
                testID="e2e.pin.input"
                onSubmitEditing={() => {
                  if (ready) onSubmit(pin)
                }}
              />
              {error ? (
                <Text style={[styles.error, align]} maxFontSizeMultiplier={1.25}>
                  {error}
                </Text>
              ) : null}
              {busy ? (
                <ActivityIndicator color={colors.accent} style={styles.busy} />
              ) : (
                <PremiumButton
                  label={t(mode === 'unlock' ? 'pin.unlockAction' : 'pin.continue')}
                  onPress={() => onSubmit(pin)}
                  disabled={!ready}
                  testID="e2e.pin.continue"
                />
              )}
              {onCancel ? (
                <Pressable onPress={onCancel} style={styles.secondaryAction} accessibilityRole="button">
                  <Text style={styles.secondaryText} maxFontSizeMultiplier={1.2}>
                    {t('common.cancel')}
                  </Text>
                </Pressable>
              ) : null}
              {mode === 'unlock' && onForgotPin ? (
                <Pressable
                  onPress={onForgotPin}
                  disabled={busy}
                  style={styles.secondaryAction}
                  accessibilityRole="button"
                  accessibilityLabel={t('pin.forgot')}
                >
                  <Text style={styles.forgotText} maxFontSizeMultiplier={1.2}>
                    {t('pin.forgot')}
                  </Text>
                </Pressable>
              ) : null}
            </FadeIn>
          </View>
          <View style={styles.bottomBreath} />
        </View>
      </KeyboardAvoidingView>
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
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
  pinSurface: {
    // Calm inset — cream-on-cream, hairline only, no heavy white card shadow.
    backgroundColor: 'rgba(255, 252, 244, 0.72)',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xl,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    gap: spacing.lg,
  },
  label: {
    color: colors.subtle,
    fontSize: font.small,
    fontWeight: '600',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    textAlign: 'center',
  },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'center',
    gap: 18,
    paddingVertical: spacing.md,
    minHeight: 48,
  },
  dot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: 'transparent',
  },
  dotFilled: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  hiddenInput: { position: 'absolute', opacity: 0, height: 1, width: 1 },
  error: { color: colors.danger, fontSize: font.small, lineHeight: 18, textAlign: 'center' },
  busy: { marginTop: spacing.sm },
  secondaryAction: { alignItems: 'center', paddingTop: spacing.sm, paddingBottom: spacing.xs },
  secondaryText: { color: colors.subtle, fontSize: font.body },
  forgotText: {
    color: colors.subtle,
    fontSize: font.small,
    fontWeight: '500',
    textAlign: 'center',
  },
})
