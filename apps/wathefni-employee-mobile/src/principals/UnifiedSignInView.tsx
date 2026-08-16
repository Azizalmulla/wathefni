import { useEffect, useState } from 'react'
import {
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { useRouter } from 'expo-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { keyboardSafeBehavior } from '@/components/keyboardSafe'
import { AuthProvider, useAuth } from '@/auth/AuthProvider'
import { ActivationView } from '@/features/activation/ActivationView'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { ApiError, rawRequest } from '@hr/api/client'
import type { AuthResponse } from '@hr/api/types'
import { saveOperatorSession } from '@hr/auth/session'
import { EditorialHeading, FadeIn, PremiumButton, Wordmark } from '@/components/premium'
import { colors, font, layout, radius, spacing } from '@/theme'
import { usePrincipalGate } from './PrincipalGate'
import { savePrincipalModePreference } from './mode'

type SignInMethod = 'phone' | 'work_email'

const unsignedQueryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})

/**
 * Single Wathefni sign-in entry.
 *
 * Two *methods* (phone OTP vs work email/password) — not two apps / principals
 * in the copy. The method is chosen by the user; we never probe identity tables
 * or guess from email/phone matching.
 */
export function UnsignedEntry() {
  return (
    <QueryClientProvider client={unsignedQueryClient}>
      <AuthProvider>
        <UnifiedSignInHost />
      </AuthProvider>
    </QueryClientProvider>
  )
}

function UnifiedSignInHost() {
  const { status, activate, requestCode } = useAuth()
  const { selectMode, refreshAvailability } = usePrincipalGate()
  const router = useRouter()
  const { t } = useI18n()
  const [method, setMethod] = useState<SignInMethod>('phone')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [company, setCompany] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [hrBusy, setHrBusy] = useState(false)
  const [hrError, setHrError] = useState<string | null>(null)

  // Returning path: employee session just established via activate → open Employee shell.
  useEffect(() => {
    if (status !== 'signedIn') return
    void (async () => {
      await savePrincipalModePreference('employee')
      await selectMode('employee')
      await refreshAvailability()
    })()
  }, [status, selectMode, refreshAvailability])

  const onRequestCode = async () => {
    setError(null)
    setBusy(true)
    try {
      await requestCode(phone.trim())
      setNotice(t('auth.codeSent'))
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  const onPhoneSignIn = async () => {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await activate(phone.trim(), code.trim())
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  const onWorkEmailSignIn = async () => {
    setHrBusy(true)
    setHrError(null)
    try {
      const response = await rawRequest<AuthResponse>('/dashboard/mobile/auth/login', {
        method: 'POST',
        json: {
          email: email.trim(),
          password,
          company_code: company.trim().toUpperCase(),
        },
      })
      await saveOperatorSession({
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        companyCode: response.me.principal.company_code,
        expiresAt: response.expires_at,
      })
      await savePrincipalModePreference('hr')
      // Land on /hr before swapping shells so Slot never mounts Employee routes
      // on `/` (which previously resolved `(tabs)` without AuthProvider).
      router.replace('/hr')
      await selectMode('hr')
      await refreshAvailability()
    } catch (caught) {
      setHrError(
        caught instanceof ApiError && caught.code === 'rate_limited'
          ? caught.message
          : caught instanceof ApiError && caught.code === 'network_error'
            ? t('auth.offline')
            : t('auth.workEmailError'),
      )
    } finally {
      setHrBusy(false)
    }
  }

  if (method === 'phone') {
    return (
      <ActivationView
        headerSlot={<MethodSwitch method={method} onChange={setMethod} />}
        phone={phone}
        code={code}
        busy={busy}
        error={error}
        notice={notice}
        onPhoneChange={(value) => {
          setPhone(value)
          setError(null)
          setNotice(null)
        }}
        onCodeChange={(value) => {
          setCode(value)
          setError(null)
        }}
        onSignIn={() => void onPhoneSignIn()}
        onRequestCode={() => void onRequestCode()}
      />
    )
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={keyboardSafeBehavior()} style={styles.flex}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          showsVerticalScrollIndicator={false}
        >
          <MethodSwitch method={method} onChange={setMethod} />
          <View style={styles.wordmarkRow}>
            <Wordmark />
          </View>
          <FadeIn style={styles.hero}>
            <Text style={styles.eyebrow}>{t('auth.workEmailEyebrow')}</Text>
            <EditorialHeading>{t('auth.welcomeTitle')}</EditorialHeading>
            <Text style={styles.subtitle}>{t('auth.workEmailSubtitle')}</Text>
          </FadeIn>
          <View style={styles.form}>
            <Field
              testID="e2e.auth.hr.company"
              label={t('auth.companyCode')}
              value={company}
              onChange={setCompany}
              autoCapitalize="characters"
            />
            <Field
              testID="e2e.auth.hr.email"
              label={t('auth.workEmail')}
              value={email}
              onChange={setEmail}
              keyboardType="email-address"
            />
            <Field
              testID="e2e.auth.hr.password"
              label={t('auth.password')}
              value={password}
              onChange={setPassword}
              secure
            />
            {hrError ? (
              <Text
                accessibilityRole="alert"
                style={styles.error}
                testID="e2e.auth.hr.error"
                accessibilityLabel={hrError}
              >
                {hrError}
              </Text>
            ) : null}
            <PremiumButton
              testID="e2e.auth.hr.signIn"
              label={t('auth.signIn')}
              busy={hrBusy}
              disabled={!email.trim() || password.length < 1 || !company.trim() || hrBusy}
              onPress={() => void onWorkEmailSignIn()}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function MethodSwitch({
  method,
  onChange,
}: {
  method: SignInMethod
  onChange: (next: SignInMethod) => void
}) {
  const { t, isRTL } = useI18n()
  return (
    <View style={[styles.switchWrap, { direction: isRTL ? 'rtl' : 'ltr' }]}>
      <View style={styles.switchRow} testID="e2e.auth.methodSwitch">
        <Pressable
          testID="e2e.auth.method.phone"
          accessibilityRole="button"
          accessibilityState={{ selected: method === 'phone' }}
          onPress={() => onChange('phone')}
          style={[styles.switchChip, method === 'phone' && styles.switchChipOn]}
        >
          <Text style={[styles.switchText, method === 'phone' && styles.switchTextOn]}>
            {t('auth.methodPhone')}
          </Text>
        </Pressable>
        <Pressable
          testID="e2e.auth.method.workEmail"
          accessibilityRole="button"
          accessibilityState={{ selected: method === 'work_email' }}
          onPress={() => onChange('work_email')}
          style={[styles.switchChip, method === 'work_email' && styles.switchChipOn]}
        >
          <Text style={[styles.switchText, method === 'work_email' && styles.switchTextOn]}>
            {t('auth.methodWorkEmail')}
          </Text>
        </Pressable>
      </View>
    </View>
  )
}

function Field({
  label,
  value,
  onChange,
  secure,
  keyboardType,
  autoCapitalize = 'none',
  testID,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  secure?: boolean
  keyboardType?: 'email-address'
  autoCapitalize?: 'none' | 'characters'
  testID?: string
}) {
  const { isRTL } = useI18n()
  return (
    <View style={styles.field}>
      <Text style={[styles.label, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
      <TextInput
        testID={testID}
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        spellCheck={false}
        textContentType="none"
        autoComplete="off"
        importantForAutofill="no"
        style={[
          styles.input,
          { textAlign: isRTL ? 'right' : 'left', writingDirection: isRTL ? 'rtl' : 'ltr' },
        ]}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  safe: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: layout.focusMargin,
    paddingBottom: spacing.xxxl,
    gap: spacing.lg,
  },
  switchWrap: {
    marginBottom: spacing.sm,
  },
  switchRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.lg,
    padding: 4,
  },
  switchChip: {
    flex: 1,
    minHeight: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
  },
  switchChipOn: { backgroundColor: colors.surface },
  switchText: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  switchTextOn: { color: colors.ink },
  wordmarkRow: { marginTop: spacing.md },
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  form: { gap: spacing.md },
  field: { gap: spacing.xs },
  label: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    color: colors.ink,
    fontSize: font.body,
  },
  error: { color: colors.danger, fontSize: font.small, lineHeight: 18 },
})
