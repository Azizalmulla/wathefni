import type { ReactNode } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n } from '@/i18n'
import {
  EditorialHeading,
  FadeIn,
  MotionProgressBar,
  PastelCard,
  PremiumButton,
  ContentSkeleton,
  Wordmark,
} from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow } from '@/components/lists'
import { SectionTitle } from '@/components/ui'
import type {
  EmployeeAppComposition,
  HomeDestination,
  HomeTask,
} from '@/composition/employeeAppComposition'
import { daysUntil, formatNumber, formatTimeRange, statusLabel } from '@/lib/format'
import { asModuleDataState, isModuleFactual, type ModuleDataState } from '@/lib/moduleState'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type { EmployeeProfile, HomeResponse } from '@/api/types'

type DestinationVisual = {
  icon: keyof typeof Ionicons.glyphMap
  tint: string
  labelKey: string
}

/**
 * Ambient module identity, used as a small tinted icon tile rather than a filled
 * card. Colour still says "this is Documents"; it no longer paints a third of the
 * screen to do it.
 */
const DESTINATION_VISUALS: Record<HomeDestination['id'], DestinationVisual> = {
  schedule: { icon: 'calendar-outline', tint: colors.sky, labelKey: 'schedule.title' },
  leave: { icon: 'umbrella-outline', tint: colors.olive, labelKey: 'leave.title' },
  documents: { icon: 'documents-outline', tint: colors.lilac, labelKey: 'documents.title' },
  payslips: { icon: 'wallet-outline', tint: colors.butter, labelKey: 'payslips.title' },
}

const TASK_LABEL_KEYS: Record<HomeTask['kind'], string> = {
  onboarding_documents: 'home.taskOnboarding',
  document_renewal: 'home.taskDocuments',
  leave_pending: 'home.taskLeave',
  payslip_released: 'home.taskPayslips',
}

type HomeViewProps = {
  profile: EmployeeProfile | null
  composition: EmployeeAppComposition
  /** Server-owned projection: the only source of Home's business facts. */
  home: HomeResponse
  tasks: HomeTask[]
  refreshing?: boolean
  onRefresh?: () => void
  onNavigate: (path: string) => void
}

/**
 * Home hierarchy: today, then what needs doing, then anywhere the tab bar cannot
 * already reach.
 *
 * Every business value is rendered only when its owning module reported `ready`,
 * so a failed or pending read is never shown as "nothing scheduled".
 */
export function HomeView({
  profile,
  composition,
  home,
  tasks,
  refreshing,
  onRefresh,
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

  const shiftState = asModuleDataState(home.modules.shifts)
  const attendanceState = asModuleDataState(home.modules.attendance)
  const inboxState = asModuleDataState(home.modules.notifications)
  const shift = home.today.shifts?.[0]
  const attendanceToday = home.today.attendance
  const unread = home.inbox.unread
  const showToday = shiftState !== 'disabled' || attendanceState !== 'disabled'
  const onboarding = home.onboarding
  const onboardingTotal = onboarding?.required_total ?? 0
  const onboardingDone = onboarding?.satisfied_count ?? 0

  // The onboarding checklist has one presence on Home. It used to have two: a
  // task card telling the employee to finish their documents, and a progress card
  // immediately below saying the same thing with a bar. The progress card wins,
  // because it carries the count as well as the call to action.
  const showOnboardingCard = composition.showOnboardingJourney
  const taskList = showOnboardingCard
    ? tasks.filter((task) => task.kind !== 'onboarding_documents')
    : tasks
  const hasWork = taskList.length > 0 || showOnboardingCard

  const rowDirection = isRTL ? styles.rowReverse : undefined
  const align = { textAlign: isRTL ? 'right' : 'left' } as const

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={[styles.header, rowDirection]}>
          <Wordmark compact />
          <View style={[styles.headerActions, rowDirection]}>
            <InboxBell
              state={inboxState}
              unread={unread}
              onPress={() => onNavigate(composition.inboxEntry.href)}
            />
            <View style={styles.avatar} accessibilityLabel={profile?.name || t('profile.title')}>
              <Text maxFontSizeMultiplier={1.2} numberOfLines={1} style={styles.avatarText}>
                {initials || 'W'}
              </Text>
            </View>
          </View>
        </View>

        <FadeIn>
          <EditorialHeading>{t('home.greeting', { name: firstName })}</EditorialHeading>
        </FadeIn>

        {showToday ? (
          <FadeIn delay={60} style={styles.section}>
            <SectionTitle>{t('home.todayAtWork')}</SectionTitle>
            {/* Sky is Schedule's identity and the one ambient surface up here.
                The workday itself is the headline; the label is a section title. */}
            <PastelCard tone="sky" style={styles.todayCard}>
              {shiftState !== 'disabled' ? (
                <ModuleValue state={shiftState} align={align}>
                  <Text
                    maxFontSizeMultiplier={typeScaling.display}
                    style={[styles.todayHeadline, align]}
                  >
                    {shift ? formatTimeRange(shift.start_time, shift.end_time, locale) : t('home.noShiftToday')}
                  </Text>
                  {shift?.location ? (
                    <Text style={[styles.cardSupporting, align]}>{shift.location}</Text>
                  ) : null}
                </ModuleValue>
              ) : null}

              {attendanceState !== 'disabled' ? (
                <View style={styles.todayRecord}>
                  <Text style={[styles.todayLabel, align]}>{t('home.attendance')}</Text>
                  <ModuleValue state={attendanceState} align={align}>
                    <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.todayRecordValue, align]}>
                      {attendanceToday
                        ? statusLabel(attendanceToday.status, t)
                        : t('home.noAttendanceRecordedToday')}
                    </Text>
                  </ModuleValue>
                </View>
              ) : null}
            </PastelCard>
          </FadeIn>
        ) : null}

        {/* "All caught up" is the server's claim, not ours: an empty task list can
            also mean a module read failed, and that must not read as good news. */}
        {hasWork || home.caught_up ? (
        <FadeIn delay={80} style={styles.section}>
          <SectionTitle>{t('home.tasks')}</SectionTitle>

          {showOnboardingCard ? (
            <PastelCard
              tone="lilac"
              onPress={() => onNavigate('/onboarding')}
              accessibilityLabel={`${t('onboarding.title')}. ${t('onboarding.progress', {
                done: formatNumber(onboardingDone, locale, 0),
                total: formatNumber(onboardingTotal, locale, 0),
              })}`}
              style={styles.progressCard}
            >
              <View style={[styles.progressTop, rowDirection]}>
                <View style={styles.grow}>
                  <Text style={[styles.progressOverline, align]}>{t('onboarding.title')}</Text>
                  <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.progressTitle, align]}>
                    {onboarding?.pending_count ? t('home.continueChecklist') : t('home.onboardingComplete')}
                  </Text>
                </View>
                <Text maxFontSizeMultiplier={1.3} numberOfLines={1} style={styles.progressCountText}>
                  {t('onboarding.progress', {
                    done: formatNumber(onboardingDone, locale, 0),
                    total: formatNumber(onboardingTotal, locale, 0),
                  })}
                </Text>
              </View>
              <MotionProgressBar value={onboardingTotal ? onboardingDone / onboardingTotal : 1} />
            </PastelCard>
          ) : null}

          {taskList.map((task) => {
            const headline = taskHeadline(task, t, locale)
            return (
              <ListRow
                key={task.id}
                title={headline}
                subtitle={headline === t(TASK_LABEL_KEYS[task.kind]) ? null : t(TASK_LABEL_KEYS[task.kind])}
                meta={
                  task.count > 1
                    ? t('home.taskCount', { count: formatNumber(task.count, locale, 0) })
                    : null
                }
                emphasis={task.severity === 'action_required' ? 'warning' : undefined}
                icon={task.severity === 'action_required' ? 'flash-outline' : 'information-circle-outline'}
                showChevron
                onPress={() => onNavigate(task.href)}
                accessibilityLabel={headline}
              />
            )
          })}

          {/* Nothing to do is a quiet line, not a decorated card. */}
          {!hasWork ? (
            <ListRow
              title={t('home.caughtUp')}
              subtitle={t('home.caughtUpHint')}
              icon="checkmark-circle-outline"
            />
          ) : null}
        </FadeIn>
        ) : null}

        {composition.homeDestinations.length ? (
          <FadeIn delay={100} style={styles.section}>
            <SectionTitle>{t('home.destinations')}</SectionTitle>
            {composition.homeDestinations.map((destination) => {
              const visual = DESTINATION_VISUALS[destination.id]
              return (
                <ListRow
                  key={destination.id}
                  title={t(visual.labelKey)}
                  icon={visual.icon}
                  iconTint={visual.tint}
                  showChevron
                  onPress={() => onNavigate(destination.href)}
                  accessibilityLabel={t(visual.labelKey)}
                />
              )
            })}
          </FadeIn>
        ) : null}

        {composition.homePrimaryAction ? (
          <PremiumButton
            label={t('home.requestLeave')}
            onPress={() => onNavigate(composition.homePrimaryAction!.href)}
          />
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

/**
 * What a task says on its strongest line.
 *
 * "Your documents need renewing" is true for a passport expiring in nine months
 * and for a Civil ID that expired last week, and an employee cannot tell which
 * without opening the screen. When the documents module names the document and
 * dates it, the task says so.
 *
 * The date is the module's; only the phrasing is chosen here. A task without
 * detail, or with a date that will not parse, falls back to the generic label —
 * an urgency this function cannot substantiate is never implied.
 */
function taskHeadline(
  task: HomeTask,
  t: (key: string, vars?: Record<string, string | number>) => string,
  locale: string,
): string {
  const generic = t(TASK_LABEL_KEYS[task.kind])
  if (task.kind !== 'document_renewal') return generic
  const label = task.detail?.label
  if (!label) return generic
  const days = daysUntil(task.detail?.expiry_date)
  if (days === null) return generic
  if (days < 0) return t('home.documentExpired', { document: label })
  if (days === 0) return t('home.documentExpiresToday', { document: label })
  return t('home.documentExpiresIn', {
    document: label,
    count: formatNumber(days, locale, 0),
  })
}

/**
 * Inbox lives here rather than in the tab bar.
 *
 * The count is spoken in the accessibility label and drawn as a numeral, so the
 * badge is never the only thing carrying "you have unread messages".
 */
function InboxBell({
  state,
  unread,
  onPress,
}: {
  state: ModuleDataState
  unread: number
  onPress: () => void
}) {
  const { t, locale } = useI18n()
  const factual = isModuleFactual(state)
  const count = factual ? unread : 0
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={
        count
          ? `${t('notifications.title')}. ${t('home.unreadMessages', { count: formatNumber(count, locale, 0) })}`
          : t('notifications.title')
      }
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [styles.bell, pressed && styles.pressed]}
    >
      <Ionicons name={count ? 'notifications' : 'notifications-outline'} size={21} color={colors.ink} />
      {count ? (
        <View style={styles.badge}>
          <Text maxFontSizeMultiplier={1.3} numberOfLines={1} style={styles.badgeText}>
            {formatNumber(count, locale, 0)}
          </Text>
        </View>
      ) : null}
    </Pressable>
  )
}

export function HomeLoadingView() {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <View style={styles.stateScreen}>
      <Wordmark compact />
      <EditorialHeading>{t('home.todayAtWork')}</EditorialHeading>
      <PastelCard tone="cream" style={styles.stateCard}>
        <ContentSkeleton rows={4} />
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
      <View style={styles.stateErrorCard}>
        <Ionicons name="cloud-offline-outline" size={34} color={colors.danger} />
        <EditorialHeading size="medium">{t('common.error')}</EditorialHeading>
        <Text style={[styles.stateMessage, align]}>{t('error.generic')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      </View>
    </View>
  )
}

/**
 * Renders a module fact only when that module's read succeeded. Unavailable data
 * is stated as unavailable — never as an empty business value.
 */
function ModuleValue({
  state,
  align,
  children,
}: {
  state: ModuleDataState
  align: { textAlign: 'left' | 'right' }
  children: ReactNode
}) {
  const { t } = useI18n()
  if (isModuleFactual(state)) return <>{children}</>
  return (
    <View style={styles.moduleUnavailable}>
      <Text style={[styles.moduleUnavailableText, align]}>
        {state === 'error' ? t('home.dataUnavailable') : t('home.dataLoading')}
      </Text>
      {state === 'error' ? (
        <Text style={[styles.cardSupporting, align]}>{t('home.dataUnavailableHint')}</Text>
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  rowReverse: { flexDirection: 'row-reverse' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  bell: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    backgroundColor: colors.pink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  section: { gap: spacing.sm },
  todayCard: { gap: spacing.md },
  todayHeadline: { color: colors.ink, fontSize: font.h1, lineHeight: 32, fontWeight: '800', letterSpacing: -0.5 },
  todayRecord: { gap: 2 },
  todayLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  todayRecordValue: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  cardSupporting: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  grow: { flex: 1, minWidth: 0 },
  pressed: { opacity: 0.85 },
  badge: {
    position: 'absolute',
    top: 4,
    right: 2,
    minWidth: 18,
    minHeight: 18,
    paddingHorizontal: 5,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.danger,
  },
  badgeText: { color: colors.surface, fontSize: 10, fontWeight: '800' },
  progressCard: { gap: spacing.md },
  progressTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  progressCountText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  progressOverline: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  progressTitle: { color: colors.ink, fontSize: font.body, fontWeight: '800', marginTop: 2 },
  moduleUnavailable: { gap: 2 },
  moduleUnavailableText: { color: colors.subtle, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  stateScreen: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    gap: layout.sectionGap,
  },
  stateCard: { gap: spacing.lg, paddingVertical: spacing.xl },
  stateErrorCard: {
    gap: spacing.lg,
    padding: spacing.lg,
    paddingVertical: spacing.xl,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: colors.danger,
  },
  stateMessage: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
})
