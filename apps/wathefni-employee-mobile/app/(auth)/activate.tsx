import { useState } from 'react'
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { Button } from '@/components/ui'
import { approvedErrorMessage } from '@/api/errors'
import { colors, font, radius, spacing } from '@/theme'

export default function ActivateScreen() {
  const { t, isRTL } = useI18n()
  const { activate, requestCode } = useAuth()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onSignIn = async () => {
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

  const align = { textAlign: isRTL ? 'right' : 'left' } as const

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={[styles.brand, align]}>{t('app.name')}</Text>
          <Text style={[styles.title, align]}>{t('auth.title')}</Text>
          <Text style={[styles.subtitle, align]}>{t('auth.subtitle')}</Text>

          <View style={styles.field}>
            <Text style={[styles.label, align]}>{t('auth.phone')}</Text>
            <TextInput
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              autoComplete="tel"
              style={[styles.input, align]}
              placeholder="9XXXXXXX"
              placeholderTextColor={colors.subtle}
            />
          </View>

          <View style={styles.field}>
            <Text style={[styles.label, align]}>{t('auth.code')}</Text>
            <TextInput
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              maxLength={6}
              style={[styles.input, styles.codeInput]}
              placeholder="••••••"
              placeholderTextColor={colors.subtle}
            />
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}
          {notice ? <Text style={styles.notice}>{notice}</Text> : null}

          <Button label={t('auth.signIn')} onPress={onSignIn} busy={busy} disabled={!phone.trim() || code.trim().length < 4} />
          <View style={styles.gap} />
          <Button label={t('auth.requestCode')} variant="secondary" onPress={onRequestCode} disabled={busy || !phone.trim()} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  content: { padding: spacing.xl, gap: spacing.md, flexGrow: 1, justifyContent: 'center' },
  brand: { fontSize: font.h1, fontWeight: '800', color: colors.primary, marginBottom: spacing.sm },
  title: { fontSize: font.h2, fontWeight: '700', color: colors.text },
  subtitle: { fontSize: font.body, color: colors.subtle, marginBottom: spacing.md },
  field: { gap: spacing.xs },
  label: { fontSize: font.small, color: colors.subtle, fontWeight: '600' },
  input: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: font.body,
    color: colors.text,
    minHeight: 50,
  },
  codeInput: { letterSpacing: 8, textAlign: 'center', fontSize: font.h2 },
  error: { color: colors.danger, fontSize: font.small },
  notice: { color: colors.success, fontSize: font.small },
  gap: { height: spacing.xs },
})
