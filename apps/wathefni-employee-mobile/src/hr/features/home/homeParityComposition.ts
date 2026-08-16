import type { PriorityItem, PrioritySection } from '@hr/api/types'
import { HOME_VISIBLE_ITEM_CAP } from '@hr/shell/ia'

export type FlatPriority = {
  section: PrioritySection
  item: PriorityItem
}

export function flattenPriorities(sections: PrioritySection[]): FlatPriority[] {
  const out: FlatPriority[] = []
  for (const section of sections) {
    for (const item of section.items) {
      if (!item.destination) continue
      out.push({ section, item })
    }
  }
  return out
}

/** Prefer conflict/high severity leave, else first item — no invented ranking beyond server order + severity flag. */
export function pickHero(items: FlatPriority[]): FlatPriority | null {
  if (!items.length) return null
  const urgent = items.find(
    (entry) =>
      entry.item.severity === 'high' ||
      (entry.section.type === 'leave_approvals' && entry.item.severity),
  )
  return urgent || items[0]
}

/**
 * How many decisions the company actually has waiting, not how many this
 * response happened to carry. The priorities endpoint returns a capped window
 * per section, so counting fetched items would let a busy Home look clear.
 */
export function serverPriorityTotal(sections: PrioritySection[]): number {
  return sections.reduce((sum, section) => {
    const reported = Number(section.total ?? section.items.length) || 0
    return sum + Math.max(reported, section.items.length)
  }, 0)
}

export function splitHomePriorities(sections: PrioritySection[]): {
  hero: FlatPriority | null
  rows: FlatPriority[]
  overflow: number
  total: number
} {
  const flat = flattenPriorities(sections)
  const hero = pickHero(flat)
  const rest = hero
    ? flat.filter((entry) => entry.item.target_id !== hero.item.target_id || entry.item.type !== hero.item.type)
    : flat
  const rowBudget = Math.max(0, HOME_VISIBLE_ITEM_CAP - (hero ? 1 : 0))
  const rows = rest.slice(0, rowBudget)
  const total = Math.max(serverPriorityTotal(sections), flat.length)
  const shown = rows.length + (hero ? 1 : 0)
  return { hero, rows, overflow: Math.max(0, total - shown), total }
}

export function sectionLabelKey(sectionType: string): string {
  switch (sectionType) {
    case 'leave_approvals':
      return 'hrHome.sectionLeave'
    case 'onboarding_reviews':
      return 'hrHome.sectionOnboarding'
    case 'attendance_exceptions':
      return 'hrHome.sectionAttendance'
    case 'hr_tasks':
      return 'hrHome.sectionTasks'
    case 'document_reviews':
      return 'hrHome.sectionDocuments'
    case 'shift_swap_decisions':
      return 'hrHome.sectionSwaps'
    default:
      return 'hrHome.waitingSection'
  }
}

export function iconForSection(
  sectionType: string,
): 'umbrella-outline' | 'ribbon-outline' | 'calendar-outline' | 'checkbox-outline' | 'document-text-outline' | 'swap-horizontal-outline' | 'ellipse-outline' {
  switch (sectionType) {
    case 'leave_approvals':
      return 'umbrella-outline'
    case 'onboarding_reviews':
      return 'ribbon-outline'
    case 'attendance_exceptions':
      return 'calendar-outline'
    case 'hr_tasks':
      return 'checkbox-outline'
    case 'document_reviews':
      return 'document-text-outline'
    case 'shift_swap_decisions':
      return 'swap-horizontal-outline'
    default:
      return 'ellipse-outline'
  }
}

/** Provisional ambient family for warmth — not frozen HR semantics. */
export function ambientForSection(
  sectionType: string,
): 'schedule' | 'leave' | 'documents' | 'onboarding' | 'payslips' {
  switch (sectionType) {
    case 'leave_approvals':
      return 'leave'
    case 'onboarding_reviews':
      return 'onboarding'
    case 'attendance_exceptions':
      return 'schedule'
    case 'document_reviews':
      return 'documents'
    case 'shift_swap_decisions':
      return 'schedule'
    case 'hr_tasks':
      return 'payslips'
    default:
      return 'documents'
  }
}

/** Warm Home phrasing — never surface snake_case or clinical enum chrome. */
export function hrHomeStatusKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'not_started':
      return 'hrHome.statusReady'
    case 'requested':
    case 'pending':
    case 'open':
      return 'hrHome.statusNeedsDecision'
    case 'in_progress':
    case 'processing':
    case 'submitted':
    case 'received':
      return 'hrHome.statusInReview'
    case 'completed':
    case 'approved':
    case 'reviewed':
    case 'accepted':
      return 'hrHome.statusDone'
    case 'high':
    case 'late':
    case 'lateness':
    case 'absent':
    case 'absence':
    case 'early_leave':
    case 'missing_check_in':
    case 'missing_check_out':
    case 'incomplete_session':
    case 'needs_hr_action':
    case 'rejected':
    case 'blocked':
    case 'replacement_required':
      return 'hrHome.statusUrgent'
    default:
      return 'hrHome.statusNeedsDecision'
  }
}

/**
 * Progress chip tone for trailing StatusChips.
 * Colour semantics live only on chips (row icons stay neutral ink):
 * yellow = action/review · blue = in progress · pink = correction/blocked · green = done
 */
export function hrHomeProgressTone(
  status: string | null | undefined,
): 'yellow' | 'blue' | 'pink' | 'green' {
  switch ((status || '').trim().toLowerCase()) {
    case 'requested':
    case 'pending':
    case 'open':
    case 'not_started':
    case 'needs_review':
    case 'needs_info':
      return 'yellow'
    case 'high':
    case 'late':
    case 'lateness':
    case 'absent':
    case 'absence':
    case 'early_leave':
    case 'missing_check_in':
    case 'missing_check_out':
    case 'incomplete_session':
    case 'needs_hr_action':
    case 'rejected':
    case 'blocked':
    case 'replacement_required':
      return 'pink'
    case 'completed':
    case 'approved':
    case 'reviewed':
    case 'accepted':
      return 'green'
    case 'in_progress':
    case 'processing':
    case 'submitted':
    case 'received':
    default:
      return 'blue'
  }
}
