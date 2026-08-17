import { useState } from 'react'
import { Alert, StyleSheet, Switch, Text, View } from 'react-native'

import type { MobileMe } from '@hr/api/types'
import { operatorRoleLabel, operatorRoleLabelKey } from '@hr/features/settings/settingsComposition'
import { listAutoLockTimeoutOptions, type AutoLockTimeoutMs } from '@/auth/autoLockPolicy'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn, Wordmark } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { selectionFeedback, warningFeedback } from '@/native/haptics'
import { colors, font, spacing, typeScaling } from '@/theme'
import { resolveCompanyBrand } from '@/branding/CompanyBrand'

type Props = {
  me: MobileMe
  showBack?: boolean
  onBack?: () => void
  onToggleLocale: () => void | Promise<void>
  onRefresh: () => void | Promise<void>
  onSignOut: () => void | Promise<void>
  onSignOutAll: () => void | Promise<void>
  onOpenNotificationSettings: () => void | Promise<void>
  onOpenPrivacy: () => void | Promise<void>
  onOpenSupport: () => void | Promise<void>
  onSwitchEmployee?: () => void | Promise<void>
  principalSwitchBusy?: boolean
  principalSwitchError?: string | null
  version: string
  pinEnabled?: boolean
  biometricEnabled?: boolean
  biometricPreferenceOn?: boolean
  biometricBusy?: boolean
  biometricLabel?: string
  onToggleBiometric?: (enable: boolean) => void | Promise<void>
  autoLockTimeoutMs?: AutoLockTimeoutMs
  autoLockBusy?: boolean
  onSelectAutoLock?: (value: AutoLockTimeoutMs) => void | Promise<void>
  onChangePin?: () => void
}

/**
 * HR Settings — this operator + this device.
 * Includes Wave 2 local Device Security (PIN / Face ID / auto-lock) — not session merge.
 */
export function SettingsView({
  me,
  showBack = true,
  onBack,
  onToggleLocale,
  onRefresh,
  onSignOut,
  onSignOutAll,
  onOpenNotificationSettings,
  onOpenPrivacy,
  onOpenSupport,
  onSwitchEmployee,
  principalSwitchBusy = false,
  principalSwitchError,
  version,
  pinEnabled = false,
  biometricEnabled = false,
  biometricPreferenceOn = false,
  biometricBusy = false,
  biometricLabel,
  onToggleBiometric,
  autoLockTimeoutMs,
  autoLockBusy = false,
  onSelectAutoLock,
  onChangePin,
}: Props) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const companyName = resolveCompanyBrand(me.company_identity, locale).name
  const [refreshing, setRefreshing] = useState(false)

  const roleKey = operatorRoleLabelKey(me)
  const labeled = String(me.principal.role_label || '').trim()
  const roleLabel = labeled || (roleKey ? t(roleKey) : operatorRoleLabel(me))
  const localeLabel = locale === 'ar' ? t('hrSettings.localeArabic') : t('hrSettings.localeEnglish')
  const autoLockOptions = listAutoLockTimeoutOptions()
  const showDeviceSecurity = pinEnabled

  const confirmSignOut = () => {
    warningFeedback()
    Alert.alert(t('hrSettings.signOutConfirmTitle'), t('hrSettings.signOutConfirmBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('hrSettings.signOut'),
        style: 'destructive',
        onPress: () => void onSignOut(),
      },
    ])
  }

  const confirmSignOutAll = () => {
    warningFeedback()
    Alert.alert(t('hrSettings.signOutAllConfirmTitle'), t('hrSettings.signOutAllConfirmBody'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('hrSettings.signOutAll'),
        style: 'destructive',
        onPress: () => void onSignOutAll(),
      },
    ])
  }

  const refresh = async () => {
    setRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={() => void refresh()}>
        <View style={styles.nav}>
          {showBack && onBack ? (
            <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
          ) : (
            <View style={styles.navSpacer} />
          )}
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrSettings.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrSettings.subtitle')}
          </Text>
        </FadeIn>

        <View style={styles.section}>
          <SectionHeader title={t('hrSettings.sectionYou')} />
          <ListRow
            title={me.principal.display_name || t('hrSettings.operator')}
            subtitle={me.principal.email || undefined}
            icon="person-outline"
            iconTint={colors.surfaceMuted}
            style={styles.row}
          />
          <ListRow
            title={t('hrSettings.company')}
            subtitle={companyName}
            icon="business-outline"
            iconTint={colors.surfaceMuted}
            style={styles.row}
          />
          <ListRow
            title={t('hrSettings.role')}
            subtitle={roleLabel}
            icon="shield-outline"
            iconTint={colors.surfaceMuted}
            style={styles.row}
          />
        </View>

        {showDeviceSecurity ? (
          <View style={styles.section}>
            <SectionHeader title={t('hrSettings.sectionDeviceSecurity')} />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
              {t('hrSettings.deviceSecurityHint')}
            </Text>
            {biometricEnabled && onToggleBiometric ? (
              <View style={[styles.row, styles.switchRow]}>
                <View style={styles.switchCopy}>
                  <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.switchTitle, align]}>
                    {biometricLabel || t('biometric.settings')}
                  </Text>
                  <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.switchSub, align]}>
                    {t('biometric.settingsSubtitle')}
                  </Text>
                </View>
                <Switch
                  accessibilityLabel={biometricLabel || t('biometric.settings')}
                  accessibilityState={{ disabled: biometricBusy, checked: biometricPreferenceOn }}
                  value={biometricPreferenceOn}
                  disabled={biometricBusy}
                  onValueChange={(next) => {
                    selectionFeedback()
                    void onToggleBiometric(next)
                  }}
                  trackColor={{ false: colors.surfaceMuted, true: colors.ink }}
                  thumbColor={colors.bg}
                />
              </View>
            ) : null}
            {onSelectAutoLock && autoLockTimeoutMs !== undefined ? (
              <>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('autoLock.settings')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('autoLock.settingsSubtitle')}
                </Text>
                {autoLockOptions.map((option) => {
                  const selected = option.value === autoLockTimeoutMs
                  return (
                    <ListRow
                      key={String(option.value)}
                      title={t(option.labelKey)}
                      icon={selected ? 'checkmark-circle' : 'ellipse-outline'}
                      iconTint={selected ? colors.ink : colors.surfaceMuted}
                      onPress={
                        autoLockBusy
                          ? undefined
                          : () => {
                              selectionFeedback()
                              void onSelectAutoLock(option.value)
                            }
                      }
                      style={styles.row}
                    />
                  )
                })}
              </>
            ) : null}
            {onChangePin ? (
              <ListRow
                title={t('pin.change')}
                subtitle={t('hrSettings.changePinSub')}
                icon="keypad-outline"
                iconTint={colors.surfaceMuted}
                showChevron
                onPress={() => {
                  selectionFeedback()
                  onChangePin()
                }}
                style={styles.row}
              />
            ) : null}
          </View>
        ) : null}

        <View style={styles.section}>
          <SectionHeader title={t('hrSettings.sectionDevice')} />
          <ListRow
            title={t('hrSettings.language')}
            subtitle={localeLabel}
            icon="language-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={() => void onToggleLocale()}
            style={styles.row}
          />
          <ListRow
            title={t('hrSettings.notifications')}
            subtitle={t('hrSettings.notificationsSub')}
            icon="notifications-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={() => void onOpenNotificationSettings()}
            style={styles.row}
          />
          {onSwitchEmployee ? (
            <>
              <ListRow
                testID="e2e.principal.switch.employee"
                title={
                  principalSwitchBusy
                    ? t('principal.switchingEmployee')
                    : t('hrSettings.switchEmployee')
                }
                subtitle={t('hrSettings.switchEmployeeSub')}
                icon="swap-horizontal-outline"
                iconTint={colors.surfaceMuted}
                showChevron={!principalSwitchBusy}
                disabled={principalSwitchBusy}
                onPress={() => void onSwitchEmployee()}
                style={styles.row}
              />
              {principalSwitchError ? (
                <Text
                  testID="e2e.principal.switch.error"
                  accessibilityRole="alert"
                  maxFontSizeMultiplier={typeScaling.body}
                  style={[styles.transitionError, align]}
                >
                  {principalSwitchError}
                </Text>
              ) : null}
            </>
          ) : null}
        </View>

        <View style={styles.section}>
          <SectionHeader title={t('hrSettings.sectionPrivacySupport')} />
          <ListRow
            title={t('hrSettings.privacy')}
            subtitle={t('hrSettings.privacySub')}
            icon="shield-checkmark-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={() => void onOpenPrivacy()}
            style={styles.row}
          />
          <ListRow
            title={t('hrSettings.support')}
            subtitle={t('hrSettings.supportSub')}
            icon="help-circle-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={() => void onOpenSupport()}
            style={styles.row}
          />
        </View>

        <View style={styles.section}>
          <SectionHeader title={t('hrSettings.sectionSession')} />
          <ListRow
            title={t('hrSettings.signOut')}
            subtitle={t('hrSettings.signOutSub')}
            icon="log-out-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={confirmSignOut}
            style={styles.row}
          />
          <ListRow
            title={t('hrSettings.signOutAll')}
            subtitle={t('hrSettings.signOutAllSub')}
            icon="exit-outline"
            iconTint={colors.surfaceMuted}
            showChevron
            onPress={confirmSignOutAll}
            style={styles.row}
          />
        </View>

        <View style={styles.section}>
          <SectionHeader title={t('hrSettings.sectionAbout')} />
          <ListRow
            title={t('hrSettings.aboutTitle')}
            subtitle={t('hrSettings.version', { version })}
            icon="information-circle-outline"
            iconTint={colors.surfaceMuted}
            style={styles.row}
          />
        </View>

        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.webNote, align]}>
          {t('hrSettings.webNote')}
        </Text>
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  nav: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  navSpacer: { width: 44 },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: 16,
  },
  switchCopy: { flex: 1, gap: 4 },
  switchTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  switchSub: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  footnote: { color: colors.subtle, fontSize: font.tiny },
  webNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18, paddingBottom: spacing.lg },
  transitionError: { color: colors.danger, fontSize: font.small, lineHeight: 18 },
})
