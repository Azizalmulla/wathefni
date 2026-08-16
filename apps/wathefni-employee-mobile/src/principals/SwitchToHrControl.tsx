import { Pressable, Text } from 'react-native'
import { useRouter } from 'expo-router'

import { usePrincipalGate } from '@/principals/PrincipalGate'
import { hrWorkspaceEnabled } from '@/principals/mode'
import { colors, font, spacing } from '@/theme'

export function SwitchToHrControl() {
  const enabled = hrWorkspaceEnabled()
  const router = useRouter()
  // PrincipalGateProvider wraps the whole app; when HR flag is off the control hides.
  const gate = usePrincipalGate()
  if (!enabled) return null
  return (
    <Pressable
      onPress={() => {
        void gate.selectMode('hr').then(() => router.replace('/hr'))
      }}
      style={{
        marginTop: spacing.lg,
        marginHorizontal: spacing.lg,
        marginBottom: spacing.xl,
        paddingVertical: 14,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
      }}
      accessibilityRole="button"
      accessibilityLabel="Switch to HR"
    >
      <Text style={{ textAlign: 'center', color: colors.ink, fontSize: font.body, fontWeight: '700' }}>
        Switch to HR
      </Text>
    </Pressable>
  )
}
