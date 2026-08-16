import { Loader2, RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Profiler as ReactProfiler, useCallback, useState } from 'react'

import { fetchAssessmentReport } from '@/lib/query/fetchers'
import { qk } from '@/lib/query/keys'
import {
  assessmentQueueActionLabel,
  normalizeAssessmentCohortKey,
  queuePrimaryAction,
} from '@/lib/assessmentCohorts'
import {
  applicationCountOnly,
  type AssessmentCohortCountBlock,
} from '@/lib/assessmentsQueueContract'
import {
  assessmentCohortChipLabel,
  assessmentCopy,
  assessmentStatusLabel,
} from '@/lib/assessmentVocabulary'
import {
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
  dashboardPerfMarkProfilerCommit,
} from '@/lib/perf/dashboardPerf'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { AssessmentAttemptWorkspace, AssessmentReportPage, type AssessmentReportPresentation } from '@/components/assessments/AssessmentReportPage'
import { AttemptRow, ReportRow, SendRow } from '@/components/assessments/AssessmentRows'
import { Product2AuthoringPanel } from '@/components/Product2AuthoringPanel'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { EmptyState, Info } from '@/pages/shared/primitives'
import {
  assessmentQueue,
  assessmentSetupIsReady,
  assessmentSetupLastRefreshedAt,
  assessmentSetupLastRefreshedLabel,
  candidateName,
  setupCalibrationLabel,
  stageLabel,
} from '@/pages/shared/format'
import type {
  ApplicationSummary,
  AssessmentAttempt,
  AssessmentConfigResponse,
  DashboardAccess,
} from '@/types'
import type { OutboundSendResult } from '@/components/SendResultPanel'

function AssessmentsSectionProfiler({
  id,
  children,
}: {
  id: string
  children: React.ReactNode
}) {
  const onRender = useCallback(
    (
      profilerId: string,
      phase: 'mount' | 'update' | 'nested-update',
      actualDuration: number,
      baseDuration: number,
    ) => {
      dashboardPerfMarkProfilerCommit(`assessments:${profilerId}`, {
        phase,
        actualDurationMs: Math.round(actualDuration),
        baseDurationMs: Math.round(baseDuration),
      })
    },
    [],
  )
  return (
    <ReactProfiler id={id} onRender={onRender}>
      {children}
    </ReactProfiler>
  )
}

export function AssessmentsPage({
  access,
  applications,
  assessmentTab,
  lastSendResult,
  locale,
  cohortKey,
  cohortCounts,
  canManageAssessments,
  enabled,
  config,
  userRoleKey,
  attempts,
  busy,
  limit,
  offset,
  total,
  onSelectCohort,
  onSelectTab,
  onOpenCandidate: _onOpenCandidate,
  onOpenFollowUpCandidates,
  onCancelAttempt,
  onResendAttempt,
  onReviewAttempt,
  onRecalculateNorms,
  onRefresh: _onRefresh,
  onSendAssessment,
  onResendAssessment,
  onSetOffset,
  needsReviewCount = 0,
  reportReadyCount = 0,
  pendingTotal,
  queueHasMore = false,
  queueLoadingMore = false,
  onLoadMoreQueue,
  attemptsLoading = false,
  attemptsRefreshing = false,
  attemptsError = false,
  queueLoading = false,
  queueRefreshing = false,
  queueError = false,
}: {
  access: DashboardAccess
  applications: ApplicationSummary[]
  assessmentTab: string
  lastSendResult?: OutboundSendResult | null
  locale: RecruitingLocale
  cohortKey: string
  cohortCounts?: Record<string, AssessmentCohortCountBlock>
  canManageAssessments: boolean
  enabled: boolean
  config: AssessmentConfigResponse | null
  userRoleKey?: string
  attempts: AssessmentAttempt[]
  busy: boolean
  limit: number
  offset: number
  total: number
  onSelectCohort: (cohortKey: string) => void
  onSelectTab: (tab: string) => void
  onOpenCandidate: (appKey: string) => void
  onOpenFollowUpCandidates: () => void
  onCancelAttempt: (attempt: AssessmentAttempt) => void
  onResendAttempt: (attempt: AssessmentAttempt) => void
  onReviewAttempt: (attempt: AssessmentAttempt) => void
  onRecalculateNorms: () => void
  onRefresh: () => void
  onSendAssessment: (application: ApplicationSummary) => void
  onResendAssessment: (application: ApplicationSummary) => void
  onSetOffset: (offset: number) => void
  needsReviewCount?: number
  reportReadyCount?: number
  pendingTotal?: number
  queueHasMore?: boolean
  queueLoadingMore?: boolean
  onLoadMoreQueue?: () => void
  attemptsLoading?: boolean
  attemptsRefreshing?: boolean
  attemptsError?: boolean
  queueLoading?: boolean
  queueRefreshing?: boolean
  queueError?: boolean
}) {
  void _onOpenCandidate
  const isAr = locale === 'ar'
  const queue = assessmentQueue(applications, cohortKey)
  const queueCopy = assessmentQueueActionLabel(cohortKey, locale)
  const pendingCount = typeof pendingTotal === 'number' ? pendingTotal : queue.length
  const canGoBack = offset > 0
  const canGoNext = offset + limit < total
  const itemBank = config?.item_bank
  const roleProfileCount = Object.keys(config?.role_profiles || {}).length
  const competencyCount = Object.keys(config?.framework?.competencies || {}).length
  const sections = Object.keys(itemBank?.section_totals || {}).map(stageLabel).join(', ') || (isAr ? 'القدرة + الحكم العملي' : 'Ability + workplace judgment')
  const questionCount = itemBank?.total_items || 22
  const batteryName = String(config?.battery?.name || 'Wathefni Ability Assessment')
  const batteryVersion = String(config?.battery?.version || 'v1')
  const cohortTabs: Array<{ key: string }> = [
    { key: 'assessment_ready_to_send' },
    { key: 'assessment_resend_needed' },
    { key: 'assessment_delivery_failed' },
    { key: 'assessment_in_progress' },
    { key: 'assessment_sent_pending' },
  ]
  const isSendTab = ['send', 'resend', 'delivery_failed', 'in_progress', 'sent_pending'].includes(assessmentTab)
  const isAttemptsTab = assessmentTab === 'attempts' || assessmentTab === 'completed' || assessmentTab === 'needs_review'
  const isReportsTab = assessmentTab === 'reports'
  const isNeedsReviewTab = assessmentTab === 'needs_review'
  const canSeeSetup = canManageAssessments && userRoleKey !== 'recruiter' && userRoleKey !== 'hiring_manager'
  const setupReady = assessmentSetupIsReady(config)
  const setupReadyLabel = setupReady
    ? (isAr ? 'الإعداد جاهز' : 'Setup ready')
    : (isAr ? 'يحتاج انتباه' : 'Needs attention')
  const questionsLabel = isAr
    ? `${itemBank?.total_items ?? questionCount} أسئلة`
    : `${itemBank?.total_items ?? questionCount} questions`
  const evidenceLabel = isAr
    ? `${competencyCount} مؤشر دليل`
    : `${competencyCount} evidence indicators`
  const lastRefreshedLabel = assessmentSetupLastRefreshedLabel(
    assessmentSetupLastRefreshedAt(config),
    locale,
  )
  const queryClient = useQueryClient()
  const [selectedAttempt, setSelectedAttempt] = useState<AssessmentAttempt | null>(null)
  const [reportAttempt, setReportAttempt] = useState<AssessmentAttempt | null>(null)
  const [reportPresentation, setReportPresentation] = useState<AssessmentReportPresentation | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState(false)

  // assessments.cohort.* — application_count only; never status_counts fallback.
  const peopleFor = (key: string) => applicationCountOnly(cohortCounts?.[key])

  function selectTab(tab: string) {
    dashboardPerfMarkInteractionStart('assessments_tab', { tab })
    onSelectTab(tab)
    dashboardPerfMarkNetworkComplete('assessments_tab', { tab })
  }

  function selectCohort(key: string) {
    dashboardPerfMarkInteractionStart('assessments_cohort', { cohort: key })
    onSelectCohort(key)
    dashboardPerfMarkNetworkComplete('assessments_cohort', { cohort: key })
  }

  function setPageOffset(next: number) {
    dashboardPerfMarkInteractionStart('assessments_pagination', { offset: next })
    onSetOffset(next)
    dashboardPerfMarkNetworkComplete('assessments_pagination', { offset: next })
  }

  async function openReport(attempt: AssessmentAttempt) {
    dashboardPerfMarkInteractionStart('assessments_open_report', { attempt: 1 })
    const reportKey = qk.assessmentReport(access, attempt.attempt_id)
    type ReportPayload = Awaited<ReturnType<typeof fetchAssessmentReport>>
    const cachedPayload = queryClient.getQueryData<ReportPayload>(reportKey)
    setReportError(false)
    setReportLoading(!cachedPayload)
    if (cachedPayload) {
      setReportAttempt((cachedPayload.attempt as AssessmentAttempt) || attempt)
      setReportPresentation((cachedPayload.report_presentation as AssessmentReportPresentation) || null)
    } else {
      setReportAttempt(attempt)
      setReportPresentation(null)
    }
    try {
      const payload = await queryClient.fetchQuery({
        queryKey: reportKey,
        queryFn: ({ signal }) => fetchAssessmentReport(access, attempt.attempt_id, signal),
      })
      const nextAttempt = (payload.attempt as AssessmentAttempt) || attempt
      const nextPresentation = (payload.report_presentation as AssessmentReportPresentation) || null
      setReportAttempt(nextAttempt)
      setReportPresentation(nextPresentation)
      setReportError(false)
      dashboardPerfMarkNetworkComplete('assessments_open_report', { cached: Boolean(cachedPayload) })
    } catch {
      setReportError(true)
      if (!cachedPayload) {
        setReportAttempt(attempt)
        setReportPresentation(null)
      }
      dashboardPerfMarkNetworkComplete('assessments_open_report', { error: true })
    } finally {
      setReportLoading(false)
    }
  }

  function openWorkspace(attempt: AssessmentAttempt) {
    dashboardPerfMarkInteractionStart('assessments_open_workspace', { attempt: 1 })
    setSelectedAttempt(attempt)
    dashboardPerfMarkNetworkComplete('assessments_open_workspace', { open: true })
  }

  const staleHint =
    (isSendTab && queueRefreshing && !queueLoading) || (isAttemptsTab || isReportsTab) && attemptsRefreshing && !attemptsLoading

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'}>
      {enabled ? (
        <div className="flex flex-wrap gap-2">
          {[
            { id: 'send', label: assessmentCopy(locale, 'send') },
            { id: 'attempts', label: assessmentCopy(locale, 'attempts') },
            { id: 'reports', label: assessmentCopy(locale, 'reports') },
          ].map((tab) => (
            <Button
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              size="sm"
              variant={
                assessmentTab === tab.id
                || (tab.id === 'send' && isSendTab)
                || (tab.id === 'attempts' && isNeedsReviewTab)
                  ? 'default'
                  : 'secondary'
              }
            >
              {tab.label}
              {tab.id === 'attempts' && total && !isNeedsReviewTab && !isReportsTab ? ` (${total})` : ''}
              {tab.id === 'reports' && reportReadyCount ? ` (${reportReadyCount})` : ''}
            </Button>
          ))}
          {needsReviewCount > 0 || isNeedsReviewTab ? (
            <Button
              onClick={() => selectTab('needs_review')}
              size="sm"
              variant={isNeedsReviewTab ? 'default' : 'secondary'}
            >
              {assessmentCopy(locale, 'needs_review')}
              {needsReviewCount > 0 ? ` (${needsReviewCount})` : ''}
            </Button>
          ) : (
            // Reserve chip width while attempts load so the tab row does not shift.
            attemptsLoading ? (
              <span aria-hidden className="inline-flex h-8 min-w-[7.5rem] rounded-md bg-[#f0ebe3] opacity-60" />
            ) : null
          )}
        </div>
      ) : null}

      {!enabled ? (
        <Card tone="board">
          <CardHeader>
            <CardTitle className="text-[#23211d]">{isAr ? 'التقييمات' : 'Assessments'}</CardTitle>
            <CardDescription className="text-[#716a5e]">
              {isAr
                ? 'التقييمات غير مفعّلة لهذه الشركة بعد. يمكنك متابعة المرشحين والسير الذاتية والمقابلات والترتيب.'
                : 'Assessments are not enabled for this company yet. You can still review candidates, CVs, interviews, and ranking evidence.'}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {staleHint ? (
        <div className="rounded-xl border border-[#e8dfd0] bg-[#fffaf0] px-3 py-2 text-xs text-[#716a5e]">
          {isAr ? 'جاري تحديث البيانات…' : 'Updating…'}
        </div>
      ) : null}

      {enabled && canSeeSetup ? (
        <details className="rounded-2xl border border-[#e8dfd0] bg-[#f8f3e9]/70 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-[#716a5e]">
            {isAr ? 'إعداد التقييم (ثانوي)' : 'Assessment setup (secondary)'}
          </summary>
          <div className="mt-3">
            <Product2AuthoringPanel access={access} canManageAssessments={canManageAssessments} />
          </div>
        </details>
      ) : null}

      {isSendTab ? (
        <AssessmentsSectionProfiler id="send">
          <Card
            className="border-transparent bg-wf-accent-assess-soft text-wf-accent-assess-ink shadow-[0_10px_28px_rgba(74,36,56,0.06)]"
            tone="board"
          >
            <CardHeader className="mb-4 border-b border-black/5 pb-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle className="text-inherit">{queueCopy.title}</CardTitle>
                  <CardDescription className="text-inherit opacity-75">{queueCopy.description}</CardDescription>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5" role="tablist" aria-label={isAr ? 'مجموعات الإرسال' : 'Send cohorts'}>
                {cohortTabs.map((tab) => {
                  const active = normalizeAssessmentCohortKey(cohortKey) === tab.key
                    || (tab.key === 'assessment_resend_needed' && normalizeAssessmentCohortKey(cohortKey) === 'assessment_expired')
                  const count = peopleFor(tab.key)
                  return (
                    <button
                      key={tab.key}
                      onClick={() => selectCohort(tab.key)}
                      role="tab"
                      aria-selected={active}
                      type="button"
                      className={
                        active
                          ? 'rounded-full bg-wf-ink px-3 py-1.5 text-sm font-semibold text-white'
                          : 'rounded-full bg-white/50 px-3 py-1.5 text-sm text-inherit hover:bg-white/75'
                      }
                    >
                      {assessmentCohortChipLabel(locale, tab.key)}
                      {` (${count})`}
                    </button>
                  )
                })}
              </div>
            </CardHeader>
            <CardContent>
              {queueError ? (
                <EmptyState text={isAr ? 'تعذّر تحميل قائمة الإرسال.' : 'Could not load the send queue.'} />
              ) : queueLoading && !queue.length ? (
                <div className="flex items-center gap-2 text-sm text-inherit opacity-75">
                  <Loader2 className="animate-spin" size={16} />
                  {isAr ? 'جاري التحميل…' : 'Loading…'}
                </div>
              ) : queue.length ? (
                <div className="overflow-x-auto rounded-[1.2rem] bg-white/55">
                  {queue.map((application) => {
                    const action = queuePrimaryAction(
                      application.assessment_cohort || cohortKey,
                      application.assessment_allowed_actions || application.allowed_actions,
                    )
                    const delivery = application.assessment?.delivery_status
                    const stateRaw = application.assessment?.status || application.status
                    return (
                      <SendRow
                        applicationContact={application.candidate?.email || application.phone}
                        applicationName={candidateName(application)}
                        deliveryLabel={
                          delivery
                            ? `${isAr ? 'التسليم' : 'Delivery'}: ${assessmentStatusLabel(locale, delivery)}`
                            : undefined
                        }
                        disabled={busy || !enabled || !canManageAssessments}
                        job={application.position?.title || application.position?.code || '—'}
                        key={application.app_key}
                        locale={locale}
                        onPrimary={() => {
                          dashboardPerfMarkInteractionStart('assessments_row_action', { action })
                          if (action === 'send') onSendAssessment(application)
                          else if (action === 'resend') onResendAssessment(application)
                          else {
                            const attempt = attempts.find((item) => item.app_key === application.app_key)
                            if (attempt) openWorkspace(attempt)
                            else selectTab('attempts')
                          }
                          dashboardPerfMarkNetworkComplete('assessments_row_action', { action })
                        }}
                        primaryLabel={
                          action === 'send'
                            ? assessmentCopy(locale, 'send_assessment')
                            : action === 'resend'
                              ? assessmentCopy(locale, 'resend_assessment')
                              : assessmentCopy(locale, 'open_attempt')
                        }
                        secondaryActions={[
                          {
                            label: isAr ? 'فتح في المرشحين' : 'Open in Candidates',
                            action: onOpenFollowUpCandidates,
                          },
                        ]}
                        stateLabel={assessmentStatusLabel(locale, stateRaw)}
                      />
                    )
                  })}
                </div>
              ) : (
                <EmptyState text={enabled ? queueCopy.empty : (isAr ? 'التقييمات غير مفعّلة لهذه الشركة.' : 'Assessments are not enabled for this company.')} />
              )}
              {queue.length && (queueHasMore || pendingCount > queue.length) ? (
                <div className="mt-3 space-y-2">
                  {queueHasMore ? (
                    <LoadMoreBar
                      loaded={queue.length}
                      loading={queueLoadingMore}
                      noun={isAr ? 'مرشح' : 'candidate'}
                      onLoadMore={() => {
                        dashboardPerfMarkInteractionStart('assessments_pagination', { kind: 'load_more' })
                        onLoadMoreQueue?.()
                        dashboardPerfMarkNetworkComplete('assessments_pagination', { kind: 'load_more' })
                      }}
                      total={Math.max(pendingCount, queue.length)}
                    />
                  ) : (
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-inherit opacity-80">
                      <span>
                        {isAr
                          ? `عرض ${queue.length} من ${pendingCount} في هذه المجموعة.`
                          : `Showing ${queue.length} of ${pendingCount} in this cohort.`}
                      </span>
                      <Button onClick={onOpenFollowUpCandidates} size="sm" variant="secondary">
                        {isAr ? 'فتح الكل في المرشحين' : 'Open all in Candidates'}
                      </Button>
                    </div>
                  )}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </AssessmentsSectionProfiler>
      ) : null}

      {isAttemptsTab ? (
        <AssessmentsSectionProfiler id="attempts">
          <Card
            className={
              isNeedsReviewTab
                ? 'border-transparent bg-wf-accent-review-soft text-wf-accent-review-ink shadow-[0_10px_28px_rgba(61,52,16,0.06)]'
                : undefined
            }
            tone="board"
          >
            <CardHeader className={isNeedsReviewTab ? 'mb-4 border-b border-black/5 pb-4' : undefined}>
              <CardTitle className={isNeedsReviewTab ? 'text-inherit' : 'text-[#23211d]'}>
                {isNeedsReviewTab ? assessmentCopy(locale, 'needs_review') : (isAr ? 'المحاولات الأخيرة' : 'Recent attempts')}
                {total ? ` (${total})` : ''}
              </CardTitle>
              <CardDescription className={isNeedsReviewTab ? 'text-inherit opacity-75' : 'text-[#716a5e]'}>
                {isNeedsReviewTab
                  ? (isAr
                    ? 'محاولات مكتملة بانتظار مراجعة الموارد البشرية (نفس شرط العدّ في الواجهة الخلفية).'
                    : 'Completed attempts awaiting HR review (same backend predicate as the Needs review count).')
                  : (isAr
                    ? 'كل المحاولات التاريخية ضمن نطاق ظهورك — بما فيها الملغاة والمنتهية.'
                    : 'Every historical attempt under your visibility scope — including cancelled and superseded expired.')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {attemptsError ? (
                <EmptyState text={isAr ? 'تعذّر تحميل المحاولات.' : 'Could not load attempts.'} />
              ) : attemptsLoading && !attempts.length ? (
                <div className="flex items-center gap-2 text-sm text-[#716a5e]">
                  <Loader2 className="animate-spin" size={16} />
                  {isAr ? 'جاري التحميل…' : 'Loading…'}
                </div>
              ) : attempts.length ? (
                <div className={`overflow-x-auto rounded-[1.2rem] ${isNeedsReviewTab ? 'bg-white/55' : 'border border-[#e8dfd0] bg-white/40'}`}>
                  {attempts.map((attempt) => (
                    <AttemptRow
                      attempt={attempt}
                      busy={busy}
                      canManage={canManageAssessments}
                      key={attempt.attempt_id}
                      locale={locale}
                      onCancel={() => onCancelAttempt(attempt)}
                      onMarkReviewed={() => onReviewAttempt(attempt)}
                      onOpen={() => openWorkspace(attempt)}
                      onResend={() => onResendAttempt(attempt)}
                      onViewReport={() => void openReport(attempt)}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  text={
                    isNeedsReviewTab
                      ? (isAr ? 'لا توجد تقييمات تحتاج مراجعة.' : 'No assessments need review.')
                      : (isAr ? 'لا توجد محاولات تقييم بعد.' : 'No assessment attempts yet.')
                  }
                />
              )}
              {total ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-[#716a5e]">
                  <div>
                    {isAr
                      ? `عرض ${offset + 1}-${Math.min(offset + attempts.length, total)} من ${total}`
                      : `Showing ${offset + 1}-${Math.min(offset + attempts.length, total)} of ${total}`}
                  </div>
                  <div className="flex gap-2">
                    <Button disabled={!canGoBack} onClick={() => setPageOffset(Math.max(0, offset - limit))} size="sm" variant="secondary">
                      {isAr ? 'السابق' : 'Previous'}
                    </Button>
                    <Button disabled={!canGoNext} onClick={() => setPageOffset(offset + limit)} size="sm" variant="secondary">
                      {isAr ? 'التالي' : 'Next'}
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </AssessmentsSectionProfiler>
      ) : null}

      {isReportsTab ? (
        <AssessmentsSectionProfiler id="reports">
          <Card tone="board">
            <CardHeader>
              <CardTitle className="text-[#23211d]">
                {assessmentCopy(locale, 'reports')}
                {reportReadyCount ? ` (${reportReadyCount})` : ''}
              </CardTitle>
              <CardDescription className="text-[#716a5e]">
                {isAr
                  ? `تقارير مكتملة ضمن نفس النطاق (${reportReadyCount} جاهز).`
                  : `Completed reports under the same scoped total (${reportReadyCount} ready).`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {attemptsError ? (
                <EmptyState text={isAr ? 'تعذّر تحميل التقارير.' : 'Could not load reports.'} />
              ) : attemptsLoading && !attempts.length ? (
                <div className="flex items-center gap-2 text-sm text-[#716a5e]">
                  <Loader2 className="animate-spin" size={16} />
                  {isAr ? 'جاري التحميل…' : 'Loading…'}
                </div>
              ) : attempts.length ? (
                <div className="overflow-x-auto rounded-[1.35rem] border border-[#e8dfd0] bg-white/40">
                  {attempts.map((attempt) => (
                    <ReportRow attempt={attempt} key={attempt.attempt_id} locale={locale} onViewReport={() => void openReport(attempt)} />
                  ))}
                </div>
              ) : (
                <EmptyState text={isAr ? 'لا توجد تقارير تقييم مكتملة بعد.' : 'No completed assessment reports yet.'} />
              )}
              {total ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-[#716a5e]">
                  <div>
                    {isAr
                      ? `عرض ${offset + 1}-${Math.min(offset + attempts.length, total)} من ${total}`
                      : `Showing ${offset + 1}-${Math.min(offset + attempts.length, total)} of ${total}`}
                  </div>
                  <div className="flex gap-2">
                    <Button disabled={!canGoBack} onClick={() => setPageOffset(Math.max(0, offset - limit))} size="sm" variant="secondary">
                      {isAr ? 'السابق' : 'Previous'}
                    </Button>
                    <Button disabled={!canGoNext} onClick={() => setPageOffset(offset + limit)} size="sm" variant="secondary">
                      {isAr ? 'التالي' : 'Next'}
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </AssessmentsSectionProfiler>
      ) : null}

      {enabled && config && canSeeSetup ? (
        <details
          className="rounded-2xl border border-[#e8dfd0] bg-[#fffaf0]/85 p-4"
          data-testid="assessment-configuration"
        >
          <summary
            className="cursor-pointer list-none marker:content-none [&::-webkit-details-marker]:hidden"
            data-testid="assessment-configuration-summary"
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[#23211d]">
                  {isAr ? 'إعداد التقييم' : 'Assessment configuration'}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium text-[#716a5e]">
                  <span data-testid="assessment-configuration-ready">{setupReadyLabel}</span>
                  <span aria-hidden className="opacity-40">·</span>
                  <span data-testid="assessment-configuration-questions">{questionsLabel}</span>
                  <span aria-hidden className="opacity-40">·</span>
                  <span data-testid="assessment-configuration-evidence">{evidenceLabel}</span>
                  <span aria-hidden className="opacity-40">·</span>
                  <span data-testid="assessment-configuration-refreshed">{lastRefreshedLabel}</span>
                </div>
              </div>
              <div className="shrink-0 text-xs font-semibold text-[#8a8274]">
                {isAr ? 'التفاصيل للإداريين' : 'Admin details'}
              </div>
            </div>
          </summary>
          <div className="mt-4 border-t border-[#e8dfd0]/80 pt-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="text-sm leading-6 text-[#716a5e]">
                {isAr
                  ? 'التفاصيل التقنية متاحة لمسؤولي الموارد البشرية للتحقق من المعايرة وتغطية المحتوى.'
                  : 'Technical details are available for HR admins who need to check assessment calibration and content coverage.'}
              </div>
              <Button disabled={busy || !canManageAssessments} onClick={onRecalculateNorms} size="sm" variant="secondary">
                {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} {isAr ? 'تحديث الإعداد' : 'Refresh setup'}
              </Button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="assessment-configuration-details">
              <Info label={isAr ? 'الأسئلة' : 'Questions'} value={`${itemBank?.total_items ?? questionCount} items`} />
              <Info label={isAr ? 'مجالات الدليل' : 'Evidence areas'} value={`${competencyCount} indicators`} />
              <Info label={isAr ? 'ملفات التوافق' : 'Fit profiles'} value={`${roleProfileCount} profiles`} />
              <Info label={isAr ? 'المعايرة' : 'Calibration'} value={setupCalibrationLabel(config.norms?.status)} />
              <Info
                label={isAr ? 'فحص المحتوى' : 'Content check'}
                value={itemBank?.validation?.ok ? (isAr ? 'جاهز' : 'Looks ready') : `${itemBank?.validation?.error_count || 0} issues`}
              />
              <Info label={isAr ? 'مصدر المحتوى' : 'Content source'} value={itemBank?.content_policy ? stageLabel(itemBank.content_policy) : 'Wathefni items'} />
              <Info label={isAr ? 'إصدار الإعداد' : 'Setup version'} value={config.norms?.active_norm_version || (isAr ? 'غير محدد' : 'Not set')} />
              <Info
                label={isAr ? 'البطارية' : 'Battery'}
                value={`${batteryName} ${batteryVersion} · ${sections}`}
              />
            </div>
          </div>
        </details>
      ) : null}

      {selectedAttempt ? (
        <AssessmentAttemptWorkspace
          attempt={selectedAttempt}
          locale={locale}
          onClose={() => setSelectedAttempt(null)}
          onViewReport={() => void openReport(selectedAttempt)}
          sendResult={lastSendResult}
        />
      ) : null}
      {reportAttempt ? (
        <AssessmentReportPage
          attempt={reportAttempt}
          busy={busy}
          loadError={reportError}
          loading={reportLoading}
          locale={locale}
          onClose={() => {
            setReportAttempt(null)
            setReportPresentation(null)
            setReportError(false)
            setReportLoading(false)
          }}
          onMarkReviewed={() => onReviewAttempt(reportAttempt)}
          presentation={reportPresentation}
        />
      ) : null}
    </div>
  )
}
