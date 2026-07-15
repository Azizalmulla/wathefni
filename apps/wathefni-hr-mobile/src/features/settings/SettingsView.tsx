import { StyleSheet, Text, View } from 'react-native'

import type { MobileMe } from '@/api/types'
import {
  ActionButton,
  Card,
  EditorialHeading,
  Screen,
  StatusBadge,
  WorkspaceHeader,
} from '@/components/primitives'
import { useLocale } from '@/i18n'
import { colors, spacing, type as typography } from '@/theme'

export function SettingsView({
  me,
  onLocale,
  onRefresh,
  onSignOut,
  onSignOutAll,
}: {
  me: MobileMe
  onLocale: () => void
  onRefresh: () => void
  onSignOut: () => void
  onSignOutAll: () => void
}) {
  const { t, isRTL, locale } = useLocale()
  return (
    <Screen>
      <WorkspaceHeader company={me.principal.company_code} onLocale={onLocale} />
      <EditorialHeading eyebrow={t('settings.eyebrow')}>{t('settings.title')}</EditorialHeading>
      <Card tone="cream">
        <Fact label={t('settings.company')} value={me.principal.company_code} />
        <Fact label={t('settings.operator')} value={me.principal.display_name} />
        <Fact label={t('common.email')} value={me.principal.email} />
        <Fact label={t('settings.scope')} value={me.scope.restricted ? t('home.scopeRestricted') : t('home.scopeCompany')} />
        <View style={[styles.statusRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
          <StatusBadge label={me.permission_authority} tone="success" />
          <StatusBadge label={me.account_state} tone="info" />
        </View>
      </Card>
      <Card tone="lilac">
        <Fact label={t('settings.locale')} value={locale === 'ar' ? 'العربية' : 'English'} />
        <ActionButton label={t('settings.changeLocale')} tone="secondary" onPress={onLocale} />
        <ActionButton label={t('settings.refreshAuthority')} tone="secondary" onPress={onRefresh} />
      </Card>
      <View style={styles.actions}>
        <ActionButton label={t('settings.signOut')} tone="secondary" onPress={onSignOut} />
        <ActionButton label={t('settings.signOutAll')} tone="danger" onPress={onSignOutAll} />
      </View>
    </Screen>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  const { isRTL } = useLocale()
  return (
    <View style={styles.fact}>
      <Text style={[styles.label, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
      <Text style={[styles.value, { textAlign: isRTL ? 'right' : 'left' }]}>{value}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  fact: { gap: spacing.xs },
  label: { color: colors.muted, fontSize: typography.label, fontWeight: '800' },
  value: { color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  statusRow: { gap: spacing.sm, flexWrap: 'wrap' },
  actions: { gap: spacing.md },
})
