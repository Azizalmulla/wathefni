import type { PositionSummary, PrehireWorkQueueItem } from '@/types'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'

/** Canonical work-queue identity: same application + same action → one row. */
export function workQueueItemKey(item: Pick<PrehireWorkQueueItem, 'action_type' | 'app_key' | 'position_code'>): string {
  const action = String(item.action_type || '').trim()
  const appKey = String(item.app_key || '').trim()
  const fallback = String(item.position_code || '').trim()
  return `${action}:${appKey || fallback}`
}

/**
 * Deduplicate by (action_type, app_key). Keeps the higher-priority row.
 * Distinct actions for the same application are preserved.
 * Separate applications for the same person are preserved.
 */
export function dedupeWorkQueueItems(items: PrehireWorkQueueItem[]): PrehireWorkQueueItem[] {
  const best = new Map<string, PrehireWorkQueueItem>()
  const order: string[] = []
  for (const item of items) {
    const key = workQueueItemKey(item)
    if (!key || key.endsWith(':')) continue
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

/** Keep API totals honest when a page still contained duplicate keys. */
export function workQueueDisplayTotal(apiTotal: number | undefined, rawCount: number, uniqueCount: number): number {
  const collapsed = Math.max(0, rawCount - uniqueCount)
  const base = Number(apiTotal || 0)
  if (base > 0) return Math.max(uniqueCount, Math.max(0, base - collapsed))
  return uniqueCount
}

export function roleBottleneckLabel(
  job: PositionSummary,
  locale: RecruitingLocale,
  assessmentEnabled = true,
): string {
  const stageCounts = job.stage_counts || []
  if (!stageCounts.length) {
    return Number(job.application_count || 0)
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
