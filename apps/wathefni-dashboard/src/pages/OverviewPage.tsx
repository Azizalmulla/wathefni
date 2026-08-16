import { CheckCircle2, Circle, Loader2, RefreshCw } from 'lucide-react'
import { startTransition, useCallback, useEffect, useState } from 'react'

import { OverviewCalendarPanel } from '@/components/OverviewCalendarPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dashboardPerfMarkInteractionStart } from '@/lib/perf/dashboardPerf'
import { dedupeWorkQueueItems, formatOverviewPeopleMetric, formatWorkQueueShownTotal, roleDisplayCount, roleSignalDetail } from '@/lib/prehireOverviewPresentation'
import { overviewActionGridClass, type OverviewLayoutMode } from '@/lib/workspaceCapability'
import { usePrefetchOppositeWorkScope, useWorkQueueQuery } from '@/lib/query/hooks'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { ResourceState } from '@/pages/shared/dataState'
import type {
  DashboardAccess,
  Page,
  PrehireNextAction,
  PrehireRoleNextStep,
  PrehireRolePriority,
  PrehireWorkQueueItem,
  SetupReadinessResponse,
} from '@/types'

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
    <Card className="border-[#e8c47d]/55 bg-[#fffaf0]/70">
      <CardHeader>
        <CardTitle>Get your workspace ready</CardTitle>
        <CardDescription>
          {remaining > 0
            ? `${remaining} step${remaining === 1 ? '' : 's'} left before your HR team can run day-to-day on Wathefni - here is what to do next, and why.`
            : 'A couple of optional recommendations to get the most out of Wathefni.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.map((step) => (
          <div
            key={step.key}
            className="flex flex-col gap-3 rounded-2xl border border-line/70 bg-panel/60 p-4 sm:flex-row sm:items-center"
          >
            {step.done ? (
              <CheckCircle2 className="mt-0.5 shrink-0 text-[#15803d]" size={20} />
            ) : (
              <Circle className="mt-0.5 shrink-0 text-mist" size={20} />
            )}
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-text">{step.title}</span>
                {step.optional ? <Badge tone="muted">Recommended</Badge> : null}
              </div>
              <p className="mt-1 text-[13px] leading-6 text-subtle/90">{step.why}</p>
            </div>
            {!step.done ? (
              <Button onClick={() => onAction(step.action_page as Page)} variant="secondary">
                {step.action_label}
              </Button>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
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
  calendarAccess?: DashboardAccess
  calendarEnabled?: boolean
  onOpenCalendar?: () => void
  canManageWorkspace?: boolean
  setupReadiness?: SetupReadinessResponse | null
  onOpenSetupAction?: (page: Page) => void
  overviewLayout?: OverviewLayoutMode
  showWorkQueue?: boolean
  showRolePriority?: boolean
}) {
  void _onOpenCandidate
  void _onOpenRoleRanking
  void _nextAction

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
  const totalAttention = reviewCount + followUpCount + assessmentPeople
  const queueItems = workQueueLoading || workQueueError ? [] : dedupeWorkQueueItems(workQueue?.items || [])
  const people = queueItems.slice(0, 5)
  const roles = (roleNextSteps || []).filter((role) => roleDisplayCount(role) > 0).slice(0, 5)

  const actionCards = [
    reviewCount > 0 && (!overviewPrioritySurfaces || overviewPrioritySurfaces.includes('overview.action.review'))
      ? {
          key: 'review',
          metric: reviewMetric,
          title: isAr ? 'مراجعة المرشحين' : 'Review candidates',
          srLabel: 'Review ready candidates',
          sentence: isAr ? 'مرشحون جاهزون لقرارك.' : 'Candidates are ready for your decision.',
          action: isAr ? 'مراجعة' : 'Review',
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
          sentence: isAr ? 'التقييمات تحتاج إجراء.' : 'Assessments need action.',
          action: isAr ? 'فتح' : 'Open',
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
          sentence: isAr ? 'بعض المرشحين لم يتم الوصول إليهم.' : 'Some candidates were not reached.',
          action: isAr ? 'متابعة' : 'Follow up',
          onClick: onOpenFollowUps,
        }
      : null,
  ].filter(Boolean) as Array<{
    key: string
    metric: ReturnType<typeof formatOverviewPeopleMetric>
    title: string
    sentence: string
    action: string
    srLabel?: string
    onClick: () => void
  }>

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

  const roleSentence = (role: PrehireRoleNextStep) => {
    const peopleCount = roleDisplayCount(role)
    const detail = roleSignalDetail(role, locale)
    if (detail && !/h\b|~\d+/.test(detail)) return detail
    if (peopleCount === 1) return isAr ? 'مرشح واحد نشط فقط. فكّر في ترويج هذه الوظيفة.' : 'Only 1 active candidate. Consider promoting this role.'
    return isAr ? `${peopleCount} مرشحون يحتاجون إجراء.` : `${peopleCount} candidates need action.`
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
  const roleActionLabel = (role: PrehireRoleNextStep) => {
    const detail = roleSignalDetail(role, locale).toLowerCase()
    if (detail.includes('assessment') || detail.includes('التقييم')) return isAr ? 'مراجعة التقييمات' : 'Check assessments'
    if (detail.includes('review') || detail.includes('مراجعة')) return isAr ? 'مراجعة الطلبات' : 'Review applications'
    return isAr ? 'عرض المرشحين' : 'View candidates'
  }

  const greeting = personalizedOverviewGreeting(locale, userDisplayName, timeZone)
  const actionPalette = [
    { card: 'bg-[#f1d96f]', ink: 'text-[#272319]' },
    { card: 'bg-[#e8acd0]', ink: 'text-[#2a2026]' },
    { card: 'bg-[#b4c9e5]', ink: 'text-[#202630]' },
  ]
  const peoplePalette = ['bg-[#efb9d7]', 'bg-[#b8cc98]', 'bg-[#aec7e8]', 'bg-[#efd46d]', 'bg-[#d8bee8]']
  const showSetupReadiness = canManageWorkspace
    && setupReadiness
    && !setupReadiness.ready
    && Array.isArray(setupReadiness.steps)
    && setupReadiness.steps.length > 0

  return (
    <div className="mx-auto max-w-[1480px] space-y-4" dir={isAr ? 'rtl' : 'ltr'}>
      {showSetupReadiness && onOpenSetupAction ? (
        <SetupReadinessCard readiness={setupReadiness} onAction={onOpenSetupAction} />
      ) : null}
      <header className="flex flex-wrap items-start justify-between gap-4 px-1 pb-2 pt-1">
        <div className="max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8f887b]">{isAr ? 'مساحة التوظيف' : 'Hiring workspace'}</div>
          <h1 className="mt-2 text-[2rem] font-semibold leading-none tracking-[-0.055em] text-[#211f1b] sm:text-[2.6rem]">{greeting}</h1>
          <p className="mt-2 text-sm text-[#777064]">
            {totalAttention > 0
              ? (isAr ? `${totalAttention} عناصر تحتاج انتباهك اليوم.` : `${totalAttention} item${totalAttention === 1 ? '' : 's'} need your attention today.`)
              : (isAr ? 'كل شيء يسير بشكل جيد اليوم.' : 'Everything is moving well today.')}
          </p>
          <h3 className="sr-only">What needs attention today</h3>
          <h3 className="sr-only">Suggested next action</h3>
          <span className="sr-only">Review ready candidates</span>
          <span className="sr-only">Follow up with candidates</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[#eee5d4] px-3.5 py-2 text-xs font-medium text-[#6e675b]">{today}</span>
          <button
            className="inline-flex h-9 items-center justify-center gap-2 rounded-full bg-[#23211d] px-3.5 text-sm font-semibold text-white hover:bg-black disabled:opacity-50"
            disabled={busy}
            onClick={onRefresh}
            type="button"
          >
            {busy ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
            {isAr ? 'تحديث' : 'Refresh'}
          </button>
          <Button className="rounded-full" onClick={() => onLocaleChange(isAr ? 'en' : 'ar')} type="button" variant="ghost">
            {t('language')}
          </Button>
        </div>
      </header>

      {actionCards.length ? (
        <section className={overviewActionGridClass(overviewLayout, actionCards.length)} data-overview-layout={overviewLayout}>
          {actionCards.map((card, index) => {
            const palette = actionPalette[index % actionPalette.length]
            return (
              <button
                className={`group min-h-[154px] overflow-hidden rounded-[1.45rem] p-4 text-start transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_16px_30px_rgba(35,33,29,0.12)] ${palette.card} ${palette.ink}`}
                key={card.key}
                onClick={card.onClick}
                type="button"
              >
                <div className="flex h-full flex-col justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] opacity-55">{card.title}</div>
                    <div className="mt-3 text-[2.4rem] font-semibold leading-none tracking-[-0.06em]">{card.metric.primary}</div>
                    <div className="mt-1.5 text-[11px] font-medium opacity-60">
                      {card.metric.unitLabel}
                      {card.metric.applicationsHint ? ` · ${card.metric.applicationsHint}` : ''}
                    </div>
                  </div>
                  <div className="mt-5 flex items-end justify-between gap-4">
                    <p className="max-w-[68%] text-xs leading-5 opacity-65">{card.sentence}</p>
                    <span className="rounded-full bg-[#23211d] px-3 py-1.5 text-[11px] font-semibold text-white">{card.action}</span>
                  </div>
                </div>
                {card.srLabel ? <span className="sr-only">{card.srLabel}</span> : null}
              </button>
            )
          })}
        </section>
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
        <div className="space-y-4">
          {showRolePriority && rolePriority ? (
            <section className="rounded-[1.55rem] bg-[#a9ba7d] p-5 text-[#202319] sm:p-6" data-overview-role-priority>
              <div className="flex min-h-[168px] flex-col justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-55">{isAr ? 'الأولوية التالية' : 'Next priority'}</div>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em]">{rolePriority.position_title || rolePriority.position_code}</h2>
                </div>
                <div className="mt-5 flex flex-wrap items-end justify-between gap-5">
                  <div className="space-y-1.5">
                    {prioritySignals.length ? (
                      prioritySignals.map((signal) => (
                        <div className="flex items-center gap-2 text-sm font-medium text-[#34372a]/80" key={signal}>
                          <span className="h-1.5 w-1.5 rounded-full bg-[#4d543b]" />
                          <span>{signal}</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-sm font-medium text-[#34372a]/80">{isAr ? 'تحتاج هذه الوظيفة انتباهًا.' : 'This role needs attention.'}</div>
                    )}
                  </div>
                  <button
                    className="inline-flex h-9 items-center justify-center rounded-full bg-[#23211d] px-4 text-sm font-semibold text-white hover:bg-black"
                    onClick={onOpenRolePriority}
                    type="button"
                  >
                    {isAr ? 'مراجعة الوظيفة' : 'Review role'}
                  </button>
                </div>
              </div>
            </section>
          ) : null}

          {showWorkQueue ? (
          <section className="rounded-[1.55rem] bg-[#fffaf0] p-4 shadow-[0_1px_0_rgba(255,255,255,0.8)_inset]" data-overview-work-queue>
            <div className="flex flex-wrap items-center justify-between gap-3 px-1 pb-3">
              <div>
                <h3 className="text-[15px] font-semibold tracking-[-0.025em] text-[#23211d]">
                  {workQueueScope === 'company'
                    ? (isAr ? 'عمل الشركة' : 'Company work')
                    : (isAr ? 'عملي' : 'My work')}
                </h3>
                <p className="mt-0.5 text-xs text-[#716a5e]">
                  {workQueueScope === 'company'
                    ? (isAr ? 'أولويات تشغيلية على مستوى الشركة' : 'Company-wide operational priorities')
                    : (isAr ? 'ما أنت مسؤول عنه فقط' : 'Only what you are responsible for')}
                </p>
                <h3 className="sr-only">Top priorities</h3>
              </div>
              <div className="flex items-center gap-2">
                {canViewCompanyWork ? (
                  <div className="inline-flex items-center gap-2">
                    <div className="inline-flex rounded-full border border-[#e8dfd0] bg-[#f8f3e9] p-0.5" role="group" aria-label={isAr ? 'نطاق العمل' : 'Work scope'}>
                      <button
                        className={`rounded-full px-3 py-1 text-xs font-semibold ${workQueueScope === 'mine' ? 'bg-[#23211d] text-white' : 'text-[#716a5e]'}`}
                        onClick={() => onWorkQueueScopeChange('mine')}
                        type="button"
                      >
                        {isAr ? 'عملي' : 'My work'}
                      </button>
                      <button
                        className={`rounded-full px-3 py-1 text-xs font-semibold ${workQueueScope === 'company' ? 'bg-[#23211d] text-white' : 'text-[#716a5e]'}`}
                        onClick={() => onWorkQueueScopeChange('company')}
                        type="button"
                      >
                        {isAr ? 'عمل الشركة' : 'Company work'}
                      </button>
                    </div>
                    {workQueueRefreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin text-[#716a5e]" aria-label={isAr ? 'جاري التحديث' : 'Refreshing'} /> : null}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="space-y-2">
              {workQueueLoading ? (
                <ResourceState
                  kind="loading"
                  locale={locale}
                  title={t('overviewWorkLoading')}
                  testId="overview-work-loading"
                />
              ) : workQueueError ? (
                <ResourceState
                  kind="error"
                  locale={locale}
                  title={t('overviewWorkLoadError')}
                  detail={t('overviewWorkLoadErrorDetail')}
                  onRetry={() => void workQueueQuery.refetch()}
                  retrying={workQueueQuery.isFetching}
                  testId="overview-work-error"
                />
              ) : people.length ? (
                people.map((item, index) => {
                  const apps = item.applications || []
                  const appCount = Math.max(apps.length, Number(item.application_count || 0))
                  return (
                    <div className="flex min-h-[60px] items-center justify-between gap-3 rounded-[1.1rem] border border-[#e8dfd0] bg-[#f8f3e9] px-3 py-2.5" key={item.entity_id || item.person_key || `${item.action_type}-${item.app_key}`}>
                      <div className="flex min-w-0 items-center gap-3">
                        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-bold text-[#23211d] ${peoplePalette[index % peoplePalette.length]}`}>
                          {String(item.candidate_name || item.position_title || item.job_label || 'C').trim().charAt(0).toUpperCase()}
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-[#23211d]">
                            {item.candidate_name || item.job_label || item.position_title || (isAr ? 'مهمة' : 'Task')}
                          </div>
                          <div className="truncate text-xs text-[#716a5e]">
                            {item.reason}
                            {appCount > 1
                              ? ` · ${recruitingCopy(locale, 'overviewApplicationsHint', { count: appCount })}`
                              : ''}
                          </div>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[#8a8274]">
                            <span>{isAr ? 'المالك' : 'Owner'}: {item.owner || (isAr ? 'غير معيّن' : 'Unassigned')}</span>
                            <span>{isAr ? 'الاستحقاق' : 'Due'}: {dueStateLabel(item.due_state)}</span>
                            <span>{isAr ? 'الإجراء التالي' : 'Next'}: {personAction(item)}</span>
                            <span>{isAr ? 'المصدر' : 'Source'}: {sourceLabel(item.source)}</span>
                          </div>
                        </div>
                      </div>
                      <button
                        className="shrink-0 rounded-full bg-[#23211d] px-3 py-1.5 text-xs font-semibold text-white"
                        onClick={() => onOpenDestination(item.destination)}
                        type="button"
                      >
                        {personAction(item)}
                      </button>
                    </div>
                  )
                })
              ) : (
                <ResourceState
                  kind="empty"
                  locale={locale}
                  title={
                    workQueueScope === 'company'
                      ? (isAr ? 'لا توجد أولويات على مستوى الشركة الآن.' : 'No company-wide priorities right now.')
                      : (isAr ? 'لا يوجد عمل مسند إليك الآن.' : 'No personal work assigned to you right now.')
                  }
                  testId="overview-work-empty"
                />
              )}
            </div>
            {typeof workQueue?.total === 'number' && !workQueueError && !workQueueLoading ? (
              <div className="mt-2 px-1 text-[11px] text-[#8a8274]">
                {formatWorkQueueShownTotal(locale, people.length, workQueue.total)}
              </div>
            ) : null}
          </section>
          ) : null}
        </div>

        <div className="space-y-4">
          {calendarAccess && calendarEnabled && onOpenCalendar ? (
            <OverviewCalendarPanel
              access={calendarAccess}
              locale={locale}
              calendarEnabled={calendarEnabled}
              onOpenCalendar={onOpenCalendar}
              onAddEvent={onOpenCalendar}
            />
          ) : null}
          {showRolePriority && roles.length ? (
            <section className="rounded-[1.55rem] bg-[#fffaf0] p-5">
              <div className="flex items-center justify-between gap-3 px-1 pb-3">
                <h3 className="text-[15px] font-semibold tracking-[-0.025em] text-[#23211d]">{isAr ? 'وظائف تحتاج انتباهًا' : 'Roles needing attention'}</h3>
                <button className="text-xs font-semibold text-[#716a5e] underline-offset-4 hover:underline" onClick={() => onOpenDestination({ page: 'jobs' })} type="button">
                  {isAr ? 'عرض الكل' : 'View all'}
                </button>
              </div>
              <div className="divide-y divide-[#ddd3c1]/70">
                {roles.map((role) => (
                  <button
                    className="group flex w-full items-center justify-between gap-3 py-3 text-start"
                    key={role.position_code}
                    onClick={() => {
                      if (role.destination) onOpenDestination(role.destination)
                      else onOpenRoleCandidates(role)
                    }}
                    type="button"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-[#23211d]">{role.position_title || role.position_code}</div>
                      <div className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-[#716a5e]">{roleSentence(role)}</div>
                    </div>
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#eee5d4] text-sm text-[#23211d] transition group-hover:bg-[#23211d] group-hover:text-white" aria-label={roleActionLabel(role)}>
                      {isAr ? '←' : '→'}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}
