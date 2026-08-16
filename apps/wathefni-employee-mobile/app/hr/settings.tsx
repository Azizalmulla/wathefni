import { useState } from 'react'
import { useRouter } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { SettingsView } from '@hr/features/settings/SettingsView'
import { useLocale as useHrLocale } from '@hr/i18n'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'
import { usePrincipalGate } from '@/principals/PrincipalGate'

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
  const { employeeSession, selectMode, refreshAvailability } = usePrincipalGate()
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
    router.replace('/hr/sign-in')
  }

  const biometricLabel =
    biometricKind === 'face'
      ? t('biometric.settingsFace')
      : biometricKind === 'fingerprint'
        ? t('biometric.settingsFingerprint')
        : t('biometric.settings')

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
      onSwitchEmployee={
        employeeSession
          ? () =>
              void (async () => {
                await selectMode('employee')
                await refreshAvailability()
                router.replace('/(tabs)')
              })()
          : undefined
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
    />
  )
}
