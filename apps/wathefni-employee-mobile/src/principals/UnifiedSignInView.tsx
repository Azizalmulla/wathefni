import { useEffect, useRef, useState } from 'react'
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

import { keyboardSafeBehavior } from '@/components/keyboardSafe'
import { useAuth } from '@/auth/AuthProvider'
import { rawRequest as publicRawRequest } from '@/api/client'
import { ActivationView } from '@/features/activation/ActivationView'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { ApiError, rawRequest as hrRawRequest } from '@hr/api/client'
import type { AuthResponse } from '@hr/api/types'
import { saveOperatorSession } from '@hr/auth/session'
import { EditorialHeading, FadeIn, PremiumButton, Wordmark } from '@/components/premium'
import { colors, font, layout, radius, spacing } from '@/theme'
import { usePrincipalGate } from './PrincipalGate'

type SignInMethod = 'phone' | 'work_email' | 'store_review'
type ReviewPrincipal = 'employee' | 'hr'

const EMPLOYEE_SHELL_AUTH_STATES = new Set([
  'needsPinSetup',
  'needsBiometricOptIn',
  'locked',
  'signedIn',
])

/**
 * Single Wathefni sign-in entry.
 *
 * Two *methods* (phone OTP vs work email/password) — not two apps / principals
 * in the copy. The method is chosen by the user; we never probe identity tables
 * or guess from email/phone matching.
 */
export function UnsignedEntry() {
  return <UnifiedSignInHost />
}

function UnifiedSignInHost() {
  const { status, activate, reviewSignIn, requestCode } = useAuth()
  const { selectMode } = usePrincipalGate()
  const { t } = useI18n()
  const [method, setMethod] = useState<SignInMethod>('phone')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const activationInFlightRef = useRef(false)
  const employeeHandoffInFlightRef = useRef(false)

  const [company, setCompany] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [hrBusy, setHrBusy] = useState(false)
  const [hrError, setHrError] = useState<string | null>(null)
  const [reviewAvailable, setReviewAvailable] = useState(false)
  const [reviewPrincipal, setReviewPrincipal] = useState<ReviewPrincipal>('employee')
  const [reviewUsername, setReviewUsername] = useState('')
  const [reviewPassword, setReviewPassword] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void publicRawRequest<{ available?: boolean }>('/auth/store-review-availability')
      .then((response) => {
        if (active) setReviewAvailable(response.available === true)
      })
      .catch(() => {
        if (active) setReviewAvailable(false)
      })
    return () => {
      active = false
    }
  }, [])

  // A verified Employee session may still need local PIN/biometric setup or unlock.
  // Mount EmployeeShell for every post-auth state so its AuthGate owns those screens.
  useEffect(() => {
    if (!EMPLOYEE_SHELL_AUTH_STATES.has(status) || employeeHandoffInFlightRef.current) return
    employeeHandoffInFlightRef.current = true
    void (async () => {
      try {
        const switched = await selectMode('employee')
        if (!switched) setError(t('principal.transitionError'))
      } finally {
        employeeHandoffInFlightRef.current = false
      }
    })()
  }, [status, selectMode, t])

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
    if (activationInFlightRef.current) return
    activationInFlightRef.current = true
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await activate(phone.trim(), code.trim())
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      activationInFlightRef.current = false
      setBusy(false)
    }
  }

  const onWorkEmailSignIn = async () => {
    setHrBusy(true)
    setHrError(null)
    try {
      const response = await hrRawRequest<AuthResponse>('/dashboard/mobile/auth/login', {
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
      const switched = await selectMode('hr')
      if (!switched) setHrError(t('principal.transitionError'))
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

  const onStoreReviewSignIn = async () => {
    if (reviewBusy) return
    setReviewBusy(true)
    setReviewError(null)
    try {
      if (reviewPrincipal === 'employee') {
        await reviewSignIn(reviewUsername.trim(), reviewPassword)
        return
      }
      const response = await hrRawRequest<AuthResponse>('/dashboard/mobile/auth/store-review-login', {
        method: 'POST',
        json: { username: reviewUsername.trim(), password: reviewPassword },
      })
      await saveOperatorSession({
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        companyCode: response.me.principal.company_code,
        expiresAt: response.expires_at,
      })
      const switched = await selectMode('hr')
      if (!switched) setReviewError(t('principal.transitionError'))
    } catch (caught) {
      setReviewError(
        caught instanceof ApiError && caught.code === 'network_error'
          ? t('auth.offline')
          : t('auth.storeReviewError'),
      )
    } finally {
      setReviewBusy(false)
    }
  }

  if (method === 'phone') {
    return (
      <ActivationView
        headerSlot={<MethodSwitch method={method} onChange={setMethod} reviewAvailable={reviewAvailable} />}
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

  if (method === 'store_review' && reviewAvailable) {
    return (
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView behavior={keyboardSafeBehavior()} style={styles.flex}>
          <ScrollView
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="interactive"
            showsVerticalScrollIndicator={false}
          >
            <MethodSwitch method={method} onChange={setMethod} reviewAvailable={reviewAvailable} />
            <View style={styles.wordmarkRow}>
              <Wordmark />
            </View>
            <FadeIn style={styles.hero}>
              <Text style={styles.eyebrow}>{t('auth.storeReviewEyebrow')}</Text>
              <EditorialHeading>{t('auth.storeReviewTitle')}</EditorialHeading>
              <Text style={styles.subtitle}>{t('auth.storeReviewSubtitle')}</Text>
            </FadeIn>
            <View style={styles.form}>
              <View style={styles.switchRow} testID="e2e.auth.review.principalSwitch">
                {(['employee', 'hr'] as ReviewPrincipal[]).map((principal) => (
                  <Pressable
                    key={principal}
                    testID={`e2e.auth.review.principal.${principal}`}
                    accessibilityRole="button"
                    accessibilityState={{ selected: reviewPrincipal === principal }}
                    onPress={() => setReviewPrincipal(principal)}
                    style={[styles.switchChip, reviewPrincipal === principal && styles.switchChipOn]}
                  >
                    <Text style={[styles.switchText, reviewPrincipal === principal && styles.switchTextOn]}>
                      {t(principal === 'employee' ? 'auth.employeeApp' : 'auth.hrWorkspace')}
                    </Text>
                  </Pressable>
                ))}
              </View>
              <Field
                testID="e2e.auth.review.username"
                label={t('auth.reviewUsername')}
                value={reviewUsername}
                onChange={setReviewUsername}
                keyboardType="email-address"
              />
              <Field
                testID="e2e.auth.review.password"
                label={t('auth.password')}
                value={reviewPassword}
                onChange={setReviewPassword}
                secure
              />
              {reviewError ? (
                <Text accessibilityRole="alert" style={styles.error} testID="e2e.auth.review.error">
                  {reviewError}
                </Text>
              ) : null}
              <PremiumButton
                testID="e2e.auth.review.signIn"
                label={t('auth.signIn')}
                busy={reviewBusy}
                disabled={!reviewUsername.trim() || !reviewPassword || reviewBusy}
                onPress={() => void onStoreReviewSignIn()}
              />
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
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
          <MethodSwitch method={method} onChange={setMethod} reviewAvailable={reviewAvailable} />
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
  reviewAvailable = false,
}: {
  method: SignInMethod
  onChange: (next: SignInMethod) => void
  reviewAvailable?: boolean
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
        {reviewAvailable ? (
          <Pressable
            testID="e2e.auth.method.storeReview"
            accessibilityRole="button"
            accessibilityState={{ selected: method === 'store_review' }}
            onPress={() => onChange('store_review')}
            style={[styles.switchChip, method === 'store_review' && styles.switchChipOn]}
          >
            <Text style={[styles.switchText, method === 'store_review' && styles.switchTextOn]}>
              {t('auth.methodStoreReview')}
            </Text>
          </Pressable>
        ) : null}
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
          // Company codes, emails, and passwords are LTR credentials even in
          // Arabic UI. RTL writing direction can reorder secure Latin input.
          { textAlign: isRTL ? 'right' : 'left', writingDirection: 'ltr' },
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
