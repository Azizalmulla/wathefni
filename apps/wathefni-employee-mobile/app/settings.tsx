import { useEffect, useState } from 'react'
import { Alert, Linking } from 'react-native'
import { useRouter } from 'expo-router'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { PUSH_REGISTRATION_ENABLED, registerForPushToken } from '@/push/registerForPush'
import { loadPushPreference, savePushPreference } from '@/push/preferences'
import { SettingsView } from '@/features/remaining/RemainingViews'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const { request, can } = useAuth()
  const router = useRouter()
  const [pushOn, setPushOn] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)

  useEffect(() => {
    if (PUSH_REGISTRATION_ENABLED) {
      void Promise.all([Notifications.getPermissionsAsync(), loadPushPreference()]).then(([p, preferred]) => {
        const permitted = p.granted || p.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
        setPushOn(permitted && preferred)
      })
    }
  }, [])

  const togglePush = async (next: boolean) => {
    setPushBusy(true)
    try {
      if (next) {
        const result = await registerForPushToken({ requestPermission: true })
        if (!result) {
          setPushOn(false)
          const permission = await Notifications.getPermissionsAsync()
          Alert.alert(t('settings.push'), t('settings.pushDenied'), [
            { text: t('common.cancel'), style: 'cancel' },
            ...(!permission.canAskAgain
              ? [{ text: t('onboarding.openSettings'), onPress: () => void Linking.openSettings() }]
              : []),
          ])
          return
        }
        await request('/app/push/register', { method: 'POST', json: { push_token: result.token, platform: result.platform } })
        await savePushPreference(true)
        setPushOn(true)
      } else {
        await request('/app/push/unregister', { method: 'POST', json: {} })
        await savePushPreference(false)
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
      canManagePush={PUSH_REGISTRATION_ENABLED && can('settings', 'manage_push')}
      version={Constants.expoConfig?.version ?? '—'}
      onLocale={(code) => void setLocale(code)}
      onTogglePush={(next) => {
        if (!next) {
          void togglePush(false)
          return
        }
        Alert.alert(t('settings.push'), t('settings.pushRationale'), [
          { text: t('common.cancel'), style: 'cancel' },
          { text: t('common.continue'), onPress: () => void togglePush(true) },
        ])
      }}
      onPrivacySupport={() => router.push('/privacy-support')}
      onDelete={onRequestDeletion}
    />
  )
}
