import { useState } from 'react'
import { Alert } from 'react-native'

import { PinView } from './PinView'
import { PIN_LENGTH, isValidPinFormat } from '@/auth/pinPolicy'
import { useI18n } from '@/i18n'

type CreatePinFlowProps = {
  busy?: boolean
  onCreate: (pin: string) => Promise<void>
}

export function CreatePinFlow({ busy = false, onCreate }: CreatePinFlowProps) {
  const { t } = useI18n()
  const [step, setStep] = useState<'create' | 'confirm'>('create')
  const [first, setFirst] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const submit = async (pin: string) => {
    setError(null)
    if (!isValidPinFormat(pin)) {
      setError(t('pin.invalidFormat'))
      return
    }
    if (step === 'create') {
      setFirst(pin)
      setStep('confirm')
      return
    }
    if (pin !== first) {
      setError(t('pin.mismatch'))
      setStep('create')
      setFirst('')
      return
    }
    setSaving(true)
    try {
      await onCreate(pin)
    } catch {
      setError(t('pin.saveFailed'))
      setStep('create')
      setFirst('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <PinView
      mode={step}
      busy={busy || saving}
      error={error}
      onSubmit={(pin) => void submit(pin)}
    />
  )
}

type UnlockPinFlowProps = {
  busy?: boolean
  error?: string | null
  onUnlock: (pin: string) => void
  onForgotPin?: () => void
  /** Optional i18n keys — HR uses operator re-auth copy instead of activation OTP. */
  forgotTitleKey?: string
  forgotConfirmKey?: string
}

export function UnlockPinFlow({
  busy,
  error,
  onUnlock,
  onForgotPin,
  forgotTitleKey = 'pin.forgotTitle',
  forgotConfirmKey = 'pin.forgotConfirm',
}: UnlockPinFlowProps) {
  const { t } = useI18n()

  const confirmForgot = () => {
    if (!onForgotPin || busy) return
    Alert.alert(t(forgotTitleKey), t(forgotConfirmKey), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('pin.forgotConfirmAction'),
        onPress: () => onForgotPin(),
      },
    ])
  }

  return (
    <PinView
      mode="unlock"
      busy={busy}
      error={error}
      onSubmit={onUnlock}
      onForgotPin={onForgotPin ? confirmForgot : undefined}
    />
  )
}

type ChangePinFlowProps = {
  onChange: (current: string, next: string) => Promise<{ ok: boolean; errorKey?: string }>
  onCancel: () => void
}

export function ChangePinFlow({ onChange, onCancel }: ChangePinFlowProps) {
  const { t } = useI18n()
  const [step, setStep] = useState<'changeCurrent' | 'changeNext' | 'changeConfirm'>('changeCurrent')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (pin: string) => {
    setError(null)
    if (pin.length !== PIN_LENGTH || !isValidPinFormat(pin)) {
      setError(t('pin.invalidFormat'))
      return
    }
    if (step === 'changeCurrent') {
      setCurrent(pin)
      setStep('changeNext')
      return
    }
    if (step === 'changeNext') {
      setNext(pin)
      setStep('changeConfirm')
      return
    }
    if (pin !== next) {
      setError(t('pin.mismatch'))
      setStep('changeNext')
      setNext('')
      return
    }
    setBusy(true)
    try {
      const result = await onChange(current, next)
      if (!result.ok) {
        setError(t(result.errorKey || 'pin.wrong'))
        setStep('changeCurrent')
        setCurrent('')
        setNext('')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <PinView
      mode={step}
      busy={busy}
      error={error}
      onSubmit={(pin) => void submit(pin)}
      onCancel={onCancel}
    />
  )
}
