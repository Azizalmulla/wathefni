import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
import {
  EditorialHeading,
  FadeIn,
  IconBadge,
  PastelCard,
  WathefniBloom,
  Wordmark,
  type PastelTone,
} from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { SectionTitle, StatusChip } from '@/components/ui'
import { formatClockTime, formatDate, formatNumber, formatTimeRange, statusLabel, statusTone } from '@/lib/format'
import { asModuleDataState, isModuleFactual, type ModuleDataState } from '@/lib/moduleState'
import { colors, font, radius, spacing, typeScaling } from '@/theme'
import type { WorkdayEntry, WorkdayRecorded, WorkdayResponse, WorkdayScheduled } from '@/api/types'

/**
 * One Schedule surface over the Shifts and Attendance authorities.
 *
 * The employee has a single workday, so today's expected schedule and today's recorded
 * attendance are shown together instead of split across two module screens. Every value
 * is the owning module's stored value; this surface adds no clocking, no correction and
 * no derived judgement. An authority that is off or unreadable says so rather than
 * rendering as "nothing scheduled".
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
  const shiftsState = asModuleDataState(data.authority.shifts)
  const attendanceState = asModuleDataState(data.authority.attendance)
  const upcomingState = asModuleDataState(data.authority.shifts_upcoming)
  const entries = data.today.entries
  const summary = data.window?.summary

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
          <WathefniBloom variant="ribbon" style={styles.heroBloom} />
        </FadeIn>

        <View style={styles.section}>
          <SectionTitle>{t('schedule.today')}</SectionTitle>
          {entries.length ? (
            entries.map((entry, index) => (
              <WorkdayEntryCard
                key={entry.scheduled?.shift_id || entry.recorded?.attendance_id || `entry-${index}`}
                entry={entry}
                attendanceState={attendanceState}
              />
            ))
          ) : (
            <TodayEmptyCard shiftsState={shiftsState} attendanceState={attendanceState} />
          )}
        </View>

        {attendanceState !== 'disabled' ? (
          <View style={styles.section}>
            <SectionTitle>{t('schedule.recentRecord')}</SectionTitle>
            {isModuleFactual(attendanceState) ? (
              <>
                {summary ? (
                  <View style={styles.summaryRow}>
                    <SummaryMetric status="success" label={t('attendance.present')} value={summary.present} />
                    <SummaryMetric status="warning" label={t('attendance.late')} value={summary.late} />
                    <SummaryMetric status="danger" label={t('attendance.absent')} value={summary.absent} />
                  </View>
                ) : null}
                <Text style={[styles.windowNote, align]}>
                  {t('schedule.windowNote', { days: formatNumber(data.window?.days ?? 30, locale, 0) })}
                </Text>
                {data.recent?.length ? (
                  data.recent.map((record, index) => (
                    <RecordedRow key={record.attendance_id || `${record.date}-${index}`} record={record} />
                  ))
                ) : (
                  <InfoCard icon="time-outline" tone="cream" message={t('schedule.noRecentRecords')} />
                )}
              </>
            ) : (
              <AuthorityUnavailableCard state={attendanceState} subject={t('schedule.attendanceAuthority')} />
            )}
          </View>
        ) : null}

        {shiftsState !== 'disabled' ? (
          <View style={styles.section}>
            <SectionTitle>{t('schedule.upcoming')}</SectionTitle>
            {isModuleFactual(upcomingState) ? (
              data.upcoming?.length ? (
                data.upcoming.map((shift, index) => (
                  <ScheduledCard key={shift.shift_id || `${shift.date}-${index}`} shift={shift} />
                ))
              ) : (
                <InfoCard icon="calendar-outline" tone="cream" message={t('schedule.noUpcoming')} />
              )
            ) : (
              <AuthorityUnavailableCard state={upcomingState} subject={t('schedule.shiftsAuthority')} />
            )}
          </View>
        ) : null}

        {/* The employee cannot clock in or correct a record here; say so once, plainly. */}
        <PastelCard tone="cream" style={styles.authorityCard}>
          <View style={styles.authorityRow}>
            <IconBadge name="shield-checkmark-outline" size={34} />
            <Text style={[styles.authorityText, styles.flex, align]}>{t('schedule.hrAuthority')}</Text>
          </View>
        </PastelCard>
      </PageScrollView>
    </PageScreen>
  )
}

/** Today's row: what was expected, and what was recorded against it. */
function WorkdayEntryCard({
  entry,
  attendanceState,
}: {
  entry: WorkdayEntry
  attendanceState: ModuleDataState
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const { scheduled, recorded } = entry

  return (
    <PastelCard tone="sky" style={styles.entryCard}>
      <View style={styles.entryBlock}>
        <Text style={[styles.blockLabel, align]}>{t('schedule.expected')}</Text>
        {scheduled ? (
          <>
            <View style={styles.cardHead}>
              <Text style={[styles.entryTime, align]}>
                {formatTimeRange(scheduled.start_time, scheduled.end_time, locale)}
              </Text>
              <StatusChip label={statusLabel(scheduled.status, t)} tone={statusTone(scheduled.status)} />
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
          <Text style={[styles.entryMuted, align]}>{t('schedule.noScheduleForRecord')}</Text>
        )}
      </View>

      <View style={styles.entryDivider} />

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
        <StatusChip label={statusLabel(record.status, t)} tone={statusTone(record.status)} />
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
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <PastelCard tone="sky" style={styles.shiftCard}>
      <View style={styles.cardHead}>
        <Text style={[styles.metaStrong, align]}>{formatDate(shift.date, locale)}</Text>
        <StatusChip label={statusLabel(shift.status, t)} tone={statusTone(shift.status)} />
      </View>
      <Text style={[styles.entryTime, align]}>{formatTimeRange(shift.start_time, shift.end_time, locale)}</Text>
      {shift.location || shift.role ? (
        <View style={styles.metaRow}>
          <Ionicons name="location-outline" size={16} color={colors.subtle} />
          <Text style={[styles.supporting, align]}>{shift.location || shift.role}</Text>
        </View>
      ) : null}
    </PastelCard>
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
      <StatusChip label={statusLabel(record.status, t)} tone={statusTone(record.status)} />
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
    return <InfoCard icon="cloud-offline-outline" tone="notice" message={t('schedule.todayUnavailable')} />
  }
  if (shiftsState === 'loading' || attendanceState === 'loading') {
    return <InfoCard icon="time-outline" tone="cream" message={t('home.dataLoading')} />
  }
  if (shiftsState === 'disabled') {
    // Attendance only: there is no schedule authority to be empty about.
    return <InfoCard icon="time-outline" tone="cream" message={t('schedule.noRecordToday')} />
  }
  return <InfoCard icon="calendar-clear-outline" tone="sky" message={t('schedule.nothingToday')} />
}

function AuthorityUnavailableCard({ state, subject }: { state: ModuleDataState; subject: string }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View style={[styles.infoCard, styles.noticeCard, state === 'error' && styles.noticeCardError]}>
      <View style={styles.authorityRow}>
        <IconBadge name={state === 'error' ? 'cloud-offline-outline' : 'time-outline'} size={32} />
        <View style={styles.flex}>
          <Text style={[styles.infoMessage, align]}>
            {state === 'error' ? t('home.dataUnavailable') : t('home.dataLoading')}
          </Text>
          <Text style={[styles.supporting, align]}>
            {state === 'error' ? `${subject} · ${t('home.dataUnavailableHint')}` : subject}
          </Text>
        </View>
      </View>
    </View>
  )
}

/**
 * `notice` renders on neutral surface with a semantic edge: an unreadable or
 * empty authority is a state, not an ambient brand moment.
 */
function InfoCard({
  icon,
  message,
  tone,
}: {
  icon: keyof typeof Ionicons.glyphMap
  message: string
  tone: PastelTone | 'notice'
}) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const body = (
    <View style={styles.authorityRow}>
      <IconBadge name={icon} size={32} />
      <Text
        maxFontSizeMultiplier={typeScaling.body}
        style={[styles.infoMessage, styles.flex, align]}
      >
        {message}
      </Text>
    </View>
  )
  if (tone === 'notice') {
    return <View style={[styles.infoCard, styles.noticeCard, styles.noticeCardError]}>{body}</View>
  }
  return (
    <PastelCard tone={tone} style={styles.infoCard}>
      {body}
    </PastelCard>
  )
}

/**
 * Present / Late / Absent are statuses, so they are neutral tiles with a semantic
 * figure rather than green / yellow / red fills that would collide with the
 * ambient palette used elsewhere on this screen.
 */
function SummaryMetric({
  status,
  label,
  value,
}: {
  status: 'success' | 'warning' | 'danger'
  label: string
  value: number
}) {
  const { locale } = useI18n()
  const fg = status === 'success' ? colors.success : status === 'warning' ? colors.warning : colors.danger
  return (
    <View style={styles.summaryMetric} accessibilityLabel={`${label}: ${formatNumber(value, locale, 0)}`}>
      <Text maxFontSizeMultiplier={typeScaling.heading} style={[styles.summaryValue, { color: fg }]}>
        {formatNumber(value, locale, 0)}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} numberOfLines={2} style={styles.summaryLabel}>
        {label}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  nav: { flexDirection: 'row', alignItems: 'center' },
  hero: { gap: spacing.xs },
  heroBloom: { marginTop: spacing.xs },
  eyebrow: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', letterSpacing: 0.4 },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  section: { gap: spacing.sm },
  entryCard: { gap: spacing.md },
  entryBlock: { gap: spacing.xs },
  entryDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  blockLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.4 },
  entryTime: { color: colors.ink, fontSize: font.h3, lineHeight: 26, fontWeight: '700' },
  entryMuted: { color: colors.subtle, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaStrong: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  supporting: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
  shiftCard: { gap: spacing.xs },
  summaryRow: { flexDirection: 'row', gap: spacing.sm },
  summaryMetric: {
    flex: 1,
    alignItems: 'center',
    gap: 2,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  summaryValue: { fontSize: font.h2, fontWeight: '800' },
  summaryLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', textAlign: 'center' },
  windowNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 17 },
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
  infoCard: { paddingVertical: spacing.md },
  noticeCard: {
    paddingHorizontal: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  noticeCardError: { borderWidth: StyleSheet.hairlineWidth * 2, borderColor: colors.danger },
  infoMessage: { color: colors.ink, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  authorityCard: { paddingVertical: spacing.md },
  authorityRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  authorityText: { color: colors.ink, fontSize: font.small, lineHeight: 19, fontWeight: '600' },
  flex: { flex: 1 },
})
