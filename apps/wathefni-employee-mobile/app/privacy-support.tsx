import { Alert, Linking } from 'react-native'
import { useRouter } from 'expo-router'

import { useI18n } from '@/i18n'
import { PRIVACY_URL } from '@/config'
import { PrivacySupportView } from '@/features/remaining/RemainingViews'

const SUPPORT_URL = 'mailto:support@wathefni.ai'

export default function PrivacySupportScreen() {
  const { t } = useI18n()
  const router = useRouter()

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
      onBack={() => router.back()}
    />
  )
}
