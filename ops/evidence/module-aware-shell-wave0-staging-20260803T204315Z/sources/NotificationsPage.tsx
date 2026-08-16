import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { scopeDeliveryNotificationRows } from '@/lib/moduleWorkspace'
import { EmptyState } from '@/pages/shared/primitives'
import type { NotificationActionItem, NotificationRow, Page } from '@/types'

const NOTIFICATION_ACTION_TARGETS: Record<string, Page> = {
  'Open Assessments queue': 'assessments',
  'Open Interviews queue': 'interviews',
  'Review in Wathefni Assistant': 'ai',
  'Review completed screening': 'candidates',
}

type NotificationGroupId = 'pre_hiring' | 'onboarding' | 'delivery_issues' | 'completions'

type NotificationAlert = {
  id: string
  group: NotificationGroupId
  title: string
  detail: string
  actionLabel: string
  count: number
  severity?: string
}

const NOTIFICATION_GROUPS: Array<{ id: NotificationGroupId; label: string; description: string }> = [
  { id: 'pre_hiring', label: 'Hiring alerts', description: 'Important candidate or assistant actions that need HR attention now.' },
  { id: 'onboarding', label: 'Onboarding exceptions', description: 'Urgent employee issues only when that module is active.' },
  { id: 'delivery_issues', label: 'Delivery alerts', description: 'Assessment or interview messages that did not reach the candidate.' },
  { id: 'completions', label: 'Completions', description: 'Candidate steps completed today that may need quick HR review.' },
]

export function NotificationsPage({
  actionItems,
  deliveryCenter,
  enabledModules,
  notifications,
  onNavigate,
}: {
  actionItems: NotificationActionItem[]
  deliveryCenter?: ReactNode
  enabledModules?: string[]
  notifications: NotificationRow[]
  onNavigate: (page: Page) => void
}) {
  const issues = moduleScopedNotificationRows(notifications, enabledModules)
  const alerts = groupedNotificationAlerts(actionItems, issues, enabledModules)
  return (
    <div className="space-y-6">
      {deliveryCenter}
      <Card>
        <CardHeader>
          <CardTitle>Urgent HR alerts</CardTitle>
          <CardDescription>Important hiring issues HR should check now. Daily work stays in Candidates, Assessments, Interviews, and Reports.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {alerts.length ? (
            NOTIFICATION_GROUPS.filter((group) => alerts.some((item) => item.group === group.id)).map((group) => (
              <section className="rounded-2xl border border-line bg-panel/70 p-4" key={group.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">{group.label}</div>
                    <div className="mt-1 text-sm text-subtle">{group.description}</div>
                  </div>
                  <Badge tone={group.id === 'delivery_issues' ? 'warning' : 'muted'}>
                    {notificationGroupCount(alerts, group.id)} alert{notificationGroupCount(alerts, group.id) === 1 ? '' : 's'}
                  </Badge>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {alerts.filter((item) => item.group === group.id).map((item) => (
                    <div className="rounded-xl border border-line bg-panel-muted/60 p-4" key={item.id}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold">{item.title}</div>
                          <div className="mt-1 text-sm leading-6 text-subtle">{item.detail}</div>
                        </div>
                        <Badge tone={notificationSeverityTone(item.severity)}>{item.count}</Badge>
                      </div>
                      {NOTIFICATION_ACTION_TARGETS[item.actionLabel] ? (
                        <button
                          type="button"
                          onClick={() => onNavigate(NOTIFICATION_ACTION_TARGETS[item.actionLabel])}
                          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-[#8a5a16] transition hover:text-[#6f4711]"
                        >
                          {item.actionLabel}
                          <span aria-hidden="true">→</span>
                        </button>
                      ) : (
                        <div className="mt-3 text-xs text-subtle">Suggested next step: {item.actionLabel}</div>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            ))
          ) : (
            <EmptyState text="All clear - no urgent HR alerts." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function groupedNotificationAlerts(actionItems: NotificationActionItem[], issues: NotificationRow[], enabledModules?: string[]) {
  const alerts = actionItems
    .map(notificationAlertFromActionItem)
    .filter((item): item is NotificationAlert => item !== null && notificationGroupEnabled(item.group, enabledModules))
  void issues
  const severityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 }
  return alerts.sort((a, b) => {
    const groupOrder = NOTIFICATION_GROUPS.findIndex((group) => group.id === a.group) - NOTIFICATION_GROUPS.findIndex((group) => group.id === b.group)
    if (groupOrder) return groupOrder
    const severity = (severityOrder[String(a.severity || '')] ?? 9) - (severityOrder[String(b.severity || '')] ?? 9)
    if (severity) return severity
    return b.count - a.count
  })
}

function notificationAlertFromActionItem(item: NotificationActionItem): NotificationAlert | null {
  const count = Number(item.count || 0)
  if (count <= 0) return null
  const group = notificationItemGroup(item)
  const kind = String(item.kind || '')
  const label = String(item.metadata?.label || item.metadata?.document_type || 'required document')
  if (kind === 'missing_onboarding_item') {
    return {
      id: `${kind}:${label}`,
      group: 'onboarding',
      title: 'Missing document',
      detail: `${count} employee${count === 1 ? '' : 's'} still need ${label}.`,
      actionLabel: 'Follow up with employee',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'screening_completed_today') {
    return {
      id: kind,
      group: 'completions',
      title: 'Review completed screening',
      detail: `${count} candidate${count === 1 ? '' : 's'} finished a screening step today.`,
      actionLabel: 'Review completed screening',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'assessment_delivery_failed') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Assessment delivery failed',
      detail: `${count} assessment message${count === 1 ? '' : 's'} did not reach the candidate.`,
      actionLabel: 'Open Assessments queue',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'interview_invite_failed') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Interview invite failed',
      detail: `${count} interview invite${count === 1 ? '' : 's'} did not reach the candidate.`,
      actionLabel: 'Open Interviews queue',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'ai_action_needs_approval') {
    return {
      id: kind,
      group: 'pre_hiring',
      title: 'AI action needs approval',
      detail: `${count} AI action${count === 1 ? '' : 's'} are waiting for HR approval.`,
      actionLabel: 'Review in Wathefni Assistant',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'closed_conversations') {
    return {
      id: kind,
      group: 'delivery_issues',
      title: 'Send approved message',
      detail: `${count} person${count === 1 ? '' : 's'} need an approved message before contact can continue.`,
      actionLabel: 'Send approved message',
      count,
      severity: item.severity,
    }
  }
  if (kind === 'stale_conversations' || kind === 'failed_onboarding_reminders') {
    return {
      id: kind,
      group: kind === 'failed_onboarding_reminders' ? 'onboarding' : 'delivery_issues',
      title: kind === 'failed_onboarding_reminders' ? 'Follow up with employee' : 'Needs HR attention',
      detail: kind === 'failed_onboarding_reminders'
        ? `${count} employee${count === 1 ? '' : 's'} need HR follow-up for onboarding.`
        : `${count} person${count === 1 ? '' : 's'} need HR to choose the best contact method.`,
      actionLabel: kind === 'failed_onboarding_reminders' ? 'Follow up with employee' : 'Needs HR attention',
      count,
      severity: item.severity,
    }
  }
  if (kind.startsWith('compliance_')) {
    return {
      id: kind,
      group: 'onboarding',
      title: 'Missing document',
      detail: `${count} employee document${count === 1 ? '' : 's'} need HR review.`,
      actionLabel: 'Follow up with employee',
      count,
      severity: item.severity,
    }
  }
  return {
    id: `${kind}:${item.title}`,
    group,
    title: hrNotificationText(item.title || 'Needs HR attention'),
    detail: hrNotificationText(item.action || 'Needs HR attention'),
    actionLabel: hrNotificationActionLabel(group),
    count,
    severity: item.severity,
  }
}

function notificationItemGroup(item: NotificationActionItem): NotificationGroupId {
  const configured = String(item.metadata?.module_group || '')
  if (configured === 'pre_hiring' || configured === 'onboarding' || configured === 'delivery_issues' || configured === 'completions') return configured
  const kind = String(item.kind || '')
  if (kind.includes('screening_completed') || kind.includes('completed')) return 'completions'
  if (kind.includes('onboarding') || kind.includes('compliance') || item.page === 'onboarding') return 'onboarding'
  if (kind.includes('conversation') || kind.includes('delivery') || kind.includes('failed')) return 'delivery_issues'
  return 'pre_hiring'
}

function notificationGroupCount(alerts: NotificationAlert[], groupId: NotificationGroupId) {
  return alerts.filter((item) => item.group === groupId).length
}

function notificationGroupEnabled(groupId: NotificationGroupId, enabledModules?: string[]) {
  if (!enabledModules?.length) return true
  if (groupId === 'onboarding') return enabledModules.includes('onboarding')
  if (groupId === 'pre_hiring' || groupId === 'completions') return enabledModules.includes('pre_hiring')
  return true
}

function notificationSeverityTone(severity: string | undefined): 'success' | 'warning' | 'danger' | 'muted' {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  if (severity === 'low') return 'success'
  return 'muted'
}

function hrNotificationActionLabel(group: NotificationGroupId) {
  if (group === 'pre_hiring') return 'Open Candidates queue'
  if (group === 'onboarding') return 'Open Onboarding queue'
  if (group === 'completions') return 'Review completed work'
  return 'Needs HR attention'
}

function hrNotificationText(value: string) {
  return value
    .replace(/invalid_grant/gi, 'Email needs reconnecting')
    .replace(/no_usable_conversation_id/gi, 'WhatsApp conversation is not active')
    .replace(new RegExp(['stale', 'conversations?'].join(' '), 'gi'), 'people needing attention')
    .replace(new RegExp(['fallback', 'channel'].join(' '), 'gi'), 'best contact method')
    .replace(new RegExp(['reminders?', 'failed'].join(' '), 'gi'), 'people need HR follow-up')
    .replace(new RegExp(['conversation', 'closed'].join(' '), 'gi'), 'approved message needed')
    .replace(new RegExp(['delivery', 'exception'].join(' '), 'gi'), 'needs HR attention')
}

function notificationIssueRows(notifications: NotificationRow[]) {
  return notifications.filter((item) => !['sent', 'completed', 'recovered', 'delivered'].includes(normalizedDeliveryStatus(item)))
}

function moduleScopedNotificationRows(notifications: NotificationRow[], enabledModules?: string[]) {
  return scopeDeliveryNotificationRows(notificationIssueRows(notifications), enabledModules)
}

function normalizedDeliveryStatus(item: NotificationRow) {
  const raw = String(item.dashboard_status || item.status || 'unknown').toLowerCase()
  if (raw === 'blocked_closed_conversation') return 'blocked_by_closed_conversation'
  if (raw === 'stale_conversation') return 'stale'
  return raw || 'unknown'
}
