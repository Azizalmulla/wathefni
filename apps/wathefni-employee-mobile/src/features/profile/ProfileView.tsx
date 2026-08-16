import { Linking, Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { PastelCard, Wordmark } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { SectionHeader } from '@/components/lists'
import { displayPhone, telHref } from '@/lib/contact'
import { formatDate } from '@/lib/format'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { ProfileEmployment, ProfilePersonal, ProfileResponse } from '@/api/types'

type Props = {
  profile: ProfileResponse | null
  /** Fallback from /app/me while /app/profile is loading. */
  fallbackName?: string | null
  refreshing?: boolean
  onRefresh?: () => void
  onBank?: () => void
  onPreboarding?: () => void
  onProbation?: () => void
  onSettings: () => void
  onPrivacySupport: () => void
  onSignOut: () => void
  profileError?: boolean
  onRetryProfile?: () => void
}

/**
 * Profile hierarchy: Personal → Employment → Bank (frozen ESS) → Account.
 * Documents and Payslips are not duplicated here — they own their destinations.
 */
export function ProfileView({
  profile,
  fallbackName,
  refreshing,
  onRefresh,
  onBank,
  onPreboarding,
  onProbation,
  onSettings,
  onPrivacySupport,
  onSignOut,
  profileError,
  onRetryProfile,
}: Props) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const personal: ProfilePersonal | null = profile?.personal ?? null
  const employment: ProfileEmployment | null = profile?.employment ?? null
  const name = personal?.name || fallbackName || '—'
  const initials = initialsFor(name)

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={styles.nav}>
          <Wordmark compact />
        </View>

        {/*
          Identity is stated once. The screen used to open with the heading
          "Profile", a subtitle about the profile, a hero card with the employee's
          name and job title, and then a Personal section whose first row was the
          same name and an Employment section whose first row was the same job
          title — four restatements before a single new fact.

          Identity is also the one pink moment in the app: it is about the person.
        */}
        <PastelCard tone="pink" style={styles.profileHero} accessibilityLabel={name}>
          <View style={styles.profileTop}>
            <View style={styles.largeAvatar} accessibilityElementsHidden>
              <Text style={styles.largeAvatarText}>{initials || 'W'}</Text>
            </View>
            <View style={styles.flex}>
              <Text style={[styles.profileName, align]}>{name}</Text>
              {employment?.position_title ? (
                <Text style={[styles.supporting, align]}>{employment.position_title}</Text>
              ) : null}
            </View>
          </View>
        </PastelCard>

        {/* A failed read is a status, not an ambient moment: neutral card, semantic edge. */}
        {profileError && !profile ? (
          <View style={styles.noticeCard}>
            <Text style={[styles.itemTitle, align]}>{t('profile.unavailable')}</Text>
            <Text style={[styles.supporting, align]}>{t('profile.unavailableHint')}</Text>
            {onRetryProfile ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t('common.retry')}
                onPress={onRetryProfile}
                style={styles.retryChip}
                hitSlop={8}
              >
                <Text style={styles.retryText}>{t('common.retry')}</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        <View style={styles.section}>
          <SectionHeader title={t('profile.personal')} />
          <View style={styles.detailsCard}>
            <DetailRow icon="call-outline" label={t('profile.phone')} value={displayPhone(personal?.phone) || '—'} />
            {personal?.email ? (
              <DetailRow icon="mail-outline" label={t('profile.email')} value={personal.email} />
            ) : null}
          </View>
        </View>

        <View style={styles.section}>
          <SectionHeader title={t('profile.employment')} />
          <View style={styles.detailsCard}>
            <DetailRow
              icon="people-outline"
              label={t('profile.department')}
              value={employment?.department || '—'}
            />
            {/*
             * Company and Employee ID are intentionally absent. `/app/profile` only
             * exposes `company_code` and `employee_key`, which are backend keys
             * (the employee key is a company prefix plus a phone number), not values
             * an employee can read or quote. Showing part of a key would be inventing
             * a staff number. Reinstate these rows when the profile contract carries a
             * real company name / staff number.
             */}
            {employment?.start_date ? (
              <DetailRow
                icon="calendar-outline"
                label={t('profile.startDate')}
                value={formatDate(employment.start_date, locale)}
              />
            ) : null}
            {/* A manager the employee cannot reach is trivia. The number is the
                one already stored on their own record and already shown here;
                the call action only saves them copying it out. */}
            {employment?.manager ? (
              <DetailRow
                icon="person-circle-outline"
                label={t('profile.manager')}
                value={employment.manager.name || displayPhone(employment.manager.phone) || '—'}
                supporting={
                  employment.manager.name ? displayPhone(employment.manager.phone) || null : null
                }
                action={
                  telHref(employment.manager.phone)
                    ? {
                        icon: 'call-outline',
                        label: t('profile.callManager'),
                        onPress: () => void openTel(telHref(employment.manager!.phone)),
                      }
                    : null
                }
              />
            ) : null}
          </View>
        </View>

        {onBank ? (
          <View style={styles.section}>
            <SectionHeader title={t('profile.bank')} />
            <MenuRow icon="card-outline" label={t('bank.menuEntry')} onPress={onBank} />
            <Text style={[styles.supporting, align]}>{t('profile.bankHint')}</Text>
          </View>
        ) : null}

        {onPreboarding || onProbation ? (
          <View style={styles.section}>
            <SectionHeader title={t('profile.journeys')} />
            {onPreboarding ? (
              <MenuRow icon="airplane-outline" label={t('profile.preboarding')} onPress={onPreboarding} />
            ) : null}
            {onProbation ? (
              <MenuRow icon="hourglass-outline" label={t('profile.probation')} onPress={onProbation} />
            ) : null}
          </View>
        ) : null}

        <View style={styles.section}>
          <SectionHeader title={t('profile.account')} />
          <MenuRow icon="settings-outline" label={t('settings.title')} onPress={onSettings} />
          <MenuRow icon="help-circle-outline" label={t('remaining.privacySupportTitle')} onPress={onPrivacySupport} />
          <MenuRow icon="log-out-outline" label={t('auth.signOut')} onPress={onSignOut} danger />
        </View>
      </PageScrollView>
    </PageScreen>
  )
}

function initialsFor(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

/**
 * Label above value, both starting at the same edge.
 *
 * The previous row pinned the label to a fixed 96pt column and floated the value
 * to the opposite edge, which broke on long emails, long Arabic department names
 * and large Dynamic Type. Stacking removes the width arithmetic entirely: the
 * value wraps down the card instead of fighting the label for horizontal space,
 * and the same layout is correct in LTR and RTL.
 */
function DetailRow({
  icon,
  label,
  value,
  supporting,
  action,
}: {
  icon: keyof typeof Ionicons.glyphMap
  label: string
  value: string
  supporting?: string | null
  /**
   * Trailing action, as its own control rather than a tap target on the whole
   * row: a row that dials when brushed is a row nobody scrolls past safely.
   */
  action?: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void } | null
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View
      style={styles.detailRow}
      accessibilityLabel={`${label}: ${value}${supporting ? `. ${supporting}` : ''}`}
    >
      <View style={styles.detailIcon} accessibilityElementsHidden>
        <Ionicons name={icon} size={18} color={colors.ink} />
      </View>
      <View style={styles.detailText}>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.detailLabel, align]}>
          {label}
        </Text>
        <Text
          maxFontSizeMultiplier={typeScaling.body}
          style={[styles.detailValue, align]}
          selectable
        >
          {value}
        </Text>
        {supporting ? (
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.detailSupporting, align]} selectable>
            {supporting}
          </Text>
        ) : null}
      </View>
      {action ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action.label}
          onPress={action.onPress}
          style={({ pressed }) => [styles.detailAction, pressed && styles.pressed]}
          hitSlop={6}
        >
          <Ionicons name={action.icon} size={19} color={colors.accent} />
        </Pressable>
      ) : null}
    </View>
  )
}

/**
 * Hand the number to the phone app. A device that cannot dial (simulator, iPad
 * without a paired phone) simply does nothing — there is no error worth showing
 * for "this device does not make calls".
 */
async function openTel(href: string | null): Promise<void> {
  if (!href) return
  try {
    if (await Linking.canOpenURL(href)) await Linking.openURL(href)
  } catch {
    // Dialling is a convenience; the number stays visible and selectable above.
  }
}

function MenuRow({
  icon,
  label,
  onPress,
  danger = false,
}: {
  icon: keyof typeof Ionicons.glyphMap
  label: string
  onPress: () => void
  danger?: boolean
}) {
  const { isRTL } = useI18n()
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.menuRow, pressed && styles.pressed]}
      hitSlop={4}
    >
      <View style={[styles.menuIcon, danger && styles.menuIconDanger]}>
        <Ionicons name={icon} size={19} color={danger ? colors.danger : colors.ink} />
      </View>
      <Text
        style={[
          styles.menuLabel,
          styles.flex,
          danger && { color: colors.danger },
          readingEdgeAlign(isRTL),
        ]}
      >
        {label}
      </Text>
      <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={18} color={colors.subtle} />
    </Pressable>
  )
}

const styles = StyleSheet.create({
  nav: { flexDirection: 'row', alignItems: 'center' },
  profileHero: { minHeight: 96, justifyContent: 'center' },
  profileTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, zIndex: 2 },
  largeAvatar: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  largeAvatarText: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  profileName: { color: colors.ink, fontSize: font.h3, fontWeight: '800' },
  supporting: { color: colors.subtle, fontSize: font.small, lineHeight: 19 },
  section: { gap: spacing.sm },
  detailsCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    gap: 2,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    minHeight: layout.touchTarget,
  },
  detailIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted,
  },
  detailText: { flex: 1, gap: 1, minWidth: 0, paddingTop: 2 },
  detailLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  detailSupporting: { color: colors.subtle, fontSize: font.small, lineHeight: 18, marginTop: 1 },
  detailAction: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  detailValue: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  menuRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 52,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
  },
  menuIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted,
  },
  menuIconDanger: { backgroundColor: colors.surfaceMuted },
  menuLabel: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  pressed: { opacity: 0.85 },
  flex: { flex: 1 },
  noticeCard: {
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: colors.danger,
  },
  itemTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  retryChip: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
    minHeight: 44,
    justifyContent: 'center',
  },
  retryText: { color: colors.surface, fontWeight: '700', fontSize: font.small },
})
