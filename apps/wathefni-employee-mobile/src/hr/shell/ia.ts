/**
 * Provisional HR mobile IA — foundation contract.
 *
 * Tabs: Home · People · Inbox · Hiring · More
 * Authority: backend capabilities + /dashboard/mobile/priorities only.
 * No invented urgency. No module directory on Home.
 */

import type { MobileMe, PrioritySection } from '@hr/api/types'
import { hasAnyCapability, hasCapability } from '@hr/capabilities'

export type HrTabKey = 'home' | 'people' | 'inbox' | 'hiring' | 'more'

/** Decision-oriented priority sections eligible for Inbox (not a notification dump). */
export const INBOX_SECTION_TYPES = new Set([
  'leave_approvals',
  'onboarding_reviews',
  'attendance_exceptions',
  // Shift swaps are decided on detail routes; include if backend emits a section later.
  'shift_swap_decisions',
  // Document reviews when/if priorities emit them with review actions.
  'document_reviews',
  // Open HR follow-ups — same truth as Home / More Tasks.
  'hr_tasks',
])

/** Home attention feed — ops only; hiring stays on Hiring tab. */
export const HOME_SECTION_TYPES = new Set([
  'leave_approvals',
  'onboarding_reviews',
  'attendance_exceptions',
  'hr_tasks',
  'shift_swap_decisions',
  'document_reviews',
])

/** Hiring tab feed — recruiting cognitively separate from HR ops Inbox. */
export const HIRING_SECTION_TYPES = new Set([
  'prehire_priorities',
  'candidate_decisions',
  'requisitions_attention',
])

export const HOME_VISIBLE_ITEM_CAP = 6

export function tabPeopleEnabled(me: MobileMe | null): boolean {
  return hasAnyCapability(me, 'hr', ['employee_search', 'employee_quick_profile'])
}

export function tabInboxEnabled(me: MobileMe | null): boolean {
  return hasAnyCapability(me, 'hr', [
    'leave_approvals',
    'onboarding_review',
    'attendance_exceptions',
    'document_review',
    'shift_swap_decisions',
    'hr_tasks',
  ])
}

export function tabHiringEnabled(me: MobileMe | null): boolean {
  if (!me?.workspaces.recruiting?.enabled) return false
  return (
    hasAnyCapability(me, 'recruiting', [
      'candidate_rankings',
      'candidate_summary',
      'candidate_evidence',
      'interview_status',
      'interview_notes',
      'assessments',
      'employment_offers',
      'requisitions_review',
    ]) || hasCapability(me, 'recruiting', 'candidate_shortlist')
  )
}

export function filterPrioritySections(
  sections: PrioritySection[],
  allow: Set<string>,
): PrioritySection[] {
  return sections
    .filter((section) => allow.has(section.type))
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => Boolean(item.destination)),
    }))
    .filter((section) => section.items.length > 0 || section.total > 0)
}

/** AI Recruiter lives inside candidate review (rankings/evidence) — no extra root tab. */
export const AI_RECRUITER_IA_NOTE =
  'AI Recruiter surfaces via Candidates detail rankings/evidence; not a sixth root tab.'

/** Re-export More launcher authority — Hiring modules are not listed on More. */
export { moreLinksFor, moreModulesFor, MORE_MODULE_LINKS } from '@hr/features/more/moreLauncher'
export type { MoreModuleLink, MoreGroup } from '@hr/features/more/moreLauncher'
