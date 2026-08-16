import { Alert } from 'react-native'

import { useAuth } from '@hr/auth/AuthProvider'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { ChangePinFlow } from '@/features/pin/PinFlows'
import { useI18n } from '@/i18n'
import { errorFeedback, successFeedback } from '@/native/haptics'

export default function HrChangePinScreen() {
  const { t } = useI18n()
  const { changeLocalPin, pinEnabled, status } = useAuth()
  const onBack = useHrSafeBack()

  if (!pinEnabled || status !== 'signedIn') {
    return null
  }

  return (
    <ChangePinFlow
      onCancel={onBack}
      onChange={async (current, next) => {
        const result = await changeLocalPin(current, next)
        if (result.ok) {
          successFeedback()
          Alert.alert(t('pin.changed'))
          onBack()
          return { ok: true }
        }
        errorFeedback()
        return { ok: false, errorKey: result.errorKey || 'pin.wrong' }
      }}
    />
  )
}
