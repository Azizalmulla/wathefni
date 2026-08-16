/**
 * Phase 3 local unlock overlay — PIN only (Face ID gated off until ×25 crash-free).
 * Does not change AuthStatus, SecureStore session, or navigation.
 */

import { useState } from 'react'
import { StyleSheet, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import * as SecureStore from 'expo-secure-store'

import { UnlockPinFlow } from '@/features/pin/PinFlows'
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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <View style={styles.root} pointerEvents="auto" accessibilityViewIsModal>
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <UnlockPinFlow busy={busy} error={error} onUnlock={onUnlockPin} />
      </SafeAreaView>
    </View>
  )
}

/** App-switcher privacy cover — not an auth lock. */
export function PrivacyCover() {
  return <View style={styles.privacy} pointerEvents="none" accessibilityElementsHidden />
}

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 1000,
    elevation: 1000,
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
