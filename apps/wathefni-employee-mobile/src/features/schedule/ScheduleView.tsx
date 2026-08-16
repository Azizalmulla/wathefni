import { memo, useCallback, useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { EditorialHeading, FadeIn, PastelCard, Wordmark } from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { formatClockTime, formatDate, formatNumber, formatTimeRange, statusLabel } from '@/lib/format'
import { asModuleDataState, isModuleFactual, type ModuleDataState } from '@/lib/moduleState'
import { colors, font, layout, radius, scheduleComposition, spacing, typeScaling } from '@/theme'
import type { WorkdayEntry, WorkdayRecorded, WorkdayResponse, WorkdayScheduled } from '@/api/types'

import { AttendanceCountPill, AttendanceStatusMark, ScheduledStatusMark } from './attendancePills'
import { presenceDates, resolveSelectedDay } from './scheduleDayModel'
import { ScheduleWeekStrip } from './ScheduleWeekStrip'

/** Root previews only — more stays behind Show more within the fetched window. */
const UPCOMING_PREVIEW = 5
const RECENT_PREVIEW = 5

/**
 * One Schedule surface over the Shifts and Attendance authorities.
 *
 * Root order: week selector → selected day / Today → Upcoming preview → Recent
 * attendance with a quiet 30-day Present/Late/Absent line. Day navigation is
 * client-side over the existing `/app/workday` window only — never a fabricated
 * archive. Date taps must not re-render Upcoming/Recent (isolated trailing sections).
 */
export function ScheduleView({
  data,
  refreshing,
  onRefresh,
}: {
  data: WorkdayResponse
  refreshing?: boolean
  onRefresh?: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const [selectedDate, setSelectedDate] = useState(data.date)
  const windowDays = data.window?.days ?? 30
  // Stable while the workday payload identity fields are unchanged — not on every parent render.
  const presence = useMemo(
    () => presenceDates(data),
    [data.date, data.today.entries, data.upcoming, data.recent],
  )
  const jumpToToday = useCallback(() => setSelectedDate(data.date), [data.date])

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={styles.nav}>
          <Wordmark compact />
        </View>

        <FadeIn style={styles.hero}>
          <Text style={[styles.eyebrow, align]}>{formatDate(data.date, locale)}</Text>
          <EditorialHeading>{t('schedule.title')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('schedule.subtitle')}</Text>
        </FadeIn>

        <ScheduleWeekStrip
          today={data.date}
          selectedDate={selectedDate}
          windowDays={windowDays}
          presence={presence}
          onSelectDate={setSelectedDate}
        />

        <SelectedDaySection data={data} selectedDate={selectedDate} onJumpToToday={jumpToToday} />

        {/* Memoized: date taps must not rebuild upcoming/recent lists. */}
        <ScheduleTrailingSections data={data} />
      </PageScrollView>
    </PageScreen>
  )
}

const SelectedDaySection = memo(function SelectedDaySection({
  data,
  selectedDate,
  onJumpToToday,
}: {
  data: WorkdayResponse
  selectedDate: string
  onJumpToToday: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const selected = useMemo(() => resolveSelectedDay(data, selectedDate), [data, selectedDate])
  const dayTitle = selected.isToday ? t('schedule.today') : formatDate(selected.date, locale)
  const shiftsState = asModuleDataState(data.authority.shifts)
  const attendanceState = asModuleDataState(data.authority.attendance)

  return (
    <View style={styles.section}>
      <View style={styles.dayHead}>
        <Text
          accessibilityRole="header"
          maxFontSizeMultiplier={typeScaling.heading}
          style={[styles.dayTitle, readingEdgeAlign(isRTL)]}
        >
          {dayTitle}
        </Text>
        {!selected.isToday ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('schedule.backToToday')}
            hitSlop={8}
            onPress={onJumpToToday}
            style={styles.todayJump}
          >
            <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.todayJumpText}>
              {t('schedule.backToToday')}
            </Text>
          </Pressable>
        ) : null}
      </View>
      <SelectedDayPanel
        selected={selected}
        shiftsState={shiftsState}
        attendanceState={attendanceState}
      />
    </View>
  )
})

/**
 * Upcoming + Recent + HR. Isolated so rapid date selection cannot reconcile
 * these subtrees on every tap.
 */
const ScheduleTrailingSections = memo(function ScheduleTrailingSections({
  data,
}: {
  data: WorkdayResponse
}) {
  const { t, locale, isRTL } = useI18n()
  const router = useRouter()
  const align = readingEdgeAlign(isRTL)
  const shiftsState = asModuleDataState(data.authority.shifts)
  const attendanceState = asModuleDataState(data.authority.attendance)
  const upcomingState = asModuleDataState(data.authority.shifts_upcoming)
  const summary = data.window?.summary
  const upcoming = data.upcoming ?? []
  const recent = data.recent ?? []
  const upcomingPage = usePagedList(upcoming, UPCOMING_PREVIEW)
  const recentPage = usePagedList(recent, RECENT_PREVIEW)
  const windowDays = data.window?.days ?? 30

  return (
    <>
      {shiftsState !== 'disabled' ? (
        <View style={styles.section}>
          <SectionHeader title={t('schedule.upcoming')} />
          {isModuleFactual(upcomingState) ? (
            upcoming.length ? (
              <>
                {upcomingPage.visible.map((shift, index) => (
                  <ScheduledCard key={shift.shift_id || `${shift.date}-${index}`} shift={shift} />
                ))}
                {upcomingPage.hidden ? (
                  <ShowMoreButton
                    label={t('common.showMore', {
                      count: formatNumber(upcomingPage.hidden, locale, 0),
                    })}
                    onPress={upcomingPage.showMore}
                  />
                ) : null}
              </>
            ) : (
              <CalmNote message={t('schedule.noUpcoming')} />
            )
          ) : (
            <AuthorityUnavailableCard state={upcomingState} subject={t('schedule.shiftsAuthority')} />
          )}
        </View>
      ) : null}

      {attendanceState !== 'disabled' ? (
        <View style={styles.section}>
          <SectionHeader title={t('schedule.recentRecord')} />
          {isModuleFactual(attendanceState) ? (
            <>
              <Text style={[styles.windowNote, align]}>
                {t('schedule.windowNote', { days: formatNumber(windowDays, locale, 0) })}
              </Text>
              {summary ? (
                <WindowSummaryLine
                  present={summary.present}
                  late={summary.late}
                  absent={summary.absent}
                />
              ) : null}
              {recent.length ? (
                <>
                  {recentPage.visible.map((record, index) => (
                    <RecordedRow
                      key={record.attendance_id || `${record.date}-${index}`}
                      record={record}
                    />
                  ))}
                  {recentPage.hidden ? (
                    <ShowMoreButton
                      label={t('common.showMore', {
                        count: formatNumber(recentPage.hidden, locale, 0),
                      })}
                      onPress={recentPage.showMore}
                    />
                  ) : null}
                </>
              ) : (
                <CalmNote message={t('schedule.noRecentRecords')} />
              )}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t('schedule.history.view')}
                accessibilityHint={t('schedule.history.viewHint')}
                onPress={() => router.push('/schedule/history')}
                style={({ pressed }) => [styles.historyLink, pressed && styles.historyLinkPressed]}
              >
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.historyLinkText, align]}>
                  {t('schedule.history.view')}
                </Text>
                <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={16} color={colors.accent} />
              </Pressable>
            </>
          ) : (
            <AuthorityUnavailableCard
              state={attendanceState}
              subject={t('schedule.attendanceAuthority')}
            />
          )}
        </View>
      ) : null}

      <Text style={[styles.authorityFootnote, align]}>{t('schedule.hrAuthority')}</Text>
    </>
  )
})

/** Selected-day panel — only facts the current `/app/workday` payload can support. */
function SelectedDayPanel({
  selected,
  shiftsState,
  attendanceState,
}: {
  selected: ReturnType<typeof resolveSelectedDay>
  shiftsState: ModuleDataState
  attendanceState: ModuleDataState
}) {
  const { t } = useI18n()

  if (!selected.inWindow) {
    return <CalmNote message={t('schedule.dayOutsideWindow')} />
  }

  if (selected.isToday) {
    if (selected.entries.length) {
      return (
        <>
          {selected.entries.map((entry, index) => (
            <WorkdayEntryCard
              key={entry.scheduled?.shift_id || entry.recorded?.attendance_id || `today-${index}`}
              entry={entry}
              attendanceState={attendanceState}
              mode="today"
            />
          ))}
        </>
      )
    }
    return <TodayEmptyCard shiftsState={shiftsState} attendanceState={attendanceState} />
  }

  if (selected.relation === 'future') {
    if (shiftsState === 'error') {
      return <StatusNotice message={t('home.dataUnavailable')} danger />
    }
    if (shiftsState === 'loading') {
      return <CalmNote message={t('home.dataLoading')} />
    }
    if (shiftsState === 'disabled') {
      return <CalmNote message={t('schedule.shiftsNotAvailable')} />
    }
    if (!selected.entries.length) {
      return <CalmNote message={t('schedule.nothingOnDay')} />
    }
    return (
      <>
        {selected.entries.map((entry, index) => (
          <WorkdayEntryCard
            key={entry.scheduled?.shift_id || `future-${index}`}
            entry={entry}
            attendanceState={attendanceState}
            mode="future"
          />
        ))}
      </>
    )
  }

  // Past day: attendance rows only (shift roster for past days is not in this contract).
  if (attendanceState === 'error') {
    return <StatusNotice message={t('home.dataUnavailable')} danger />
  }
  if (attendanceState === 'loading') {
    return <CalmNote message={t('home.dataLoading')} />
  }
  if (attendanceState === 'disabled') {
    return <CalmNote message={t('schedule.attendanceNotAvailable')} />
  }
  if (!selected.entries.length) {
    return <CalmNote message={t('schedule.noRecordOnDay')} />
  }
  return (
    <>
      {selected.entries.map((entry, index) => (
        <WorkdayEntryCard
          key={entry.recorded?.attendance_id || `past-${index}`}
          entry={entry}
          attendanceState={attendanceState}
          mode="past"
        />
      ))}
    </>
  )
}

/** One day row: expected and/or recorded, depending on what the contract supplies. */
function WorkdayEntryCard({
  entry,
  attendanceState,
  mode,
}: {
  entry: WorkdayEntry
  attendanceState: ModuleDataState
  mode: 'today' | 'past' | 'future'
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const { scheduled, recorded } = entry
  const showExpected = mode === 'today' || mode === 'future' || mode === 'past'
  const showRecorded = mode === 'today' || mode === 'past'

  return (
    <PastelCard tone="sky" style={[styles.entryCard, styles.plannedEntryCard]}>
      {showExpected ? (
        <View style={styles.entryBlock}>
          <Text style={[styles.blockLabel, align]}>{t('schedule.expected')}</Text>
          {scheduled ? (
            <>
              <View style={styles.cardHead}>
                <Text style={[styles.entryTime, align]}>
                  {formatTimeRange(scheduled.start_time, scheduled.end_time, locale)}
                </Text>
                {mode !== 'future' || scheduled.status ? (
                  <ScheduledStatusMark label={statusLabel(scheduled.status, t)} />
                ) : null}
              </View>
              {scheduled.location || scheduled.role ? (
                <View style={styles.metaRow}>
                  <Ionicons name="location-outline" size={16} color={colors.subtle} />
                  <Text style={[styles.supporting, align]}>{scheduled.location || scheduled.role}</Text>
                </View>
              ) : null}
              {scheduled.notes ? <Text style={[styles.supporting, align]}>{scheduled.notes}</Text> : null}
            </>
          ) : (
            <Text style={[styles.entryMuted, align]}>
              {mode === 'past' ? t('schedule.noScheduleForRecord') : t('schedule.nothingOnDay')}
            </Text>
          )}
        </View>
      ) : null}

      {showExpected && showRecorded ? <View style={styles.entryDivider} /> : null}

      {showRecorded ? (
        <View style={styles.entryBlock}>
          <Text style={[styles.blockLabel, align]}>{t('schedule.recorded')}</Text>
          {recorded ? (
            <RecordedDetail record={recorded} />
          ) : isModuleFactual(attendanceState) ? (
            <Text style={[styles.entryMuted, align]}>{t('schedule.noRecordYet')}</Text>
          ) : (
            <Text style={[styles.entryMuted, align]}>
              {attendanceState === 'disabled'
                ? t('schedule.attendanceNotAvailable')
                : attendanceState === 'error'
                  ? t('home.dataUnavailable')
                  : t('home.dataLoading')}
            </Text>
          )}
        </View>
      ) : null}
    </PastelCard>
  )
}

function RecordedDetail({ record }: { record: WorkdayRecorded }) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <>
      <View style={styles.cardHead}>
        <Text style={[styles.entryTime, align]}>
          {record.check_in_at || record.check_out_at
            ? `${formatClockTime(record.check_in_at, locale)} – ${formatClockTime(record.check_out_at, locale)}`
            : t('schedule.noTimesRecorded')}
        </Text>
        <AttendanceStatusMark status={record.status} label={statusLabel(record.status, t)} />
      </View>
      {record.late_minutes > 0 ? (
        <Text style={[styles.supporting, align]}>
          {t('schedule.lateBy', { minutes: formatNumber(record.late_minutes, locale, 0) })}
        </Text>
      ) : null}
      {record.early_leave_minutes > 0 ? (
        <Text style={[styles.supporting, align]}>
          {t('schedule.leftEarlyBy', { minutes: formatNumber(record.early_leave_minutes, locale, 0) })}
        </Text>
      ) : null}
      {record.notes ? <Text style={[styles.supporting, align]}>{record.notes}</Text> : null}
    </>
  )
}

function ScheduledCard({ shift }: { shift: WorkdayScheduled }) {
  const { t, locale } = useI18n()
  const location = shift.location || shift.role
  return (
    <ListRow
      title={formatDate(shift.date, locale)}
      subtitle={formatTimeRange(shift.start_time, shift.end_time, locale)}
      meta={location || null}
      trailing={<ScheduledStatusMark label={statusLabel(shift.status, t)} />}
      accessibilityLabel={`${formatDate(shift.date, locale)}. ${formatTimeRange(shift.start_time, shift.end_time, locale)}. ${statusLabel(shift.status, t)}`}
    />
  )
}

function RecordedRow({ record }: { record: WorkdayRecorded }) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const hasTimes = Boolean(record.check_in_at || record.check_out_at)
  return (
    <View style={styles.recordRow}>
      <View style={styles.flex}>
        <Text style={[styles.recordDate, align]}>{formatDate(record.date, locale)}</Text>
        {hasTimes ? (
          <Text style={[styles.supporting, align]}>
            {`${formatClockTime(record.check_in_at, locale)} – ${formatClockTime(record.check_out_at, locale)}`}
          </Text>
        ) : null}
        {record.late_minutes > 0 ? (
          <Text style={[styles.supporting, align]}>
            {t('schedule.lateBy', { minutes: formatNumber(record.late_minutes, locale, 0) })}
          </Text>
        ) : null}
      </View>
      <AttendanceStatusMark status={record.status} label={statusLabel(record.status, t)} />
    </View>
  )
}

/**
 * Today with no entries. The message depends on which authorities were actually read:
 * "no shift today" is a fact only when Shifts was read successfully.
 */
function TodayEmptyCard({
  shiftsState,
  attendanceState,
}: {
  shiftsState: ModuleDataState
  attendanceState: ModuleDataState
}) {
  const { t } = useI18n()
  if (shiftsState === 'error' || attendanceState === 'error') {
    return <StatusNotice message={t('schedule.todayUnavailable')} danger />
  }
  if (shiftsState === 'loading' || attendanceState === 'loading') {
    return <CalmNote message={t('home.dataLoading')} />
  }
  if (shiftsState === 'disabled') {
    return <CalmNote message={t('schedule.noRecordToday')} />
  }
  return <CalmNote message={t('schedule.nothingToday')} />
}

/** Cream-ground empty — no bordered white panel (QuietEmpty still paints a surface card). */
function CalmNote({ message }: { message: string }) {
  const { isRTL } = useI18n()
  return (
    <Text
      maxFontSizeMultiplier={typeScaling.body}
      style={[styles.calmNote, readingEdgeAlign(isRTL)]}
      accessibilityRole="summary"
    >
      {message}
    </Text>
  )
}

function AuthorityUnavailableCard({ state, subject }: { state: ModuleDataState; subject: string }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const danger = state === 'error'
  return (
    <View style={[styles.statusNotice, danger && styles.statusNoticeDanger]}>
      <Text style={[styles.statusNoticeTitle, align]}>
        {danger ? t('home.dataUnavailable') : t('home.dataLoading')}
      </Text>
      <Text style={[styles.supporting, align]}>
        {danger ? `${subject} · ${t('home.dataUnavailableHint')}` : subject}
      </Text>
    </View>
  )
}

/** Error / unavailable — neutral surface with a semantic edge, not an ambient card. */
function StatusNotice({ message, danger }: { message: string; danger?: boolean }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View style={[styles.statusNotice, danger && styles.statusNoticeDanger]}>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.statusNoticeTitle, align]}>
        {message}
      </Text>
    </View>
  )
}

/** Three brand count pills for the 30-day window — Home palette, Schedule job. */
function WindowSummaryLine({
  present,
  late,
  absent,
}: {
  present: number
  late: number
  absent: number
}) {
  const { t, locale, isRTL } = useI18n()
  const presentLabel = t('attendance.present')
  const lateLabel = t('attendance.late')
  const absentLabel = t('attendance.absent')
  const presentN = formatNumber(present, locale, 0)
  const lateN = formatNumber(late, locale, 0)
  const absentN = formatNumber(absent, locale, 0)

  return (
    <View
      style={[styles.summaryLine, isRTL && styles.summaryLineRtl]}
      accessibilityRole="summary"
      accessibilityLabel={`${presentN} ${presentLabel}. ${lateN} ${lateLabel}. ${absentN} ${absentLabel}`}
    >
      <AttendanceCountPill kind="present" value={presentN} label={presentLabel} />
      <AttendanceCountPill kind="late" value={lateN} label={lateLabel} />
      <AttendanceCountPill kind="absent" value={absentN} label={absentLabel} />
    </View>
  )
}

const styles = StyleSheet.create({
  nav: { flexDirection: 'row', alignItems: 'center' },
  hero: { gap: spacing.xs },
  eyebrow: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', letterSpacing: 0.4 },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  section: { gap: spacing.sm },
  dayHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  dayTitle: {
    flex: 1,
    color: colors.ink,
    fontSize: font.h3,
    fontWeight: '800',
    lineHeight: 24,
  },
  todayJump: {
    minHeight: layout.touchTarget,
    justifyContent: 'center',
    paddingHorizontal: spacing.xs,
  },
  todayJumpText: {
    color: colors.accent,
    fontSize: font.small,
    fontWeight: '700',
  },
  entryCard: { gap: spacing.md },
  plannedEntryCard: { backgroundColor: scheduleComposition.planned.fill },
  entryBlock: { gap: spacing.xs },
  entryDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  blockLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.4 },
  entryTime: { color: colors.ink, fontSize: font.h3, lineHeight: 26, fontWeight: '700' },
  entryMuted: { color: colors.subtle, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  supporting: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  windowNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
    paddingVertical: spacing.sm,
  },
  summaryLine: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'stretch',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  summaryLineRtl: { flexDirection: 'row-reverse' },
  historyLink: {
    minHeight: layout.touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  historyLinkPressed: { opacity: 0.7 },
  historyLinkText: { flex: 1, color: colors.accent, fontSize: font.small, fontWeight: '700' },
  recordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
  },
  recordDate: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  statusNotice: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  statusNoticeDanger: {
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: colors.danger,
  },
  statusNoticeTitle: { color: colors.ink, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  authorityFootnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  flex: { flex: 1 },
})
