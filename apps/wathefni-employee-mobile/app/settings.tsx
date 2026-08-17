import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Linking } from 'react-native'
import { useRouter } from 'expo-router'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import Constants from 'expo-constants'
import * as Notifications from 'expo-notifications'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import {
  errorFeedback,
  selectionFeedback,
  successFeedback,
  warningFeedback,
} from '@/native/haptics'
import type { DeviceSecurityResponse } from '@/api/types'
import { PUSH_REGISTRATION_ENABLED, registerForPushToken } from '@/push/registerForPush'
import { isPushOptedOut, setPushOptedOut } from '@/push/preferences'
import { syncInboxBadge } from '@/push/syncInboxBadge'
import { SettingsView } from '@/features/remaining/RemainingViews'
import { SwitchToHrControl } from '@/principals/SwitchToHrControl'
import { usePrincipalGate } from '@/principals/PrincipalGate'

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
  const { refreshAvailability } = usePrincipalGate()
  const onBack = useEmployeeSafeBack()
  const [pushOn, setPushOn] = useState(false)
  const [pushBusy, setPushBusy] = useState(false)
  const [biometricBusy, setBiometricBusy] = useState(false)
  const [autoLockBusy, setAutoLockBusy] = useState(false)
  const [deletionBusy, setDeletionBusy] = useState(false)
  const [deletionRequested, setDeletionRequested] = useState(false)
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
    if (PUSH_REGISTRATION_ENABLED) {
      void Promise.all([Notifications.getPermissionsAsync(), isPushOptedOut()]).then(([p, optedOut]) => {
        const permitted = p.granted || p.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
        setPushOn(permitted && !optedOut)
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
    selectionFeedback()
    setPushBusy(true)
    try {
      if (next) {
        // Manage/enable — clear opt-out and register; OS dialog only if needed.
        await setPushOptedOut(false)
        const result = await registerForPushToken({ requestPermission: true })
        if (!result) {
          setPushOn(false)
          const permission = await Notifications.getPermissionsAsync()
          warningFeedback()
          Alert.alert(t('settings.push'), t('settings.pushDenied'), [
            { text: t('common.cancel'), style: 'cancel' },
            ...(!permission.canAskAgain
              ? [{ text: t('onboarding.openSettings'), onPress: () => void Linking.openSettings() }]
              : []),
          ])
          return
        }
        await request('/app/push/register', { method: 'POST', json: { push_token: result.token, platform: result.platform } })
        setPushOn(true)
        successFeedback()
      } else {
        await request('/app/push/unregister', { method: 'POST', json: {} })
        await setPushOptedOut(true)
        await syncInboxBadge(0)
        setPushOn(false)
      }
    } catch (err) {
      errorFeedback()
      Alert.alert(t('common.error'), approvedErrorMessage(err, t))
    } finally {
      setPushBusy(false)
    }
  }

  const toggleBiometric = async (next: boolean) => {
    selectionFeedback()
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
    selectionFeedback()
    setAutoLockBusy(true)
    try {
      await setAutoLockTimeout(next)
    } finally {
      setAutoLockBusy(false)
    }
  }

  const onSignOutDevice = () => {
    warningFeedback()
    Alert.alert(t('deviceSecurity.signOutConfirmTitle'), t('deviceSecurity.signOutConfirmBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('deviceSecurity.signOutDevice'),
        style: 'destructive',
        onPress: () => {
          void signOut().then(() => refreshAvailability())
        },
      },
    ])
  }

  const onRequestDeletion = () => {
    if (!canRequestDeletion || deletionLock.current) return
    warningFeedback()
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
            successFeedback()
            Alert.alert(t('settings.deleteRequested'))
          } catch (err) {
            deletionLock.current = false
            errorFeedback()
            Alert.alert(t('common.error'), approvedErrorMessage(err, t))
          } finally {
            setDeletionBusy(false)
          }
        },
      },
    ])
  }

  return (
    <>
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
        deviceSecurity={deviceSecurity}
        deviceSecurityLoading={deviceSecurityLoading}
        version={Constants.expoConfig?.version ?? '—'}
        onLocale={(code) => {
          selectionFeedback()
          void setLocale(code, { resumeUnlockedSession: status === 'signedIn' })
        }}
        onTogglePush={(next) => void togglePush(next)}
        onToggleBiometric={(next) => void toggleBiometric(next)}
        onAutoLockTimeout={(next) => void onAutoLockTimeout(next)}
        onPrivacySupport={() => router.push('/privacy-support')}
        onChangePin={pinEnabled ? () => router.push('/change-pin') : undefined}
        onSignOutDevice={onSignOutDevice}
        onDelete={canRequestDeletion ? onRequestDeletion : undefined}
        deleteBusy={deletionBusy || deletionRequested}
        onRetryDeviceSecurity={() => void loadDeviceSecurity()}
        onBack={onBack}
      />
      <SwitchToHrControl />
    </>
  )
}
