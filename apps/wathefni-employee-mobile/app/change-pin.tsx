import { Alert, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { EmployeePushedEscape } from '@/components/EmployeePushedEscape'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { ChangePinFlow } from '@/features/pin/PinFlows'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { errorFeedback, successFeedback } from '@/native/haptics'
import { colors, font, spacing, typeScaling } from '@/theme'

export default function ChangePinScreen() {
  const { t, isRTL } = useI18n()
  const { changeLocalPin, pinEnabled, status } = useAuth()
  const onBack = useEmployeeSafeBack('/settings')
  const align = readingEdgeAlign(isRTL)

  if (status !== 'signedIn') {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <View style={styles.pad}>
          <EditorialHeading size="medium">{t('pin.change')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.body, align]}>
            {t('access.session_expired.message')}
          </Text>
          <PremiumButton label={t('common.back')} onPress={onBack} />
        </View>
      </EmployeePushedEscape>
    )
  }

  if (!pinEnabled) {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <View style={styles.pad}>
          <EditorialHeading size="medium">{t('pin.change')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.body, align]}>
            {t('feature.unavailable.message')}
          </Text>
          <PremiumButton label={t('common.back')} onPress={onBack} />
        </View>
      </EmployeePushedEscape>
    )
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

const styles = StyleSheet.create({
  pad: { gap: spacing.md, paddingTop: spacing.lg },
  body: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})
