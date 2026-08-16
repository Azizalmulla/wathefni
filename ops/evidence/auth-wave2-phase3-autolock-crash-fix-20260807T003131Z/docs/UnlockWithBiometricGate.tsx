import { useEffect, useRef } from 'react'
import { AppState } from 'react-native'

import { UnlockPinFlow } from './PinFlows'
import {
  promptBiometricUnlock,
  shouldAttemptBiometricUnlock,
} from '@/auth/biometricAuth'
import { useI18n } from '@/i18n'

type UnlockWithBiometricGateProps = {
  biometricFeatureOn: boolean
  busy: boolean
  error: string | null
  onUnlockPin: (pin: string) => void
  onUnlockBiometric: () => Promise<boolean>
}

/**
 * Calm reopen: try Face ID / Touch ID once over the PIN screen.
 * Delay the OS prompt until AppState is stably active — presenting
 * LocalAuthentication during resume transitions hard-crashes on iOS.
 */
export function UnlockWithBiometricGate({
  biometricFeatureOn,
  busy,
  error,
  onUnlockPin,
  onUnlockBiometric,
}: UnlockWithBiometricGateProps) {
  const { t } = useI18n()
  const attempted = useRef(false)
  const promptInFlight = useRef(false)

  useEffect(() => {
    if (!biometricFeatureOn || attempted.current || promptInFlight.current) return

    let cancelled = false
    let settleTimer: ReturnType<typeof setTimeout> | null = null

    const run = () => {
      if (cancelled || attempted.current || promptInFlight.current) return
      if (AppState.currentState !== 'active') return
      attempted.current = true
      promptInFlight.current = true
      void (async () => {
        try {
          const { attempt } = await shouldAttemptBiometricUnlock()
          if (cancelled || !attempt) return
          // Second settle after availability check — AppState can still be transitioning.
          await new Promise((r) => setTimeout(r, 250))
          if (cancelled || AppState.currentState !== 'active') return
          const result = await promptBiometricUnlock({
            promptMessage: t('biometric.unlockPrompt'),
            cancelLabel: t('common.cancel'),
          })
          if (cancelled) return
          if (result.ok) {
            await onUnlockBiometric()
          }
        } catch (error) {
          console.warn('[biometric] unlock gate error', error)
        } finally {
          promptInFlight.current = false
        }
      })()
    }

    // Wait for resume to finish before Face ID (avoids iOS crash on LAContext present).
    settleTimer = setTimeout(run, 450)

    return () => {
      cancelled = true
      if (settleTimer) clearTimeout(settleTimer)
    }
  }, [biometricFeatureOn, onUnlockBiometric, t])

  return <UnlockPinFlow busy={busy} error={error} onUnlock={onUnlockPin} />
}
