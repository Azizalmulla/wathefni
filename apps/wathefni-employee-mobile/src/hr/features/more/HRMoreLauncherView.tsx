import { StyleSheet, Text, View, Alert } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { moreModulesFor, type MoreModuleLink } from '@hr/features/more/moreLauncher'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn, Wordmark } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { usePrincipalGate } from '@/principals/PrincipalGate'
import { colors, font, radius, spacing, typeScaling } from '@/theme'
import { recordPrincipalDiagnostic } from '@/principals/principalDiagnostics'

/**
 * More — long-term modular workspace launcher.
 * Cream/black, quiet rows, entitlement-gated. Not a dashboard.
 */
export function HRMoreLauncherView() {
  const router = useRouter()
  const { me, signOut } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const {
    employeeSession,
    hrSession,
    transition,
    selectMode,
    clearTransitionError,
    refreshAvailability,
  } = usePrincipalGate()
  const modules = moreModulesFor(me)

  if (!me) return null

  const confirmSignOut = () => {
    Alert.alert(t('hrSettings.signOutConfirmTitle'), t('hrSettings.signOutConfirmBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('hrMore.signOut'),
        style: 'destructive',
        onPress: () => void signOut().then(() => refreshAvailability()),
      },
    ])
  }

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <View style={styles.nav}>
          <Wordmark />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrMore.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrMore.subtitle')}
          </Text>
        </FadeIn>

        {modules.length ? (
          <View style={styles.section}>
            <SectionHeader title={t('hrMore.groupOperations')} />
            {modules.map((link) => (
              <ModuleRow
                key={link.key}
                link={link}
                onPress={() => router.push(link.path as never)}
              />
            ))}
          </View>
        ) : (
          <View style={styles.emptyOps}>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyTitle, align]}>
              {t('hrMore.emptyOpsTitle')}
            </Text>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyBody, align]}>
              {t('hrMore.emptyOpsBody')}
            </Text>
          </View>
        )}

        <View style={styles.section}>
          <SectionHeader title={t('hrMore.groupAccount')} />
          <ListRow
            title={t('hrMore.settings')}
            subtitle={t('hrMore.settingsBody')}
            icon="settings-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={() => router.push('/hr/settings' as never)}
            style={styles.row}
          />
          <>
            <ListRow
              testID="e2e.principal.switch.employee"
              title={
                transition.status === 'switching'
                  ? t('principal.switchingEmployee')
                  : t('hrMore.switchEmployee')
              }
              subtitle={t('hrMore.switchEmployeeBody')}
              icon="swap-horizontal-outline"
              iconTint={colors.surfaceMuted}
              showChevron={transition.status !== 'switching'}
              disabled={transition.status === 'switching'}
              onPress={() => {
                recordPrincipalDiagnostic({
                  event: 'switch_tap',
                  target: 'employee',
                  employeeSession,
                  hrSession,
                })
                clearTransitionError()
                void selectMode('employee')
              }}
              style={styles.row}
            />
            {transition.status === 'error' && transition.to === 'employee' ? (
              <Text
                testID="e2e.principal.switch.error"
                accessibilityRole="alert"
                maxFontSizeMultiplier={typeScaling.body}
                style={[styles.switchError, align]}
              >
                {t('principal.transitionError')}
              </Text>
            ) : null}
          </>
          <ListRow
            testID="e2e.hr.signOut"
            title={t('hrMore.signOut')}
            subtitle={t('hrMore.signOutBody')}
            icon="log-out-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={confirmSignOut}
            style={styles.row}
          />
        </View>
      </PageScrollView>
    </PageScreen>
  )
}

function ModuleRow({ link, onPress }: { link: MoreModuleLink; onPress: () => void }) {
  const { t } = useI18n()
  return (
    <ListRow
      title={t(link.titleKey)}
      subtitle={t(link.subtitleKey)}
      icon={link.icon}
      iconTint={colors.surfaceMuted}
      showChevron
      onPress={onPress}
      style={styles.row}
    />
  )
}

const styles = StyleSheet.create({
  nav: { minHeight: 42, justifyContent: 'center' },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  emptyOps: {
    gap: spacing.sm,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
  },
  emptyTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  switchError: { color: colors.danger, fontSize: font.small, lineHeight: 18 },
  emptyBody: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
})
