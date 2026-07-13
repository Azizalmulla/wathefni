import {
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
import { Ionicons } from '@expo/vector-icons'

import { useI18n } from '@/i18n'
import { Button } from '@/components/ui'
import { BrandLockup, EditorialHeading, FadeIn } from '@/components/premium'
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
  const align = { textAlign: isRTL ? 'right' : 'left' } as const

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.top}>
            <BrandLockup />
            <PastelBloom mirrored={isRTL} />
          </View>

          <FadeIn style={styles.hero}>
            <Text style={[styles.eyebrow, align]}>{t('auth.employeeApp')}</Text>
            <EditorialHeading>{t('auth.welcomeTitle')}</EditorialHeading>
            <Text style={[styles.subtitle, align]}>{t('auth.subtitle')}</Text>
          </FadeIn>

          <FadeIn style={styles.formCard}>
            <View style={styles.field}>
              <Text style={[styles.label, align]}>{t('auth.phone')}</Text>
              <View style={[styles.inputShell, isRTL && styles.rowReverse]}>
                <View style={styles.countryCode}>
                  <Text style={styles.countryText}>+965</Text>
                </View>
                <TextInput
                  value={phone}
                  onChangeText={onPhoneChange}
                  keyboardType="phone-pad"
                  autoComplete="tel"
                  style={styles.phoneInput}
                  placeholder="0000 0000"
                  placeholderTextColor={colors.subtle}
                  accessibilityLabel={t('auth.phone')}
                />
              </View>
            </View>

            <View style={styles.field}>
              <Text style={[styles.label, align]}>{t('auth.code')}</Text>
              <TextInput
                value={code}
                onChangeText={onCodeChange}
                keyboardType="number-pad"
                maxLength={6}
                style={styles.codeInput}
                placeholder="••••••"
                placeholderTextColor={colors.subtle}
                accessibilityLabel={t('auth.code')}
              />
            </View>

            {error ? (
              <View style={[styles.feedback, styles.errorFeedback, isRTL && styles.rowReverse]}>
                <Ionicons name="alert-circle-outline" size={19} color={colors.danger} />
                <Text style={[styles.feedbackText, { color: colors.danger }, align]}>{error}</Text>
              </View>
            ) : null}
            {notice ? (
              <View style={[styles.feedback, styles.noticeFeedback, isRTL && styles.rowReverse]}>
                <Ionicons name="checkmark-circle-outline" size={19} color={colors.success} />
                <Text style={[styles.feedbackText, { color: colors.success }, align]}>{notice}</Text>
              </View>
            ) : null}

            <Button
              label={t('auth.signIn')}
              onPress={onSignIn}
              busy={busy}
              disabled={!phone.trim() || code.trim().length < 4}
            />
            <Pressable
              accessibilityRole="button"
              onPress={onRequestCode}
              disabled={busy || !phone.trim()}
              style={({ pressed }) => [styles.codeLink, { opacity: busy || !phone.trim() ? 0.4 : pressed ? 0.6 : 1 }]}
            >
              <Text style={styles.codeLinkText}>{t('auth.requestCode')}</Text>
            </Pressable>
          </FadeIn>

          <View style={[styles.secureNote, isRTL && styles.rowReverse]}>
            <Ionicons name="shield-checkmark-outline" size={20} color={colors.success} />
            <Text style={[styles.secureText, align]}>{t('auth.secureNote')}</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function PastelBloom({ mirrored }: { mirrored: boolean }) {
  return (
    <View style={[styles.bloom, mirrored && styles.bloomMirrored]} accessibilityElementsHidden>
      <View style={[styles.bloomShape, styles.bloomLilac]} />
      <View style={[styles.bloomShape, styles.bloomButter]} />
      <View style={[styles.bloomShape, styles.bloomBlush]} />
      <View style={[styles.bloomShape, styles.bloomSage]} />
    </View>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  content: {
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.xl,
  },
  top: { minHeight: 76, justifyContent: 'flex-start' },
  bloom: { position: 'absolute', top: -14, right: -6, width: 104, height: 92 },
  bloomMirrored: { right: undefined, left: -6, transform: [{ scaleX: -1 }] },
  bloomShape: { position: 'absolute', borderRadius: 22 },
  bloomLilac: { width: 46, height: 29, right: 30, top: 5, backgroundColor: colors.pastelLilac, transform: [{ rotate: '24deg' }] },
  bloomButter: { width: 34, height: 48, right: 5, top: 20, backgroundColor: colors.pastelButter, transform: [{ rotate: '-18deg' }] },
  bloomBlush: { width: 43, height: 31, right: 42, top: 46, backgroundColor: colors.pastelBlush, transform: [{ rotate: '-28deg' }] },
  bloomSage: { width: 30, height: 32, right: 15, top: 57, backgroundColor: colors.pastelSage, transform: [{ rotate: '15deg' }] },
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.accent,
    fontSize: font.tiny,
    fontWeight: '800',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 23, maxWidth: 330 },
  formCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.lg,
    ...shadows.card,
  },
  field: { gap: spacing.sm },
  label: { color: colors.text, fontSize: font.small, fontWeight: '700' },
  inputShell: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.bg,
    overflow: 'hidden',
  },
  rowReverse: { flexDirection: 'row-reverse' },
  countryCode: {
    height: '100%',
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderEndWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  countryText: { color: colors.text, fontSize: font.body, fontWeight: '700' },
  phoneInput: {
    flex: 1,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    color: colors.text,
    fontSize: font.h3,
    textAlign: 'left',
    writingDirection: 'ltr',
  },
  codeInput: {
    minHeight: 62,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.bg,
    color: colors.text,
    fontSize: font.h1,
    letterSpacing: 10,
    textAlign: 'center',
    writingDirection: 'ltr',
  },
  feedback: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderRadius: radius.md },
  errorFeedback: { backgroundColor: colors.dangerSoft },
  noticeFeedback: { backgroundColor: colors.successSoft },
  feedbackText: { flex: 1, fontSize: font.small, lineHeight: 19 },
  codeLink: { minHeight: 38, alignItems: 'center', justifyContent: 'center' },
  codeLinkText: { color: colors.text, fontSize: font.small, fontWeight: '700', textDecorationLine: 'underline' },
  secureNote: {
    marginTop: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  secureText: { color: colors.subtle, fontSize: font.small, lineHeight: 19, flexShrink: 1 },
})
