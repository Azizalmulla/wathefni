import { Alert, Linking } from 'react-native'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'

import { useI18n } from '@/i18n'
import { PRIVACY_URL, SUPPORT_URL } from '@/config'
import { PrivacySupportView } from '@/features/remaining/RemainingViews'

export default function PrivacySupportScreen() {
  const { t } = useI18n()
  const onBack = useEmployeeSafeBack()

  const open = async (url: string) => {
    try {
      await Linking.openURL(url)
    } catch {
      Alert.alert(t('common.error'), t('error.generic'))
    }
  }

  return (
    <PrivacySupportView
      onPrivacy={() => void open(PRIVACY_URL)}
      onSupport={() => void open(SUPPORT_URL)}
      onBack={onBack}
    />
  )
}
