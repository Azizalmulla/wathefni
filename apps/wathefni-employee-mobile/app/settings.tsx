import { useEffect, useState } from 'react'
import { Alert } from 'react-native'
import { useRouter } from 'expo-router'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { registerForPushToken } from '@/push/registerForPush'
import { SettingsView } from '@/features/remaining/RemainingViews'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const { request, can } = useAuth()
  const router = useRouter()
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
    <SettingsView
      locale={locale}
      pushOn={pushOn}
      pushBusy={pushBusy}
      canManagePush={can('settings', 'manage_push')}
      version={Constants.expoConfig?.version ?? '—'}
      onLocale={(code) => void setLocale(code)}
      onTogglePush={(next) => void togglePush(next)}
      onPrivacySupport={() => router.push('/privacy-support')}
      onDelete={onRequestDeletion}
    />
  )
}
