import { useState } from 'react'
import { StyleSheet, Text, TextInput, View } from 'react-native'

import { ApiError } from '@hr/api/client'
import { useLocale } from '@hr/i18n'
import { ActionButton, EditorialHeading, Screen, Wordmark } from '@hr/components/primitives'
import { colors, radius, spacing, type as typography } from '@hr/theme'

export function SignInView({
  onSignIn,
}: {
  onSignIn: (email: string, password: string, companyCode: string) => Promise<void>
}) {
  const { t, isRTL, locale, setLocale } = useLocale()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setLoading(true)
    setError(null)
    try {
      await onSignIn(email.trim(), password, company.trim())
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === 'rate_limited'
          ? caught.message
          : caught instanceof ApiError && caught.code === 'network_error'
            ? t('state.offlineBody')
            : t('auth.genericError'),
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Screen contentStyle={styles.screen}>
      <View style={styles.brandRow}>
        <Wordmark />
        <ActionButton
          label={locale === 'ar' ? 'EN' : 'ع'}
          tone="secondary"
          onPress={() => void setLocale(locale === 'ar' ? 'en' : 'ar')}
        />
      </View>
      <EditorialHeading>{t('auth.title')}</EditorialHeading>
      <Text style={[styles.subtitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('auth.subtitle')}</Text>
      <View style={styles.form} testID="e2e.auth.hr.routeSignIn">
        <Field testID="e2e.auth.hr.company" label={t('auth.company')} value={company} onChange={setCompany} autoCapitalize="characters" isRTL={isRTL} />
        <Field testID="e2e.auth.hr.email" label={t('auth.email')} value={email} onChange={setEmail} keyboardType="email-address" isRTL={isRTL} />
        <Field testID="e2e.auth.hr.password" label={t('auth.password')} value={password} onChange={setPassword} secure isRTL={isRTL} />
        {error ? <Text accessibilityRole="alert" style={[styles.error, { textAlign: isRTL ? 'right' : 'left' }]}>{error}</Text> : null}
        <ActionButton
          label={t('auth.signIn')}
          loading={loading}
          disabled={!email.trim() || password.length < 1 || !company.trim()}
          onPress={() => void submit()}
          testID="e2e.auth.hr.signIn"
        />
      </View>
    </Screen>
  )
}

function Field({
  label,
  value,
  onChange,
  secure,
  keyboardType,
  autoCapitalize = 'none',
  isRTL,
  testID,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  secure?: boolean
  keyboardType?: 'email-address'
  autoCapitalize?: 'none' | 'characters'
  isRTL: boolean
  testID?: string
}) {
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
        style={[styles.input, { textAlign: isRTL ? 'right' : 'left', writingDirection: isRTL ? 'rtl' : 'ltr' }]}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { justifyContent: 'center', minHeight: 720 },
  brandRow: { gap: spacing.md },
  subtitle: { color: colors.muted, fontSize: typography.body, lineHeight: 23 },
  form: { gap: spacing.lg, backgroundColor: colors.surface, padding: spacing.xl, borderRadius: radius.xl, borderWidth: 1, borderColor: colors.line },
  field: { gap: spacing.sm },
  label: { color: colors.ink, fontSize: typography.label, fontWeight: '800' },
  input: { minHeight: 52, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surfaceStrong, paddingHorizontal: spacing.md, color: colors.ink, fontSize: typography.body },
  error: { color: colors.danger, fontSize: typography.label, lineHeight: 19 },
})
