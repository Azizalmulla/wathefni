import { useEffect, useRef } from 'react'
import { AppState } from 'react-native'

import { UnlockPinFlow } from './PinFlows'
import {
  promptBiometricUnlock as defaultPromptBiometricUnlock,
  shouldAttemptBiometricUnlock as defaultShouldAttemptBiometricUnlock,
  type BiometricAvailability,
  type BiometricPromptResult,
} from '@/auth/biometricAuth'
import { patchAutoLockDiagnostics } from '@/auth/autoLockDiagnostics'
import { useI18n } from '@/i18n'

type ShouldAttemptFn = () => Promise<{
  attempt: boolean
  preferred: boolean
  availability: BiometricAvailability
}>
type PromptFn = (opts: {
  promptMessage: string
  cancelLabel: string
}) => Promise<BiometricPromptResult>

type UnlockWithBiometricGateProps = {
  biometricFeatureOn: boolean
  busy: boolean
  error: string | null
  onUnlockPin: (pin: string) => void
  onUnlockBiometric: () => Promise<boolean>
  onForgotPin?: () => void
  forgotTitleKey?: string
  forgotConfirmKey?: string
  /** Inject HR preference store without forking the settle-timer UX. */
  shouldAttempt?: ShouldAttemptFn
  promptUnlock?: PromptFn
}

/**
 * Calm reopen: try Face ID / Touch ID once over the PIN screen.
 * Delay the OS prompt until AppState is stably active — presenting
 * LocalAuthentication during resume transitions hard-crashes on iOS.
 *
 * Rising-edge arm: each time biometricFeatureOn goes false→true (cold start
 * mount or overlay Modal ready), allow exactly one prompt attempt.
 * Do not mark "attempted" until we either skip definitively or call authenticate.
 */
export function UnlockWithBiometricGate({
  biometricFeatureOn,
  busy,
  error,
  onUnlockPin,
  onUnlockBiometric,
  onForgotPin,
  forgotTitleKey,
  forgotConfirmKey,
  shouldAttempt = defaultShouldAttemptBiometricUnlock,
  promptUnlock = defaultPromptBiometricUnlock,
}: UnlockWithBiometricGateProps) {
  const { t } = useI18n()
  const attempted = useRef(false)
  const promptInFlight = useRef(false)
  const wasFeatureOn = useRef(false)
  const onUnlockBiometricRef = useRef(onUnlockBiometric)
  const shouldAttemptRef = useRef(shouldAttempt)
  const promptUnlockRef = useRef(promptUnlock)
  const tRef = useRef(t)
  onUnlockBiometricRef.current = onUnlockBiometric
  shouldAttemptRef.current = shouldAttempt
  promptUnlockRef.current = promptUnlock
  tRef.current = t

  useEffect(() => {
    if (!biometricFeatureOn) {
      wasFeatureOn.current = false
      return
    }

    // New unlock session (overlay Modal became ready, or cold-start gate mounted).
    if (!wasFeatureOn.current) {
      attempted.current = false
      promptInFlight.current = false
      wasFeatureOn.current = true
      patchAutoLockDiagnostics({ lastBioGateReason: 'armed' })
    }

    if (attempted.current || promptInFlight.current) return

    let cancelled = false
    let settleTimer: ReturnType<typeof setTimeout> | null = null

    const present = () => {
      if (cancelled || attempted.current || promptInFlight.current) return
      if (AppState.currentState !== 'active') {
        patchAutoLockDiagnostics({ lastBioGateReason: 'wait_active' })
        return
      }

      promptInFlight.current = true
      void (async () => {
        try {
          const { attempt, preferred, availability } = await shouldAttemptRef.current()
          if (cancelled) return
          if (!attempt) {
            // Definitive skip (preference off / not usable) — do not retry this session.
            attempted.current = true
            patchAutoLockDiagnostics({
              lastBioGateReason: preferred ? 'not_usable' : 'pref_off',
              biometricPreferenceOn: preferred,
              biometricUsable: availability.usable,
            })
            return
          }

          // Second settle after availability — AppState can still be transitioning.
          await new Promise((r) => setTimeout(r, 300))
          if (cancelled) return
          if (AppState.currentState !== 'active') {
            // Do not consume the single-attempt token — AppState listener will retry.
            patchAutoLockDiagnostics({ lastBioGateReason: 'wait_active_post_avail' })
            return
          }

          // Commit to one OS prompt for this session.
          attempted.current = true
          patchAutoLockDiagnostics({
            lastBioGateReason: 'prompting',
            biometricUsable: true,
            biometricPreferenceOn: true,
          })
          const result = await promptUnlockRef.current({
            promptMessage: tRef.current('biometric.unlockPrompt'),
            cancelLabel: tRef.current('common.cancel'),
          })
          if (cancelled) return
          patchAutoLockDiagnostics({
            lastBioGateReason: result.ok
              ? 'success'
              : `fallback_pin:${'reason' in result ? result.reason : 'fail'}`,
          })
          if (result.ok) {
            await onUnlockBiometricRef.current()
          }
        } catch (error) {
          console.warn('[biometric] unlock gate error', error)
          attempted.current = true
          patchAutoLockDiagnostics({ lastBioGateReason: 'error' })
        } finally {
          promptInFlight.current = false
        }
      })()
    }

    const schedule = () => {
      if (settleTimer) clearTimeout(settleTimer)
      settleTimer = setTimeout(present, 500)
    }

    schedule()
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active' && !attempted.current && !promptInFlight.current && !cancelled) {
        schedule()
      }
    })

    return () => {
      cancelled = true
      if (settleTimer) clearTimeout(settleTimer)
      sub.remove()
    }
  }, [biometricFeatureOn])

  return (
    <UnlockPinFlow
      busy={busy}
      error={error}
      onUnlock={onUnlockPin}
      onForgotPin={onForgotPin}
      forgotTitleKey={forgotTitleKey}
      forgotConfirmKey={forgotConfirmKey}
    />
  )
}
