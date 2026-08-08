import { useEffect, useRef, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { useI18n } from '@/i18n'
import { EditorialHeading, FadeIn, PremiumButton, Wordmark } from '@/components/premium'
import { PIN_LENGTH } from '@/auth/pinPolicy'
import { colors, font, layout, radius, shadows, spacing } from '@/theme'

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
  const [pin, setPin] = useState('')
  const inputRef = useRef<TextInput>(null)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const

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
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} key={`pin-${locale}-${mode}`}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
        <View style={styles.content}>
          <View style={styles.wordmarkRow}>
            <Wordmark />
          </View>
          <FadeIn style={styles.hero}>
            <Text style={[styles.eyebrow, align]}>{t('pin.eyebrow')}</Text>
            <EditorialHeading>{t(titleKey)}</EditorialHeading>
            <Text style={[styles.subtitle, align]}>{t(subtitleKey)}</Text>
          </FadeIn>

          <FadeIn delay={80} style={styles.card}>
            <Text style={[styles.label, align]}>{t('pin.label')}</Text>
            <Pressable onPress={() => inputRef.current?.focus()} style={styles.dotsRow} accessibilityRole="button">
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
              onSubmitEditing={() => {
                if (ready) onSubmit(pin)
              }}
            />
            {error ? <Text style={[styles.error, align]}>{error}</Text> : null}
            {busy ? (
              <ActivityIndicator color={colors.accent} style={{ marginTop: spacing.md }} />
            ) : (
              <PremiumButton
                label={t(mode === 'unlock' ? 'pin.unlockAction' : 'pin.continue')}
                onPress={() => onSubmit(pin)}
                disabled={!ready}
              />
            )}
            {onCancel ? (
              <Pressable onPress={onCancel} style={styles.cancel} accessibilityRole="button">
                <Text style={styles.cancelText}>{t('common.cancel')}</Text>
              </Pressable>
            ) : null}
            {mode === 'unlock' && onForgotPin ? (
              <Pressable
                onPress={onForgotPin}
                disabled={busy}
                style={styles.cancel}
                accessibilityRole="button"
                accessibilityLabel={t('pin.forgot')}
              >
                <Text style={[styles.forgotText, align]}>{t('pin.forgot')}</Text>
              </Pressable>
            ) : null}
          </FadeIn>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  content: { flex: 1, paddingHorizontal: layout.focusMargin, paddingTop: spacing.lg, paddingBottom: spacing.xxl },
  wordmarkRow: { marginBottom: spacing.xl },
  hero: { gap: spacing.sm, marginBottom: spacing.xl },
  eyebrow: { color: colors.subtle, fontSize: font.small, letterSpacing: 0.4 },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22, marginTop: spacing.xs },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
    gap: spacing.md,
  },
  label: { color: colors.ink, fontSize: font.small, fontWeight: '600' },
  dotsRow: { flexDirection: 'row', justifyContent: 'center', gap: 12, paddingVertical: spacing.lg },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceMuted,
  },
  dotFilled: { backgroundColor: colors.ink, borderColor: colors.ink },
  hiddenInput: { position: 'absolute', opacity: 0, height: 1, width: 1 },
  error: { color: colors.danger, fontSize: font.small, lineHeight: 18 },
  cancel: { alignItems: 'center', paddingVertical: spacing.sm },
  cancelText: { color: colors.subtle, fontSize: font.body },
  forgotText: { color: colors.accent, fontSize: font.body, fontWeight: '600' },
})
