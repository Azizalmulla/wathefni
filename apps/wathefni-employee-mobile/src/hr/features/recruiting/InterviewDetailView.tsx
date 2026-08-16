import { useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@hr/api/client'
import { mobileApi } from '@hr/api/mobile'
import { resourceState } from '@hr/api/state'
import type { InterviewSummary } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  facetStatusLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@hr/features/recruiting/lifecycle'
import { formatDateTime } from '@hr/i18n/date'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

function isNotesStale(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === 'stale_interview_notes' ||
      error.code === 'missing_expected_version' ||
      error.code === 'stale_decision')
  )
}

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

export function InterviewDetailView() {
  const { interviewId = '' } = useLocalSearchParams<{ interviewId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const client = useQueryClient()
  const permitted = routeAvailable(me, 'interviews')
  const [notesDraft, setNotesDraft] = useState('')
  const [notesError, setNotesError] = useState<'stale' | 'error' | null>(null)

  const query = useQuery({
    queryKey: ['interview', interviewId],
    queryFn: ({ signal }) => mobileApi.interviewDetail(request, interviewId, signal),
    enabled: permitted && Boolean(interviewId),
  })

  const item = query.data?.item

  useEffect(() => {
    if (item) setNotesDraft(item.notes || '')
  }, [item?.interview_id, item?.updated_at, item?.notes_version, item?.notes])

  const notes = useMutation({
    mutationFn: (value: string) =>
      mobileApi.interviewNotes(request, interviewId, {
        notes: value,
        expected_updated_at: item?.updated_at || null,
        expected_version: item?.notes_version ?? null,
      }),
    onSuccess: async () => {
      setNotesError(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['interview', interviewId] }),
        client.invalidateQueries({ queryKey: ['interviews'] }),
        client.invalidateQueries({ queryKey: ['hr-hiring-interviews'] }),
        client.invalidateQueries({ queryKey: ['mobile-priorities'] }),
        client.invalidateQueries({ queryKey: ['candidates'] }),
        client.invalidateQueries({ queryKey: ['hr-hiring-candidates'] }),
      ])
    },
    onError: (error) => {
      setNotesError(isNotesStale(error) ? 'stale' : 'error')
      if (isNotesStale(error)) void query.refetch()
    },
  })

  const canWriteNotes =
    item?.allowed_actions.includes('write_notes') || item?.allowed_actions.includes('write')
  const analysis = String(item?.ai_summary?.overall_summary || item?.ai_summary?.summary || '')

  const state = !permitted
    ? 'permission'
    : resourceState({
        loading: query.isLoading,
        error: query.error,
        stale: query.data?.stale,
      })

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} keyboardInsets>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
            {t('hrInterviews.detailEyebrow')}
          </Text>
          <EditorialHeading>
            {item?.candidate.name || t('hrInterviews.detailTitle')}
          </EditorialHeading>
          {item?.application_stage || item?.status ? (
            <StatusChip
              label={lifecycleStageLabel(item.application_stage || item.status, appLocale)}
              tone="neutral"
            />
          ) : null}
        </FadeIn>

        {state === 'loading' ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}

        {state === 'permission' ? (
          <ListRow title={t('hrInterviews.permissionTitle')} subtitle={t('hrInterviews.permissionBody')} />
        ) : null}

        {state === 'error' || state === 'offline' ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            emphasis="warning"
            showChevron
            onPress={() => void query.refetch()}
          />
        ) : null}

        {state === 'ready' && item ? (
          <>
            <View style={styles.section}>
              <SectionHeader title={t('hrInterviews.sectionOverview')} />
              <Fact label={t('common.position')} value={item.position?.title || item.position?.code} />
              <Fact
                label={t('hrInterviews.applicationStage')}
                value={lifecycleStageLabel(item.application_stage, appLocale)}
              />
              <Fact label={t('hrInterviews.status')} value={facetStatusLabel(item.status, appLocale)} />
              <Fact
                label={t('hrInterviews.scheduled')}
                value={item.scheduled_at ? formatDateTime(item.scheduled_at, appLocale) : null}
              />
              <Fact
                label={t('hrInterviews.channelLocation')}
                value={item.meeting?.join_url || item.meeting?.type}
              />
              <Fact
                label={t('hrInterviews.invitationStatus')}
                value={lifecycleCommunicationLabel(
                  item.invitation_status || item.communication_status,
                  appLocale,
                )}
              />
              <Fact
                label={t('hrInterviews.candidateConfirmation')}
                value={facetStatusLabel(item.candidate_confirmation, appLocale)}
              />
              <Fact
                label={t('hrInterviews.notesStatus')}
                value={facetStatusLabel(item.notes_status, appLocale)}
              />
              <Fact
                label={t('hrInterviews.nextHumanAction')}
                value={workflowLabel(item.next_human_action, appLocale)}
              />
              <Fact label={t('hrInterviews.advisorySummary')} value={analysis || null} />
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrInterviews.notes')} />
              {notesError === 'stale' ? (
                <ListRow
                  title={t('hrInterviews.staleTitle')}
                  subtitle={t('hrInterviews.staleBody')}
                  emphasis="warning"
                  showChevron
                  onPress={() => {
                    setNotesError(null)
                    void query.refetch()
                  }}
                />
              ) : null}
              {notesError === 'error' ? (
                <ListRow
                  title={t('hrInterviews.notesSaveFailed')}
                  subtitle={t('home.dataUnavailableHint')}
                  emphasis="warning"
                />
              ) : null}
              {canWriteNotes ? (
                <View style={styles.notesBlock}>
                  <TextInput
                    value={notesDraft}
                    onChangeText={(value) => {
                      setNotesDraft(value)
                      if (notesError) setNotesError(null)
                    }}
                    multiline
                    maxLength={2000}
                    placeholder={t('hrInterviews.notesPlaceholder')}
                    placeholderTextColor={colors.subtle}
                    accessibilityLabel={t('hrInterviews.notes')}
                    style={[
                      styles.notes,
                      {
                        textAlign: isRTL ? 'right' : 'left',
                        writingDirection: isRTL ? 'rtl' : 'ltr',
                      },
                    ]}
                  />
                  <Pressable
                    onPress={() => notes.mutate(notesDraft.trim())}
                    disabled={!notesDraft.trim() || notes.isPending}
                    style={[styles.saveBtn, (!notesDraft.trim() || notes.isPending) && styles.saveDisabled]}
                    accessibilityRole="button"
                    accessibilityLabel={t('common.save')}
                  >
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.saveText}>
                      {notes.isPending ? t('common.loading') : t('common.save')}
                    </Text>
                  </Pressable>
                </View>
              ) : (
                <Fact label={t('hrInterviews.notes')} value={item.notes || t('common.none')} />
              )}
            </View>
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

export type { InterviewSummary }

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  section: { gap: spacing.sm },
  fact: { gap: spacing.xs, paddingVertical: spacing.sm },
  factLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  factValue: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  notesBlock: { gap: spacing.md },
  notes: {
    minHeight: 112,
    color: colors.ink,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    fontSize: font.body,
    textAlignVertical: 'top',
  },
  saveBtn: {
    alignSelf: 'flex-start',
    backgroundColor: colors.ink,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
  },
  saveDisabled: { opacity: 0.4 },
  saveText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
})

