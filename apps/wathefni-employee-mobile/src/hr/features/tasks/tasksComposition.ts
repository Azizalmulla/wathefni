import type { HRTask } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'
import { TASKS_DEMO_ID_PREFIX, TASKS_DEMO_SOURCE } from './tasksDemoGate'

export function taskPriorityLabelKey(priority: string | null | undefined): string {
  switch ((priority || '').trim().toLowerCase()) {
    case 'high':
      return 'hrTasks.priorityHigh'
    case 'low':
      return 'hrTasks.priorityLow'
    default:
      return 'hrTasks.priorityNormal'
  }
}

export function taskPriorityTone(priority: string | null | undefined): StatusTone {
  switch ((priority || '').trim().toLowerCase()) {
    case 'high':
      return 'pink'
    case 'low':
      return 'neutral'
    default:
      return 'yellow'
  }
}

export function taskTypeLabelKey(taskType: string | null | undefined): string {
  switch ((taskType || '').trim().toLowerCase()) {
    case 'candidate_handoff':
      return 'hrTasks.typeHandoff'
    case 'app_activation_handoff':
      return 'hrTasks.typeActivation'
    case 'account_deletion':
      return 'hrTasks.typeDeletion'
    case 'delivery_failed':
    case 'delivery_failure': // legacy alias — canonical is delivery_failed
    case 'outbound_follow_up':
      return 'hrTasks.typeDelivery'
    default:
      return 'hrTasks.typeFollowUp'
  }
}

export function queueSubtitle(
  item: HRTask,
  t: (k: string, p?: Record<string, string | number>) => string,
): string {
  const parts: string[] = []
  if (item.employee?.name) parts.push(item.employee.name)
  parts.push(t(taskTypeLabelKey(item.task_type)))
  if (item.source) parts.push(item.source)
  return parts.filter(Boolean).join(' · ')
}

export function buildTasksDemoQueue(): {
  source: typeof TASKS_DEMO_SOURCE
  open: HRTask[]
} {
  const id = (s: string) => `${TASKS_DEMO_ID_PREFIX}${s}`
  const open: HRTask[] = [
    {
      task_id: id('delivery'),
      task_type: 'delivery_failed',
      source: 'outbound',
      title: 'WhatsApp delivery failed — Civil ID reminder',
      detail: 'Last attempt returned conversation_inactive. Follow up so the employee can renew.',
      employee: {
        name: 'Sara Al-Mutairi',
        employee_key: '__demo_task_emp__sara',
        department: 'Retail',
        position_title: 'Store Manager',
      },
      status: 'open',
      priority: 'high',
      created_at: '2026-08-09T16:20:00+03:00',
      updated_at: '2026-08-09T16:20:00+03:00',
      destination: `/tasks/${id('delivery')}`,
      allowed_actions: ['resolve'],
    },
    {
      task_id: id('activation'),
      task_type: 'app_activation_handoff',
      source: 'employee_app',
      title: 'App activation needs HR follow-up',
      detail: 'Invite accepted but first sign-in did not complete. Confirm access with the employee.',
      employee: {
        name: 'Noura Hassan',
        employee_key: '__demo_task_emp__noura',
        department: 'Sales',
        position_title: 'Sales Associate',
      },
      status: 'open',
      priority: 'normal',
      created_at: '2026-08-08T11:00:00+03:00',
      updated_at: '2026-08-10T08:15:00+03:00',
      destination: `/tasks/${id('activation')}`,
      allowed_actions: ['resolve'],
    },
    {
      task_id: id('handoff'),
      task_type: 'candidate_handoff',
      source: 'recruiting',
      title: 'Candidate handoff waiting on HR',
      detail: 'Automation paused for a recruiter handoff. Mark done to resume the candidate journey.',
      employee: {
        name: 'Ahmed Darwish',
        employee_key: '__demo_task_emp__ahmed',
        department: 'Support',
        position_title: 'Customer Care',
      },
      status: 'open',
      priority: 'high',
      created_at: '2026-08-07T09:40:00+03:00',
      updated_at: '2026-08-07T09:40:00+03:00',
      destination: `/tasks/${id('handoff')}`,
      allowed_actions: ['resolve'],
    },
    {
      task_id: id('company'),
      task_type: 'account_deletion',
      source: 'privacy',
      title: 'Account deletion request — company follow-up',
      detail:
        'Company-wide task (no employee_key). Visible to unrestricted HR only — managers never see these.',
      status: 'open',
      priority: 'normal',
      created_at: '2026-08-06T14:00:00+03:00',
      updated_at: '2026-08-06T14:00:00+03:00',
      destination: `/tasks/${id('company')}`,
      allowed_actions: ['resolve'],
    },
  ]
  return { source: TASKS_DEMO_SOURCE, open }
}
