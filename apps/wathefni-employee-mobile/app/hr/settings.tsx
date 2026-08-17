import { useState } from 'react'
import { Alert, Linking } from 'react-native'
import { useRouter } from 'expo-router'
import Constants from 'expo-constants'

import { useAuth } from '@hr/auth/AuthProvider'
import { SettingsView } from '@hr/features/settings/SettingsView'
import { useLocale as useHrLocale } from '@hr/i18n'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'
import { PRIVACY_URL, SUPPORT_URL } from '@/config'
import { usePrincipalGate } from '@/principals/PrincipalGate'
import { recordPrincipalDiagnostic } from '@/principals/principalDiagnostics'

/**
 * Settings route — operator + device session + local Device Security.
 * Locale toggles both app i18n stores so cream screens and leftover HR shells stay aligned.
 */
export default function SettingsRoute() {
  const {
    me,
    refreshMe,
    signOut,
    signOutAll,
    pinEnabled,
    biometricEnabled,
    biometricPreferenceOn,
    biometricKind,
    autoLockTimeoutMs,
    setAutoLockTimeout,
    setBiometricUnlockEnabled,
  } = useAuth()
  const { locale, setLocale, t } = useI18n()
  const { setLocale: setHrLocale } = useHrLocale()
  const {
    employeeSession,
    hrSession,
    transition,
    selectMode,
    clearTransitionError,
    refreshAvailability,
  } = usePrincipalGate()
  const router = useRouter()
  const onBack = useHrSafeBack()
  const [biometricBusy, setBiometricBusy] = useState(false)
  const [autoLockBusy, setAutoLockBusy] = useState(false)

  if (!me) return null

  const toggleLocale = async () => {
    const next = locale === 'ar' ? 'en' : 'ar'
    await Promise.all([setLocale(next), setHrLocale(next)])
  }

  const afterSignOut = async () => {
    await refreshAvailability()
  }

  const biometricLabel =
    biometricKind === 'face'
      ? t('biometric.settingsFace')
      : biometricKind === 'fingerprint'
        ? t('biometric.settingsFingerprint')
        : t('biometric.settings')

  const openExternal = async (url: string) => {
    try {
      await Linking.openURL(url)
    } catch {
      Alert.alert(t('common.error'), t('error.generic'))
    }
  }

  const openNotificationSettings = async () => {
    try {
      await Linking.openSettings()
    } catch {
      Alert.alert(t('common.error'), t('error.generic'))
    }
  }

  return (
    <SettingsView
      me={me}
      onBack={onBack}
      onToggleLocale={toggleLocale}
      onRefresh={async () => {
        await refreshMe()
      }}
      onSignOut={async () => {
        await signOut()
        await afterSignOut()
      }}
      onSignOutAll={async () => {
        await signOutAll()
        await afterSignOut()
      }}
      onOpenNotificationSettings={openNotificationSettings}
      onOpenPrivacy={() => openExternal(PRIVACY_URL)}
      onOpenSupport={() => openExternal(SUPPORT_URL)}
      onSwitchEmployee={() =>
        void (async () => {
          recordPrincipalDiagnostic({
            event: 'switch_tap',
            target: 'employee',
            employeeSession,
            hrSession,
          })
          clearTransitionError()
          await selectMode('employee')
        })()
      }
      principalSwitchBusy={transition.status === 'switching'}
      principalSwitchError={
        transition.status === 'error' && transition.to === 'employee'
          ? t('principal.transitionError')
          : null
      }
      pinEnabled={pinEnabled}
      biometricEnabled={biometricEnabled}
      biometricPreferenceOn={biometricPreferenceOn}
      biometricBusy={biometricBusy}
      biometricLabel={biometricLabel}
      onToggleBiometric={async (enable) => {
        setBiometricBusy(true)
        try {
          await setBiometricUnlockEnabled(enable, {
            promptMessage: t('biometric.unlockPrompt'),
            cancelLabel: t('common.cancel'),
          })
        } finally {
          setBiometricBusy(false)
        }
      }}
      autoLockTimeoutMs={autoLockTimeoutMs}
      autoLockBusy={autoLockBusy}
      onSelectAutoLock={async (value) => {
        setAutoLockBusy(true)
        try {
          await setAutoLockTimeout(value)
        } finally {
          setAutoLockBusy(false)
        }
      }}
      onChangePin={pinEnabled ? () => router.push('/hr/change-pin' as never) : undefined}
      version={Constants.expoConfig?.version ?? '—'}
    />
  )
}
