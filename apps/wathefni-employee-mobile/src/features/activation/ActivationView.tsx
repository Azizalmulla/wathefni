import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n } from '@/i18n'
import { EditorialHeading, FadeIn, PremiumButton, WathefniBloom, Wordmark } from '@/components/premium'
import { motion, useReducedMotion } from '@/motion'
import { colors, font, radius, shadows, spacing } from '@/theme'

type ActivationViewProps = {
  phone: string
  code: string
  busy: boolean
  error: string | null
  notice: string | null
  onPhoneChange: (value: string) => void
  onCodeChange: (value: string) => void
  onSignIn: () => void
  onRequestCode: () => void
}

export function ActivationView({
  phone,
  code,
  busy,
  error,
  notice,
  onPhoneChange,
  onCodeChange,
  onSignIn,
  onRequestCode,
}: ActivationViewProps) {
  const { t, isRTL } = useI18n()
  const codeRef = useRef<TextInput>(null)
  const [phoneFocused, setPhoneFocused] = useState(false)
  const [codeFocused, setCodeFocused] = useState(false)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const valid = Boolean(phone.trim() && code.trim().length >= 4)

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          automaticallyAdjustKeyboardInsets
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.wordmarkRow}>
            <Wordmark />
          </View>

          <FadeIn style={styles.hero}>
            <Text style={[styles.eyebrow, align]}>{t('auth.activationEyebrow')}</Text>
            <EditorialHeading>{t('auth.welcomeTitle')}</EditorialHeading>
            <Text style={[styles.subtitle, align]}>{t('auth.subtitle')}</Text>
          </FadeIn>

          <FadeIn delay={70} style={styles.interlude}>
            <View style={styles.interludeLine} />
            <WathefniBloom variant="ribbon" style={styles.interludeBloom} />
            <View style={styles.interludeGlow} />
          </FadeIn>

          <FadeIn delay={110} style={styles.formCard}>
            <View style={styles.field}>
              <Text style={[styles.label, align]}>{t('auth.phone')}</Text>
              <FocusFrame focused={phoneFocused} invalid={Boolean(error)}>
                <View style={[styles.phoneRow, isRTL && styles.rowReverse]}>
                  <View style={styles.countryCode}>
                    <Text style={styles.countryText}>+965</Text>
                  </View>
                  <TextInput
                    value={phone}
                    onChangeText={onPhoneChange}
                    onFocus={() => setPhoneFocused(true)}
                    onBlur={() => setPhoneFocused(false)}
                    onSubmitEditing={() => codeRef.current?.focus()}
                    keyboardType="phone-pad"
                    autoComplete="tel"
                    textContentType="telephoneNumber"
                    returnKeyType="next"
                    style={styles.phoneInput}
                    placeholder="0000 0000"
                    placeholderTextColor={colors.subtle}
                    accessibilityLabel={t('auth.phone')}
                  />
                </View>
              </FocusFrame>
            </View>

            <View style={styles.field}>
              <Text style={[styles.label, align]}>{t('auth.code')}</Text>
              <FocusFrame focused={codeFocused} invalid={Boolean(error)}>
                <TextInput
                  ref={codeRef}
                  value={code}
                  onChangeText={onCodeChange}
                  onFocus={() => setCodeFocused(true)}
                  onBlur={() => setCodeFocused(false)}
                  onSubmitEditing={valid ? onSignIn : undefined}
                  keyboardType="number-pad"
                  autoComplete="sms-otp"
                  textContentType="oneTimeCode"
                  returnKeyType="done"
                  maxLength={6}
                  style={styles.codeInput}
                  placeholder="••••••"
                  placeholderTextColor={colors.subtle}
                  accessibilityLabel={t('auth.code')}
                />
              </FocusFrame>
            </View>

            {error ? (
              <FadeIn style={[styles.feedback, styles.errorFeedback, isRTL && styles.rowReverse]}>
                <Ionicons name="alert-circle-outline" size={18} color={colors.danger} />
                <Text
                  accessibilityLiveRegion="assertive"
                  style={[styles.feedbackText, { color: colors.danger }, align]}
                >
                  {error}
                </Text>
              </FadeIn>
            ) : null}
            {notice ? (
              <FadeIn style={[styles.feedback, styles.noticeFeedback, isRTL && styles.rowReverse]}>
                <Ionicons name="checkmark-circle-outline" size={18} color={colors.success} />
                <Text
                  accessibilityLiveRegion="polite"
                  style={[styles.feedbackText, { color: colors.success }, align]}
                >
                  {notice}
                </Text>
              </FadeIn>
            ) : null}

            <PremiumButton
              label={t('auth.signIn')}
              onPress={onSignIn}
              busy={busy}
              disabled={!valid}
              showDirection
            />
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: busy || !phone.trim() }}
              onPress={onRequestCode}
              disabled={busy || !phone.trim()}
              style={({ pressed }) => [
                styles.codeLink,
                { opacity: busy || !phone.trim() ? 0.34 : pressed ? 0.58 : 1 },
              ]}
            >
              <Text style={styles.codeLinkText}>{t('auth.requestCode')}</Text>
            </Pressable>
          </FadeIn>

          <View style={[styles.secureNote, isRTL && styles.rowReverse]}>
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.success} />
            <Text style={[styles.secureText, align]}>{t('auth.secureNote')}</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function FocusFrame({
  focused,
  invalid,
  children,
}: {
  focused: boolean
  invalid: boolean
  children: ReactNode
}) {
  const reducedMotion = useReducedMotion()
  const focus = useRef(new Animated.Value(focused ? 1 : 0)).current

  useEffect(() => {
    Animated.timing(focus, {
      toValue: focused ? 1 : 0,
      duration: reducedMotion ? 0 : motion.duration.instant,
      easing: motion.easing.standard,
      useNativeDriver: false,
    }).start()
  }, [focus, focused, reducedMotion])

  const borderColor = invalid
    ? colors.danger
    : focus.interpolate({
        inputRange: [0, 1],
        outputRange: [colors.border, colors.ink],
      })
  const backgroundColor = focus.interpolate({
    inputRange: [0, 1],
    outputRange: [colors.bg, colors.surface],
  })

  return (
    <Animated.View
      style={[
        styles.inputShell,
        {
          borderColor,
          backgroundColor,
          shadowOpacity: focused && !reducedMotion ? 0.08 : 0,
        },
      ]}
    >
      {children}
    </Animated.View>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  content: {
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl,
    gap: spacing.lg,
  },
  wordmarkRow: { minHeight: 42, justifyContent: 'center' },
  hero: { gap: spacing.sm, paddingTop: spacing.xs },
  eyebrow: {
    color: colors.accent,
    fontSize: font.tiny,
    fontWeight: '800',
    letterSpacing: 1.05,
    textTransform: 'uppercase',
  },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22, maxWidth: 335 },
  interlude: {
    height: 48,
    justifyContent: 'center',
    overflow: 'hidden',
    borderRadius: radius.lg,
  },
  interludeLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
  interludeBloom: { position: 'absolute', right: -8, top: -8, width: 114, opacity: 0.68 },
  interludeGlow: {
    position: 'absolute',
    left: 20,
    width: 86,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: colors.pastelSky,
    opacity: 0.34,
    transform: [{ rotate: '-4deg' }],
  },
  formCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadows.card,
  },
  field: { gap: 7 },
  label: { color: colors.text, fontSize: font.small, fontWeight: '700' },
  inputShell: {
    minHeight: 48,
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: colors.ink,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 3 },
    elevation: 1,
  },
  phoneRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center' },
  rowReverse: { flexDirection: 'row-reverse' },
  countryCode: {
    height: 48,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderEndWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  countryText: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  phoneInput: {
    flex: 1,
    height: 48,
    paddingHorizontal: spacing.md,
    color: colors.text,
    fontSize: font.h3,
    textAlign: 'left',
    writingDirection: 'ltr',
  },
  codeInput: {
    height: 52,
    paddingHorizontal: spacing.lg,
    color: colors.text,
    fontSize: 25,
    letterSpacing: 9,
    textAlign: 'center',
    writingDirection: 'ltr',
  },
  feedback: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.md,
  },
  errorFeedback: { backgroundColor: colors.dangerSoft },
  noticeFeedback: { backgroundColor: colors.successSoft },
  feedbackText: { flex: 1, fontSize: font.small, lineHeight: 18 },
  codeLink: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  codeLinkText: { color: colors.text, fontSize: font.small, fontWeight: '700', textDecorationLine: 'underline' },
  secureNote: {
    marginTop: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  secureText: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17, flexShrink: 1 },
})
