import { useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { usePrincipalGate } from '@/principals/PrincipalGate'
import { hrWorkspaceEnabled } from '@/principals/mode'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing } from '@/theme'
import { recordPrincipalDiagnostic } from '@/principals/principalDiagnostics'

export function SwitchToHrControl() {
  const enabled = hrWorkspaceEnabled()
  // PrincipalGateProvider wraps the whole app; when HR flag is off the control hides.
  const gate = usePrincipalGate()
  const { sealForPrincipalSwitch } = useAuth()
  const { t, isRTL } = useI18n()
  const [preparing, setPreparing] = useState(false)
  const pressInFlight = useRef(false)
  if (!enabled) return null
  const busy = preparing || gate.transition.status === 'switching'
  const failed = gate.transition.status === 'error' && gate.transition.to === 'hr'
  return (
    <View>
      <Pressable
        testID="e2e.principal.switch.hr"
        onPress={() => {
          if (pressInFlight.current) return
          pressInFlight.current = true
          setPreparing(true)
          recordPrincipalDiagnostic({
            event: 'switch_tap',
            target: 'hr',
            employeeSession: gate.employeeSession,
            hrSession: gate.hrSession,
          })
          gate.clearTransitionError()
          // Start the controlled transition first so the Employee lock gate is
          // suppressed in this event turn, then seal only the Employee
          // request-capable session. HR SecureStore/PIN state is untouched.
          const transition = gate.selectMode('hr', sealForPrincipalSwitch)
          void (async () => {
            try {
              await transition
            } finally {
              pressInFlight.current = false
              setPreparing(false)
            }
          })()
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
