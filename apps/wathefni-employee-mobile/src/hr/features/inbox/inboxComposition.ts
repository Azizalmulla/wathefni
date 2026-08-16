import type { PriorityItem, PrioritySection } from '@hr/api/types'
import { hrHomeStatusKey, sectionLabelKey } from '@hr/features/home/homeParityComposition'
import { ambient, scheduleComposition } from '@/theme'

export type InboxDecisionRow = {
  key: string
  sectionType: string
  item: PriorityItem
}

/** Flatten Inbox allowlist sections in server order — no invented ranking. */
export function flattenInboxDecisions(sections: PrioritySection[]): InboxDecisionRow[] {
  const out: InboxDecisionRow[] = []
  for (const section of sections) {
    for (const item of section.items) {
      if (!item.destination) continue
      out.push({
        key: `${section.type}:${item.type}:${item.target_id}`,
        sectionType: section.type,
        item,
      })
    }
  }
  return out
}

export function groupInboxDecisions(
  rows: InboxDecisionRow[],
): { sectionType: string; labelKey: string; rows: InboxDecisionRow[]; accentColor: string }[] {
  const order: string[] = []
  const map = new Map<string, InboxDecisionRow[]>()
  for (const row of rows) {
    if (!map.has(row.sectionType)) {
      order.push(row.sectionType)
      map.set(row.sectionType, [])
    }
    map.get(row.sectionType)!.push(row)
  }
  return order.map((sectionType) => ({
    sectionType,
    labelKey: sectionLabelKey(sectionType),
    rows: map.get(sectionType) || [],
    accentColor: inboxAccentForSection(sectionType),
  }))
}

/**
 * Left accent bar — Wathefni pastels by decision family (never ink/black).
 * yellow onboarding/tasks · green leave/docs · pink attendance · blue swaps
 */
export function inboxAccentForSection(sectionType: string): string {
  switch (sectionType) {
    case 'leave_approvals':
      return ambient.leave.fill
    case 'onboarding_reviews':
      return ambient.onboarding.fill
    case 'attendance_exceptions':
      return ambient.schedule.fill
    case 'document_reviews':
      return ambient.documents.fill
    case 'shift_swap_decisions':
      return scheduleComposition.planned.fill
    case 'hr_tasks':
      return ambient.payslips.fill
    default:
      return ambient.onboarding.fill
  }
}

/** Secondary line: warm status · optional severity — never raw snake_case alone. */
export function inboxDecisionBody(
  item: PriorityItem,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  const status = t(hrHomeStatusKey(item.status))
  const severity = String(item.severity || '').trim().toLowerCase()
  if (severity === 'high') return `${status} · ${t('hrHome.statusUrgent')}`
  return status
}

export const INBOX_DECISION_PAGE = 15

/**
 * Server maximum for `/dashboard/mobile/priorities`. Home and Inbox share one
 * cache entry, so both must request the same window.
 */
export const PRIORITIES_LIMIT = 30
