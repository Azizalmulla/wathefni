import type { OnboardingChecklistItem, OnboardingEmployee } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'
import { ONBOARDING_DEMO_ID_PREFIX, ONBOARDING_DEMO_SOURCE } from './onboardingDemoGate'

export function itemStatusLabelKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'submitted':
    case 'processing':
    case 'received':
    case 'needs_review':
      return 'hrOnboarding.statusNeedsHr'
    case 'accepted':
      return 'hrOnboarding.statusAccepted'
    case 'waived':
      return 'hrOnboarding.statusWaived'
    case 'pending':
    case 'in_progress':
      return 'hrOnboarding.statusWaitingEmployee'
    default:
      return 'hrOnboarding.statusNeedsHr'
  }
}

export function itemStatusTone(status: string | null | undefined): StatusTone {
  switch ((status || '').trim().toLowerCase()) {
    case 'submitted':
    case 'processing':
    case 'received':
    case 'needs_review':
      return 'yellow'
    case 'accepted':
    case 'waived':
      return 'green'
    case 'pending':
    case 'in_progress':
      return 'blue'
    default:
      return 'yellow'
  }
}

export function queueSubtitle(item: OnboardingEmployee, t: (k: string, p?: Record<string, string | number>) => string): string {
  const count = item.hr_actionable_count ?? item.items?.length ?? 0
  const dept = item.employee.department
  return [t('hrOnboarding.actionableCount', { count }), dept].filter(Boolean).join(' · ')
}

/** Demo model — includes waiting-on-employee employee to prove queue filtering excludes them. */
export function buildOnboardingDemoModel(): {
  source: typeof ONBOARDING_DEMO_SOURCE
  /** Queue = HR-actionable employees only */
  queue: OnboardingEmployee[]
  /** Full roster including waiting-only (not shown in queue) */
  all: OnboardingEmployee[]
} {
  const key = (s: string) => `${ONBOARDING_DEMO_ID_PREFIX}${s}`

  const docReview: OnboardingChecklistItem = {
    item_id: 'civil_id',
    label: 'Civil ID',
    item_type: 'document',
    document_type: 'civil_id',
    required: true,
    status: 'processing',
    group: 'being_reviewed',
    has_file: true,
    preview_path: '/dashboard/mobile/documents/files/demo-civil',
    download_path: '/dashboard/mobile/documents/files/demo-civil?disposition=attachment',
    allowed_actions: ['preview', 'accept', 'waive'],
  }
  const nonDoc: OnboardingChecklistItem = {
    item_id: 'policy_ack',
    label: 'Policy acknowledgement',
    item_type: 'task',
    required: true,
    status: 'submitted',
    group: 'being_reviewed',
    has_file: false,
    allowed_actions: ['accept', 'waive'],
  }
  const waiveOnly: OnboardingChecklistItem = {
    item_id: 'optional_cert',
    label: 'Optional certification',
    item_type: 'document',
    document_type: 'certificate',
    required: false,
    status: 'processing',
    group: 'being_reviewed',
    has_file: true,
    preview_path: '/dashboard/mobile/documents/files/demo-cert',
    allowed_actions: ['preview', 'accept', 'waive'],
  }
  const bankHandoff: OnboardingChecklistItem = {
    item_id: 'bank_details',
    label: 'Bank details',
    item_type: 'bank',
    required: true,
    status: 'processing',
    group: 'being_reviewed',
    is_bank_ess: true,
    has_file: false,
    allowed_actions: ['review_bank'],
  }
  const waitingItem: OnboardingChecklistItem = {
    item_id: 'passport',
    label: 'Passport',
    item_type: 'document',
    document_type: 'passport',
    required: true,
    status: 'pending',
    group: 'your_actions',
    has_file: false,
    allowed_actions: [],
  }

  const hrReadyDoc: OnboardingEmployee = {
    employee_key: key('sara'),
    employee: {
      name: 'Sara Al-Mutairi',
      employee_key: key('sara'),
      position_title: 'Store Manager',
      department: 'Retail',
      onboarding_status: 'in_progress',
    },
    status: 'in_progress',
    hr_actionable_count: 1,
    hr_mutate_enabled: true,
    hr_actionable_items: [docReview],
    waiting_on_employee_items: [waitingItem],
    items: [docReview],
    allowed_actions: ['read', 'review'],
  }
  const hrReadyMixed: OnboardingEmployee = {
    employee_key: key('noura'),
    employee: {
      name: 'Noura Hassan',
      employee_key: key('noura'),
      position_title: 'Sales Associate',
      department: 'Sales',
      onboarding_status: 'in_progress',
    },
    status: 'in_progress',
    hr_actionable_count: 3,
    hr_mutate_enabled: true,
    hr_actionable_items: [nonDoc, waiveOnly, bankHandoff],
    waiting_on_employee_items: [],
    items: [nonDoc, waiveOnly, bankHandoff],
    allowed_actions: ['read', 'review'],
  }
  /** Waiting on employee only — must NOT appear in HR-actionable queue. */
  const waitingOnly: OnboardingEmployee = {
    employee_key: key('bilal'),
    employee: {
      name: 'Bilal Chowdhury',
      employee_key: key('bilal'),
      position_title: 'Warehouse Operative',
      department: 'Warehouse',
      onboarding_status: 'in_progress',
    },
    status: 'in_progress',
    hr_actionable_count: 0,
    hr_mutate_enabled: true,
    hr_actionable_items: [],
    waiting_on_employee_items: [waitingItem],
    items: [],
    allowed_actions: ['read'],
  }

  const queue = [hrReadyDoc, hrReadyMixed]
  return { source: ONBOARDING_DEMO_SOURCE, queue, all: [...queue, waitingOnly] }
}
