import { useState } from 'react'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { ActivationView } from '@/features/activation/ActivationView'

export default function ActivateScreen() {
  const { t } = useI18n()
  const { activate, requestCode } = useAuth()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onSignIn = async () => {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await activate(phone.trim(), code.trim())
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  const onRequestCode = async () => {
    setError(null)
    setBusy(true)
    try {
      await requestCode(phone.trim())
      setNotice(t('auth.codeSent'))
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ActivationView
      phone={phone}
      code={code}
      busy={busy}
      error={error}
      notice={notice}
      onPhoneChange={(value) => {
        setPhone(value)
        setError(null)
        setNotice(null)
      }}
      onCodeChange={(value) => {
        setCode(value)
        setError(null)
      }}
      onSignIn={() => void onSignIn()}
      onRequestCode={() => void onRequestCode()}
    />
  )
}
