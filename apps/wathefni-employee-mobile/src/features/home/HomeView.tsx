import type { ReactNode } from 'react'
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
import {
  EditorialHeading,
  FadeIn,
  MotionProgressBar,
  PremiumButton,
  ContentSkeleton,
  Wordmark,
  editorialFont,
} from '@/components/premium'
import { AmbientCard, AmbientIconTile } from '@/components/ambient'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow } from '@/components/lists'
import type {
  EmployeeAppComposition,
  HomeDestination,
  HomeTask,
} from '@/composition/employeeAppComposition'
import { daysUntil, formatNumber, formatTimeRange, kuwaitDayPart, statusLabel } from '@/lib/format'
import { asModuleDataState, isModuleFactual, type ModuleDataState } from '@/lib/moduleState'
import {
  ambient,
  colors,
  font,
  homeComposition,
  layout,
  radius,
  shadows,
  spacing,
  typeScaling,
} from '@/theme'
import type { EmployeeProfile, HomeResponse } from '@/api/types'
import {
  ambientForPriorityTone,
  isSparseHomePage,
  planHomeActions,
  visibleHomeDestinations,
} from '@/features/home/homeComposition'

type DestinationVisual = {
  icon: keyof typeof Ionicons.glyphMap
  labelKey: string
}

/**
 * Destination iconography. Workspace uses the green ambient family so it never
 * reads as a second yellow obligation card under Your tasks.
 */
const DESTINATION_VISUALS: Record<HomeDestination['id'], DestinationVisual> = {
  schedule: { icon: 'calendar-outline', labelKey: 'schedule.title' },
  leave: { icon: 'umbrella-outline', labelKey: 'leave.title' },
  documents: { icon: 'documents-outline', labelKey: 'documents.title' },
  payslips: { icon: 'wallet-outline', labelKey: 'payslips.title' },
  performance: { icon: 'ribbon-outline', labelKey: 'performance.title' },
  talent: { icon: 'sparkles-outline', labelKey: 'talent.title' },
  learning: { icon: 'school-outline', labelKey: 'learning.title' },
  benefits: { icon: 'heart-outline', labelKey: 'benefits.title' },
  engagement: { icon: 'chatbubble-ellipses-outline', labelKey: 'engagement.title' },
}

const TASK_LABEL_KEYS: Record<HomeTask['kind'], string> = {
  onboarding_documents: 'home.taskOnboarding',
  document_renewal: 'home.taskDocuments',
  leave_pending: 'home.taskLeave',
  payslip_released: 'home.taskPayslips',
}

const TASK_ICONS: Record<HomeTask['kind'], keyof typeof Ionicons.glyphMap> = {
  onboarding_documents: 'ribbon-outline',
  document_renewal: 'document-text-outline',
  leave_pending: 'umbrella-outline',
  payslip_released: 'wallet-outline',
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

/** Synthetic canary names arrive as `W5C-SYNTH|Aziz`. Greet the person. */
function personalDisplayName(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (trimmed.includes('|')) return trimmed.split('|').pop()!.trim()
  const synth = trimmed.match(/^W5C-SYNTH[\s:_-]+(.+)$/i)
  return synth ? synth[1].trim() : trimmed
}

/**
 * Home answers three questions, in this order: what is happening with my
 * workday, is anything waiting for me, and what can I do right now.
 *
 * Layout: pink workday → yellow priority under Your tasks → blue Request leave
 * in the same action cluster → quiet cream destination links only when they are
 * not already covered by the yellow card. On a quiet day the workday hero grows
 * so the cream below reads as page margin, not missing content.
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
  const { fontScale, width } = useWindowDimensions()
  const compactProgress = fontScale >= 1.3 || width < 360

  const personalName = personalDisplayName(profile?.name || '')
  const firstName = personalName.split(/\s+/).filter(Boolean)[0] || ''
  const initials = (personalName || t('home.employee'))
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
  const showPreboardingCard = composition.showPreboardingJourney
  const showProbationCard = composition.showProbationJourney
  const taskList = showOnboardingCard
    ? tasks.filter((task) => task.kind !== 'onboarding_documents')
    : tasks
  const hasWork =
    taskList.length > 0 || showOnboardingCard || showPreboardingCard || showProbationCard

  const plan = planHomeActions({ showOnboarding: showOnboardingCard, tasks: taskList })
  const leaveAction = composition.homePrimaryAction
  const destinations = visibleHomeDestinations(composition.homeDestinations, plan)
  const showCaughtUp = !hasWork && home.caught_up
  const showTasksSection =
    plan.showOnboarding ||
    showPreboardingCard ||
    showProbationCard ||
    Boolean(plan.actionTask) ||
    plan.secondaryTasks.length > 0 ||
    showCaughtUp
  const sparse = isSparseHomePage({
    plan,
    destinationCount: destinations.length,
    showCaughtUp,
  })

  const align = readingEdgeAlign(isRTL)
  const sectionTitleStyle = { fontFamily: editorialFont(locale), ...align }
  const dayPart = kuwaitDayPart()
  const greetingKey =
    dayPart === 'morning'
      ? 'home.greetingMorning'
      : dayPart === 'afternoon'
        ? 'home.greetingAfternoon'
        : 'home.greetingEvening'

  return (
    <PageScreen>
      <PageScrollView
        refreshing={refreshing}
        onRefresh={onRefresh}
        gap={sparse ? spacing.xxl : spacing.xl}
        contentStyle={[styles.pageContent, sparse ? styles.pageContentSparse : null]}
      >
        <View style={styles.header}>
          <Wordmark showPlatformAttribution />
          <View style={styles.headerActions}>
            <InboxBell
              state={inboxState}
              unread={unread}
              onPress={() => onNavigate(composition.inboxEntry.href)}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={personalName || t('profile.title')}
              hitSlop={8}
              onPress={() => onNavigate('/(tabs)/profile')}
              style={({ pressed }) => [styles.avatar, pressed && styles.avatarPressed]}
            >
              <Text maxFontSizeMultiplier={1.2} numberOfLines={1} style={styles.avatarText}>
                {initials || 'W'}
              </Text>
            </Pressable>
          </View>
        </View>

        {/* One enter after loading — staggered section FadeIns felt laggy/cheap. */}
        <FadeIn style={{ gap: sparse ? spacing.xxl : spacing.xl }}>
        <View style={[styles.hero, sparse ? styles.heroSparse : null]}>
          <Text maxFontSizeMultiplier={typeScaling.heading} style={[styles.eyebrow, align]}>
            {t(greetingKey, { name: firstName })}
          </Text>
          <EditorialHeading>{t('home.todayAtWork')}</EditorialHeading>
        </View>

        {showToday ? (
          <AmbientCard
              module="schedule"
              style={[styles.todayCard, sparse ? styles.todayCardSparse : null]}
            >
              <View style={styles.todayTop}>
                <View style={styles.chip}>
                  <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.chipText}>
                    {shiftState === 'disabled' ? t('home.attendance') : t('home.todayShift')}
                  </Text>
                </View>
                <AmbientIconTile
                  module="schedule"
                  icon="calendar-outline"
                  size={sparse ? 40 : 34}
                />
              </View>

              {shiftState !== 'disabled' ? (
                <ModuleValue state={shiftState} align={align}>
                  <Text
                    maxFontSizeMultiplier={typeScaling.display}
                    style={[
                      styles.todayHeadline,
                      sparse ? styles.todayHeadlineSparse : null,
                      !isRTL ? styles.todayHeadlineLTR : null,
                      align,
                    ]}
                  >
                    {shift
                      ? formatTimeRange(shift.start_time, shift.end_time, locale)
                      : t('home.noShiftToday')}
                  </Text>
                  {shift?.location ? (
                    <Text style={[styles.cardSupporting, align]}>{shift.location}</Text>
                  ) : null}
                </ModuleValue>
              ) : null}

              {attendanceState !== 'disabled' ? (
                <View style={[styles.attendanceLine, sparse ? styles.attendanceLineSparse : null]}>
                  <Text style={[styles.todayLabel, align]}>{t('home.attendance')}</Text>
                  <ModuleValue state={attendanceState} align={align}>
                    <Text
                      maxFontSizeMultiplier={typeScaling.body}
                      style={[styles.todayRecordValue, align]}
                    >
                      {attendanceToday
                        ? statusLabel(attendanceToday.status, t)
                        : t('home.noAttendanceRecordedToday')}
                    </Text>
                  </ModuleValue>
                </View>
              ) : null}
            </AmbientCard>
        ) : null}

        {/* "All caught up" is the server's claim, not ours: an empty task list can
            also mean a module read failed, and that must not read as good news. */}
        {showTasksSection ? (
          <View style={styles.section}>
            <Text
              accessibilityRole="header"
              maxFontSizeMultiplier={typeScaling.heading}
              style={[styles.homeSectionTitle, sectionTitleStyle]}
            >
              {t('home.tasks')}
            </Text>

            {plan.showOnboarding ? (
              <OnboardingActionCard
                compactProgress={compactProgress}
                done={onboardingDone}
                total={onboardingTotal}
                pending={onboarding?.pending_count ?? 0}
                onPress={() => onNavigate('/onboarding')}
              />
            ) : null}

            {showPreboardingCard ? (
              <ListRow
                title={t('home.preboarding')}
                subtitle={t('home.preboardingHint')}
                icon="airplane-outline"
                showChevron
                onPress={() => onNavigate('/preboarding')}
                accessibilityLabel={t('home.preboarding')}
              />
            ) : null}

            {showProbationCard ? (
              <ListRow
                title={t('home.probation')}
                subtitle={t('home.probationHint')}
                icon="hourglass-outline"
                showChevron
                onPress={() => onNavigate('/probation')}
                accessibilityLabel={t('home.probation')}
              />
            ) : null}

            {plan.actionTask ? (
              <HomeTaskCard
                task={plan.actionTask}
                headline={taskHeadline(plan.actionTask, t, locale)}
                subtitle={
                  taskHeadline(plan.actionTask, t, locale) ===
                  t(TASK_LABEL_KEYS[plan.actionTask.kind])
                    ? null
                    : t(TASK_LABEL_KEYS[plan.actionTask.kind])
                }
                meta={
                  plan.actionTask.count > 1
                    ? t('home.taskCount', {
                        count: formatNumber(plan.actionTask.count, locale, 0),
                      })
                    : null
                }
                onPress={() => onNavigate(plan.actionTask!.href)}
              />
            ) : null}

            {plan.secondaryTasks.map((task) => {
              const headline = taskHeadline(task, t, locale)
              const subtitle =
                headline === t(TASK_LABEL_KEYS[task.kind]) ? null : t(TASK_LABEL_KEYS[task.kind])
              return (
                <ListRow
                  key={task.id}
                  title={headline}
                  subtitle={subtitle}
                  meta={
                    task.count > 1
                      ? t('home.taskCount', { count: formatNumber(task.count, locale, 0) })
                      : null
                  }
                  emphasis={task.severity === 'action_required' ? 'warning' : undefined}
                  icon={TASK_ICONS[task.kind]}
                  showChevron
                  onPress={() => onNavigate(task.href)}
                  accessibilityLabel={headline}
                />
              )
            })}

            {showCaughtUp ? (
              <ListRow
                title={t('home.caughtUp')}
                subtitle={t('home.caughtUpHint')}
                icon="checkmark-circle-outline"
              />
            ) : null}
          </View>
        ) : null}

        {/* Request leave sits in the action cluster — right after waiting work. */}
        {leaveAction ? (
          <View style={styles.primaryAction}>
            <RequestLeavePill onPress={() => onNavigate(leaveAction.href)} />
          </View>
        ) : null}

        {/* Quiet discovery only. Documents is omitted when the yellow priority
            already opens that work. */}
        {destinations.length ? (
          <View style={styles.destinationSection}>
            {destinations.length > 1 ? (
              <Text
                accessibilityRole="header"
                maxFontSizeMultiplier={typeScaling.heading}
                style={[styles.homeSectionTitle, sectionTitleStyle]}
              >
                {t('home.destinations')}
              </Text>
            ) : null}
            {destinations.map((destination) => {
              const visual = DESTINATION_VISUALS[destination.id]
              return (
                <DestinationLink
                  key={destination.id}
                  label={t(visual.labelKey)}
                  icon={visual.icon}
                  onPress={() => onNavigate(destination.href)}
                />
              )
            })}
          </View>
        ) : null}
        </FadeIn>
      </PageScrollView>
    </PageScreen>
  )
}

/**
 * Full-width soft blue pill with ink label — Home composition blue, not module
 * green and not the black nav. Local to Home.
 */
function RequestLeavePill({ onPress }: { onPress: () => void }) {
  const { t } = useI18n()
  const label = t('home.requestLeave')
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.requestLeavePill, pressed ? styles.pressed : null]}
    >
      <Ionicons name="calendar-outline" size={18} color={colors.ink} />
      <Text maxFontSizeMultiplier={typeScaling.body} style={styles.requestLeaveLabel}>
        {label}
      </Text>
    </Pressable>
  )
}

/**
 * Discovery destination — no outer card. The small green tile communicates
 * workspace identity while the cream page remains visible around the link.
 */
function DestinationLink({
  label,
  icon,
  onPress,
}: {
  label: string
  icon: keyof typeof Ionicons.glyphMap
  onPress: () => void
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.destinationLink,
        pressed ? styles.pressed : null,
      ]}
    >
      <AmbientIconTile module="documents" icon={icon} size={34} />
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.destinationTitle, align]}>
        {label}
      </Text>
      <Ionicons
        name={isRTL ? 'chevron-back' : 'chevron-forward'}
        size={16}
        color={colors.subtle}
      />
    </Pressable>
  )
}

/**
 * The onboarding journey as the action surface: state, count and a bar in one
 * card, so the checklist never appears twice on Home.
 */
function OnboardingActionCard({
  compactProgress,
  done,
  total,
  pending,
  onPress,
}: {
  compactProgress: boolean
  done: number
  total: number
  pending: number
  onPress: () => void
}) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const progress = t('onboarding.progress', {
    done: formatNumber(done, locale, 0),
    total: formatNumber(total, locale, 0),
  })

  return (
    <AmbientCard
      module="onboarding"
      onPress={onPress}
      accessibilityLabel={`${t('onboarding.title')}. ${progress}`}
      style={styles.actionCard}
    >
      <View style={styles.actionRowInner}>
        {!compactProgress ? (
          <AmbientIconTile module="onboarding" icon="ribbon-outline" size={36} />
        ) : null}
        <View style={styles.grow}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.actionTitle, align]}>
            {pending ? t('home.continueChecklist') : t('home.onboardingComplete')}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.actionMeta, align]}>
            {progress}
          </Text>
        </View>
      </View>
      <MotionProgressBar value={total ? done / total : 1} color={ambient.onboarding.accent} />
    </AmbientCard>
  )
}

/**
 * The one thing waiting on the employee.
 *
 * Yellow means "you must act" on this Home. Informational work never reaches
 * this component — it stays a row.
 */
function HomeTaskCard({
  task,
  headline,
  subtitle,
  meta,
  onPress,
}: {
  task: HomeTask
  headline: string
  subtitle: string | null
  meta: string | null
  onPress: () => void
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const module = ambientForPriorityTone('action')
  const accessibilityLabel = [headline, subtitle, meta].filter(Boolean).join('. ')

  return (
    <AmbientCard
      module={module}
      onPress={onPress}
      accessibilityLabel={accessibilityLabel}
      style={styles.actionCard}
    >
      <View style={styles.actionRowInner}>
        <AmbientIconTile module={module} icon={TASK_ICONS[task.kind]} size={36} />
        <View style={styles.grow}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.actionTitle, align]}>
            {headline}
          </Text>
          {meta ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.actionMeta, align]}>
              {meta}
            </Text>
          ) : null}
        </View>
        <View style={styles.actionOrb}>
          <Ionicons
            name={isRTL ? 'chevron-back' : 'chevron-forward'}
            size={15}
            color={colors.ink}
          />
        </View>
      </View>
    </AmbientCard>
  )
}

/**
 * What a task says on its strongest line.
 *
 * "Your documents need renewing" is true for a passport expiring in nine months
 * and for a Civil ID that expired last week, and an employee cannot tell which
 * without opening the screen. When the documents module names the document and
 * dates it, the task says so.
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
  const { t, locale, isRTL } = useI18n()
  const factual = isModuleFactual(state)
  const count = factual ? unread : 0
  const label =
    state === 'error'
      ? t('home.dataUnavailable')
      : state === 'loading'
        ? t('home.dataLoading')
        : count > 0
          ? t('home.unreadMessages', { count: formatNumber(count, locale, 0) })
          : t('notifications.title')

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.bell, pressed ? styles.pressed : null]}
    >
      <Ionicons name="notifications-outline" size={22} color={colors.ink} />
      {count > 0 ? (
        <View style={[styles.badge, isRTL ? styles.badgeRTL : styles.badgeLTR]}>
          <Text maxFontSizeMultiplier={1.2} style={styles.badgeText}>
            {count > 99 ? '99+' : formatNumber(count, locale, 0)}
          </Text>
        </View>
      ) : null}
    </Pressable>
  )
}

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
  if (state === 'ready') return <>{children}</>
  if (state === 'loading') {
    return <Text style={[styles.cardSupporting, align]}>{t('home.dataLoading')}</Text>
  }
  return (
    <View style={styles.moduleUnavailable}>
      <Text style={[styles.moduleUnavailableText, align]}>{t('home.dataUnavailable')}</Text>
      <Text style={[styles.cardSupporting, align]}>{t('home.dataUnavailableHint')}</Text>
    </View>
  )
}

export function HomeLoadingView() {
  return (
    <View style={styles.stateScreen}>
      <Wordmark />
      <ContentSkeleton rows={4} />
    </View>
  )
}

export function HomeErrorView({ onRetry }: { onRetry: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <PageScreen style={styles.stateScreen}>
      <Wordmark />
      <View style={styles.stateErrorCard}>
        <Text style={[styles.moduleUnavailableText, align]}>{t('home.dataUnavailable')}</Text>
        <Text style={[styles.stateMessage, align]}>{t('home.dataUnavailableHint')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      </View>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  // No flexGrow footer tricks — content stacks as one intentional unit.
  // Sparse days open the rhythm and grow the workday hero instead.
  // Bottom clearance stays on PageScrollView (do not override paddingBottom).
  pageContent: { paddingTop: spacing.lg },
  pageContentSparse: { paddingTop: spacing.xl },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  bell: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.pink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarPressed: { opacity: 0.82 },
  avatarText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  section: { gap: spacing.md },
  homeSectionTitle: {
    color: colors.ink,
    fontSize: font.h2,
    lineHeight: 26,
    fontWeight: '600',
    letterSpacing: -0.3,
  },
  hero: { gap: 4, paddingTop: spacing.xs },
  heroSparse: { gap: spacing.sm, paddingTop: spacing.sm },
  eyebrow: { color: colors.subtle, fontSize: font.body, fontWeight: '500' },
  chip: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: 5,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  chipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  todayCard: {
    gap: spacing.md,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  todayCardSparse: {
    gap: spacing.lg,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.xl,
  },
  todayTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  todayHeadline: { color: colors.ink, fontSize: font.h1, fontWeight: '800' },
  todayHeadlineSparse: { fontSize: font.display },
  todayHeadlineLTR: { letterSpacing: -0.45 },
  attendanceLine: { gap: 2 },
  attendanceLineSparse: { gap: spacing.xs, paddingTop: spacing.xs },
  todayLabel: { color: colors.ink, fontSize: font.tiny, fontWeight: '700', opacity: 0.62 },
  todayRecordValue: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  cardSupporting: { color: colors.ink, fontSize: font.tiny, lineHeight: 16, opacity: 0.7 },
  actionCard: {
    gap: spacing.sm,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.lg,
  },
  actionRowInner: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  actionTitle: { color: colors.ink, fontSize: font.body, lineHeight: 21, fontWeight: '800' },
  actionMeta: {
    color: colors.ink,
    fontSize: font.tiny,
    fontWeight: '700',
    opacity: 0.7,
    marginTop: 2,
  },
  actionOrb: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  primaryAction: {
    marginTop: -spacing.sm,
  },
  requestLeavePill: {
    minHeight: 52,
    borderRadius: radius.pill,
    backgroundColor: homeComposition.requestLeave.fill,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    ...shadows.card,
  },
  requestLeaveLabel: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '700',
    letterSpacing: -0.1,
  },
  destinationSection: {
    gap: spacing.sm,
  },
  destinationLink: {
    minHeight: layout.touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  destinationTitle: {
    flex: 1,
    minWidth: 0,
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '700',
  },
  grow: { flex: 1, minWidth: 0 },
  pressed: { opacity: 0.88 },
  badge: {
    position: 'absolute',
    top: 4,
    minWidth: 18,
    minHeight: 18,
    paddingHorizontal: 5,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ink,
  },
  badgeLTR: { right: 2 },
  badgeRTL: { left: 2 },
  badgeText: { color: colors.surface, fontSize: 10, fontWeight: '800' },
  moduleUnavailable: { gap: 2 },
  moduleUnavailableText: {
    color: colors.ink,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
  },
  stateScreen: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    gap: layout.sectionGap,
  },
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
