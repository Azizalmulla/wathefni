import {
  ChevronDown,
  ExternalLink,
  Loader2,
  Pencil,
  SlidersHorizontal,
} from 'lucide-react'
import { memo, useEffect, useState } from 'react'

import {
  interviewAssignInterviewer,
  interviewReschedule,
  interviewSendVideoInvitation,
  updateInterviewStatus,
} from '@/lib/api'
import {
  actionLabel as recruitingActionLabel,
  canonicalStageLabel,
  communicationLabel,
  facetStatusLabel,
  recruitingCopy,
  workflowItemLabel,
  type RecruitingLocale,
} from '@/lib/recruitingLifecycle'
import { cn, formatDateTime, statusTone } from '@/lib/utils'
import { PeoplePicker } from '@/components/PeoplePicker'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Textarea } from '@/components/ui/field'
import { resolveAllowedActions } from '@/lib/allowedActions'
import { EmptyState } from '@/pages/shared/primitives'
import { ResourceState } from '@/pages/shared/dataState'
import {
  asyncVideoDisplayStatus,
  calendarEventLabel,
  friendlyDashboardError,
  interviewFeedbackCount,
  interviewStatusCount,
  inviteTruthLabel,
  normalizeEvidenceConfidence,
  normalizeOverallImpression,
  notesStateLabel,
  notificationChannelLabel,
  stageLabel,
  summaryValue,
  transcriptStatusLabel,
  videoInterviewProcessingLine,
} from '@/pages/shared/format'
import type { CandidateInterview, DashboardAccess } from '@/types'

function QuietInfo({ label, value, locale }: { label: string; value?: string | null; locale: RecruitingLocale }) {
  return (
    <div className="rounded-2xl border border-[#e8dfd0] bg-[#fffaf0]/70 p-3.5">
      <div
        className={cn(
          'font-semibold text-subtle',
          locale === 'ar' ? 'text-[12px]' : 'text-[11px] uppercase tracking-[0.12em]',
        )}
      >
        {label}
      </div>
      <div className="mt-1.5 break-words text-sm font-medium text-text">{value || '—'}</div>
    </div>
  )
}

function interviewSummaryLine(interview: CandidateInterview, locale: RecruitingLocale): string {
  const presentation = interview.presentation
  const isVideo = presentation?.display?.is_async ?? interview.interview_type === 'async_video'
  const mainStatus = presentation?.progress_label || presentation?.display?.status_label || facetStatusLabel(interview.status, locale)
  const feedback = interview.feedback
  if (isVideo) {
    const progress = presentation?.progress_state || ''
    if (progress === 'ready_for_review') return recruitingCopy(locale, 'interviewReadyReview')
    if (progress === 'reviewed') return recruitingCopy(locale, 'interviewReviewed')
    if (['opened', 'consented', 'link_sent'].includes(progress)) return recruitingCopy(locale, 'interviewWaitingVideo')
    if (progress === 'expired') return mainStatus
    if (presentation?.invitation_state === 'delivery_failed') return recruitingCopy(locale, 'interviewFailedInvite')
    return presentation?.progress_label || recruitingCopy(locale, 'interviewRecordedDefault')
  }
  if (presentation?.progress_state === 'completed') {
    return feedback?.complete
      ? recruitingCopy(locale, 'interviewCompletedFeedbackDone')
      : recruitingCopy(locale, 'interviewCompletedFeedbackPending')
  }
  if (presentation?.schedule_state === 'date_missing') return recruitingCopy(locale, 'interviewSetDatetime')
  if (presentation?.invitation_state === 'delivery_failed') return recruitingCopy(locale, 'interviewFailedInvite')
  return presentation?.progress_label || mainStatus
}

export function InterviewsPage({
  access,
  busy,
  canManageInterviews,
  feedbackCounts,
  filters,
  interviews,
  limit,
  listError = false,
  listLoading = false,
  locale,
  notesDrafts,
  offset,
  onOpenCandidate,
  onLocale,
  onPreviewVideoAnswer,
  onRetryVideoTranscripts,
  onSaveNotes,
  onRefresh,
  onRetryList,
  onSetNotes,
  onSetOffset,
  onStatusChange,
  onUpdateFilters,
  statusCounts,
  total,
  videoCount,
  videoInterviewsEnabled = true,
}: {
  access: DashboardAccess
  busy: boolean
  canManageInterviews: boolean
  feedbackCounts: Array<{ feedback_status: string; count: number }>
  filters: { tab: string; q: string; role: string; date: string; interviewer: string }
  interviews: CandidateInterview[]
  limit: number
  listError?: boolean
  listLoading?: boolean
  locale: RecruitingLocale
  notesDrafts: Record<string, string>
  offset: number
  onOpenCandidate: (appKey?: string) => void
  onLocale: () => void
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
  onSaveNotes: (interview: CandidateInterview) => void
  onRefresh: () => void
  onRetryList?: () => void
  onSetNotes: (interviewId: string, value: string) => void
  onSetOffset: (offset: number) => void
  onStatusChange: (interview: CandidateInterview, status: string) => void
  onUpdateFilters: (filters: Partial<{ tab: string; q: string; role: string; date: string; interviewer: string }>) => void
  statusCounts: Array<{ status: string; count: number }>
  total: number
  videoCount: number
  videoInterviewsEnabled?: boolean
}) {
  const [selectedInterviewId, setSelectedInterviewId] = useState<string | null>(null)
  const [selectedSnapshot, setSelectedSnapshot] = useState<CandidateInterview | null>(null)

  useEffect(() => {
    // Only correct after authority is known (false), not while undefined/loading.
    if (videoInterviewsEnabled === false && filters.tab === 'video_interviews') {
      onUpdateFilters({ tab: 'upcoming' })
    }
  }, [videoInterviewsEnabled, filters.tab, onUpdateFilters])
  const selectedFromList = selectedInterviewId
    ? interviews.find((item) => item.interview_id === selectedInterviewId) || null
    : null
  const selectedInterview =
    selectedFromList ||
    (busy && selectedSnapshot && selectedSnapshot.interview_id === selectedInterviewId ? selectedSnapshot : null)

  useEffect(() => {
    if (selectedFromList) setSelectedSnapshot(selectedFromList)
  }, [selectedFromList])

  useEffect(() => {
    if (!selectedInterviewId) {
      setSelectedSnapshot(null)
      return
    }
    // While refreshing, keep the drawer open even if the id briefly drops out of
    // the filtered list (filter key change / invalidate). Clear only when settled.
    if (busy) return
    if (!interviews.some((item) => item.interview_id === selectedInterviewId)) {
      setSelectedInterviewId(null)
      setSelectedSnapshot(null)
    }
  }, [interviews, selectedInterviewId, busy])

  const scheduled = interviewStatusCount(statusCounts, 'scheduled') + interviewStatusCount(statusCounts, 'rescheduled')
  const completed = interviewStatusCount(statusCounts, 'completed')
  const noShows = interviewStatusCount(statusCounts, 'no_show')
  const cancelled = interviewStatusCount(statusCounts, 'cancelled')
  const notesPending = interviewFeedbackCount(feedbackCounts, 'notes_pending')
  const allCount = statusCounts.reduce((sum, item) => sum + Number(item.count || 0), 0)

  const primaryTabs = [
    { id: 'upcoming', label: recruitingCopy(locale, 'interviewTabUpcoming'), count: scheduled },
    { id: 'needs_feedback', label: recruitingCopy(locale, 'interviewTabNeedsFeedback'), count: notesPending },
    ...(videoInterviewsEnabled
      ? [{ id: 'video_interviews', label: recruitingCopy(locale, 'interviewTabVideo'), count: videoCount }]
      : []),
    { id: 'completed', label: recruitingCopy(locale, 'interviewTabCompleted'), count: completed },
    { id: 'all', label: recruitingCopy(locale, 'interviewTabAll'), count: allCount },
  ]
  const secondaryTabs = [
    { id: 'no_show', label: recruitingCopy(locale, 'interviewTabNoShow'), count: noShows },
    { id: 'cancelled', label: recruitingCopy(locale, 'interviewTabCancelled'), count: cancelled },
  ]
  const selectedSecondary = secondaryTabs.find((tab) => tab.id === filters.tab) || null
  const filtersActive = Boolean(filters.role || filters.date || filters.interviewer)
  const canGoBack = offset > 0
  const canGoNext = offset + limit < total
  const headerLabelClass =
    locale === 'ar'
      ? 'text-[12px] font-semibold text-[#6f675c]'
      : 'text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6f675c]'

  function selectTab(tabId: string) {
    onUpdateFilters({ tab: tabId })
    onSetOffset(0)
  }

  return (
    <div className="space-y-5" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <Card className="shadow-[0_12px_36px_rgba(35,33,29,0.06)]" tone="board">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="font-sans text-wf-ink">{recruitingCopy(locale, 'interviewQueue')}</CardTitle>
              <CardDescription className="mt-1 text-wf-ink-muted">{recruitingCopy(locale, 'interviewQueueDescription')}</CardDescription>
            </div>
            <Button onClick={onLocale} size="sm" type="button" variant="secondary">
              {recruitingCopy(locale, 'language')}
            </Button>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-3" data-testid="interview-status-tiles">
            <button
              type="button"
              className="rounded-[1.2rem] bg-wf-accent-follow px-3.5 py-3 text-start text-wf-accent-follow-ink transition hover:brightness-[0.98]"
              onClick={() => selectTab('upcoming')}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">
                {recruitingCopy(locale, 'interviewTabUpcoming')}
              </div>
              <div className="mt-1 text-xl font-semibold tracking-tight">{scheduled}</div>
            </button>
            <button
              type="button"
              className="rounded-[1.2rem] bg-wf-accent-review px-3.5 py-3 text-start text-wf-accent-review-ink transition hover:brightness-[0.98]"
              onClick={() => selectTab('needs_feedback')}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">
                {recruitingCopy(locale, 'interviewTabNeedsFeedback')}
              </div>
              <div className="mt-1 text-xl font-semibold tracking-tight">{notesPending}</div>
            </button>
            <button
              type="button"
              className="rounded-[1.2rem] bg-wf-accent-priority px-3.5 py-3 text-start text-wf-accent-priority-ink transition hover:brightness-[0.98]"
              onClick={() => selectTab('completed')}
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-75">
                {recruitingCopy(locale, 'interviewTabCompleted')}
              </div>
              <div className="mt-1 text-xl font-semibold tracking-tight">{completed}</div>
            </button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {primaryTabs.map((tab) => (
              <button
                className={cn(
                  'rounded-full px-3.5 py-1.5 text-sm transition',
                  filters.tab === tab.id
                    ? 'bg-[#23211d] font-semibold text-white'
                    : 'text-[#6f675c] hover:bg-white/70 hover:text-[#23211d]',
                )}
                key={tab.id}
                onClick={() => selectTab(tab.id)}
                type="button"
              >
                {tab.label} <span className="ms-1 opacity-70">{tab.count}</span>
              </button>
            ))}
            <details className="relative">
              <summary
                className={cn(
                  'flex cursor-pointer list-none items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm transition marker:content-none [&::-webkit-details-marker]:hidden',
                  selectedSecondary
                    ? 'bg-[#23211d] font-semibold text-white'
                    : 'border border-[#e8dfd0] bg-white/55 text-[#6f675c] hover:border-[#23211d]/25 hover:text-[#23211d]',
                )}
              >
                {selectedSecondary
                  ? `${selectedSecondary.label} ${selectedSecondary.count}`
                  : recruitingCopy(locale, 'interviewMore')}
                <ChevronDown size={14} />
              </summary>
              <div className="absolute z-20 mt-2 min-w-[11rem] rounded-2xl border border-[#e8dfd0] bg-[#fffaf0] p-1.5 shadow-[0_16px_40px_rgba(35,33,29,0.12)]">
                {secondaryTabs.map((tab) => (
                  <button
                    className={cn(
                      'flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition',
                      filters.tab === tab.id ? 'bg-[#23211d] text-white' : 'text-[#23211d] hover:bg-white/80',
                    )}
                    key={tab.id}
                    onClick={(event) => {
                      selectTab(tab.id)
                      const details = (event.currentTarget as HTMLElement).closest('details')
                      if (details) details.open = false
                    }}
                    type="button"
                  >
                    <span>{tab.label}</span>
                    <span className="opacity-70">{tab.count}</span>
                  </button>
                ))}
              </div>
            </details>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
            <Input
              aria-label={recruitingCopy(locale, 'interviewSearchPlaceholder')}
              className="flex-1"
              onChange={(event) => onUpdateFilters({ q: event.target.value })}
              placeholder={recruitingCopy(locale, 'interviewSearchPlaceholder')}
              value={filters.q}
            />
            <details className="relative shrink-0">
              <summary
                className={cn(
                  'flex cursor-pointer list-none items-center gap-2 rounded-full border px-3.5 py-2 text-sm marker:content-none [&::-webkit-details-marker]:hidden',
                  filtersActive
                    ? 'border-[#23211d] bg-[#23211d] font-semibold text-white'
                    : 'border-[#e8dfd0] bg-white/55 text-[#6f675c] hover:border-[#23211d]/25 hover:text-[#23211d]',
                )}
              >
                <SlidersHorizontal size={14} />
                {recruitingCopy(locale, 'interviewFilters')}
                {filtersActive ? <span className="opacity-80">·</span> : null}
              </summary>
              <div className="absolute end-0 z-20 mt-2 w-[min(100vw-2rem,20rem)] space-y-2 rounded-2xl border border-[#e8dfd0] bg-[#fffaf0] p-3 shadow-[0_16px_40px_rgba(35,33,29,0.12)]">
                <Input
                  onChange={(event) => onUpdateFilters({ role: event.target.value })}
                  placeholder={recruitingCopy(locale, 'interviewRolePlaceholder')}
                  value={filters.role}
                />
                <Input
                  aria-label={recruitingCopy(locale, 'interviewDateFilter')}
                  onChange={(event) => onUpdateFilters({ date: event.target.value })}
                  type="date"
                  value={filters.date}
                />
                <Input
                  onChange={(event) => onUpdateFilters({ interviewer: event.target.value })}
                  placeholder={recruitingCopy(locale, 'interviewInterviewerPlaceholder')}
                  value={filters.interviewer}
                />
                {filtersActive ? (
                  <Button
                    onClick={() => onUpdateFilters({ role: '', date: '', interviewer: '' })}
                    size="sm"
                    type="button"
                    variant="secondary"
                  >
                    {recruitingCopy(locale, 'interviewClearFilters')}
                  </Button>
                ) : null}
              </div>
            </details>
          </div>

          {listLoading ? (
            <ResourceState
              kind="loading"
              locale={locale}
              title={recruitingCopy(locale, 'interviewLoading')}
              testId="interviews-list-loading"
            />
          ) : listError ? (
            <ResourceState
              kind="error"
              locale={locale}
              title={recruitingCopy(locale, 'interviewLoadError')}
              detail={recruitingCopy(locale, 'interviewLoadErrorDetail')}
              onRetry={() => (onRetryList || onRefresh)()}
              retrying={busy}
              testId="interviews-list-error"
            />
          ) : interviews.length ? (
            <div className="overflow-x-auto rounded-[1.35rem] border border-[#e8dfd0] bg-[#f8f2e6]/65">
              <div className="min-w-[1160px]">
                <div
                  className={cn(
                    'grid grid-cols-[minmax(200px,1.4fr)_minmax(150px,1fr)_minmax(170px,1.1fr)_minmax(130px,0.9fr)_minmax(130px,0.9fr)_minmax(150px,1fr)] items-center gap-3 border-b border-[#e8dfd0] bg-[#f7f1e7]/90 px-4 py-2.5',
                    headerLabelClass,
                  )}
                >
                  <div>{recruitingCopy(locale, 'candidate')}</div>
                  <div>{recruitingCopy(locale, 'job')}</div>
                  <div>{locale === 'ar' ? 'المقابلة' : 'Interview'}</div>
                  <div>{recruitingCopy(locale, 'interviewInterviewerPlaceholder')}</div>
                  <div>{locale === 'ar' ? 'التقييم' : 'Feedback'}</div>
                  <div className="text-end">{recruitingCopy(locale, 'nextHumanAction')}</div>
                </div>
                {interviews.map((interview) => (
                  <InterviewQueueRow
                    interview={interview}
                    key={interview.interview_id}
                    locale={locale}
                    onOpen={() => {
                      setSelectedInterviewId(interview.interview_id)
                      setSelectedSnapshot(interview)
                    }}
                  />
                ))}
              </div>
            </div>
          ) : (
            <ResourceState
              kind="empty"
              locale={locale}
              title={recruitingCopy(locale, 'interviewEmpty')}
              testId="interviews-list-empty"
            />
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[#6f675c]">
            <div>
              {recruitingCopy(locale, 'interviewShowing', {
                from: total ? offset + 1 : 0,
                to: Math.min(offset + interviews.length, total),
                total,
              })}
              {busy ? (
                <span className="ms-2 inline-flex items-center gap-1 text-xs">
                  <Loader2 className="animate-spin" size={12} /> {recruitingCopy(locale, 'interviewUpdating')}
                </span>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button disabled={!canGoBack} onClick={() => onSetOffset(Math.max(0, offset - limit))} size="sm" variant="secondary">
                {recruitingCopy(locale, 'interviewPrevious')}
              </Button>
              <Button disabled={!canGoNext} onClick={() => onSetOffset(offset + limit)} size="sm" variant="secondary">
                {recruitingCopy(locale, 'interviewNext')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      {selectedInterview ? (
        <InterviewDetailDrawer
          access={access}
          busy={busy}
          interview={selectedInterview}
          locale={locale}
          notesDraft={notesDrafts[selectedInterview.interview_id] || ''}
          onClose={() => {
            setSelectedInterviewId(null)
            setSelectedSnapshot(null)
          }}
          onOpenCandidate={onOpenCandidate}
          onPreviewVideoAnswer={onPreviewVideoAnswer}
          onRefresh={onRefresh}
          onRetryVideoTranscripts={onRetryVideoTranscripts}
          onSaveNotes={onSaveNotes}
          onSetNotes={onSetNotes}
          onStatusChange={onStatusChange}
          canManageInterviews={canManageInterviews}
        />
      ) : null}
    </div>
  )
}

export const InterviewQueueRow = memo(function InterviewQueueRow({
  interview,
  locale,
  onOpen,
}: {
  interview: CandidateInterview
  locale: RecruitingLocale
  onOpen: () => void
}) {
  const p = interview.presentation
  const isAsync = p?.display?.is_async ?? interview.interview_type === 'async_video'
  const typeLabel =
    p?.interview_type_label
    || (isAsync ? recruitingCopy(locale, 'recordedVideo') : recruitingCopy(locale, 'interviewLiveType'))
  const progressLabel = p?.progress_label || p?.display?.status_label || facetStatusLabel(interview.status, locale)
  const dateTime = p?.display?.show_datetime && p.date_time ? formatDateTime(p.date_time) : null
  const interviewerLabel = p?.interviewer_assignment?.label || recruitingCopy(locale, 'interviewUnassigned')
  const feedbackComplete = Boolean(interview.feedback?.complete)
  const feedbackLabel = feedbackComplete
    ? recruitingCopy(locale, 'interviewFeedbackComplete')
    : (interview.feedback?.needs_feedback
      ? recruitingCopy(locale, 'interviewFeedbackPending')
      : (interview.feedback?.label || recruitingCopy(locale, 'interviewFeedbackNotStarted')))
  const nextAction = p?.next_human_action || interview.next_human_action || ''
  const muted = interview.status === 'cancelled' || interview.status === 'no_show' || p?.progress_state === 'cancelled'
  return (
    <div
      className={cn(
        'grid h-14 cursor-pointer grid-cols-[minmax(200px,1.4fr)_minmax(150px,1fr)_minmax(170px,1.1fr)_minmax(130px,0.9fr)_minmax(130px,0.9fr)_minmax(150px,1fr)] items-center gap-3 border-b border-[#e8dfd0]/80 px-4 text-sm transition hover:bg-white/55 last:border-b-0',
        muted && 'opacity-75',
      )}
      onClick={onOpen}
    >
      <div className="min-w-0">
        <div className="truncate font-semibold text-[#23211d]">{interview.candidate_name || interview.phone || 'Candidate'}</div>
        <div className="truncate text-xs text-[#6f675c]">{interview.candidate_email || interview.phone || ''}</div>
      </div>
      <div className="truncate text-[#6f675c]">{interview.position_title || interview.position_code || 'Role'}</div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-[#23211d]">{typeLabel}</div>
        <div className="truncate text-xs text-[#6f675c]">{dateTime ? `${progressLabel} · ${dateTime}` : progressLabel}</div>
      </div>
      <div className="truncate text-[#6f675c]">{interviewerLabel}</div>
      <div>
        <Badge tone={feedbackComplete ? 'success' : 'warning'}>{feedbackLabel}</Badge>
      </div>
      <div className="flex justify-end">
        <Button onClick={onOpen} size="sm" variant="secondary">
          {nextAction ? workflowItemLabel(nextAction, locale) : recruitingCopy(locale, 'open')}
        </Button>
      </div>
    </div>
  )
})

InterviewQueueRow.displayName = 'InterviewQueueRow'

type InterviewDialogState =
  | { kind: 'datetime' }
  | { kind: 'assign' }
  | { kind: 'invite' }
  | { kind: 'cancel' }
  | { kind: 'no_show' }
  | { kind: 'complete' }
  | { kind: 'reopen' }
  | null

export function InterviewActions({
  access,
  allowed,
  busy,
  interview,
  locale,
  onOpenCandidate,
  onRefresh,
  onStatusChange: _onStatusChange,
}: {
  access: DashboardAccess
  allowed: string[]
  busy: boolean
  interview: CandidateInterview
  locale: RecruitingLocale
  onOpenCandidate: (appKey?: string) => void
  onRefresh: () => void
  onStatusChange: (interview: CandidateInterview, status: string) => void
}) {
  const actions = new Set(allowed)
  const isAr = locale === 'ar'
  void _onStatusChange
  const [dialog, setDialog] = useState<InterviewDialogState>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [datetimeValue, setDatetimeValue] = useState('')
  const [assigneeValue, setAssigneeValue] = useState('')

  const primary = interview.presentation?.next_human_action || ''
  const primaryLabel = primary ? workflowItemLabel(primary, locale) : null

  async function run(fn: () => Promise<unknown>, success: string) {
    setSubmitting(true)
    setError(null)
    try {
      await fn()
      setDialog(null)
      onRefresh()
    } catch (err) {
      setError(friendlyDashboardError(err, success))
    } finally {
      setSubmitting(false)
    }
  }

  function openDialog(kind: NonNullable<InterviewDialogState>['kind']) {
    setError(null)
    if (kind === 'datetime') {
      const raw = interview.scheduled_start ? new Date(interview.scheduled_start) : null
      setDatetimeValue(raw && !Number.isNaN(raw.getTime()) ? raw.toISOString().slice(0, 16) : '')
    }
    setDialog({ kind })
  }

  return (
    <>
      {primaryLabel && (actions.has('set_interview_datetime') || actions.has('reschedule_interview')) && (primary === 'set_interview_datetime' || primary === 'schedule_interview' || primary === 'reschedule_interview') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('datetime')} size="sm">
          {isAr ? 'تحديد التاريخ والوقت' : 'Set date and time'}
        </Button>
      ) : null}
      {actions.has('set_interview_datetime') && !(primary === 'set_interview_datetime' || primary === 'schedule_interview') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('datetime')} size="sm" variant="secondary">
          {isAr ? 'تحديد التاريخ والوقت' : 'Set date and time'}
        </Button>
      ) : null}
      {actions.has('reschedule_interview') && primary !== 'set_interview_datetime' ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('datetime')} size="sm" variant="secondary">
          {isAr ? 'إعادة الجدولة' : 'Reschedule'}
        </Button>
      ) : null}
      {actions.has('assign_interviewer') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('assign')} size="sm" variant="secondary">
          {isAr ? 'تعيين المقابِل' : 'Assign interviewer'}
        </Button>
      ) : null}
      {actions.has('send_video_invitation') || actions.has('resend_video_link') || actions.has('retry_video_invitation') || actions.has('reopen_invitation') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('invite')} size="sm" variant="secondary">
          {actions.has('resend_video_link') || actions.has('retry_video_invitation') || actions.has('reopen_invitation')
            ? (isAr ? 'إعادة إرسال رابط الفيديو' : 'Resend video link')
            : (isAr ? 'إرسال دعوة الفيديو' : 'Send video invitation')}
        </Button>
      ) : null}
      {actions.has('send_interview_invitation') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('invite')} size="sm" variant="secondary">
          {isAr ? 'إرسال الدعوة' : 'Send invitation'}
        </Button>
      ) : null}
      {actions.has('mark_completed') || actions.has('mark_reviewed') ? (
        <Button disabled={busy || submitting} onClick={() => openDialog('complete')} size="sm" variant="secondary">
          {actions.has('mark_reviewed') ? (isAr ? 'تحديد كمراجعة' : 'Mark reviewed') : recruitingActionLabel('mark_completed', locale)}
        </Button>
      ) : null}
      {interview.meet_link ? (
        <Button onClick={() => window.open(interview.meet_link, '_blank', 'noopener,noreferrer')} size="sm" variant="ghost">
          <ExternalLink size={14} /> Meet
        </Button>
      ) : null}
      {actions.has('open_candidate') ? (
        <Button onClick={() => onOpenCandidate(interview.app_key)} size="sm" variant="ghost">
          {recruitingActionLabel('open_candidate', locale)}
        </Button>
      ) : null}
      {actions.has('mark_no_show') || actions.has('cancel_interview') ? (
        <details className="relative">
          <summary className="cursor-pointer rounded-full border border-[#e8dfd0] bg-white/55 px-3 py-1.5 text-sm text-[#6f675c] transition hover:border-[#23211d]/25 hover:text-[#23211d]">
            {recruitingCopy(locale, 'interviewMore')}
          </summary>
          <div className="absolute end-0 z-10 mt-2 grid w-44 gap-2 rounded-xl border border-[#e8dfd0] bg-[#fffaf0] p-2 shadow-soft">
            {actions.has('mark_no_show') ? (
              <Button disabled={busy || submitting} onClick={() => openDialog('no_show')} size="sm" variant="ghost">
                {recruitingActionLabel('mark_no_show', locale)}
              </Button>
            ) : null}
            {actions.has('cancel_interview') ? (
              <Button disabled={busy || submitting} onClick={() => openDialog('cancel')} size="sm" variant="ghost">
                {recruitingActionLabel('cancel_interview', locale)}
              </Button>
            ) : null}
          </div>
        </details>
      ) : null}

      {dialog ? (
        <InterviewActionDialog
          access={access}
          assigneeValue={assigneeValue}
          datetimeValue={datetimeValue}
          dialog={dialog}
          error={error}
          interview={interview}
          locale={locale}
          onAssigneeChange={setAssigneeValue}
          onClose={() => setDialog(null)}
          onDatetimeChange={setDatetimeValue}
          onSubmit={async () => {
            if (dialog.kind === 'datetime') {
              if (!datetimeValue) {
                setError(isAr ? 'التاريخ والوقت مطلوبان.' : 'Date and time are required.')
                return
              }
              await run(async () => {
                await interviewReschedule(access, interview.interview_id, { scheduled_start: new Date(datetimeValue).toISOString() })
              }, isAr ? 'تعذر تحديث الموعد.' : 'Could not update the schedule.')
            } else if (dialog.kind === 'assign') {
              if (!assigneeValue.trim()) {
                setError(isAr ? 'اختر المقابِل.' : 'Choose an interviewer.')
                return
              }
              await run(async () => {
                await interviewAssignInterviewer(access, interview.interview_id, {
                  assignee: { user_id: assigneeValue.trim() },
                })
              }, isAr ? 'تعذر تعيين المقابِل.' : 'Could not assign the interviewer.')
            } else if (dialog.kind === 'invite') {
              await run(async () => {
                if (actions.has('send_video_invitation') || actions.has('resend_video_link') || actions.has('retry_video_invitation') || actions.has('reopen_invitation')) {
                  await interviewSendVideoInvitation(access, interview.interview_id, {})
                } else {
                  await interviewReschedule(access, interview.interview_id, { send_invite: true })
                }
              }, isAr ? 'تعذر إرسال الدعوة.' : 'Could not send the invitation.')
            } else if (dialog.kind === 'cancel' || dialog.kind === 'no_show' || dialog.kind === 'complete') {
              const status = dialog.kind === 'cancel' ? 'cancelled' : dialog.kind === 'no_show' ? 'no_show' : 'completed'
              await run(async () => {
                await updateInterviewStatus(access, interview.interview_id, status)
              }, isAr ? 'تعذر تحديث المقابلة.' : 'Could not update the interview.')
              setDialog(null)
            }
          }}
          submitting={submitting}
        />
      ) : null}
    </>
  )
}

export function InterviewActionDialog({
  access,
  assigneeValue,
  datetimeValue,
  dialog,
  error,
  interview,
  locale,
  onAssigneeChange,
  onClose,
  onDatetimeChange,
  onSubmit,
  submitting,
}: {
  access: DashboardAccess
  assigneeValue: string
  datetimeValue: string
  dialog: NonNullable<InterviewDialogState>
  error: string | null
  interview: CandidateInterview
  locale: RecruitingLocale
  onAssigneeChange: (value: string) => void
  onClose: () => void
  onDatetimeChange: (value: string) => void
  onSubmit: () => Promise<void>
  submitting: boolean
}) {
  const isAr = locale === 'ar'
  const title = {
    datetime: isAr ? 'تحديد التاريخ والوقت' : 'Set date and time',
    assign: isAr ? 'تعيين المقابِل' : 'Assign interviewer',
    invite: isAr ? 'إرسال/إعادة إرسال الدعوة' : 'Send / resend invitation',
    cancel: isAr ? 'إلغاء المقابلة' : 'Cancel interview',
    no_show: isAr ? 'تسجيل عدم الحضور' : 'Mark no-show',
    complete: interview.presentation?.allowed_actions?.includes('mark_reviewed') ? (isAr ? 'تحديد كمراجعة' : 'Mark reviewed') : (isAr ? 'تحديد كمكتملة' : 'Mark completed'),
    reopen: isAr ? 'إعادة فتح الدعوة' : 'Reopen invitation',
  }[dialog.kind]
  const confirmLabel = {
    datetime: isAr ? 'حفظ الموعد' : 'Save schedule',
    assign: isAr ? 'تعيين' : 'Assign',
    invite: isAr ? 'إرسال' : 'Send',
    cancel: isAr ? 'إلغاء المقابلة' : 'Cancel interview',
    no_show: isAr ? 'تأكيد' : 'Confirm',
    complete: isAr ? 'تأكيد' : 'Confirm',
    reopen: isAr ? 'إعادة الفتح' : 'Reopen',
  }[dialog.kind]
  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-ink/40 p-4"
      onClick={() => {
        if (!submitting) onClose()
      }}
      role="dialog"
    >
      <div className="w-full max-w-md rounded-[1.4rem] border border-line bg-panel p-5 shadow-soft" onClick={(event) => event.stopPropagation()}>
        <h4 className="text-lg font-semibold text-text">{title}</h4>
        <p className="mt-1 text-sm text-subtle">{interview.candidate_name || interview.phone || 'Candidate'}</p>
        <div className="mt-4 space-y-3">
          {dialog.kind === 'datetime' ? (
            <label className="grid gap-1.5 text-sm">
              <span className="font-medium text-text">{isAr ? 'التاريخ والوقت' : 'Date and time'}</span>
              <input className="rounded-xl border border-line bg-white px-3 py-2 text-sm" onChange={(event) => onDatetimeChange(event.target.value)} type="datetime-local" value={datetimeValue} />
            </label>
          ) : null}
          {dialog.kind === 'assign' ? (
            <label className="grid gap-1.5 text-sm">
              <span className="font-medium text-text">{isAr ? 'المقابِل' : 'Interviewer'}</span>
              <PeoplePicker
                access={access}
                allowUnassigned={false}
                disabled={submitting}
                locale={isAr ? 'ar' : 'en'}
                onChange={(userId) => onAssigneeChange(userId)}
                purpose="interviewer"
                value={assigneeValue}
              />
            </label>
          ) : null}
          {dialog.kind === 'cancel' ? (
            <p className="text-sm text-subtle">{isAr ? 'سيتم إلغاء هذه المقابلة. يمكن جدولة مقابلة جديدة لاحقًا.' : 'This interview will be cancelled. You can schedule a new one later.'}</p>
          ) : null}
          {dialog.kind === 'no_show' ? (
            <p className="text-sm text-subtle">{isAr ? 'سيتم تسجيل عدم حضور المرشح.' : 'This will mark the candidate as no-show.'}</p>
          ) : null}
          {dialog.kind === 'invite' ? (
            <p className="text-sm text-subtle">{isAr ? 'إرسال الدعوة آمن ولن ينشئ مقابلة مكررة.' : 'Sending is idempotent and will not duplicate the interview.'}</p>
          ) : null}
          {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button disabled={submitting} onClick={onClose} variant="secondary">
            {isAr ? 'إلغاء' : 'Cancel'}
          </Button>
          <Button disabled={submitting} onClick={() => void onSubmit()}>
            {submitting ? <Loader2 className="animate-spin" size={14} /> : null} {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function InterviewDetailDrawer({
  access,
  busy,
  canManageInterviews,
  interview,
  locale,
  notesDraft,
  onClose,
  onOpenCandidate,
  onPreviewVideoAnswer,
  onRefresh,
  onRetryVideoTranscripts,
  onSaveNotes,
  onSetNotes,
  onStatusChange,
}: {
  access: DashboardAccess
  busy: boolean
  canManageInterviews: boolean
  interview: CandidateInterview
  locale: RecruitingLocale
  notesDraft: string
  onClose: () => void
  onOpenCandidate: (appKey?: string) => void
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRefresh: () => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
  onSaveNotes: (interview: CandidateInterview) => void
  onSetNotes: (interviewId: string, value: string) => void
  onStatusChange: (interview: CandidateInterview, status: string) => void
}) {
  useEffect(() => {
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0
    const body = document.body
    const html = document.documentElement
    const previous = {
      bodyOverflow: body.style.overflow,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyLeft: body.style.left,
      bodyRight: body.style.right,
      bodyWidth: body.style.width,
      htmlOverflow: html.style.overflow,
      htmlOverscroll: html.style.overscrollBehavior,
    }
    body.style.overflow = 'hidden'
    body.style.position = 'fixed'
    body.style.top = `-${scrollY}px`
    body.style.left = '0'
    body.style.right = '0'
    body.style.width = '100%'
    html.style.overflow = 'hidden'
    html.style.overscrollBehavior = 'none'
    return () => {
      body.style.overflow = previous.bodyOverflow
      body.style.position = previous.bodyPosition
      body.style.top = previous.bodyTop
      body.style.left = previous.bodyLeft
      body.style.right = previous.bodyRight
      body.style.width = previous.bodyWidth
      html.style.overflow = previous.htmlOverflow
      html.style.overscrollBehavior = previous.htmlOverscroll
      window.scrollTo(0, scrollY)
    }
  }, [])

  const presentation = interview.presentation
  const isVideo = presentation?.display?.is_async ?? interview.interview_type === 'async_video'
  const videoStatus = asyncVideoDisplayStatus(interview)
  const mainStatus = presentation?.progress_label || presentation?.display?.status_label || facetStatusLabel(interview.status, locale)
  const allowedActions = new Set(resolveAllowedActions(interview.allowed_actions, presentation?.allowed_actions))
  const roleLabel = interview.position_title || interview.position_code || 'Role'
  const scheduleLabel = presentation?.display?.show_datetime && presentation.date_time
    ? formatDateTime(presentation.date_time)
    : isVideo
      ? (presentation?.interview_type_label || recruitingCopy(locale, 'recordedVideo'))
      : (interview.scheduled_start ? formatDateTime(interview.scheduled_start) : recruitingCopy(locale, 'dateNotSet'))
  const typeLabel =
    presentation?.interview_type_label
    || (isVideo ? recruitingCopy(locale, 'recordedVideo') : recruitingCopy(locale, 'interviewLiveType'))
  const summaryLine = interviewSummaryLine(interview, locale)
  const failedInvite = presentation?.invitation_state === 'delivery_failed'
  const hasAnalysis = Boolean(interview.ai_summary?.summary || interview.ai_summary?.overall_summary)
  const notRecorded = recruitingCopy(locale, 'interviewNotRecorded')

  return (
    <div className="fixed inset-0 z-30 overflow-hidden bg-[#23211d]/35" dir={locale === 'ar' ? 'rtl' : 'ltr'} onClick={onClose}>
      <aside
        className="ms-auto flex h-full w-full max-w-3xl flex-col overflow-y-auto overscroll-contain border-s border-[#e8dfd0] bg-[#fffaf0] p-5 shadow-[0_24px_80px_rgba(35,33,29,0.18)] sm:p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-col gap-4 border-b border-[#e8dfd0] pb-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xl font-semibold tracking-tight text-[#23211d]">
                {interview.candidate_name || interview.phone || 'Candidate'}
              </h3>
              <Badge tone={isVideo ? videoStatus.tone : statusTone(interview.status)}>
                {mainStatus}
              </Badge>
            </div>
            <div className="mt-1.5 text-sm text-[#6f675c]">
              {[
                roleLabel,
                typeLabel,
                presentation?.display?.show_datetime ? scheduleLabel : null,
              ].filter(Boolean).join(' · ')}
            </div>
            <div className="mt-1 text-xs text-[#8a8276]">
              {recruitingCopy(locale, 'applicationStage')}: {canonicalStageLabel(interview.application_stage, locale)}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onClose} size="sm" variant="secondary">
              {recruitingCopy(locale, 'interviewClose')}
            </Button>
            <InterviewActions
              access={access}
              allowed={[...allowedActions]}
              busy={busy}
              interview={interview}
              locale={locale}
              onOpenCandidate={onOpenCandidate}
              onRefresh={onRefresh}
              onStatusChange={onStatusChange}
            />
          </div>
        </div>

        <p className="mt-4 text-[15px] leading-7 text-[#4a453c]">{summaryLine}</p>

        <div className="mt-4 space-y-4">
          {failedInvite ? (
            <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm text-amber-950">
              {recruitingCopy(locale, 'interviewFailedInvite')}
            </div>
          ) : null}
          {hasAnalysis ? <PracticalInterviewSummary interview={interview} locale={locale} /> : null}
          {isVideo ? (
            <VideoInterviewReview
              busy={busy}
              canManageInterviews={canManageInterviews}
              interview={interview}
              locale={locale}
              onPreviewVideoAnswer={onPreviewVideoAnswer}
              onRetryVideoTranscripts={onRetryVideoTranscripts}
            />
          ) : null}
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <Textarea
              onChange={(event) => onSetNotes(interview.interview_id, event.target.value)}
              placeholder={recruitingCopy(locale, 'interviewFeedbackPlaceholder')}
              value={notesDraft}
            />
            <Button disabled={busy || !allowedActions.has('write_notes')} onClick={() => onSaveNotes(interview)} variant="secondary">
              {busy ? <Loader2 className="animate-spin" size={14} /> : <Pencil size={14} />} {recruitingCopy(locale, 'interviewSaveFeedback')}
            </Button>
          </div>
          {!interview.allowed_actions?.length ? (
            <div className="text-xs text-[#6f675c]">{recruitingCopy(locale, 'noPermittedActions')}</div>
          ) : null}
        </div>

        <div className="mt-5 space-y-2">
          <details className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewInviteDetails')}</summary>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
              <QuietInfo label={recruitingCopy(locale, 'interviewInvite')} locale={locale} value={inviteTruthLabel(interview)} />
              <QuietInfo label={recruitingCopy(locale, 'invitationStatus')} locale={locale} value={communicationLabel(interview.invitation_status, locale)} />
              <QuietInfo label={recruitingCopy(locale, 'candidateConfirmation')} locale={locale} value={stageLabel(interview.candidate_confirmation)} />
              <QuietInfo
                label={recruitingCopy(locale, 'interviewMeeting')}
                locale={locale}
                value={isVideo ? recruitingCopy(locale, 'interviewVideoLink') : interview.meet_link ? recruitingCopy(locale, 'interviewMeetAvailable') : calendarEventLabel(interview)}
              />
              <QuietInfo label={recruitingCopy(locale, 'interviewInviteSentAt')} locale={locale} value={interview.invite_sent_at ? formatDateTime(interview.invite_sent_at) : notRecorded} />
              <QuietInfo label={recruitingCopy(locale, 'interviewContact')} locale={locale} value={interview.candidate_email || interview.phone || notRecorded} />
              <QuietInfo label={recruitingCopy(locale, 'interviewChannel')} locale={locale} value={notificationChannelLabel(interview.notification_channel)} />
            </div>
          </details>
          {interview.sent_subject || interview.sent_body ? (
            <details className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
              <summary className="cursor-pointer text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewSentMessage')}</summary>
              {interview.sent_subject ? <div className="mt-3 text-sm font-medium text-[#23211d]">{interview.sent_subject}</div> : null}
              {interview.sent_body ? <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#6f675c]">{interview.sent_body}</div> : null}
            </details>
          ) : null}
          <details className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewTimeline')}</summary>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
              <QuietInfo label={isVideo ? recruitingCopy(locale, 'interviewLatestActivity') : recruitingCopy(locale, 'interviewScheduledTime')} locale={locale} value={scheduleLabel} />
              <QuietInfo label={recruitingCopy(locale, 'interviewCreated')} locale={locale} value={interview.created_at ? formatDateTime(interview.created_at) : notRecorded} />
              <QuietInfo label={recruitingCopy(locale, 'interviewUpdated')} locale={locale} value={interview.updated_at ? formatDateTime(interview.updated_at) : notRecorded} />
            </div>
          </details>
          <details className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewStatusDetails')}</summary>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
              <QuietInfo label={recruitingCopy(locale, 'interviewState')} locale={locale} value={isVideo ? mainStatus : stageLabel(interview.status)} />
              <QuietInfo label={recruitingCopy(locale, 'applicationStage')} locale={locale} value={canonicalStageLabel(interview.application_stage, locale)} />
              <QuietInfo label={recruitingCopy(locale, 'interviewFeedbackState')} locale={locale} value={interview.feedback?.label || stageLabel(interview.feedback_status || 'notes_pending')} />
              <QuietInfo label={recruitingCopy(locale, 'notesStatus')} locale={locale} value={stageLabel(interview.notes_status || notesStateLabel(interview))} />
            </div>
            {interview.notes ? (
              <div className="mt-3 text-sm leading-6 text-[#6f675c]">
                {recruitingCopy(locale, 'interviewLatestHrNotes')}: {interview.notes}
              </div>
            ) : null}
          </details>
        </div>
      </aside>
    </div>
  )
}

export function PracticalInterviewSummary({ interview, locale }: { interview: CandidateInterview; locale: RecruitingLocale }) {
  const summary = interview.ai_summary
  const overallSummary = summary?.overall_summary || summary?.summary || recruitingCopy(locale, 'interviewNoAiSummary')
  const strengths = summary?.strengths || []
  const concerns = summary?.gaps_or_risks || summary?.concerns || []
  const followUps = summary?.suggested_follow_up_questions || summary?.follow_up_questions || summary?.follow_up_points || []
  const recommended = summary?.recommended_next_step || summary?.recommendation || recruitingCopy(locale, 'interviewReviewEvidenceNext')
  const overallFit = normalizeOverallImpression(summaryValue(summary, ['overall_fit', 'fit', 'fit_label'])) || recruitingCopy(locale, 'interviewNeedsMoreEvidence')
  const confidence = normalizeEvidenceConfidence(summaryValue(summary, ['confidence', 'confidence_label'])) || recruitingCopy(locale, 'interviewConfidenceLimited')
  return (
    <div className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'analysis')}</div>
          <p className="mt-2 text-sm leading-6 text-[#6f675c]">{overallSummary}</p>
        </div>
        <div className="grid min-w-[220px] gap-2 text-sm sm:grid-cols-2 md:grid-cols-1">
          <QuietInfo label={recruitingCopy(locale, 'interviewOverallImpression')} locale={locale} value={overallFit} />
          <QuietInfo label={recruitingCopy(locale, 'confidence')} locale={locale} value={confidence} />
        </div>
      </div>
      <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <InterviewSummaryList label={recruitingCopy(locale, 'interviewKeyStrengths')} values={strengths} />
        <InterviewSummaryList label={recruitingCopy(locale, 'concerns')} values={concerns} />
        <InterviewSummaryList label={recruitingCopy(locale, 'recommendation')} values={[recommended]} />
      </div>
      {followUps.length ? (
        <div className="mt-4 rounded-xl border border-[#e8dfd0] bg-[#fffaf0] p-3">
          <div className="text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewFollowUpQuestions')}</div>
          <ol className="mt-2 list-decimal space-y-1 ps-5 text-sm leading-6 text-[#6f675c]">
            {followUps.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ol>
        </div>
      ) : null}
      <details className="mt-4 rounded-xl border border-[#e8dfd0] bg-[#fffaf0] p-3">
        <summary className="cursor-pointer text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewDetailedEvidence')}</summary>
        <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
          <InterviewSummaryList label={recruitingCopy(locale, 'interviewRoleFitEvidence')} values={summary?.role_fit_evidence || []} />
          <InterviewSummaryList label={recruitingCopy(locale, 'interviewCommunicationNotes')} values={summary?.communication_notes || []} />
          <InterviewSummaryList label={recruitingCopy(locale, 'missingInformation')} values={summary?.missing_evidence || []} />
        </div>
      </details>
      <div className="mt-3 text-xs leading-5 text-[#8a8276]">{summary?.hr_decision_maker_note || summary?.decision_policy || recruitingCopy(locale, 'advisory')}</div>
    </div>
  )
}

export function VideoInterviewReview({
  busy,
  canManageInterviews,
  interview,
  locale,
  onPreviewVideoAnswer,
  onRetryVideoTranscripts,
}: {
  busy: boolean
  canManageInterviews: boolean
  interview: CandidateInterview
  locale: RecruitingLocale
  onPreviewVideoAnswer: (videoUrl?: string) => void
  onRetryVideoTranscripts: (interview: CandidateInterview) => void
}) {
  const answers = interview.video_answers || []
  const questions = interview.video_questions || answers[0]?.covered_questions || []
  const singleVideo = interview.response_mode === 'single_video' || answers.some((answer) => answer.response_mode === 'single_video')
  const failed = answers.some((answer) => answer.transcript_status === 'failed')
  const labelClass = locale === 'ar' ? 'text-xs font-semibold text-[#8a8276]' : 'text-xs font-semibold uppercase tracking-[0.08em] text-[#8a8276]'
  return (
    <div className="rounded-2xl border border-[#e8dfd0] bg-[#f8f2e6]/70 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-[#23211d]">{recruitingCopy(locale, 'interviewVideoEvidence')}</div>
            <Badge tone={asyncVideoDisplayStatus(interview).tone}>{asyncVideoDisplayStatus(interview).label}</Badge>
          </div>
          <div className="mt-1 text-sm leading-6 text-[#6f675c]">{videoInterviewProcessingLine(interview)}</div>
        </div>
        {failed ? (
          <Button disabled={busy || !canManageInterviews} onClick={() => onRetryVideoTranscripts(interview)} size="sm" variant="secondary">
            {recruitingCopy(locale, 'interviewTryAgain')}
          </Button>
        ) : null}
      </div>
      {singleVideo && questions.length && answers.length ? (
        <div className="mt-4 rounded-xl border border-[#e8dfd0] bg-[#fffaf0] p-3">
          <div className={labelClass}>{recruitingCopy(locale, 'interviewQuestionList')}</div>
          <div className="mt-1 text-sm font-medium text-[#23211d]">{recruitingCopy(locale, 'interviewAnsweredFullList')}</div>
          <ol className="mt-2 list-decimal space-y-2 ps-5 text-sm leading-6 text-[#6f675c]">
            {questions.map((question, index) => (
              <li key={question.question_id || index}>{question.prompt_text || recruitingCopy(locale, 'interviewVideoEvidence')}</li>
            ))}
          </ol>
        </div>
      ) : null}
      <div className="mt-4 space-y-3">
        {answers.length ? (
          answers.map((answer) => (
            <div className="rounded-xl border border-[#e8dfd0] bg-[#fffaf0] p-3" key={answer.response_id}>
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className={labelClass}>
                    {singleVideo
                      ? recruitingCopy(locale, 'interviewVideoAnswer')
                      : recruitingCopy(locale, 'interviewQuestionN', { n: answer.question_order || '' })}
                  </div>
                  <div className="mt-1 text-sm font-medium text-[#23211d]">
                    {singleVideo ? recruitingCopy(locale, 'interviewAnsweredFullList') : answer.question_text || recruitingCopy(locale, 'interviewVideoEvidence')}
                  </div>
                  <div className="mt-1 text-xs text-[#8a8276]">
                    {recruitingCopy(locale, 'interviewTranscript')}: {transcriptStatusLabel(answer.transcript_status)}
                  </div>
                </div>
                {answer.has_video ? (
                  <Button onClick={() => onPreviewVideoAnswer(answer.video_url)} size="sm" variant="ghost">
                    <ExternalLink size={14} /> {recruitingCopy(locale, 'interviewTabVideo')}
                  </Button>
                ) : null}
              </div>
              {answer.transcript_status === 'completed' && answer.transcript_text ? (
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#6f675c]">{answer.transcript_text}</p>
              ) : null}
              {answer.transcript_status === 'failed' ? (
                <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  {recruitingCopy(locale, 'interviewTranscriptFailed')}
                </div>
              ) : null}
            </div>
          ))
        ) : (
          <EmptyState text={recruitingCopy(locale, 'interviewNoVideoAnswers')} />
        )}
      </div>
    </div>
  )
}

export function InterviewSummaryList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <div className="font-medium text-[#23211d]">{label}</div>
      {values.length ? (
        <ul className="mt-1 list-disc space-y-1 ps-4 text-[#6f675c]">
          {values.slice(0, 4).map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}
        </ul>
      ) : (
        <div className="mt-1 text-[#8a8276]">—</div>
      )}
    </div>
  )
}
