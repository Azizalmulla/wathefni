import type { ReactNode } from 'react'
import { StyleSheet, View } from 'react-native'

import { PageScreen } from '@/components/layout'
import { PageBackButton } from '@/components/lists'
import { Wordmark } from '@/components/premium'
import { useI18n } from '@/i18n'
import { spacing } from '@/theme'

/**
 * Minimum chrome for pushed loading/error/unavailable escapes.
 * Tab roots must not use this.
 */
export function EmployeePushedEscape({
  onBack,
  children,
}: {
  onBack: () => void
  children: ReactNode
}) {
  const { t } = useI18n()
  return (
    <PageScreen>
      <View style={styles.nav}>
        <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
        <Wordmark compact align="center" />
        <View style={styles.navSpacer} />
      </View>
      <View style={styles.body}>{children}</View>
    </PageScreen>
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
  body: { flex: 1 },
})
