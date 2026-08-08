import { Alert } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { ChangePinFlow } from '@/features/pin/PinFlows'

export default function ChangePinScreen() {
  const { t } = useI18n()
  const { changeLocalPin, pinEnabled, status } = useAuth()
  const router = useRouter()

  if (!pinEnabled || status !== 'signedIn') {
    return null
  }

  return (
    <ChangePinFlow
      onCancel={() => router.back()}
      onChange={async (current, next) => {
        const result = await changeLocalPin(current, next)
        if (result.ok) {
          Alert.alert(t('pin.changed'))
          router.back()
          return { ok: true }
        }
        return { ok: false, errorKey: result.errorKey || 'pin.wrong' }
      }}
    />
  )
}
