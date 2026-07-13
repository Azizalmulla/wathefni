import { useEffect, useRef } from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { registerForPushToken } from '@/push/registerForPush'
import { Card, FeatureMark, PageIntro, SectionTitle, StatusChip } from '@/components/ui'
import { ErrorState, LoadingState } from '@/components/States'
import { formatTimeRange } from '@/lib/format'
import { colors, font, radius, spacing } from '@/theme'
import type { NotificationItem, NotificationsResponse, OnboardingResponse, ShiftRow } from '@/api/types'

export default function HomeScreen() {
  const { t } = useI18n()
  const { profile, request, hasFeature, can } = useAuth()
  const router = useRouter()
  const pushRegistered = useRef(false)

  // Register for push once per signed-in session. Non-blocking and best-effort:
  // a denied permission simply means the in-app inbox is the only channel.
  useEffect(() => {
    if (pushRegistered.current || !can('settings', 'manage_push')) return
    pushRegistered.current = true
    void (async () => {
      const result = await registerForPushToken()
      if (!result) return
      try {
        await request('/app/push/register', { method: 'POST', json: { push_token: result.token, platform: result.platform } })
      } catch {
        pushRegistered.current = false
      }
    })()
  }, [request, can])

  const shiftsEnabled = hasFeature('shifts')
  const onboardingEnabled = hasFeature('onboarding')
  const documentsEnabled = hasFeature('documents')
  const attendanceEnabled = hasFeature('attendance')
  const leaveEnabled = hasFeature('leave')
  const today = useAppQuery<{ shifts: ShiftRow[] }>(['shifts', 'today'], '/app/shifts/today', { enabled: shiftsEnabled })
  const onboarding = useAppQuery<OnboardingResponse>(['onboarding'], '/app/onboarding', { enabled: onboardingEnabled })
  const notifications = useAppQuery<NotificationsResponse>(['notifications'], '/app/notifications')

  if ((shiftsEnabled && today.isLoading) || notifications.isLoading) return <LoadingState />
  if (shiftsEnabled && today.isError) return <ErrorState error={today.error} onRetry={() => today.refetch()} />
  if (notifications.isError) return <ErrorState error={notifications.error} onRetry={() => notifications.refetch()} />

  const shift = today.data?.shifts?.[0]
  const firstName = (profile?.name || '').split(' ')[0] || profile?.name || ''

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <PageIntro
        eyebrow={t('app.name')}
        title={t('home.greeting', { name: firstName })}
        subtitle={t('home.subtitle')}
      />

      {shiftsEnabled ? (
        <Card tone="accent" style={styles.shiftCard}>
          <View style={styles.cardHeading}>
            <FeatureMark glyph="S" />
            <View style={styles.flex}>
              <SectionTitle>{t('home.todayShift')}</SectionTitle>
              <Text style={styles.cardHint}>{t('home.shiftHint')}</Text>
            </View>
          </View>
          {shift ? (
            <View style={styles.shiftBody}>
              <Text style={styles.shiftTime}>{formatTimeRange(shift.start_time, shift.end_time)}</Text>
              {shift.location ? <Text style={styles.muted}>{shift.location}</Text> : null}
            </View>
          ) : (
            <Text style={styles.muted}>{t('home.noShiftToday')}</Text>
          )}
        </Card>
      ) : null}

      {onboardingEnabled || documentsEnabled || attendanceEnabled || leaveEnabled ? (
        <>
          <SectionTitle>{t('home.quickActions')}</SectionTitle>
          <View style={styles.grid}>
            {onboardingEnabled ? (
              <ActionTile
                label={t('home.onboarding')}
                subtitle={t('home.onboardingHint')}
                glyph="O"
                badge={onboarding.data?.pending_count}
                onPress={() => router.push('/onboarding')}
              />
            ) : null}
            {documentsEnabled ? (
              <ActionTile label={t('home.documents')} subtitle={t('home.documentsHint')} glyph="D" onPress={() => router.push('/documents')} />
            ) : null}
            {attendanceEnabled ? (
              <ActionTile label={t('home.attendance')} subtitle={t('home.attendanceHint')} glyph="A" onPress={() => router.push('/attendance')} />
            ) : null}
            {can('leave', 'request') ? (
              <ActionTile
                label={t('home.requestLeave')}
                subtitle={t('home.leaveHint')}
                glyph="L"
                onPress={() => router.push('/leave/request')}
              />
            ) : null}
          </View>
        </>
      ) : null}

      {notifications.data && notifications.data.notifications.length ? (
        <Card>
          <View style={styles.sectionHeading}>
            <SectionTitle>{t('notifications.title')}</SectionTitle>
            {notifications.data.unread ? <StatusChip label={`${notifications.data.unread}`} tone="warning" /> : null}
          </View>
          {notifications.data.notifications.slice(0, 3).map((n: NotificationItem) => (
            <Pressable key={n.id} style={styles.notifRow} onPress={() => router.push('/(tabs)/notifications')}>
              <View style={styles.flex}>
                <Text style={styles.notifTitle}>{n.title}</Text>
                {n.body ? <Text style={styles.muted} numberOfLines={1}>{n.body}</Text> : null}
              </View>
              {!n.read ? <StatusChip label="•" tone="warning" /> : null}
            </Pressable>
          ))}
        </Card>
      ) : null}
    </ScrollView>
  )
}

function ActionTile({
  label,
  subtitle,
  glyph,
  badge,
  onPress,
}: {
  label: string
  subtitle: string
  glyph: string
  badge?: number
  onPress: () => void
}) {
  return (
    <Pressable style={({ pressed }) => [styles.tile, { opacity: pressed ? 0.85 : 1 }]} onPress={onPress} accessibilityRole="button">
      <FeatureMark glyph={glyph} />
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={styles.tileSubtitle} numberOfLines={2}>{subtitle}</Text>
      {badge ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{badge}</Text>
        </View>
      ) : null}
    </Pressable>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.lg },
  shiftCard: { padding: spacing.xl, gap: spacing.lg },
  cardHeading: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  cardHint: { color: colors.subtle, fontSize: font.small, marginTop: 2 },
  shiftBody: { gap: spacing.xs },
  shiftTime: { fontSize: font.display, fontWeight: '800', color: colors.primary, letterSpacing: -0.5 },
  muted: { fontSize: font.body, color: colors.subtle },
  flex: { flex: 1 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  tile: {
    width: '47%',
    flexGrow: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.xs,
    minHeight: 144,
  },
  tileLabel: { fontSize: font.body, fontWeight: '700', color: colors.text, marginTop: spacing.xs },
  tileSubtitle: { fontSize: font.small, color: colors.subtle, lineHeight: 18 },
  badge: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    minWidth: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { color: '#fff', fontSize: font.tiny, fontWeight: '700' },
  sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  notifRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  notifTitle: { fontSize: font.body, fontWeight: '600', color: colors.text },
})
