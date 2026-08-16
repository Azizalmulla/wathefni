/**
 * Phase 3B local unlock overlay — same premium flow as cold-start unlock.
 * Architecture unchanged: Modal above native-stack, session/nav stay mounted.
 * Face ID success only dismisses the overlay (never Wave 1 / SecureStore session).
 */

import { useCallback, useEffect, useState } from 'react'
import { Modal, StyleSheet, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as SecureStore from 'expo-secure-store'

import { useAuth } from '@/auth/AuthProvider'
import { isLocalAutoLockBiometricEnabled } from '@/auth/autoLockPolicy'
import { patchAutoLockDiagnostics } from '@/auth/autoLockDiagnostics'
import { UnlockWithBiometricGate } from '@/features/pin/UnlockWithBiometricGate'
import { verifyPin } from '@/auth/pinStorage'
import { PIN_MAX_FAILED_ATTEMPTS } from '@/auth/pinPolicy'
import { useI18n } from '@/i18n'
import { colors } from '@/theme'

const ATTEMPTS_KEY = 'wathefni.pin.failed_attempts'
const STORE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED }

type Props = {
  onUnlocked: () => void
}

export function LocalUnlockOverlay({ onUnlocked }: Props) {
  const { t } = useI18n()
  const { biometricEnabled, biometricPreferenceOn } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Face ID only after Modal is fully presented (plus UnlockWithBiometricGate settle).
  const [modalReady, setModalReady] = useState(false)

  const overlayBioFlag = isLocalAutoLockBiometricEnabled()
  const biometricFeatureOn = modalReady && overlayBioFlag && biometricEnabled

  useEffect(() => {
    // Fallback if onShow does not fire on some devices.
    const timer = setTimeout(() => setModalReady(true), 150)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    const partial: Parameters<typeof patchAutoLockDiagnostics>[0] = {
      biometricFeatureOn,
      biometricPreferenceOn,
      overlayBiometricEnabled: overlayBioFlag,
    }
    if (!overlayBioFlag) partial.lastBioGateReason = 'flag_off'
    else if (!biometricEnabled) partial.lastBioGateReason = 'feature_off'
    else if (!modalReady) partial.lastBioGateReason = 'wait_modal'
    patchAutoLockDiagnostics(partial)
  }, [biometricFeatureOn, biometricEnabled, biometricPreferenceOn, modalReady, overlayBioFlag])

  const onUnlockPin = (pin: string) => {
    void (async () => {
      setBusy(true)
      setError(null)
      try {
        const result = await verifyPin(pin)
        if (result.ok) {
          onUnlocked()
          return
        }
        // Overlay must never wipe Wave 1 session / force OTP.
        if (result.lockedOut) {
          await SecureStore.setItemAsync(ATTEMPTS_KEY, '0', STORE_OPTS)
          setError(t('pin.wrong'))
          return
        }
        const left = Math.max(0, PIN_MAX_FAILED_ATTEMPTS - result.failedAttempts)
        setError(left > 0 ? t('pin.wrongWithTries', { count: left }) : t('pin.wrong'))
      } catch (err) {
        console.warn('[autolock-overlay] pin verify error', err)
        setError(t('pin.wrong'))
      } finally {
        setBusy(false)
      }
    })()
  }

  const onUnlockBiometric = useCallback(async () => {
    // Session already signedIn — dismiss overlay only.
    onUnlocked()
    return true
  }, [onUnlocked])

  // Modal (not absolute View): native-stack screens sit above sibling Views on iOS.
  // overFullScreen keeps LAContext presentation from fighting a page-sheet modal.
  return (
    <Modal
      visible
      animationType="none"
      presentationStyle="overFullScreen"
      statusBarTranslucent
      onShow={() => setModalReady(true)}
      onRequestClose={() => {
        /* Android back must not bypass unlock */
      }}
    >
      <View style={styles.root} pointerEvents="auto" accessibilityViewIsModal>
        <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
          <UnlockWithBiometricGate
            biometricFeatureOn={biometricFeatureOn}
            busy={busy}
            error={error}
            onUnlockPin={onUnlockPin}
            onUnlockBiometric={onUnlockBiometric}
          />
        </SafeAreaView>
      </View>
    </Modal>
  )
}

/** App-switcher privacy cover — not an auth lock. */
export function PrivacyCover() {
  return <View style={styles.privacy} pointerEvents="none" accessibilityElementsHidden />
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  safe: { flex: 1, backgroundColor: colors.bg },
  privacy: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 900,
    elevation: 900,
    backgroundColor: colors.bg,
  },
})
