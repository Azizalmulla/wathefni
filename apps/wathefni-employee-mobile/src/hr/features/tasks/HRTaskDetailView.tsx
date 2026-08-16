import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { mobileApi } from '@hr/api/mobile'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import {
  buildTasksDemoQueue,
  taskPriorityLabelKey,
  taskPriorityTone,
  taskTypeLabelKey,
} from '@hr/features/tasks/tasksComposition'
import { isTasksDemoId, tasksDemoEnabled } from '@hr/features/tasks/tasksDemoGate'
import {
  ConfirmationSheet,
  type ConfirmationView,
} from '@hr/components/primitives'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDateTime } from '@/lib/format'
import { ambient, colors, font, radius, spacing, typeScaling } from '@/theme'

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

/**
 * HR task detail — Editorial Entity Detail (visual migration).
 * Contract unchanged: Mark done via resolve + expected_status; no dismiss/assign.
 */
export function HRTaskDetailView() {
  const { taskId = '' } = useLocalSearchParams<{ taskId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = hasCapability(me, 'hr', 'hr_tasks')
  const demo = tasksDemoEnabled() || isTasksDemoId(taskId)
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)

  const live = useQuery({
    queryKey: ['hr-task', taskId],
    queryFn: ({ signal }) => mobileApi.taskDetail(request, taskId, signal),
    enabled: permitted && Boolean(taskId) && !demo,
  })

  const demoItem = demo
    ? buildTasksDemoQueue().open.find((row) => row.task_id === taskId)
    : null

  const item = demoItem || live.data?.item
  const resolve = useMutation({
    mutationFn: () =>
      mobileApi.taskResolve(request, taskId, {
        status: 'done',
        expected_status: item?.status || 'open',
      }),
    onSuccess: async () => {
      setConfirmation(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['hr-task', taskId] }),
        client.invalidateQueries({ queryKey: ['hr-tasks'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
      ])
    },
  })

  const canResolve =
    !demo && item?.allowed_actions.includes('resolve') === true && item.status === 'open'

  const typeLabel = item ? t(taskTypeLabelKey(item.task_type)) : null
  const employeeLead = item
    ? item.employee?.name
      ? [item.employee.name, item.employee.position_title, item.employee.department]
          .filter(Boolean)
          .join(' · ')
      : t('hrTasks.companyWide')
    : null
  const lead = [employeeLead, typeLabel].filter(Boolean).join(' · ') || null
  const priority = (item?.priority || '').trim().toLowerCase()
  const highPriority = priority === 'high' || priority === 'urgent'

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: ambient.payslips.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrTasks.detailEyebrow')}
            </Text>
          </View>
          <EditorialHeading>{item?.title || t('hrTasks.detailTitle')}</EditorialHeading>
          {item?.priority ? (
            <StatusChip
              label={t(taskPriorityLabelKey(item.priority))}
              tone={taskPriorityTone(item.priority)}
            />
          ) : null}
          {lead ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lead, align]}>
              {lead}
            </Text>
          ) : null}
          {demo ? (
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.demoNote, align]}>
              {t('hrTasks.demoDetailNote')}
            </Text>
          ) : null}
        </FadeIn>

        {!permitted && !demo ? (
          <ListRow title={t('hrTasks.permissionTitle')} subtitle={t('hrTasks.permissionBody')} />
        ) : null}

        {permitted && !demo && live.isLoading && !item ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {permitted && !demo && (live.error || resolve.error) && !item ? (
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
            {highPriority ? (
              <View style={styles.attention}>
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.attentionLabel, align]}>
                  {t('hrTasks.attentionTitle')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.attentionBody, align]}>
                  {t('hrTasks.attentionHigh')}
                </Text>
              </View>
            ) : null}

            {item.detail ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrTasks.sectionContext')} />
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.detail, align]}>
                  {item.detail}
                </Text>
              </View>
            ) : null}

            <View style={styles.group}>
              <SectionHeader title={t('hrTasks.sectionAbout')} />
              <Fact label={t('hrTasks.type')} value={typeLabel} />
              <Fact label={t('hrTasks.source')} value={item.source || null} />
              <Fact
                label={t('hrTasks.created')}
                value={item.created_at ? formatDateTime(item.created_at, locale) : null}
              />
              <Fact
                label={t('hrTasks.updated')}
                value={item.updated_at ? formatDateTime(item.updated_at, locale) : null}
              />
            </View>

            {canResolve ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrTasks.sectionDecide')} />
                <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
                  {t('hrTasks.decideHint')}
                </Text>
                <Pressable
                  onPress={() =>
                    setConfirmation({
                      target: item.title,
                      action: t('hrTasks.markDone'),
                      consequence: t('hrTasks.resolveConsequence'),
                      currentState: item.status || 'open',
                    })
                  }
                  style={styles.btnPrimary}
                  accessibilityRole="button"
                  accessibilityLabel={t('hrTasks.markDone')}
                >
                  <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnPrimaryText}>
                    {t('hrTasks.markDone')}
                  </Text>
                </Pressable>
              </View>
            ) : null}

            {resolve.isSuccess ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.success, align]}>
                {t('hrTasks.resolveSubmitted')}
              </Text>
            ) : null}

            {resolve.error ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.error, align]}>
                {t('hrTasks.resolveFailed')}
              </Text>
            ) : null}
          </>
        ) : null}
      </PageScrollView>

      {/* Modal outside ScrollView so Confirm presses are not swallowed on iOS. */}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        loading={resolve.isPending}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => resolve.mutate()}
      />
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
  },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  lead: {
    color: colors.ink,
    fontSize: font.h3,
    fontWeight: '600',
    lineHeight: 26,
    marginTop: spacing.xs,
    maxWidth: 360,
  },
  demoNote: { color: colors.subtle, fontSize: font.tiny },
  group: { gap: spacing.md },
  detail: { color: colors.ink, fontSize: font.body, lineHeight: 24, fontWeight: '500' },
  fact: { gap: 2 },
  factLabel: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  factValue: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  attention: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: ambient.schedule.fill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 6,
  },
  attentionLabel: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  attentionBody: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  btnPrimary: {
    minHeight: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.ink,
  },
  btnPrimaryText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
  success: { color: colors.ink, fontSize: font.small, fontWeight: '600' },
  error: { color: colors.danger, fontSize: font.small },
})
