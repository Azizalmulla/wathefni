/**
 * More — modular workspace launcher (not a dashboard).
 * Operations modules gated by company/user capabilities. Hiring lives on Hiring tab.
 */

import type { MobileMe } from '@hr/api/types'
import { hasAnyCapability } from '@hr/capabilities'

export type MoreGroup = 'operations' | 'account'

export type MoreModuleLink = {
  key:
    | 'assistant'
    | 'attendance'
    | 'shifts'
    | 'onboarding'
    | 'preboarding'
    | 'probation'
    | 'performance'
    | 'employee-relations'
    | 'requisitions'
    | 'documents'
    | 'tasks'
    | 'deliveryAlerts'
  path: string
  group: MoreGroup
  workspace: 'hr' | 'recruiting'
  features: string[]
  titleKey: string
  subtitleKey: string
  icon:
    | 'chatbubble-ellipses-outline'
    | 'calendar-outline'
    | 'time-outline'
    | 'ribbon-outline'
    | 'walk-outline'
    | 'timer-outline'
    | 'briefcase-outline'
    | 'document-text-outline'
    | 'checkbox-outline'
    | 'mail-outline'
    | 'shield-checkmark-outline'
}

/**
 * Delivery alerts lock (2026-08-10):
 * Quiet read-only More monitor for non-task outbound delivery states.
 * Canonical has_task dedupe (same as web Alerts & Delivery). Not emitted into
 * Home/Inbox priorities. Separate from HR Tasks / Settings. No mutations.
 * Future converge: fold under Tasks only with has_task dedupe — never a duplicate queue.
 */
export const MORE_MODULE_LINKS: MoreModuleLink[] = [
  {
    key: 'assistant',
    path: '/hr/assistant',
    group: 'operations',
    workspace: 'hr',
    features: ['assistant'],
    titleKey: 'hrMore.assistant',
    subtitleKey: 'hrMore.assistantBody',
    icon: 'chatbubble-ellipses-outline',
  },
  {
    key: 'attendance',
    path: '/hr/attendance',
    group: 'operations',
    workspace: 'hr',
    features: ['attendance_exceptions'],
    titleKey: 'hrMore.attendance',
    subtitleKey: 'hrMore.attendanceBody',
    icon: 'calendar-outline',
  },
  {
    key: 'shifts',
    path: '/hr/shifts',
    group: 'operations',
    workspace: 'hr',
    features: ['today_shifts', 'shift_swap_decisions'],
    titleKey: 'hrMore.shifts',
    subtitleKey: 'hrMore.shiftsBody',
    icon: 'time-outline',
  },
  {
    key: 'preboarding',
    path: '/hr/preboarding',
    group: 'operations',
    workspace: 'hr',
    features: ['preboarding_review'],
    titleKey: 'hrMore.preboarding',
    subtitleKey: 'hrMore.preboardingBody',
    icon: 'walk-outline',
  },
  {
    key: 'probation',
    path: '/hr/probation',
    group: 'operations',
    workspace: 'hr',
    features: ['probation_review'],
    titleKey: 'hrMore.probation',
    subtitleKey: 'hrMore.probationBody',
    icon: 'timer-outline',
  },
  {
    key: 'performance',
    path: '/hr/performance',
    group: 'operations',
    workspace: 'hr',
    features: ['performance_reviews'],
    titleKey: 'hrPerformance.title',
    subtitleKey: 'hrPerformance.subtitle',
    icon: 'ribbon-outline',
  },
  {
    key: 'employee-relations',
    path: '/hr/employee-relations',
    group: 'operations',
    workspace: 'hr',
    features: ['employee_relations_actions'],
    titleKey: 'hrEmployeeRelations.title',
    subtitleKey: 'hrEmployeeRelations.subtitle',
    icon: 'shield-checkmark-outline',
  },
  {
    key: 'requisitions',
    path: '/hr/requisitions',
    group: 'operations',
    workspace: 'recruiting',
    features: ['requisitions_review'],
    titleKey: 'hrMore.requisitions',
    subtitleKey: 'hrMore.requisitionsBody',
    icon: 'briefcase-outline',
  },
  {
    key: 'onboarding',
    path: '/hr/onboarding',
    group: 'operations',
    workspace: 'hr',
    features: ['onboarding_review'],
    titleKey: 'hrMore.onboarding',
    subtitleKey: 'hrMore.onboardingBody',
    icon: 'ribbon-outline',
  },
  {
    key: 'documents',
    path: '/hr/documents',
    group: 'operations',
    workspace: 'hr',
    features: ['document_review'],
    titleKey: 'hrMore.documents',
    subtitleKey: 'hrMore.documentsBody',
    icon: 'document-text-outline',
  },
  {
    key: 'tasks',
    path: '/hr/tasks',
    group: 'operations',
    workspace: 'hr',
    features: ['hr_tasks'],
    titleKey: 'hrMore.tasks',
    subtitleKey: 'hrMore.tasksBody',
    icon: 'checkbox-outline',
  },
  {
    key: 'deliveryAlerts',
    path: '/hr/delivery-alerts',
    group: 'operations',
    workspace: 'hr',
    features: ['delivery_alerts'],
    titleKey: 'hrMore.deliveryAlerts',
    subtitleKey: 'hrMore.deliveryAlertsBody',
    icon: 'mail-outline',
  },
]

/** Capability + workspace enabled — disabled modules never appear. */
export function moreModulesFor(me: MobileMe | null): MoreModuleLink[] {
  return MORE_MODULE_LINKS.filter(
    (link) =>
      me?.workspaces[link.workspace]?.enabled === true &&
      hasAnyCapability(me, link.workspace, link.features),
  )
}

/** @deprecated Prefer moreModulesFor — kept for any residual callers during transition. */
export function moreLinksFor(me: MobileMe | null): MoreModuleLink[] {
  return moreModulesFor(me)
}
