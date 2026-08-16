import { StyleSheet, View } from 'react-native'

import { PageBackButton } from '@/components/lists'
import { Wordmark } from '@/components/premium'
import { spacing } from '@/theme'

/**
 * Minimum pushed-screen chrome: visible Back + centered wordmark.
 * Tab roots must not use this.
 */
export function HrPushedNav({
  onBack,
  accessibilityLabel,
}: {
  onBack: () => void
  accessibilityLabel: string
}) {
  return (
    <View style={styles.nav}>
      <PageBackButton onPress={onBack} accessibilityLabel={accessibilityLabel} />
      <Wordmark compact align="center" />
      <View style={styles.navSpacer} />
    </View>
  )
}

const styles = StyleSheet.create({
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
    marginBottom: spacing.sm,
  },
  navSpacer: { width: 40 },
})
