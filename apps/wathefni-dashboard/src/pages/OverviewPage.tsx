import { CheckCircle2, Circle, Loader2, RefreshCw } from 'lucide-react'
import { startTransition, useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { HrAttentionRow } from '@/components/hr/HrAttentionRow'
import { HrDestinationButton } from '@/components/hr/HrDestinationButton'
import { HrMetricTile } from '@/components/hr/HrMetricTile'
import { HrPageHeader } from '@/components/hr/HrPageHeader'
import { HrSection } from '@/components/hr/HrSection'
import { OverviewCalendarPanel } from '@/components/OverviewCalendarPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { dashboardPerfMarkInteractionStart } from '@/lib/perf/dashboardPerf'
import {
  dedupeWorkQueueItems,
  formatOverviewPeopleMetric,
  formatWorkQueueShownTotal,
  roleDisplayCount,
  roleSignalDetail,
} from '@/lib/prehireOverviewPresentation'
import { overviewActionGridClass, type OverviewLayoutMode } from '@/lib/workspaceCapability'
import {
  useActionInboxQuery,
  useIntelligenceOverviewQuery,
  usePrefetchOppositeWorkScope,
  useWorkQueueQuery,
} from '@/lib/query/hooks'
import { qk } from '@/lib/query/keys'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { ResourceState } from '@/pages/shared/dataState'
import { DashboardApiError } from '@/lib/api'
import type { IntelligenceMetric } from '@/lib/intelligenceApi'
import type {
  ActionInboxItem,
  DashboardAccess,
  Page,
  PrehireNextAction,
  PrehireRoleNextStep,
  PrehireRolePriority,
  PrehireWorkQueueItem,
  SetupReadinessResponse,
} from '@/types'

const CURRENT_INTELLIGENCE = new Set(['ok'])
const SIGNAL_FAMILY_ORDER = ['workforce', 'time_leave', 'hiring']
const SKIP_SIGNAL_FAMILIES = new Set(['pay'])
const SKIP_PERMISSION_CLASSES = new Set(['payroll_money', 'talent_sensitive'])

export function SetupReadinessCard({
  readiness,
  onAction,
}: {
  readiness: SetupReadinessResponse
  onAction: (page: Page) => void
}) {
  const steps = Array.isArray(readiness.steps) ? readiness.steps : []
  const remaining = steps.filter((step) => !step.done && !step.optional).length
  return (
    <HrSection
      description={
        remaining > 0
          ? `${remaining} step${remaining === 1 ? '' : 's'} left before your HR team can run day-to-day on OctoHR — here is what to do next, and why.`
          : 'A couple of optional recommendations to get the most out of OctoHR.'
      }
      title="Get your workspace ready"
    >
      <div className="space-y-3">
        {steps.map((step) => (
          <div
            key={step.key}
            className="flex flex-col gap-3 rounded-2xl border border-semantic-line bg-semantic-surface-raised p-4 sm:flex-row sm:items-center"
          >
            {step.done ? (
              <CheckCircle2 className="mt-0.5 shrink-0 text-semantic-success" size={20} />
            ) : (
              <Circle className="mt-0.5 shrink-0 text-semantic-mist" size={20} />
            )}
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-semantic-ink">{step.title}</span>
                {step.optional ? <Badge tone="muted">Recommended</Badge> : null}
              </div>
              <p className="mt-1 text-[13px] leading-6 text-semantic-subtle">{step.why}</p>
            </div>
            {!step.done ? (
              <Button onClick={() => onAction(step.action_page as Page)} variant="secondary">
                {step.action_label}
              </Button>
            ) : null}
          </div>
        ))}
      </div>
    </HrSection>
  )
}

function greetingHourInTimezone(timeZone?: string | null): number {
  const resolved =
    (timeZone && String(timeZone).trim())
    || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : '')
    || undefined
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      hour: 'numeric',
      hour12: false,
      ...(resolved ? { timeZone: resolved } : {}),
    }).formatToParts(new Date())
    const raw = Number(parts.find((part) => part.type === 'hour')?.value)
    if (!Number.isFinite(raw)) return new Date().getHours()
    return raw === 24 ? 0 : raw
  } catch {
    return new Date().getHours()
  }
}

function greetingFirstName(displayName?: string | null) {
  const cleaned = String(displayName || '').trim().replace(/\s+/g, ' ')
  if (!cleaned) return ''
  return cleaned.split(' ')[0] || ''
}

function personalizedOverviewGreeting(locale: RecruitingLocale, displayName?: string | null, timeZone?: string | null) {
  const isAr = locale === 'ar'
  const firstName = greetingFirstName(displayName)
  if (!firstName) return isAr ? 'مرحباً بعودتك' : 'Welcome back'
  const hour = greetingHourInTimezone(timeZone)
  if (hour >= 5 && hour < 12) return isAr ? `صباح الخير، ${firstName}` : `Good morning, ${firstName}`
  if (hour >= 12 && hour < 17) return isAr ? `طاب يومك، ${firstName}` : `Good afternoon, ${firstName}`
  return isAr ? `مساء الخير، ${firstName}` : `Good evening, ${firstName}`
}

function streamLabel(stream: string, isAr: boolean) {
  if (stream === 'analytics') return isAr ? 'التحليلات' : 'Analytics'
  if (stream === 'compliance') return isAr ? 'الامتثال' : 'Compliance'
  if (stream === 'employees') return isAr ? 'الموظفون' : 'Employees'
  return stream
}

function intelligenceIsCurrent(metric: IntelligenceMetric) {
  const status = String(metric.status || '')
  return metric.ok !== false && CURRENT_INTELLIGENCE.has(status)
}

function intelligenceGateOff(error: unknown) {
  if (!(error instanceof DashboardApiError)) return false
  const code = String(error.code || '')
  return (
    code.includes('intelligence_surfaces')
    || code === 'c1_registry_required'
    || code === 'c1_company_entitlement_required'
  )
}

function pickOverviewSignals(metrics: IntelligenceMetric[], isAr: boolean) {
  const ranked = [...metrics].sort((a, b) => {
    const ai = SIGNAL_FAMILY_ORDER.indexOf(String(a.family || ''))
    const bi = SIGNAL_FAMILY_ORDER.indexOf(String(b.family || ''))
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi)
  })
  const picked: IntelligenceMetric[] = []
  for (const metric of ranked) {
    const family = String(metric.family || metric.about_metric?.family || '')
    const permissionClass = String(metric.about_metric?.permission_class || '')
    if (SKIP_SIGNAL_FAMILIES.has(family) || SKIP_PERMISSION_CLASSES.has(permissionClass)) continue
    picked.push(metric)
    if (picked.length >= 4) break
  }
  return picked.map((metric) => {
    const current = intelligenceIsCurrent(metric)
    const name = isAr
      ? (metric.about_metric?.name_ar || metric.semantic_key)
      : (metric.about_metric?.name_en || metric.semantic_key)
    return { metric, current, name }
  })
}

export function OverviewPage({
  access,
  assessmentEnabled,
  busy,
  onRefresh,
  userDisplayName,
  timeZone,
  readyForReviewTotal,
  readyForReviewApplications,
  assessmentPendingTotal,
  assessmentPendingApplications,
  assessmentPrimary,
  followUpNeededTotal,
  followUpNeededApplications,
  nextAction: _nextAction,
  rolePriority,
  roleNextSteps,
  canViewCompanyWorkHint = false,
  locale,
  onLocaleChange,
  onOpenCandidate: _onOpenCandidate,
  onOpenFollowUps,
  onOpenPendingAssessments,
  onOpenReadyForReview,
  onOpenRolePriority,
  onOpenRoleRanking: _onOpenRoleRanking,
  onOpenDestination,
  onOpenRoleCandidates,
  onOpenInbox,
  onOpenInboxItem,
  calendarAccess,
  calendarEnabled = false,
  onOpenCalendar,
  canManageWorkspace = false,
  setupReadiness,
  onOpenSetupAction,
  overviewLayout = 'three' as OverviewLayoutMode,
  overviewPrioritySurfaces,
  showWorkQueue = false,
  showRolePriority = false,
  showApprovals = false,
  showSignals = false,
  showHiringMetrics = false,
}: {
  access: DashboardAccess
  assessmentEnabled: boolean
  busy: boolean
  onRefresh: () => void
  userDisplayName?: string | null
  timeZone?: string | null
  overviewPrioritySurfaces?: string[]
  readyForReviewTotal?: number
  readyForReviewApplications?: number
  assessmentPendingTotal?: number
  assessmentPendingApplications?: number
  assessmentPrimary?: {
    action?: string
    cohort_key?: string
    label?: string
    people_count?: number
    application_count?: number
    destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string }
  } | null
  followUpNeededTotal?: number
  followUpNeededApplications?: number
  nextAction?: PrehireNextAction | null
  rolePriority?: PrehireRolePriority | null
  roleNextSteps?: PrehireRoleNextStep[]
  canViewCompanyWorkHint?: boolean
  locale: RecruitingLocale
  onLocaleChange: (locale: RecruitingLocale) => void
  onOpenCandidate: (appKey?: string) => void
  onOpenFollowUps: () => void
  onOpenPendingAssessments: () => void
  onOpenReadyForReview: () => void
  onOpenRolePriority: () => void
  onOpenRoleRanking: () => void
  onOpenDestination: (destination?: { page?: string; filters?: Record<string, string>; cohort_key?: string } | null) => void
  onOpenRoleCandidates: (job: { position_code?: string; position_title?: string }) => void
  onOpenInbox?: () => void
  onOpenInboxItem?: (item: ActionInboxItem) => void
  calendarAccess?: DashboardAccess
  calendarEnabled?: boolean
  onOpenCalendar?: () => void
  canManageWorkspace?: boolean
  setupReadiness?: SetupReadinessResponse | null
  onOpenSetupAction?: (page: Page) => void
  overviewLayout?: OverviewLayoutMode
  showWorkQueue?: boolean
  showRolePriority?: boolean
  showApprovals?: boolean
  showSignals?: boolean
  showHiringMetrics?: boolean
}) {
  void _onOpenCandidate
  void _onOpenRoleRanking
  void _nextAction

  const queryClient = useQueryClient()
  const [workQueueScope, setWorkQueueScope] = useState<'mine' | 'company'>(() => {
    try {
      const stored = localStorage.getItem('wathefni_work_queue_scope')
      if (stored === 'company' && canViewCompanyWorkHint) return 'company'
      if (stored === 'mine' || stored === 'company') return stored === 'company' && !canViewCompanyWorkHint ? 'mine' : (stored as 'mine' | 'company')
    } catch {
      /* ignore */
    }
    return 'mine'
  })
  const workQueueQuery = useWorkQueueQuery(access, workQueueScope, showWorkQueue)
  const workQueue = workQueueQuery.data ?? null
  const workQueueRefreshing = workQueueQuery.isFetching && Boolean(workQueueQuery.data)
  const workQueueLoading = showWorkQueue && workQueueQuery.isPending && !workQueueQuery.data
  const workQueueError = showWorkQueue && workQueueQuery.isError && !workQueueQuery.data
  const canViewCompanyWork = Boolean(
    workQueue?.can_view_company_work
    ?? canViewCompanyWorkHint,
  )

  const inboxQuery = useActionInboxQuery(access, showApprovals)
  const inbox = inboxQuery.data ?? null
  const inboxRefreshing = inboxQuery.isFetching && Boolean(inboxQuery.data)
  const inboxLoading = showApprovals && inboxQuery.isPending && !inboxQuery.data
  const inboxError = showApprovals && inboxQuery.isError && !inboxQuery.data

  const intelligenceQuery = useIntelligenceOverviewQuery(access, locale, showSignals)
  const intelligence = intelligenceQuery.data ?? null
  const intelligenceRefreshing = intelligenceQuery.isFetching && Boolean(intelligenceQuery.data)
  const intelligenceLoading = showSignals && intelligenceQuery.isPending && !intelligenceQuery.data
  const intelligenceUnavailable = showSignals && intelligenceQuery.isError && intelligenceGateOff(intelligenceQuery.error)
  const intelligenceError = showSignals && intelligenceQuery.isError && !intelligenceQuery.data && !intelligenceUnavailable
  const signalTiles = useMemo(() => {
    if (!intelligence?.ok) return []
    const metrics = (intelligence.families || []).flatMap((family) =>
      (family.metrics || []).map((metric) => ({ ...metric, family: metric.family || family.family })),
    )
    return pickOverviewSignals(metrics, locale === 'ar')
  }, [intelligence, locale])

  usePrefetchOppositeWorkScope(access, workQueueScope, Boolean(workQueue))

  useEffect(() => {
    if (workQueue?.can_view_company_work === false && workQueueScope === 'company') {
      setWorkQueueScope('mine')
    }
  }, [workQueue?.can_view_company_work, workQueueScope])

  const onWorkQueueScopeChange = useCallback((next: 'mine' | 'company') => {
    if (next === workQueueScope) return
    dashboardPerfMarkInteractionStart('work-queue-scope')
    try {
      localStorage.setItem('wathefni_work_queue_scope', next)
    } catch {
      /* ignore */
    }
    startTransition(() => setWorkQueueScope(next))
  }, [workQueueScope])

  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) => recruitingCopy(locale, key, vars)
  const isAr = locale === 'ar'
  const personalized = workQueueScope === 'mine' && workQueue?.counts
  const reviewCount = Number(
    personalized ? (workQueue?.counts?.ready_for_review ?? 0) : (readyForReviewTotal || 0),
  )
  const followUpCount = Number(
    personalized ? (workQueue?.counts?.follow_up ?? 0) : (followUpNeededTotal || 0),
  )
  const assessmentPeople = Number(
    personalized
      ? (workQueue?.counts?.assessment ?? 0)
      : (assessmentPrimary?.people_count ?? assessmentPendingTotal ?? 0),
  )
  // Company summary publishes people + applications. My-work personalized counts
  // are person-queue rows only — do not invent application totals for them.
  const reviewMetric = formatOverviewPeopleMetric(
    locale,
    reviewCount,
    personalized ? null : readyForReviewApplications,
  )
  const followUpMetric = formatOverviewPeopleMetric(
    locale,
    followUpCount,
    personalized ? null : followUpNeededApplications,
  )
  const assessmentMetric = formatOverviewPeopleMetric(
    locale,
    assessmentPeople,
    personalized
      ? null
      : (assessmentPrimary?.application_count ?? assessmentPendingApplications),
  )
  const assessmentAction = String(assessmentPrimary?.action || '')
  const assessmentLabel = assessmentAction === 'assessment_resend_needed'
    ? (isAr ? 'إعادة إرسال التقييمات' : 'Resend assessments')
    : assessmentAction === 'assessment_delivery_failed'
      ? (isAr ? 'متابعة فشل التسليم' : 'Fix delivery failures')
      : assessmentAction === 'assessment_in_progress'
        ? (isAr ? 'متابعة التقييمات الجارية' : 'Check in-progress assessments')
        : (isAr ? 'إرسال التقييمات' : 'Send assessments')
  const queueItems = workQueueLoading || workQueueError ? [] : dedupeWorkQueueItems(workQueue?.items || [])
  const people = queueItems.slice(0, 5)
  const roles = (roleNextSteps || [])
    .filter((role) => roleDisplayCount(role) > 0)
    .filter((role) => !rolePriority || role.position_code !== rolePriority.position_code)
    .slice(0, 5)

  const metricTiles = showHiringMetrics
    ? ([
        reviewCount > 0 && (!overviewPrioritySurfaces || overviewPrioritySurfaces.includes('overview.action.review'))
          ? {
              key: 'review',
              metric: reviewMetric,
              title: isAr ? 'مراجعة المرشحين' : 'Review candidates',
              srLabel: 'Review ready candidates',
              onClick: onOpenReadyForReview,
            }
          : null,
        assessmentEnabled &&
        assessmentPeople > 0 &&
        (!overviewPrioritySurfaces || overviewPrioritySurfaces.includes('overview.action.assessment'))
          ? {
              key: 'assessment',
              metric: assessmentMetric,
              title: assessmentLabel,
              srLabel: 'Send pending assessments',
              onClick: () => {
                if (assessmentPrimary?.destination) onOpenDestination(assessmentPrimary.destination)
                else onOpenPendingAssessments()
              },
            }
          : null,
        followUpCount > 0 && (!overviewPrioritySurfaces || overviewPrioritySurfaces.includes('overview.action.followup'))
          ? {
              key: 'followup',
              metric: followUpMetric,
              title: isAr ? 'متابعة المرشحين' : 'Follow up',
              srLabel: 'Follow up with candidates',
              onClick: onOpenFollowUps,
            }
          : null,
      ].filter(Boolean) as Array<{
        key: string
        metric: ReturnType<typeof formatOverviewPeopleMetric>
        title: string
        srLabel?: string
        onClick: () => void
      }>)
    : []

  const inboxPeek = !inboxLoading && !inboxError ? (inbox?.items || []).slice(0, 5) : []
  const inboxTotal = typeof inbox?.summary?.total === 'number' ? inbox.summary.total : null
  const inboxStreamTiles = Object.entries(inbox?.summary?.by_stream || {})
    .filter(([, count]) => Number(count) > 0)
    .map(([stream, count]) => ({
      key: `stream:${stream}`,
      title: streamLabel(stream, isAr),
      primary: Number(count),
    }))

  const personAction = (item: PrehireWorkQueueItem) => {
    if (item.next_action) return item.next_action
    const type = String(item.action_type || '')
    if (type.includes('follow')) return isAr ? 'متابعة' : 'Follow up'
    if (type.includes('assessment')) return isAr ? 'إرسال التقييم' : 'Send assessment'
    if (type.includes('interview_feedback') || type === 'interview_feedback') return isAr ? 'إرسال الملاحظات' : 'Submit feedback'
    if (type.includes('interview')) return isAr ? 'جدولة مقابلة' : 'Schedule interview'
    if (type.includes('overdue')) return isAr ? 'إكمال المهمة' : 'Complete task'
    if (type.includes('approval')) return isAr ? 'موافقة' : 'Approve'
    return isAr ? 'مراجعة المرشح' : 'Review candidate'
  }

  const dueStateLabel = (state?: string) => {
    if (state === 'overdue') return isAr ? 'متأخر' : 'Overdue'
    if (state === 'due_soon') return isAr ? 'قريب الاستحقاق' : 'Due soon'
    return isAr ? 'مفتوح' : 'Open'
  }

  const sourceLabel = (source?: string) => {
    const key = String(source || '')
    if (key === 'application_owner') return isAr ? 'مالك الطلب' : 'Application owner'
    if (key === 'job_recruiter') return isAr ? 'مسؤول التوظيف' : 'Job recruiter'
    if (key === 'job_hiring_manager') return isAr ? 'مدير التوظيف' : 'Hiring manager'
    if (key === 'interview_assignment') return isAr ? 'تعيين مقابلة' : 'Interview assignment'
    if (key === 'task_assignee') return isAr ? 'مهمة مسندة' : 'Task assignee'
    if (key === 'approval_assignee') return isAr ? 'موافقة مسندة' : 'Approval assignee'
    if (key === 'company_ops') return isAr ? 'تشغيل الشركة' : 'Company operations'
    return key || (isAr ? 'مصدر غير معروف' : 'Unknown source')
  }

  const today = new Intl.DateTimeFormat(isAr ? 'ar-KW' : 'en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    ...(timeZone ? { timeZone } : {}),
  }).format(new Date())
  const prioritySignals = rolePriority
    ? roleSignalDetail(rolePriority, locale).split(/[;·]/).map((part) => part.trim()).filter(Boolean).slice(0, 3)
    : []

  const greeting = personalizedOverviewGreeting(locale, userDisplayName, timeZone)
  const showSetupReadiness = canManageWorkspace
    && setupReadiness
    && !setupReadiness.ready
    && Array.isArray(setupReadiness.steps)
    && setupReadiness.steps.length > 0
  const showAttention = showWorkQueue || (showRolePriority && Boolean(rolePriority || roles.length))
  const showApprovalsBand = showApprovals && (inboxLoading || inboxError || inboxPeek.length > 0 || (inboxTotal != null && inboxTotal > 0))
  const showSignalsBand = showSignals && !intelligenceUnavailable && (intelligenceLoading || intelligenceError || signalTiles.length > 0)
  const showMetricsBand = metricTiles.length > 0 || inboxStreamTiles.length > 0

  const refreshOverview = () => {
    onRefresh()
    void queryClient.invalidateQueries({ queryKey: qk.workQueue(access, workQueueScope) })
    void queryClient.invalidateQueries({ queryKey: qk.actionInbox(access) })
    void queryClient.invalidateQueries({ queryKey: qk.intelligenceOverview(access, locale) })
    void queryClient.invalidateQueries({ queryKey: qk.calendarOverview(access, 'mine') })
  }

  return (
    <div className="mx-auto max-w-[1480px] space-y-4" dir={isAr ? 'rtl' : 'ltr'}>
      {showSetupReadiness && onOpenSetupAction ? (
        <SetupReadinessCard readiness={setupReadiness} onAction={onOpenSetupAction} />
      ) : null}

      <HrPageHeader
        actions={(
          <>
            <span className="rounded-full bg-semantic-accent-soft px-3.5 py-2 text-xs font-medium text-semantic-subtle">{today}</span>
            <HrDestinationButton disabled={busy} onClick={refreshOverview} size="md">
              {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
              {isAr ? 'تحديث' : 'Refresh'}
            </HrDestinationButton>
            <Button className="rounded-full" onClick={() => onLocaleChange(isAr ? 'en' : 'ar')} type="button" variant="ghost">
              {t('language')}
            </Button>
          </>
        )}
        description={isAr ? 'الصفحة الرئيسية لشركتك في OctoHR.' : 'Your company home in OctoHR.'}
        dir={isAr ? 'rtl' : 'ltr'}
        eyebrow={isAr ? 'نظرة عامة' : 'Overview'}
        title={greeting}
      />
      <h3 className="sr-only">What needs attention today</h3>
      <h3 className="sr-only">Suggested next action</h3>
      <span className="sr-only">Review ready candidates</span>
      <span className="sr-only">Follow up with candidates</span>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
        <div className="space-y-4">
          {showAttention ? (
            <div className="space-y-4">
              {showRolePriority && rolePriority ? (
                <HrSection
                  className="bg-semantic-success-soft"
                  testId="overview-role-priority"
                  title={isAr ? 'ضغط الدور' : 'Role pressure'}
                  trailing={(
                    <HrDestinationButton onClick={onOpenRolePriority}>
                      {isAr ? 'مراجعة الوظيفة' : 'Review role'}
                    </HrDestinationButton>
                  )}
                >
                  <div data-overview-role-priority>
                    <h2 className="text-xl font-semibold tracking-[-0.045em] text-semantic-success-ink">
                      {rolePriority.position_title || rolePriority.position_code}
                    </h2>
                    <div className="mt-3 space-y-1.5">
                      {prioritySignals.length ? (
                        prioritySignals.map((signal) => (
                          <div className="text-sm text-semantic-success-ink/80" key={signal}>{signal}</div>
                        ))
                      ) : (
                        <div className="text-sm text-semantic-success-ink/80">
                          {roleSignalDetail(rolePriority, locale) || (isAr ? 'تحتاج هذه الوظيفة انتباهًا.' : 'This role needs attention.')}
                        </div>
                      )}
                    </div>
                    {roles.length ? (
                      <div className="mt-4 border-t border-semantic-line/70 pt-3">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="text-xs font-semibold text-semantic-subtle">{isAr ? 'وظائف أخرى' : 'More roles'}</div>
                          <button
                            className="text-xs font-semibold text-semantic-subtle underline-offset-4 hover:underline"
                            onClick={() => onOpenDestination({ page: 'jobs' })}
                            type="button"
                          >
                            {isAr ? 'عرض الكل' : 'View all'}
                          </button>
                        </div>
                        <div className="space-y-2">
                          {roles.map((role) => {
                            const detail = roleSignalDetail(role, locale)
                            return (
                              <button
                                className="flex w-full items-center justify-between gap-3 rounded-[1rem] py-1 text-start"
                                key={role.position_code}
                                onClick={() => {
                                  if (role.destination) onOpenDestination(role.destination)
                                  else onOpenRoleCandidates(role)
                                }}
                                type="button"
                              >
                                <div className="min-w-0">
                                  <div className="truncate text-[13px] font-semibold text-semantic-ink">{role.position_title || role.position_code}</div>
                                  {detail ? <div className="mt-0.5 line-clamp-2 text-[11px] text-semantic-subtle">{detail}</div> : null}
                                </div>
                                <span className="text-semantic-mist">{isAr ? '←' : '→'}</span>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </HrSection>
              ) : showRolePriority && roles.length ? (
                <HrSection
                  testId="overview-role-priority"
                  title={isAr ? 'وظائف تحتاج انتباهًا' : 'Roles needing attention'}
                  trailing={(
                    <button
                      className="text-xs font-semibold text-semantic-subtle underline-offset-4 hover:underline"
                      onClick={() => onOpenDestination({ page: 'jobs' })}
                      type="button"
                    >
                      {isAr ? 'عرض الكل' : 'View all'}
                    </button>
                  )}
                >
                  <div className="space-y-2" data-overview-role-priority>
                    {roles.map((role) => {
                      const detail = roleSignalDetail(role, locale)
                      return (
                        <button
                          className="flex w-full items-center justify-between gap-3 rounded-[1rem] py-1 text-start"
                          key={role.position_code}
                          onClick={() => {
                            if (role.destination) onOpenDestination(role.destination)
                            else onOpenRoleCandidates(role)
                          }}
                          type="button"
                        >
                          <div className="min-w-0">
                            <div className="truncate text-[13px] font-semibold text-semantic-ink">{role.position_title || role.position_code}</div>
                            {detail ? <div className="mt-0.5 line-clamp-2 text-[11px] text-semantic-subtle">{detail}</div> : null}
                          </div>
                          <span className="text-semantic-mist">{isAr ? '←' : '→'}</span>
                        </button>
                      )
                    })}
                  </div>
                </HrSection>
              ) : null}

              {showWorkQueue ? (
                <HrSection
                  cold={workQueueLoading}
                  coldFallback={(
                    <ResourceState
                      kind="loading"
                      locale={locale}
                      testId="overview-work-loading"
                      title={t('overviewWorkLoading')}
                    />
                  )}
                  description={
                    workQueueScope === 'company'
                      ? (isAr ? 'أولويات تشغيلية على مستوى الشركة' : 'Company-wide operational priorities')
                      : (isAr ? 'ما أنت مسؤول عنه فقط' : 'Only what you are responsible for')
                  }
                  refreshing={workQueueRefreshing}
                  refreshingLabel={isAr ? 'جاري التحديث' : 'Refreshing'}
                  testId="overview-work-queue"
                  title={workQueueScope === 'company' ? (isAr ? 'عمل الشركة' : 'Company work') : (isAr ? 'عملي' : 'My work')}
                  trailing={canViewCompanyWork ? (
                    <div className="inline-flex items-center gap-2">
                      <div className="inline-flex rounded-full border border-semantic-line bg-semantic-surface-raised p-0.5" role="group" aria-label={isAr ? 'نطاق العمل' : 'Work scope'}>
                        <button
                          className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors duration-150 ${workQueueScope === 'mine' ? 'bg-semantic-ink text-white' : 'text-semantic-subtle'}`}
                          onClick={() => onWorkQueueScopeChange('mine')}
                          type="button"
                        >
                          {isAr ? 'عملي' : 'My work'}
                        </button>
                        <button
                          className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors duration-150 ${workQueueScope === 'company' ? 'bg-semantic-ink text-white' : 'text-semantic-subtle'}`}
                          onClick={() => onWorkQueueScopeChange('company')}
                          type="button"
                        >
                          {isAr ? 'عمل الشركة' : 'Company work'}
                        </button>
                      </div>
                      {workQueueRefreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin text-semantic-subtle" aria-label={isAr ? 'جاري التحديث' : 'Refreshing'} /> : null}
                    </div>
                  ) : null}
                >
                  <div className="space-y-2" data-overview-work-queue>
                    <h3 className="sr-only">Top priorities</h3>
                    {workQueueError ? (
                      <ResourceState
                        detail={t('overviewWorkLoadErrorDetail')}
                        kind="error"
                        locale={locale}
                        onRetry={() => void workQueueQuery.refetch()}
                        retrying={workQueueQuery.isFetching}
                        testId="overview-work-error"
                        title={t('overviewWorkLoadError')}
                      />
                    ) : people.length ? (
                      people.map((item) => {
                        const apps = item.applications || []
                        const appCount = Math.max(apps.length, Number(item.application_count || 0))
                        return (
                          <HrAttentionRow
                            actionLabel={item.destination?.page ? personAction(item) : undefined}
                            detail={(
                              <>
                                {item.reason}
                                {appCount > 1
                                  ? ` · ${recruitingCopy(locale, 'overviewApplicationsHint', { count: appCount })}`
                                  : ''}
                              </>
                            )}
                            key={item.entity_id || item.person_key || `${item.action_type}-${item.app_key}`}
                            meta={[
                              { label: isAr ? 'المالك' : 'Owner', value: item.owner || (isAr ? 'غير معيّن' : 'Unassigned') },
                              { label: isAr ? 'الاستحقاق' : 'Due', value: dueStateLabel(item.due_state) },
                              { label: isAr ? 'الإجراء التالي' : 'Next', value: personAction(item) },
                              { label: isAr ? 'المصدر' : 'Source', value: sourceLabel(item.source) },
                            ]}
                            onAction={item.destination?.page ? () => onOpenDestination(item.destination) : undefined}
                            title={item.candidate_name || item.job_label || item.position_title || (isAr ? 'مهمة' : 'Task')}
                          />
                        )
                      })
                    ) : (
                      <ResourceState
                        kind="empty"
                        locale={locale}
                        testId="overview-work-empty"
                        title={
                          workQueueScope === 'company'
                            ? (isAr ? 'لا توجد أولويات على مستوى الشركة الآن.' : 'No company-wide priorities right now.')
                            : (isAr ? 'لا يوجد عمل مسند إليك الآن.' : 'No personal work assigned to you right now.')
                        }
                      />
                    )}
                    {typeof workQueue?.total === 'number' && !workQueueError && !workQueueLoading ? (
                      <div className="mt-2 px-1 text-[11px] text-semantic-mist">
                        {formatWorkQueueShownTotal(locale, people.length, workQueue.total)}
                      </div>
                    ) : null}
                  </div>
                </HrSection>
              ) : null}
            </div>
          ) : null}

          {showApprovalsBand ? (
            <HrSection
              cold={inboxLoading}
              coldFallback={(
                <ResourceState kind="loading" locale={locale} testId="overview-approvals-loading" title={isAr ? 'جاري التحميل…' : 'Loading…'} />
              )}
              description={isAr ? 'عناصر Needs Attention كما نشرها النظام.' : 'Needs Attention items as published by the system.'}
              refreshing={inboxRefreshing}
              refreshingLabel={isAr ? 'جاري التحديث' : 'Refreshing'}
              testId="overview-approvals"
              title={isAr ? 'الموافقات والانتباه' : 'Approvals'}
              trailing={onOpenInbox ? (
                <button className="text-xs font-semibold text-semantic-subtle underline-offset-4 hover:underline" onClick={onOpenInbox} type="button">
                  {isAr ? 'فتح الصندوق' : 'Open inbox'}
                </button>
              ) : null}
            >
              {inboxError ? (
                <ResourceState
                  kind="error"
                  locale={locale}
                  onRetry={() => void inboxQuery.refetch()}
                  retrying={inboxQuery.isFetching}
                  testId="overview-approvals-error"
                  title={isAr ? 'تعذّر تحميل صندوق الانتباه' : 'Could not load Needs Attention'}
                />
              ) : inboxPeek.length ? (
                <div className="space-y-2">
                  {inboxTotal != null ? (
                    <div className="px-1 text-[11px] text-semantic-mist">
                      {isAr ? `${inboxTotal} عنصر` : `${inboxTotal} items`}
                    </div>
                  ) : null}
                  {inboxPeek.map((item) => (
                    <HrAttentionRow
                      actionLabel={item.deep_link?.page ? (isAr ? 'فتح' : 'Open') : undefined}
                      detail={isAr ? (item.why_ar || item.why_en) : item.why_en}
                      key={item.id}
                      meta={[
                        { label: isAr ? 'المالك' : 'Owner', value: (isAr ? item.owner_label_ar : item.owner_label_en) || item.owner_role || (isAr ? 'غير معيّن' : 'Unassigned') },
                        { label: isAr ? 'الاستحقاق' : 'Due', value: (isAr ? item.deadline_label_ar : item.deadline_label_en) || item.deadline || (isAr ? 'مفتوح' : 'Open') },
                        { label: isAr ? 'المصدر' : 'Source', value: streamLabel(String(item.source_stream || item.source_module || ''), isAr) },
                      ]}
                      onAction={item.deep_link?.page ? () => onOpenInboxItem?.(item) : undefined}
                      title={(isAr ? item.what_ar : item.what_en) || item.what_en}
                    />
                  ))}
                </div>
              ) : (
                <ResourceState
                  kind="empty"
                  locale={locale}
                  testId="overview-approvals-empty"
                  title={isAr ? 'لا توجد عناصر انتباه الآن.' : 'No attention items right now.'}
                />
              )}
            </HrSection>
          ) : null}
        </div>

        <div className="space-y-4">
          {showMetricsBand ? (
            <HrSection testId="overview-metrics" title={isAr ? 'مؤشرات رئيسية' : 'Key metrics'}>
              <section className={overviewActionGridClass(overviewLayout, metricTiles.length + inboxStreamTiles.length)} data-overview-layout={overviewLayout}>
                {metricTiles.map((card) => (
                  <HrMetricTile
                    hint={card.metric.applicationsHint}
                    key={card.key}
                    label={card.title}
                    onClick={card.onClick}
                    primary={card.metric.primary}
                    srLabel={card.srLabel}
                    unitLabel={card.metric.unitLabel}
                  />
                ))}
                {inboxStreamTiles.map((tile) => (
                  <HrMetricTile
                    key={tile.key}
                    label={tile.title}
                    onClick={onOpenInbox}
                    primary={tile.primary}
                    unitLabel={isAr ? 'عناصر' : 'items'}
                  />
                ))}
              </section>
            </HrSection>
          ) : null}

          {showSignalsBand ? (
            <HrSection
              cold={intelligenceLoading}
              coldFallback={(
                <ResourceState kind="loading" locale={locale} testId="overview-signals-loading" title={isAr ? 'جاري التحميل…' : 'Loading…'} />
              )}
              description={isAr ? 'إشارات موجزة من التحليلات. التفاصيل في صفحة التحليلات.' : 'Concise signals from Analytics. Drilldowns stay on Analytics.'}
              refreshing={intelligenceRefreshing}
              refreshingLabel={isAr ? 'جاري التحديث' : 'Refreshing'}
              testId="overview-signals"
              title={isAr ? 'إشارات القوى العاملة' : 'Workforce signals'}
              trailing={(
                <button className="text-xs font-semibold text-semantic-subtle underline-offset-4 hover:underline" onClick={() => onOpenDestination({ page: 'analytics' })} type="button">
                  {isAr ? 'التحليلات' : 'Analytics'}
                </button>
              )}
            >
              {intelligenceError ? (
                <ResourceState
                  kind="error"
                  locale={locale}
                  onRetry={() => void intelligenceQuery.refetch()}
                  retrying={intelligenceQuery.isFetching}
                  testId="overview-signals-error"
                  title={isAr ? 'تعذّر تحميل الإشارات' : 'Could not load workforce signals'}
                />
              ) : signalTiles.length ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {signalTiles.map(({ metric, current, name }) => (
                    <HrMetricTile
                      current={current}
                      hint={current ? metric.unit || null : null}
                      key={metric.semantic_key}
                      label={name}
                      onClick={() => onOpenDestination({ page: 'analytics' })}
                      primary={current ? metric.value : undefined}
                      statusLabel={metric.status_label}
                    />
                  ))}
                </div>
              ) : (
                <ResourceState
                  kind="empty"
                  locale={locale}
                  testId="overview-signals-empty"
                  title={isAr ? 'لا توجد إشارات منشورة الآن.' : 'No published signals right now.'}
                />
              )}
            </HrSection>
          ) : null}

          {calendarAccess && calendarEnabled && onOpenCalendar ? (
            <OverviewCalendarPanel
              access={calendarAccess}
              calendarEnabled={calendarEnabled}
              locale={locale}
              onAddEvent={onOpenCalendar}
              onOpenCalendar={onOpenCalendar}
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}
