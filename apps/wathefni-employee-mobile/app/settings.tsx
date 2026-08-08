import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Linking } from 'react-native'
import { useRouter } from 'expo-router'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'

import { useAuth } from '@/auth/AuthProvider'
import {
  getAutoLockDiagnostics,
  subscribeAutoLockDiagnostics,
  type AutoLockDiagnostics,
} from '@/auth/autoLockDiagnostics'
import { isAutoLockDiagnosticsEnabled } from '@/auth/autoLockPolicy'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import type { DeviceSecurityResponse } from '@/api/types'
import { PUSH_REGISTRATION_ENABLED, registerForPushToken } from '@/push/registerForPush'
import { loadPushPreference, savePushPreference } from '@/push/preferences'
import { SettingsView } from '@/features/remaining/RemainingViews'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const {
    request,
    can,
    pinEnabled,
    status,
    signOut,
    biometricEnabled,
    biometricPreferenceOn,
    biometricKind,
    setBiometricUnlockEnabled,
    autoLockEnabled,
    autoLockTimeoutMs,
    setAutoLockTimeout,
  } = useAuth()
  const router = useRouter()
  const [pushOn, setPushOn] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)
  const [biometricBusy, setBiometricBusy] = useState(false)
  const [autoLockBusy, setAutoLockBusy] = useState(false)
  const [deletionBusy, setDeletionBusy] = useState(false)
  const [deletionRequested, setDeletionRequested] = useState(false)
  const [autoLockDiag, setAutoLockDiag] = useState<AutoLockDiagnostics>(() => getAutoLockDiagnostics())
  const [deviceSecurity, setDeviceSecurity] = useState<{
    platform: string
    activatedAt: string | null
    lastActiveAt: string | null
    status: string
  } | null>(null)
  const [deviceSecurityLoading, setDeviceSecurityLoading] = useState(true)
  const deletionLock = useRef(false)
  const canRequestDeletion = can('settings', 'request_deletion')

  useEffect(() => {
    setAutoLockDiag(getAutoLockDiagnostics())
    return subscribeAutoLockDiagnostics(() => setAutoLockDiag(getAutoLockDiagnostics()))
  }, [])

  useEffect(() => {
    if (PUSH_REGISTRATION_ENABLED) {
      void Promise.all([Notifications.getPermissionsAsync(), loadPushPreference()]).then(([p, preferred]) => {
        const permitted = p.granted || p.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
        setPushOn(permitted && preferred)
      })
    }
  }, [])

  const loadDeviceSecurity = useCallback(async () => {
    setDeviceSecurityLoading(true)
    try {
      const res = await request<DeviceSecurityResponse>('/app/device-security')
      setDeviceSecurity({
        platform: String(res.device?.platform || 'unknown'),
        activatedAt: res.device?.activated_at || null,
        lastActiveAt: res.device?.last_active_at || null,
        status: String(res.device?.status || 'active'),
      })
    } catch {
      setDeviceSecurity(null)
    } finally {
      setDeviceSecurityLoading(false)
    }
  }, [request])

  useEffect(() => {
    void loadDeviceSecurity()
  }, [loadDeviceSecurity])

  const biometricLabel =
    biometricKind === 'face'
      ? t('biometric.settingsFace')
      : biometricKind === 'fingerprint'
        ? t('biometric.settingsFingerprint')
        : t('biometric.settings')

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

  const toggleBiometric = async (next: boolean) => {
    setBiometricBusy(true)
    try {
      await setBiometricUnlockEnabled(next, {
        promptMessage: t('biometric.unlockPrompt'),
        cancelLabel: t('common.cancel'),
      })
      // Cancel / unavailable: leave preference off silently — PIN remains the fallback.
    } finally {
      setBiometricBusy(false)
    }
  }

  const onAutoLockTimeout = async (next: typeof autoLockTimeoutMs) => {
    if (next === autoLockTimeoutMs || autoLockBusy) return
    setAutoLockBusy(true)
    try {
      await setAutoLockTimeout(next)
    } finally {
      setAutoLockBusy(false)
    }
  }

  const onSignOutDevice = () => {
    Alert.alert(t('deviceSecurity.signOutConfirmTitle'), t('deviceSecurity.signOutConfirmBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('deviceSecurity.signOutDevice'),
        style: 'destructive',
        onPress: () => {
          void signOut()
        },
      },
    ])
  }

  const onRequestDeletion = () => {
    if (!canRequestDeletion || deletionLock.current) return
    Alert.alert(t('settings.deleteAccount'), t('settings.deleteAccountConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('settings.deleteAccount'),
        style: 'destructive',
        onPress: async () => {
          if (deletionLock.current) return
          deletionLock.current = true
          setDeletionBusy(true)
          try {
            await request('/app/account/request-deletion', { method: 'POST', json: {} })
            setDeletionRequested(true)
            Alert.alert(t('settings.deleteRequested'))
          } catch (err) {
            deletionLock.current = false
            Alert.alert(t('common.error'), approvedErrorMessage(err, t))
          } finally {
            setDeletionBusy(false)
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
      canChangePin={pinEnabled}
      canManageBiometric={biometricEnabled}
      biometricOn={biometricPreferenceOn}
      biometricBusy={biometricBusy}
      biometricLabel={biometricLabel}
      canManageAutoLock={autoLockEnabled}
      autoLockTimeoutMs={autoLockTimeoutMs}
      autoLockBusy={autoLockBusy}
      autoLockDiagnostics={pinEnabled && isAutoLockDiagnosticsEnabled() ? autoLockDiag : null}
      deviceSecurity={deviceSecurity}
      deviceSecurityLoading={deviceSecurityLoading}
      version={Constants.expoConfig?.version ?? '—'}
      onLocale={(code) => {
        void setLocale(code, { resumeUnlockedSession: status === 'signedIn' })
      }}
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
      onToggleBiometric={(next) => void toggleBiometric(next)}
      onAutoLockTimeout={(next) => void onAutoLockTimeout(next)}
      onPrivacySupport={() => router.push('/privacy-support')}
      onChangePin={pinEnabled ? () => router.push('/change-pin') : undefined}
      onSignOutDevice={onSignOutDevice}
      onDelete={canRequestDeletion ? onRequestDeletion : undefined}
      deleteBusy={deletionBusy || deletionRequested}
      onRetryDeviceSecurity={() => void loadDeviceSecurity()}
      onBack={() => router.back()}
    />
  )
}
