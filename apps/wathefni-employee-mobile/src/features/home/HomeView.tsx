import type { ReactNode } from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@expo/vector-icons'

import { useI18n } from '@/i18n'
import {
  DirectionalIcon,
  EditorialHeading,
  FadeIn,
  IconBadge,
  MotionProgressBar,
  PastelCard,
  PremiumButton,
  PreviewSkeleton,
  WathefniBloom,
  Wordmark,
} from '@/components/premium'
import { SectionTitle } from '@/components/ui'
import { formatNumber, formatTimeRange, statusLabel } from '@/lib/format'
import { colors, font, radius, spacing } from '@/theme'
import type {
  AttendanceResponse,
  EmployeeProfile,
  LeaveResponse,
  NotificationsResponse,
  OnboardingResponse,
  ShiftRow,
} from '@/api/types'

export type HomeFeatureSet = {
  shifts: boolean
  attendance: boolean
  leave: boolean
  onboarding: boolean
  documents: boolean
}

type HomeViewProps = {
  profile: EmployeeProfile | null
  features: HomeFeatureSet
  shift?: ShiftRow
  attendance?: AttendanceResponse
  leave?: LeaveResponse
  notifications?: NotificationsResponse
  onboarding?: OnboardingResponse
  canRequestLeave: boolean
  onNavigate: (path: string) => void
}

export function HomeView({
  profile,
  features,
  shift,
  attendance,
  leave,
  notifications,
  onboarding,
  canRequestLeave,
  onNavigate,
}: HomeViewProps) {
  const { t, isRTL, locale } = useI18n()
  const firstName = (profile?.name || '').split(/\s+/)[0] || ''
  const initials = (profile?.name || t('home.employee'))
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
  const latestAttendance = attendance?.records?.[0]
  const primaryBalance = leave?.balances?.[0]
  const unread = notifications?.unread ?? 0
  const onboardingPending = onboarding?.pending_count ?? 0
  const onboardingTotal = onboarding?.required_total ?? 0
  const onboardingDone = onboarding?.received_count ?? 0
  const requiredPending = onboarding?.pending?.filter((item) => item.required !== false).length ?? 0
  const rejectedPending = onboarding?.pending?.filter((item) => (item.status || '').toLowerCase() === 'rejected').length ?? 0
  const caughtUp = !shift && unread === 0 && onboardingPending === 0
  const moduleCount = Number(features.shifts) + Number(features.attendance) + Number(features.leave) + 1
  const wideTiles = moduleCount === 1
  const rowDirection = isRTL ? styles.rowReverse : undefined
  const align = { textAlign: isRTL ? 'right' : 'left' } as const

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={[styles.header, rowDirection]}>
        <Wordmark compact />
        <View style={styles.avatar} accessibilityLabel={profile?.name || t('profile.title')}>
          <Text style={styles.avatarText}>{initials || 'W'}</Text>
        </View>
      </View>

      <FadeIn style={styles.hero}>
        <Text style={[styles.greeting, align]}>{t('home.greeting', { name: firstName })}</Text>
        <EditorialHeading>{t('home.todayAtWork')}</EditorialHeading>
      </FadeIn>

      {features.onboarding && (rejectedPending || requiredPending) ? (
        <FadeIn delay={70}>
          <PastelCard
            tone={rejectedPending ? 'blush' : 'butter'}
            style={styles.attentionCard}
            onPress={() => onNavigate('/onboarding')}
            accessibilityLabel={rejectedPending ? t('home.rejectedAction') : t('home.requiredAction')}
          >
            <View style={[styles.attentionRow, rowDirection]}>
              <IconBadge name={rejectedPending ? 'alert-outline' : 'checkmark-circle-outline'} size={36} inverted />
              <View style={styles.flex}>
                <Text style={[styles.attentionEyebrow, align]}>{t('home.needsAttention')}</Text>
                <Text style={[styles.attentionTitle, align]}>
                  {rejectedPending ? t('home.rejectedAction') : t('home.requiredAction')}
                </Text>
              </View>
              <View style={styles.attentionArrow}>
                <DirectionalIcon size={16} />
              </View>
            </View>
          </PastelCard>
        </FadeIn>
      ) : null}

      {caughtUp ? (
        <PastelCard tone="lilac" style={styles.caughtUpCard}>
          <View style={[styles.caughtUpRow, rowDirection]}>
            <IconBadge name="sparkles-outline" />
            <View style={styles.flex}>
              <Text style={[styles.caughtUpTitle, align]}>{t('home.caughtUp')}</Text>
              <Text style={[styles.cardSupporting, align]}>{t('home.caughtUpHint')}</Text>
            </View>
          </View>
          <WathefniBloom variant="watermark" />
        </PastelCard>
      ) : null}

      <FadeIn delay={100} style={styles.moduleGrid}>
        {features.shifts ? (
          <ModuleCard
            tone="sky"
            icon="calendar-outline"
            title={t('home.todayShift')}
            wide={wideTiles}
            onPress={() => onNavigate('/(tabs)/shifts')}
            isRTL={isRTL}
          >
            <Text style={[styles.metric, align]}>{shift ? formatTimeRange(shift.start_time, shift.end_time, locale) : t('home.noShiftToday')}</Text>
            {shift?.location ? <Text style={[styles.cardSupporting, align]}>{shift.location}</Text> : null}
          </ModuleCard>
        ) : null}

        {features.attendance ? (
          <ModuleCard
            tone="butter"
            icon="time-outline"
            title={t('home.attendance')}
            wide={wideTiles}
            onPress={() => onNavigate('/attendance')}
            isRTL={isRTL}
          >
            <Text style={[styles.metric, align]}>
              {latestAttendance ? statusLabel(latestAttendance.status, t) : t('home.noAttendanceToday')}
            </Text>
            {latestAttendance ? (
              <Text style={[styles.cardSupporting, align]}>{t('home.latestAttendance')}</Text>
            ) : null}
          </ModuleCard>
        ) : null}

        {features.leave ? (
          <ModuleCard
            tone="sage"
            icon="umbrella-outline"
            title={t('leave.title')}
            wide={wideTiles}
            onPress={() => onNavigate('/(tabs)/leave')}
            isRTL={isRTL}
          >
            <Text style={[styles.metric, align]}>
              {primaryBalance?.balance_days != null
                ? t('home.leaveDays', { count: formatNumber(primaryBalance.balance_days, locale) })
                : t('home.leaveAvailable')}
            </Text>
            {canRequestLeave ? (
              <MiniAction label={t('leave.request')} onPress={() => onNavigate('/leave/request')} />
            ) : null}
          </ModuleCard>
        ) : null}

        <ModuleCard
          tone="blush"
          icon="mail-outline"
          title={t('notifications.title')}
          badge={unread ? formatNumber(unread, locale, 0) : undefined}
          wide={wideTiles}
          onPress={() => onNavigate('/(tabs)/notifications')}
          isRTL={isRTL}
        >
          <Text style={[styles.metric, align]}>
            {unread ? t('home.unreadMessages', { count: formatNumber(unread, locale, 0) }) : t('notifications.empty')}
          </Text>
          {notifications?.notifications?.[0]?.title ? (
            <Text style={[styles.cardSupporting, align]} numberOfLines={1}>{notifications.notifications[0].title}</Text>
          ) : null}
        </ModuleCard>
      </FadeIn>

      {features.onboarding ? (
        <PastelCard
          tone="lilac"
          onPress={() => onNavigate('/onboarding')}
          accessibilityLabel={t('onboarding.title')}
          style={styles.progressCard}
        >
          <View style={[styles.progressTop, rowDirection]}>
            <View style={styles.progressCount}>
              <Text style={styles.progressCountText}>
                {formatNumber(onboardingDone, locale, 0)}/{formatNumber(onboardingTotal || 0, locale, 0)}
              </Text>
            </View>
            <View style={styles.flex}>
              <Text style={[styles.progressOverline, align]}>{t('onboarding.title')}</Text>
              <Text style={[styles.progressTitle, align]}>
                {onboardingPending ? t('home.continueChecklist') : t('home.onboardingComplete')}
              </Text>
            </View>
            <View style={styles.arrowButton}>
              <DirectionalIcon size={17} />
            </View>
          </View>
          <MotionProgressBar value={onboardingTotal ? onboardingDone / onboardingTotal : 1} />
        </PastelCard>
      ) : null}

      {((features.onboarding && onboardingPending > 0) || features.documents || features.attendance || canRequestLeave) ? (
        <View style={styles.quickSection}>
          <SectionTitle>{t('home.quickActions')}</SectionTitle>
          <View style={[styles.quickRow, rowDirection]}>
            {canRequestLeave ? (
              <QuickAction icon="calendar-clear-outline" label={t('home.requestLeave')} onPress={() => onNavigate('/leave/request')} />
            ) : null}
            {features.documents ? (
              <QuickAction icon="documents-outline" label={t('home.documents')} onPress={() => onNavigate('/documents')} />
            ) : null}
            {features.onboarding && onboardingPending > 0 ? (
              <QuickAction icon="checkmark-done-outline" label={t('home.onboarding')} onPress={() => onNavigate('/onboarding')} />
            ) : null}
            {features.attendance ? (
              <QuickAction icon="time-outline" label={t('home.attendance')} onPress={() => onNavigate('/attendance')} />
            ) : null}
          </View>
        </View>
      ) : null}

      <Text style={styles.previewLocale} accessibilityElementsHidden>{locale === 'ar' ? 'AR' : 'EN'}</Text>
    </ScrollView>
  )
}

export function HomeLoadingView() {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <View style={styles.stateScreen}>
      <Wordmark compact />
      <EditorialHeading>{t('home.todayAtWork')}</EditorialHeading>
      <PastelCard tone="lilac" style={styles.stateCard}>
        <PreviewSkeleton rows={4} />
      </PastelCard>
      <Text style={[styles.stateMessage, align]}>{t('common.loading')}</Text>
    </View>
  )
}

export function HomeErrorView({ onRetry }: { onRetry: () => void }) {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <View style={styles.stateScreen}>
      <Wordmark compact />
      <PastelCard tone="blush" style={styles.stateCard}>
        <Ionicons name="cloud-offline-outline" size={34} color={colors.danger} />
        <EditorialHeading size="medium">{t('common.error')}</EditorialHeading>
        <Text style={[styles.stateMessage, align]}>{t('error.generic')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      </PastelCard>
    </View>
  )
}

function ModuleCard({
  tone,
  icon,
  title,
  badge,
  children,
  onPress,
  wide,
  isRTL,
}: {
  tone: 'sky' | 'butter' | 'sage' | 'blush'
  icon: keyof typeof Ionicons.glyphMap
  title: string
  badge?: string
  children: ReactNode
  onPress: () => void
  wide: boolean
  isRTL: boolean
}) {
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <PastelCard
      tone={tone}
      containerStyle={[styles.moduleCard, wide && styles.moduleCardWide]}
      style={styles.moduleCardContent}
      onPress={onPress}
      accessibilityLabel={title}
    >
      <View style={[styles.moduleHead, isRTL && styles.rowReverse]}>
        <IconBadge name={icon} size={36} inverted />
        {badge ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{badge}</Text>
          </View>
        ) : null}
      </View>
      <Text style={[styles.moduleTitle, align]}>{title}</Text>
      <View style={styles.moduleBody}>{children}</View>
    </PastelCard>
  )
}

function MiniAction({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable style={({ pressed }) => [styles.miniAction, { opacity: pressed ? 0.75 : 1 }]} onPress={onPress}>
      <Text style={styles.miniActionText}>{label}</Text>
    </Pressable>
  )
}

function QuickAction({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap
  label: string
  onPress: () => void
}) {
  return (
    <Pressable style={({ pressed }) => [styles.quickAction, { opacity: pressed ? 0.72 : 1 }]} onPress={onPress}>
      <IconBadge name={icon} size={38} />
      <Text style={styles.quickLabel} numberOfLines={2}>{label}</Text>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.lg },
  rowReverse: { flexDirection: 'row-reverse' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  avatar: {
    width: 42,
    height: 42,
    borderRadius: radius.pill,
    backgroundColor: colors.pastelButter,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  hero: { gap: spacing.xs },
  greeting: { color: colors.text, fontSize: font.small, fontWeight: '600' },
  attentionCard: { paddingVertical: spacing.md, paddingHorizontal: spacing.md },
  attentionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  attentionEyebrow: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  attentionTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', marginTop: 2 },
  attentionArrow: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ink,
  },
  caughtUpCard: { minHeight: 82, justifyContent: 'center' },
  caughtUpRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, zIndex: 2 },
  caughtUpTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800' },
  cardSupporting: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  flex: { flex: 1 },
  moduleGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  moduleCard: { width: '47%', minHeight: 178, flexGrow: 1 },
  moduleCardWide: { width: '100%' },
  moduleCardContent: { minHeight: 178, gap: spacing.sm },
  moduleHead: { minHeight: 36, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  moduleTitle: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  moduleBody: { flex: 1, justifyContent: 'space-between', gap: spacing.sm },
  metric: { color: colors.ink, fontSize: font.h3, lineHeight: 24, fontWeight: '700' },
  badge: {
    minWidth: 24,
    height: 24,
    paddingHorizontal: 7,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.danger,
  },
  badgeText: { color: colors.surface, fontSize: font.tiny, fontWeight: '800' },
  miniAction: {
    alignSelf: 'stretch',
    minHeight: 34,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.68)',
  },
  miniActionText: { color: colors.ink, fontSize: font.tiny, fontWeight: '800' },
  progressCard: { gap: spacing.md },
  progressTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  progressCount: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.62)',
  },
  progressCountText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  progressOverline: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', marginTop: 2 },
  arrowButton: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ink,
  },
  quickSection: { gap: spacing.md },
  quickRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  quickAction: {
    width: '23%',
    minWidth: 72,
    flexGrow: 1,
    minHeight: 90,
    paddingVertical: spacing.sm,
    paddingHorizontal: 4,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
  },
  quickLabel: { color: colors.text, fontSize: 10.5, lineHeight: 13, fontWeight: '700', letterSpacing: -0.15, textAlign: 'center' },
  previewLocale: { height: 0, opacity: 0 },
  stateScreen: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    gap: spacing.lg,
  },
  stateCard: { gap: spacing.lg, paddingVertical: spacing.xl },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})
