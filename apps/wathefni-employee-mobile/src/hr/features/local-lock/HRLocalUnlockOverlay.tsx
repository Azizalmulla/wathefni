import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { InteractionManager, Modal, Platform, StyleSheet, View } from 'react-native'
import { FullWindowOverlay } from 'react-native-screens'

import { useAuth } from '@hr/auth/AuthProvider'
import { isLocalAutoLockBiometricEnabled } from '@/auth/autoLockPolicy'
import { PIN_MAX_FAILED_ATTEMPTS } from '@/auth/pinPolicy'
import { shouldAttemptHrBiometricUnlock, promptBiometricUnlock } from '@hr/auth/localLock/hrBiometricAuth'
import { verifyHrPin } from '@hr/auth/localLock/hrPinStorage'
import { UnlockWithBiometricGate } from '@/features/pin/UnlockWithBiometricGate'
import { useI18n } from '@/i18n'
import { colors } from '@/theme'

type Props = { onUnlocked: () => void }

function OverlayHost({ children }: { children: ReactNode }) {
  if (Platform.OS === 'ios') {
    return <FullWindowOverlay>{children}</FullWindowOverlay>
  }
  return (
    <Modal
      visible
      animationType="none"
      presentationStyle="overFullScreen"
      statusBarTranslucent
      onRequestClose={() => {
        /* Android back must not bypass unlock */
      }}
    >
      {children}
    </Modal>
  )
}

export function HRLocalUnlockOverlay({ onUnlocked }: Props) {
  const { t } = useI18n()
  const { biometricEnabled, recoverLocalLockByReauth } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [overlayReady, setOverlayReady] = useState(false)

  const overlayBioFlag = isLocalAutoLockBiometricEnabled()
  const biometricFeatureOn = overlayReady && overlayBioFlag && biometricEnabled

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const handle = InteractionManager.runAfterInteractions(() => {
      timer = setTimeout(() => {
        if (!cancelled) setOverlayReady(true)
      }, 150)
    })
    return () => {
      cancelled = true
      handle.cancel?.()
      if (timer) clearTimeout(timer)
    }
  }, [])

  const onUnlockPin = (pin: string) => {
    void (async () => {
      setBusy(true)
      setError(null)
      try {
        const result = await verifyHrPin(pin)
        if (result.ok) {
          onUnlocked()
          return
        }
        if (result.lockedOut) {
          await recoverLocalLockByReauth()
          return
        }
        const left = Math.max(0, PIN_MAX_FAILED_ATTEMPTS - result.failedAttempts)
        setError(left > 0 ? t('pin.wrongWithTries', { count: left }) : t('pin.wrong'))
      } catch {
        setError(t('pin.wrong'))
      } finally {
        setBusy(false)
      }
    })()
  }

  const onUnlockBiometric = useCallback(async () => {
    onUnlocked()
    return true
  }, [onUnlocked])

  return (
    <OverlayHost>
      <View style={styles.root} pointerEvents="auto" accessibilityViewIsModal>
        <UnlockWithBiometricGate
          biometricFeatureOn={biometricFeatureOn}
          busy={busy}
          error={error}
          onUnlockPin={onUnlockPin}
          onUnlockBiometric={onUnlockBiometric}
          onForgotPin={() => {
            void recoverLocalLockByReauth()
          }}
          forgotTitleKey="hrPin.forgotTitle"
          forgotConfirmKey="hrPin.forgotConfirm"
          shouldAttempt={shouldAttemptHrBiometricUnlock}
          promptUnlock={promptBiometricUnlock}
        />
      </View>
    </OverlayHost>
  )
}

export function HRPrivacyCover() {
  return <View style={styles.privacy} pointerEvents="none" accessibilityElementsHidden />
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFillObject,
    flex: 1,
    backgroundColor: colors.bg,
  },
  privacy: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 900,
    elevation: 900,
    backgroundColor: colors.bg,
  },
})
