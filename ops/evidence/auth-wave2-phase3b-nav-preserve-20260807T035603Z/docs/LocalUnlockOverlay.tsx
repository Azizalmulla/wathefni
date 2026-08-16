/**
 * Phase 3B local unlock overlay — same premium flow as cold-start unlock.
 * Architecture: host above native-stack WITHOUT remounting AuthGate / navigation.
 * Face ID success only dismisses the overlay (never Wave 1 / SecureStore session).
 *
 * Host choice:
 * - iOS: react-native-screens FullWindowOverlay (above native stack; avoids RN Modal
 *   which can detach/restore the wrong UIViewController after Face ID).
 * - Android: RN Modal (reliable z-order).
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { InteractionManager, Modal, Platform, StyleSheet, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { FullWindowOverlay } from 'react-native-screens'
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

/** Renders unlock UI above the already-mounted app; never replaces the nav tree. */
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

export function LocalUnlockOverlay({ onUnlocked }: Props) {
  const { t } = useI18n()
  const { biometricEnabled, biometricPreferenceOn } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Face ID only after overlay host is presented (plus UnlockWithBiometricGate settle).
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

  useEffect(() => {
    const partial: Parameters<typeof patchAutoLockDiagnostics>[0] = {
      biometricFeatureOn,
      biometricPreferenceOn,
      overlayBiometricEnabled: overlayBioFlag,
    }
    if (!overlayBioFlag) partial.lastBioGateReason = 'flag_off'
    else if (!biometricEnabled) partial.lastBioGateReason = 'feature_off'
    else if (!overlayReady) partial.lastBioGateReason = 'wait_modal'
    patchAutoLockDiagnostics(partial)
  }, [biometricFeatureOn, biometricEnabled, biometricPreferenceOn, overlayReady, overlayBioFlag])

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
    // Session already signedIn — dismiss overlay only. No router / setStatus.
    onUnlocked()
    return true
  }, [onUnlocked])

  return (
    <OverlayHost>
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
    </OverlayHost>
  )
}

/** App-switcher privacy cover — not an auth lock. */
export function PrivacyCover() {
  return <View style={styles.privacy} pointerEvents="none" accessibilityElementsHidden />
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFillObject,
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
