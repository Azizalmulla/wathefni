import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import { useServerConfirmation } from '@hr/api/useServerConfirmation'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import {
  CORRECTION_STATUSES,
  correctionActionLabelKey,
  exceptionChipTone,
  exceptionKindLabelKey,
  type CorrectionStatus,
} from '@hr/features/attendance/attendanceComposition'
import { buildAttendanceDemoQueue } from '@hr/features/attendance/attendanceDemoData'
import {
  attendanceDemoEnabled,
  isAttendanceDemoId,
} from '@hr/features/attendance/attendanceDemoGate'
import { ConfirmationSheet } from '@hr/components/primitives'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDate, formatDateTime, kuwaitToday } from '@/lib/format'
import { colors, font, radius, scheduleComposition, spacing, typeScaling } from '@/theme'

/** Unboxed fact — typography only (static metadata, not action rows). */
function Fact({ label, value }: { label: string; value?: string | null }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  if (!value) return null
  return (
    <View style={styles.fact}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.factLabel, align]}>
        {label}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.factValue, align]}>
        {value}
      </Text>
    </View>
  )
}

function formatWindow(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: string,
): string | null {
  if (!start && !end) return null
  const a = start ? formatDateTime(start, locale) : '—'
  const b = end ? formatDateTime(end, locale) : '—'
  return `${a} → ${b}`
}

/**
 * Attendance exception detail — Editorial Entity Detail (visual migration).
 * Contract unchanged: prepare→confirm corrections, request_correction only, no instant resolve.
 */
export function HRAttendanceDetailView() {
  const { attendanceId = '' } = useLocalSearchParams<{ attendanceId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = hasCapability(me, 'hr', 'attendance_exceptions')
  const demo = attendanceDemoEnabled() || isAttendanceDemoId(attendanceId)

  const live = useQuery({
    queryKey: ['attendance', attendanceId],
    queryFn: ({ signal }) => mobileApi.attendanceDetail(request, attendanceId, signal),
    enabled: permitted && Boolean(attendanceId) && !demo,
  })

  const demoItem = demo
    ? [
        ...buildAttendanceDemoQueue(kuwaitToday()).today,
        ...buildAttendanceDemoQueue(kuwaitToday()).unresolved,
      ].find((row) => row.attendance_id === attendanceId)
    : null

  const item = demoItem || live.data?.item
  const confirmation = useServerConfirmation<{ status: CorrectionStatus }>({
    keyPrefix: 'attendance-resolve',
    execute: (input, fields) =>
      mobileApi.resolveAttendance(request, attendanceId, {
        status: input.status,
        ...fields,
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['attendance', attendanceId] }),
        client.invalidateQueries({ queryKey: ['attendance-exceptions'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
      ])
    },
  })

  const canRequest =
    !demo && item?.action_mode === 'request_correction' && item.allowed_actions.includes('resolve')

  const identity = item
    ? [item.employee.position_title, item.employee.department].filter(Boolean).join(' · ') || null
    : null
  const workDate = item?.attendance_date ? formatDate(item.attendance_date, locale) : null
  const scheduled = item ? formatWindow(item.scheduled_start, item.scheduled_end, locale) : null
  const lead = [workDate, scheduled].filter(Boolean).join(' · ') || null
  const showAbsenceAttention = item?.exception_kind === 'absence'

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: scheduleComposition.planned.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrAttendance.detailEyebrow')}
            </Text>
          </View>
          <EditorialHeading>{item?.employee.name || t('hrAttendance.detailTitle')}</EditorialHeading>
          {item?.exception_kind ? (
            <StatusChip
              label={t(exceptionKindLabelKey(item.exception_kind))}
              tone={exceptionChipTone(item.exception_kind)}
            />
          ) : null}
          {identity ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.identity, align]}>
              {identity}
            </Text>
          ) : null}
          {lead ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lead, align]}>
              {lead}
            </Text>
          ) : null}
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrAttendance.demoDetailNote')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted && !demo ? (
          <ListRow
            title={t('hrAttendance.permissionTitle')}
            subtitle={t('hrAttendance.permissionBody')}
          />
        ) : null}

        {permitted && !demo && live.isLoading && !item ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {permitted && !demo && live.error && !item ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            emphasis="warning"
            showChevron
            onPress={() => void live.refetch()}
          />
        ) : null}

        {(permitted || demo) && item ? (
          <>
            {showAbsenceAttention ? (
              <View style={styles.attention}>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.attentionLabel, align]}>
                  {t('hrAttendance.attentionTitle')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.attentionBody, align]}>
                  {t('hrAttendance.attentionAbsence')}
                </Text>
              </View>
            ) : null}

            <View style={styles.group}>
              <SectionHeader title={t('hrAttendance.sectionRecord')} />
              <Fact label={t('hrAttendance.workDate')} value={workDate} />
              <Fact label={t('hrAttendance.scheduled')} value={scheduled} />
              <Fact
                label={t('hrAttendance.checkIn')}
                value={item.check_in_at ? formatDateTime(item.check_in_at, locale) : t('hrAttendance.missing')}
              />
              <Fact
                label={t('hrAttendance.checkOut')}
                value={
                  item.check_out_at ? formatDateTime(item.check_out_at, locale) : t('hrAttendance.missing')
                }
              />
              {item.late_minutes > 0 ? (
                <Fact label={t('hrAttendance.lateMinutes')} value={String(item.late_minutes)} />
              ) : null}
              {item.early_leave_minutes > 0 ? (
                <Fact label={t('hrAttendance.earlyMinutes')} value={String(item.early_leave_minutes)} />
              ) : null}
              <Fact label={t('hrAttendance.reason')} value={item.note} />
              <Fact
                label={t('hrAttendance.updated')}
                value={item.updated_at ? formatDateTime(item.updated_at, locale) : null}
              />
            </View>

            {canRequest ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrAttendance.actionsTitle')} />
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.actionHint, align]}>
                  {t('hrAttendance.actionsHint')}
                </Text>
                {CORRECTION_STATUSES.map((status) => (
                  <Pressable
                    key={status}
                    onPress={() => void confirmation.prepare({ status }).catch(() => undefined)}
                    style={styles.actionBtn}
                    accessibilityRole="button"
                    accessibilityLabel={t(correctionActionLabelKey(status))}
                  >
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.actionBtnText}>
                      {t(correctionActionLabelKey(status))}
                    </Text>
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.actionBtnSub}>
                      {t('hrAttendance.requestCorrectionSub')}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}

            {confirmation.succeeded ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.success, align]}>
                {t('hrAttendance.correctionSubmitted')}
              </Text>
            ) : null}
          </>
        ) : null}

        <ConfirmationSheet
          visible={confirmation.visible}
          value={confirmation.view}
          loading={confirmation.loading}
          error={
            confirmation.error instanceof Error
              ? confirmation.error.message
              : confirmation.error
                ? t('confirm.errorGeneric')
                : null
          }
          onCancel={confirmation.cancel}
          onConfirm={() => void confirmation.confirm().catch(() => undefined)}
        />
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: { width: 8, height: 8, borderRadius: radius.pill },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  identity: { color: colors.subtle, fontSize: font.small },
  lead: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '600',
    marginTop: spacing.xs,
    maxWidth: 360,
  },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  attention: {
    gap: spacing.xs,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  attentionLabel: {
    color: colors.danger,
    fontSize: font.tiny,
    fontWeight: '800',
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },
  attentionBody: { color: colors.ink, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  group: { gap: spacing.md },
  fact: { gap: 2 },
  factLabel: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  factValue: { color: colors.ink, fontSize: font.body, fontWeight: '600', lineHeight: 22 },
  actionHint: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  actionBtn: {
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    gap: 2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  actionBtnText: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  actionBtnSub: { color: colors.subtle, fontSize: font.tiny, fontWeight: '600' },
  success: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
})
