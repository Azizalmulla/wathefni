import { useEffect, useState } from 'react'
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { Card, SectionTitle } from '@/components/ui'
import { approvedErrorMessage } from '@/api/errors'
import { registerForPushToken } from '@/push/registerForPush'
import { PRIVACY_URL } from '@/config'
import { colors, font, radius, spacing } from '@/theme'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const { request, can } = useAuth()
  const [pushOn, setPushOn] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)

  useEffect(() => {
    void Notifications.getPermissionsAsync().then((p) => setPushOn(p.granted))
  }, [])

  const togglePush = async (next: boolean) => {
    setPushBusy(true)
    try {
      if (next) {
        const result = await registerForPushToken()
        if (!result) {
          setPushOn(false)
          Alert.alert(t('settings.push'), t('common.error'))
          return
        }
        await request('/app/push/register', { method: 'POST', json: { push_token: result.token, platform: result.platform } })
        setPushOn(true)
      } else {
        await request('/app/push/unregister', { method: 'POST', json: {} })
        setPushOn(false)
      }
    } catch (err) {
      Alert.alert(t('common.error'), approvedErrorMessage(err, t))
    } finally {
      setPushBusy(false)
    }
  }

  const onRequestDeletion = () => {
    Alert.alert(t('settings.deleteAccount'), t('settings.deleteAccountConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('settings.deleteAccount'),
        style: 'destructive',
        onPress: async () => {
          try {
            await request('/app/account/request-deletion', { method: 'POST', json: {} })
            Alert.alert(t('settings.deleteRequested'))
          } catch (err) {
            Alert.alert(t('common.error'), approvedErrorMessage(err, t))
          }
        },
      },
    ])
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <SectionTitle>{t('settings.language')}</SectionTitle>
      <Card>
        <View style={styles.segment}>
          {(['en', 'ar'] as const).map((code) => (
            <Pressable
              key={code}
              style={[styles.segmentItem, locale === code && styles.segmentItemActive]}
              onPress={() => void setLocale(code)}
              accessibilityRole="button"
            >
              <Text style={[styles.segmentText, locale === code && styles.segmentTextActive]}>
                {t(code === 'en' ? 'settings.english' : 'settings.arabic')}
              </Text>
            </Pressable>
          ))}
        </View>
      </Card>

      {can('settings', 'manage_push') ? (
        <>
          <SectionTitle>{t('settings.push')}</SectionTitle>
          <Card>
            <View style={styles.rowBetween}>
              <Text style={styles.rowText}>{t('settings.push')}</Text>
              <Switch value={pushOn} onValueChange={togglePush} disabled={pushBusy} />
            </View>
          </Card>
        </>
      ) : null}

      <Card>
        <Pressable style={styles.linkRow} onPress={() => void Linking.openURL(PRIVACY_URL)} accessibilityRole="link">
          <Text style={styles.rowText}>{t('settings.privacy')}</Text>
          <Text style={styles.chevron}>›</Text>
        </Pressable>
        <Pressable style={styles.linkRow} onPress={onRequestDeletion} accessibilityRole="button">
          <Text style={[styles.rowText, { color: colors.danger }]}>{t('settings.deleteAccount')}</Text>
          <Text style={styles.chevron}>›</Text>
        </Pressable>
      </Card>

      <Text style={styles.version}>
        {t('settings.version')} {Constants.expoConfig?.version ?? '—'}
      </Text>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  segment: { flexDirection: 'row', backgroundColor: colors.chip, borderRadius: radius.md, padding: 4, gap: 4 },
  segmentItem: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.sm, alignItems: 'center' },
  segmentItemActive: { backgroundColor: colors.surface },
  segmentText: { fontSize: font.body, color: colors.subtle, fontWeight: '600' },
  segmentTextActive: { color: colors.text },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rowText: { fontSize: font.body, color: colors.text },
  linkRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.sm },
  chevron: { fontSize: font.h2, color: colors.subtle },
  version: { fontSize: font.tiny, color: colors.subtle, textAlign: 'center', marginTop: spacing.md },
})
