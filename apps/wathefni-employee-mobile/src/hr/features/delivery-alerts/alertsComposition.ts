import type { DeliveryAlert } from '@hr/api/types'
import type { StatusTone } from '@/components/ui'
import { ALERTS_DEMO_ID_PREFIX, ALERTS_DEMO_SOURCE } from './alertsDemoGate'

/** Canonical outbound delivery statuses already returned by needs-follow-up. */
export function alertStatusLabelKey(status: string | null | undefined): string {
  switch ((status || '').trim().toLowerCase()) {
    case 'failed':
      return 'hrAlerts.statusFailed'
    case 'needs_hr_action':
      return 'hrAlerts.statusNeedsHr'
    case 'suppressed':
      return 'hrAlerts.statusSuppressed'
    case 'throttled':
      return 'hrAlerts.statusThrottled'
    case 'dashboard_only':
      return 'hrAlerts.statusDashboardOnly'
    case 'pending':
      return 'hrAlerts.statusPending'
    default:
      return 'hrAlerts.statusOther'
  }
}

export function alertStatusTone(status: string | null | undefined): StatusTone {
  switch ((status || '').trim().toLowerCase()) {
    case 'failed':
    case 'needs_hr_action':
      return 'pink'
    case 'suppressed':
    case 'throttled':
      return 'yellow'
    case 'dashboard_only':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export function queueSubtitle(
  item: DeliveryAlert,
  t: (k: string, p?: Record<string, string | number>) => string,
): string {
  const parts: string[] = []
  if (item.employee?.name) parts.push(item.employee.name)
  if (item.channel) parts.push(item.channel)
  if (item.kind === 'info') parts.push(t('hrAlerts.kindInfo'))
  else if (item.kind === 'issue') parts.push(t('hrAlerts.kindIssue'))
  return parts.filter(Boolean).join(' · ')
}

export function buildAlertsDemoQueue(): {
  source: typeof ALERTS_DEMO_SOURCE
  items: DeliveryAlert[]
} {
  const id = (s: string) => `${ALERTS_DEMO_ID_PREFIX}${s}`
  const items: DeliveryAlert[] = [
    {
      alert_id: id('failed'),
      title: 'Civil ID expiry reminder',
      summary: 'WhatsApp returned conversation_inactive for this recipient.',
      status: 'failed',
      kind: 'issue',
      channel: 'whatsapp_session',
      flow: 'compliance_expiry',
      flow_label: 'Civil ID expiry reminder',
      occurred_at: '2026-08-09T16:20:00+03:00',
      suggested_action: 'Confirm the employee WhatsApp number on their profile.',
      attempts: 2,
      has_task: false,
      employee: {
        name: 'Sara Al-Mutairi',
        employee_key: '__demo_alert_emp__sara',
      },
      destination: '/employees/__demo_alert_emp__sara',
      allowed_actions: ['read'],
    },
    {
      alert_id: id('throttled'),
      title: 'Onboarding nudge',
      summary: 'Reminder paused — already reminded recently.',
      status: 'throttled',
      kind: 'info',
      channel: 'whatsapp_template',
      flow: 'onboarding_nudge',
      flow_label: 'Onboarding nudge',
      occurred_at: '2026-08-10T09:00:00+03:00',
      suggested_action: 'No action needed. Reminders resume after the quiet window.',
      attempts: 1,
      has_task: false,
      employee: {
        name: 'Noura Hassan',
        employee_key: '__demo_alert_emp__noura',
      },
      destination: '/employees/__demo_alert_emp__noura',
      allowed_actions: ['read'],
    },
    {
      alert_id: id('suppressed'),
      title: 'App invitation',
      summary: 'Kept on the dashboard — not pushed to WhatsApp or email.',
      status: 'dashboard_only',
      kind: 'info',
      channel: 'dashboard',
      flow: 'app_invitation',
      flow_label: 'App invitation',
      occurred_at: '2026-08-08T11:00:00+03:00',
      suggested_action: 'No action needed. This update is shown here on purpose.',
      attempts: 0,
      has_task: false,
      employee: {
        name: 'Talal Al-Sabah',
        employee_key: '__demo_alert_emp__talal',
      },
      destination: '/employees/__demo_alert_emp__talal',
      allowed_actions: ['read'],
    },
  ]
  return { source: ALERTS_DEMO_SOURCE, items }
}
