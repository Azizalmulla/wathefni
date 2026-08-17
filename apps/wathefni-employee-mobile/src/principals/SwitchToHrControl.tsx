import { Pressable, Text, View } from 'react-native'

import { usePrincipalGate } from '@/principals/PrincipalGate'
import { hrWorkspaceEnabled } from '@/principals/mode'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing } from '@/theme'

export function SwitchToHrControl() {
  const enabled = hrWorkspaceEnabled()
  // PrincipalGateProvider wraps the whole app; when HR flag is off the control hides.
  const gate = usePrincipalGate()
  const { t, isRTL } = useI18n()
  if (!enabled) return null
  const busy = gate.transition.status === 'switching'
  const failed = gate.transition.status === 'error' && gate.transition.to === 'hr'
  return (
    <View>
      <Pressable
        testID="e2e.principal.switch.hr"
        onPress={() => {
          gate.clearTransitionError()
          void gate.selectMode('hr')
        }}
        disabled={busy}
        style={{
          marginTop: spacing.lg,
          marginHorizontal: spacing.lg,
          marginBottom: failed ? spacing.sm : spacing.xl,
          paddingVertical: 14,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.surface,
          opacity: busy ? 0.6 : 1,
        }}
        accessibilityRole="button"
        accessibilityLabel={t('principal.switchHr')}
        accessibilityState={{ disabled: busy, busy }}
      >
        <Text style={{ textAlign: 'center', color: colors.ink, fontSize: font.body, fontWeight: '700' }}>
          {t(busy ? 'principal.switchingHr' : 'principal.switchHr')}
        </Text>
      </Pressable>
      {failed ? (
        <Text
          testID="e2e.principal.switch.error"
          accessibilityRole="alert"
          style={{
            marginHorizontal: spacing.lg,
            marginBottom: spacing.xl,
            color: colors.danger,
            fontSize: font.small,
            ...readingEdgeAlign(isRTL),
          }}
        >
          {t('principal.transitionError')}
        </Text>
      ) : null}
    </View>
  )
}
