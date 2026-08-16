import type { PrehireRoleNextStep, PrehireRolePriority, PrehireWorkQueueItem, PositionSummary } from '@/types'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'

/** Prefer backend person_key; fall back to legacy action×app identity. */
export function workQueueItemKey(
  item: Pick<PrehireWorkQueueItem, 'person_key' | 'action_type' | 'app_key' | 'position_code'>,
): string {
  const person = String(item.person_key || '').trim()
  if (person) return `person:${person}`
  const action = String(item.action_type || '').trim()
  const appKey = String(item.app_key || '').trim()
  const fallback = String(item.position_code || '').trim()
  return `${action}:${appKey || fallback}`
}

/**
 * Trust backend person-first rows. Only collapse exact duplicate person_keys
 * if a stale client still receives duplicates — never invent business counts.
 */
export function dedupeWorkQueueItems(items: PrehireWorkQueueItem[]): PrehireWorkQueueItem[] {
  const best = new Map<string, PrehireWorkQueueItem>()
  const order: string[] = []
  for (const item of items) {
    const key = workQueueItemKey(item)
    if (!key || key.endsWith(':') || key === 'person:') continue
    const prev = best.get(key)
    if (!prev) {
      best.set(key, item)
      order.push(key)
      continue
    }
    if (Number(item.priority || 0) > Number(prev.priority || 0)) {
      best.set(key, item)
    }
  }
  return order.map((key) => best.get(key)!)
}

/** Prefer backend total (people). Do not invent business math from FE. */
export function workQueueDisplayTotal(apiTotal: number | undefined, rawCount: number, uniqueCount: number): number {
  if (typeof apiTotal === 'number' && Number.isFinite(apiTotal)) return Math.max(0, apiTotal)
  return uniqueCount || rawCount
}

export type OverviewMetricDisplay = {
  /** Primary numeric display (people / person-queue rows). */
  primary: number
  /** Visible unit under the number, e.g. "people". */
  unitLabel: string
  /**
   * Secondary applications hint when company summary publishes a different
   * application count. Null when applications are unknown or equal to people
   * (no need to imply two different totals are the same).
   */
  applicationsHint: string | null
}

/**
 * Company-summary attention metrics are people-first. When applications differ,
 * surface both so Overview never equates 2 people with 4 applications.
 * My-work personalized counts are person-queue rows — applications stay null.
 */
export function formatOverviewPeopleMetric(
  locale: RecruitingLocale,
  people: number,
  applications?: number | null,
): OverviewMetricDisplay {
  const count = Math.max(0, Number(people) || 0)
  const apps =
    applications == null || !Number.isFinite(Number(applications))
      ? null
      : Math.max(0, Number(applications))
  const unitLabel =
    count === 1
      ? recruitingCopy(locale, 'overviewPeopleUnitOne')
      : recruitingCopy(locale, 'overviewPeopleUnit')
  const applicationsHint =
    apps != null && apps !== count
      ? recruitingCopy(locale, 'overviewApplicationsHint', { count: apps })
      : null
  return { primary: count, unitLabel, applicationsHint }
}

/** Work-queue footer: always label the total as people. */
export function formatWorkQueueShownTotal(
  locale: RecruitingLocale,
  shown: number,
  totalPeople: number,
): string {
  return recruitingCopy(locale, 'overviewWorkQueueShownTotal', {
    shown: Math.max(0, shown),
    total: Math.max(0, totalPeople),
  })
}

export function roleDisplayCount(role?: PrehireRolePriority | PrehireRoleNextStep | null): number {
  if (!role) return 0
  if (typeof role.display_count === 'number') return role.display_count
  if (typeof role.people_count === 'number') return role.people_count
  if (typeof role.active_people === 'number') return role.active_people
  return Number(role.application_count || role.active_count || 0)
}

export function roleSignalDetail(role: PrehireRolePriority | PrehireRoleNextStep, locale: RecruitingLocale): string {
  if (role.reason) return role.reason
  const signals = role.signals || {}
  const parts: string[] = []
  const follow = Number(signals.follow_up?.people || 0)
  const ready = Number(signals.ready_for_review?.people || 0)
  const pending = Number(signals.assessment_pending?.people || 0)
  if (locale === 'ar') {
    if (follow === 1) parts.push('مرشح واحد يحتاج متابعة')
    else if (follow > 1) parts.push(`${follow} مرشحين يحتاجون متابعة`)
    if (ready === 1) parts.push('مرشح واحد جاهز للمراجعة')
    else if (ready > 1) parts.push(`${ready} مرشحين جاهزين للمراجعة`)
    if (pending === 1) parts.push('مرشح واحد يحتاج انتباه التقييم')
    else if (pending > 1) parts.push(`${pending} مرشحين يحتاجون انتباه التقييم`)
  } else {
    if (follow === 1) parts.push('1 candidate needs follow-up')
    else if (follow > 1) parts.push(`${follow} candidates need follow-up`)
    if (ready === 1) parts.push('1 ready for review')
    else if (ready > 1) parts.push(`${ready} ready for review`)
    if (pending === 1) parts.push('1 needs assessment attention')
    else if (pending > 1) parts.push(`${pending} need assessment attention`)
  }
  return parts.join(locale === 'ar' ? ' · ' : '; ') || recruitingCopy(locale, 'overviewPrioritizeRoleEmpty')
}

export function roleBottleneckLabel(
  job: PositionSummary | PrehireRoleNextStep,
  locale: RecruitingLocale,
  assessmentEnabled = true,
): string {
  const nextStep = 'next_step_label' in job ? String(job.next_step_label || '') : ''
  if (nextStep) return nextStep
  const stageCounts = ('stage_counts' in job ? job.stage_counts : undefined) || []
  if (!stageCounts.length) {
    return Number(('application_count' in job ? job.application_count : 0) || 0)
      ? recruitingCopy(locale, 'overviewRoleOpenList')
      : recruitingCopy(locale, 'overviewRoleNoApplicants')
  }
  const sorted = [...stageCounts].sort((a, b) => Number(b.count || 0) - Number(a.count || 0))
  const top = sorted[0]
  const count = Number(top?.count || 0)
  if (!top || !count) return recruitingCopy(locale, 'overviewRoleNoUrgent')
  if (top.status === 'screening') {
    return count === 1
      ? recruitingCopy(locale, 'overviewRoleHelpScreeningOne')
      : recruitingCopy(locale, 'overviewRoleHelpScreening', { count })
  }
  if (top.status === 'screening_complete' || top.status === 'review_pending' || top.status === 'ready_for_review') {
    return count === 1
      ? recruitingCopy(locale, 'overviewRoleReviewOne')
      : recruitingCopy(locale, 'overviewRoleReview', { count })
  }
  if (top.status === 'shortlisted') {
    if (assessmentEnabled) {
      return count === 1
        ? recruitingCopy(locale, 'overviewRolePlanInterviewAssessmentOne')
        : recruitingCopy(locale, 'overviewRolePlanInterviewAssessment', { count })
    }
    return count === 1
      ? recruitingCopy(locale, 'overviewRolePlanInterviewOne')
      : recruitingCopy(locale, 'overviewRolePlanInterview', { count })
  }
  return count === 1
    ? recruitingCopy(locale, 'overviewRoleMoveForwardOne')
    : recruitingCopy(locale, 'overviewRoleMoveForward', { count })
}

export function roleActiveBadge(count: number, locale: RecruitingLocale): string {
  return recruitingCopy(locale, 'overviewRoleActiveCount', { count: Number(count || 0) })
}

export function overviewMetricApplicationsHint(
  locale: RecruitingLocale,
  people: number,
  applications?: number,
): string {
  const apps = Number(applications || 0)
  if (!apps || apps === people) return ''
  return locale === 'ar' ? `${apps} طلبات` : `${apps} applications`
}
