import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, Loader2, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { FRESHNESS_MS } from '@/lib/query/freshness'
import { useVisibilitySoftPoll } from '@/lib/query/useVisibilitySoftPoll'
import {
  getHrTasks,
  getOutboundNeedsFollowUp,
  resolveHrTask,
} from '@/lib/api'
import { scopeDeliveryNotificationRows } from '@/lib/moduleWorkspace'
import { canManageAlertsAndDelivery } from '@/lib/alertsDeliveryAccess'
import { useUrlBackedTab } from '@/lib/hrWebUrlTab'
import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { EmptyState } from '@/pages/shared/primitives'
import { ResourceState } from '@/pages/shared/dataState'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type {
  DashboardAccess,
  HrTask,
  NotificationActionItem,
  NotificationRow,
  OutboundFollowUpMessage,
  Page,
} from '@/types'

type IssueFilter = 'needs_follow_up' | 'failed' | 'retrying' | 'resolved' | 'all'
type IssueBucket = IssueFilter

const ALERT_FILTERS = ['needs_follow_up', 'failed', 'retrying', 'resolved', 'all'] as const

type LiveIssue = {
  id: string
  bucket: IssueBucket
  recipient: string
  purpose: string
  channel: string
  reason: string
  when: string | null
  statusLabel: string
  primary:
    | { kind: 'navigate'; page: Page; label: string }
    | { kind: 'resolve'; taskId: string; expectedStatus: string; label: string }
    | { kind: 'status'; label: string }
  details: Array<{ label: string; value: string }>
  source: 'hr_task' | 'outbound' | 'prehire_row' | 'action_item'
}

const ACTION_TARGETS: Record<string, Page> = {
  'Open Assessments queue': 'assessments',
  'Open Interviews queue': 'interviews',
  'Review in OctoHR Assistant': 'ai',
  'Review completed screening': 'candidates',
  'Open Candidates queue': 'candidates',
  'Open Onboarding queue': 'onboarding',
  'Review completed work': 'candidates',
  'Follow up with employee': 'onboarding',
  'Send approved message': 'ai',
}

function friendlyError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function isStaleDecision(error: unknown) {
  const status = (error as { status?: number } | null)?.status
  if (status === 409) return true
  return error instanceof Error && /stale_decision/i.test(error.message)
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

function normalizedDeliveryStatus(item: NotificationRow) {
  const raw = String(item.dashboard_status || item.status || 'unknown').toLowerCase()
  if (raw === 'blocked_closed_conversation') return 'blocked_by_closed_conversation'
  if (raw === 'stale_conversation') return 'stale'
  return raw || 'unknown'
}

function notificationIssueRows(notifications: NotificationRow[]) {
  return notifications.filter((item) => !['sent', 'completed', 'recovered', 'delivered'].includes(normalizedDeliveryStatus(item)))
}

export function moduleScopedNotificationRows(notifications: NotificationRow[], enabledModules?: string[]) {
  return scopeDeliveryNotificationRows(notificationIssueRows(notifications), enabledModules)
}

function fmtWhen(iso: string | null | undefined, isAr: boolean) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  try {
    return d.toLocaleString(isAr ? 'ar-KW' : 'en-GB', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  } catch {
    return iso
  }
}

function channelForRow(item: NotificationRow, isAr: boolean) {
  if (item.target_conversation_id || item.target_phone) return isAr ? 'واتساب' : 'WhatsApp'
  if (item.candidate_email) return isAr ? 'البريد' : 'Email'
  return isAr ? 'رسالة' : 'Message'
}

function purposeForRow(item: NotificationRow, isAr: boolean) {
  const blob = [item.last_error, item.dashboard_status, item.status, item.position_title]
    .map((v) => String(v || '').toLowerCase())
    .join(' ')
  if (blob.includes('assessment')) return isAr ? 'تقييم' : 'Assessment'
  if (blob.includes('interview')) return isAr ? 'مقابلة' : 'Interview'
  if (blob.includes('onboarding')) return isAr ? 'تهيئة' : 'Onboarding'
  if (item.position_title) return item.position_title
  return isAr ? 'رسالة مرشّح' : 'Candidate message'
}

function navigateForRow(item: NotificationRow): Page | null {
  const blob = [item.last_error, item.dashboard_status, item.status, item.position_title]
    .map((v) => String(v || '').toLowerCase())
    .join(' ')
  if (blob.includes('assessment')) return 'assessments'
  if (blob.includes('interview')) return 'interviews'
  if (blob.includes('onboarding') || blob.includes('compliance')) return 'onboarding'
  return null
}

function outboundBucket(m: OutboundFollowUpMessage): IssueBucket {
  if (m.status === 'throttled') return 'retrying'
  if (m.status === 'failed') return 'failed'
  if (m.status === 'needs_hr_action') return 'needs_follow_up'
  if (m.status === 'suppressed' || m.status === 'dashboard_only') return 'all'
  if ((m.kind ?? 'issue') === 'issue') return 'failed'
  return 'all'
}

function actionItemTarget(item: NotificationActionItem, actionLabel: string, enabledModules?: string[]): Page | null {
  const page = String(item.page || '').trim() as Page
  if (page) return page
  if (ACTION_TARGETS[actionLabel]) {
    const target = ACTION_TARGETS[actionLabel]
    if (target === 'onboarding' && enabledModules?.length && !enabledModules.includes('onboarding')) {
      return 'employees'
    }
    return target
  }
  return null
}

function issueFromActionItem(item: NotificationActionItem, enabledModules: string[] | undefined, isAr: boolean): LiveIssue | null {
  const count = Number(item.count || 0)
  if (count <= 0) return null
  const kind = String(item.kind || '')
  const label = String(item.metadata?.label || item.metadata?.document_type || (isAr ? 'مستند مطلوب' : 'required document'))
  let title = hrNotificationText(item.title || (isAr ? 'يحتاج متابعة' : 'Needs HR attention'))
  let detail = hrNotificationText(item.action || title)
  let actionLabel = isAr ? 'يحتاج متابعة' : 'Needs HR attention'
  let bucket: IssueBucket = 'needs_follow_up'

  if (kind === 'missing_onboarding_item') {
    title = isAr ? 'مستند ناقص' : 'Missing document'
    detail = isAr ? `${count} موظف ما زال يحتاج ${label}.` : `${count} employee${count === 1 ? '' : 's'} still need ${label}.`
    actionLabel = isAr ? 'متابعة الموظف' : 'Follow up with employee'
    bucket = 'needs_follow_up'
  } else if (kind === 'screening_completed_today') {
    title = isAr ? 'مراجعة فرز مكتمل' : 'Review completed screening'
    detail = isAr
      ? `${count} مرشّح أنهى خطوة فرز اليوم.`
      : `${count} candidate${count === 1 ? '' : 's'} finished a screening step today.`
    actionLabel = isAr ? 'مراجعة الفرز المكتمل' : 'Review completed screening'
    bucket = 'all'
  } else if (kind === 'assessment_delivery_failed') {
    title = isAr ? 'فشل تسليم التقييم' : 'Assessment delivery failed'
    detail = isAr
      ? `${count} رسالة تقييم لم تصل للمرشّح.`
      : `${count} assessment message${count === 1 ? '' : 's'} did not reach the candidate.`
    actionLabel = isAr ? 'فتح قائمة التقييمات' : 'Open Assessments queue'
    bucket = 'failed'
  } else if (kind === 'interview_invite_failed') {
    title = isAr ? 'فشل دعوة المقابلة' : 'Interview invite failed'
    detail = isAr
      ? `${count} دعوة مقابلة لم تصل للمرشّح.`
      : `${count} interview invite${count === 1 ? '' : 's'} did not reach the candidate.`
    actionLabel = isAr ? 'فتح قائمة المقابلات' : 'Open Interviews queue'
    bucket = 'failed'
  } else if (kind === 'ai_action_needs_approval') {
    title = isAr ? 'إجراء ذكاء يحتاج موافقة' : 'AI action needs approval'
    detail = isAr
      ? `${count} إجراء بانتظار موافقة الموارد البشرية.`
      : `${count} AI action${count === 1 ? '' : 's'} are waiting for HR approval.`
    actionLabel = isAr ? 'المراجعة في مساعد OctoHR' : 'Review in OctoHR Assistant'
    bucket = 'needs_follow_up'
  } else if (kind === 'closed_conversations') {
    title = isAr ? 'رسالة معتمدة مطلوبة' : 'Approved message needed'
    detail = isAr
      ? `${count} شخص يحتاج رسالة معتمدة قبل المتابعة.`
      : `${count} person${count === 1 ? '' : 's'} need an approved message before contact can continue.`
    actionLabel = isAr ? 'إرسال رسالة معتمدة' : 'Send approved message'
    bucket = 'needs_follow_up'
  } else if (kind === 'stale_conversations' || kind === 'failed_onboarding_reminders') {
    const onboarding = kind === 'failed_onboarding_reminders'
    title = onboarding ? (isAr ? 'متابعة الموظف' : 'Follow up with employee') : isAr ? 'يحتاج متابعة' : 'Needs HR attention'
    detail = onboarding
      ? isAr
        ? `${count} موظف يحتاج متابعة للتهيئة.`
        : `${count} employee${count === 1 ? '' : 's'} need HR follow-up for onboarding.`
      : isAr
        ? `${count} شخص يحتاج اختيار أفضل طريقة تواصل.`
        : `${count} person${count === 1 ? '' : 's'} need HR to choose the best contact method.`
    actionLabel = onboarding
      ? isAr
        ? 'متابعة الموظف'
        : 'Follow up with employee'
      : isAr
        ? 'يحتاج متابعة'
        : 'Needs HR attention'
    bucket = 'needs_follow_up'
  } else if (kind.startsWith('compliance_')) {
    title = isAr ? 'مستند يحتاج مراجعة' : 'Document needs review'
    detail = isAr
      ? `${count} مستند موظف يحتاج مراجعة.`
      : `${count} employee document${count === 1 ? '' : 's'} need HR review.`
    actionLabel = isAr ? 'فتح الامتثال' : 'Open Compliance'
    bucket = 'needs_follow_up'
  }

  // EN labels for ACTION_TARGETS lookup
  const enAction =
    kind === 'assessment_delivery_failed'
      ? 'Open Assessments queue'
      : kind === 'interview_invite_failed'
        ? 'Open Interviews queue'
        : kind === 'ai_action_needs_approval'
          ? 'Review in OctoHR Assistant'
          : kind === 'screening_completed_today'
            ? 'Review completed screening'
            : kind === 'closed_conversations'
              ? 'Send approved message'
              : kind === 'failed_onboarding_reminders' || kind === 'missing_onboarding_item'
                ? 'Follow up with employee'
                : kind.startsWith('compliance_')
                  ? 'Open Compliance'
                  : kind === 'stale_conversations'
                    ? 'Needs HR attention'
                    : 'Open Candidates queue'

  const navigateTarget =
    kind.startsWith('compliance_')
      ? ('compliance' as Page)
      : actionItemTarget(item, enAction, enabledModules)

  const primary: LiveIssue['primary'] = navigateTarget
    ? { kind: 'navigate', page: navigateTarget, label: actionLabel }
    : { kind: 'status', label: actionLabel }

  return {
    id: `action:${kind}:${item.title}`,
    bucket,
    recipient: isAr ? `${count} حالة` : `${count} case${count === 1 ? '' : 's'}`,
    purpose: title,
    channel: isAr ? 'تنبيه مساحة العمل' : 'Workspace alert',
    reason: detail,
    when: null,
    statusLabel: bucket === 'failed' ? (isAr ? 'فشل' : 'Failed') : isAr ? 'يحتاج متابعة' : 'Needs follow-up',
    primary,
    details: [
      { label: isAr ? 'النوع' : 'Kind', value: kind || '—' },
      { label: isAr ? 'العدد' : 'Count', value: String(count) },
    ],
    source: 'action_item',
  }
}

function issueFromPrehireRow(item: NotificationRow, isAr: boolean): LiveIssue {
  const status = normalizedDeliveryStatus(item)
  const page = navigateForRow(item)
  const reason = hrNotificationText(String(item.last_error || item.dashboard_status || item.status || (isAr ? 'لم تصل الرسالة' : 'Message did not reach the recipient')))
  const bucket: IssueBucket =
    status.includes('fail') || status.includes('blocked') || status === 'stale' ? 'failed' : 'needs_follow_up'
  return {
    id: `prehire:${item.delivery_id}`,
    bucket,
    recipient: item.candidate_name || item.candidate_email || (isAr ? 'مرشّح' : 'Candidate'),
    purpose: purposeForRow(item, isAr),
    channel: channelForRow(item, isAr),
    reason,
    when: fmtWhen(item.created_at, isAr),
    statusLabel: bucket === 'failed' ? (isAr ? 'فشل' : 'Failed') : isAr ? 'يحتاج متابعة' : 'Needs follow-up',
    primary: page
      ? {
          kind: 'navigate',
          page,
          label:
            page === 'assessments'
              ? isAr
                ? 'فتح التقييمات'
                : 'Open Assessments'
              : page === 'interviews'
                ? isAr
                  ? 'فتح المقابلات'
                  : 'Open Interviews'
                : isAr
                  ? 'فتح التهيئة'
                  : 'Open Onboarding',
        }
      : { kind: 'status', label: isAr ? 'راجع تفاصيل التسليم' : 'Review delivery details' },
    details: [
      { label: isAr ? 'معرّف التسليم' : 'Delivery id', value: item.delivery_id },
      { label: isAr ? 'الحالة' : 'Status', value: status },
      ...(item.last_error ? [{ label: isAr ? 'دليل تقني' : 'Technical evidence', value: String(item.last_error) }] : []),
      ...(item.position_title ? [{ label: isAr ? 'الوظيفة' : 'Role', value: item.position_title }] : []),
    ],
    source: 'prehire_row',
  }
}

function issueFromHrTask(task: HrTask, isAr: boolean, resolved: boolean): LiveIssue {
  return {
    id: `task:${task.task_id}`,
    bucket: resolved ? 'resolved' : 'needs_follow_up',
    recipient: task.employee_name || (isAr ? 'موظف' : 'Employee'),
    purpose: task.title,
    channel: isAr ? 'متابعة موارد بشرية' : 'HR follow-up',
    reason: task.detail || (isAr ? 'تعذر الوصول عبر القنوات الحالية.' : 'Could not reach this person on enabled channels.'),
    when: fmtWhen(task.updated_at || task.created_at, isAr),
    statusLabel: resolved ? (isAr ? 'تم الحل' : 'Resolved') : isAr ? 'يحتاج متابعة' : 'Needs follow-up',
    primary: resolved
      ? { kind: 'status', label: isAr ? 'تم وضع علامة مكتمل' : 'Marked done' }
      : {
          kind: 'resolve',
          taskId: task.task_id,
          expectedStatus: task.status || 'open',
          label: isAr ? 'تعليم كمكتمل' : 'Mark done',
        },
    details: [
      { label: isAr ? 'نوع المهمة' : 'Task type', value: task.task_type || '—' },
      { label: isAr ? 'المصدر' : 'Source', value: task.source || '—' },
      ...(task.related_message_id
        ? [{ label: isAr ? 'رسالة مرتبطة' : 'Related message', value: task.related_message_id }]
        : []),
    ],
    source: 'hr_task',
  }
}

function issueFromOutbound(m: OutboundFollowUpMessage, isAr: boolean): LiveIssue | null {
  // Rows already covered by an open HR task stay on the task path (one follow-up path).
  if (m.has_task) return null
  const bucket = outboundBucket(m)
  const statusLabel =
    bucket === 'failed'
      ? isAr
        ? 'فشل'
        : 'Failed'
      : bucket === 'retrying'
        ? isAr
          ? 'إعادة محاولة لاحقاً'
          : 'Retrying later'
        : bucket === 'needs_follow_up'
          ? isAr
            ? 'يحتاج متابعة'
            : 'Needs follow-up'
          : isAr
            ? 'معلومة'
            : 'Info'
  // Owning-module deep link from flow when obvious; otherwise non-actionable guidance.
  const flow = String(m.flow || '').toLowerCase()
  let page: Page | null = null
  if (flow.includes('onboard')) page = 'onboarding'
  else if (flow.includes('compliance')) page = 'compliance'
  else if (flow.includes('leave')) page = 'leave'
  else if (flow.includes('shift')) page = 'shifts'
  else if (flow.includes('attend')) page = 'attendance'
  else if (flow.includes('payroll')) page = 'payroll'

  const primary: LiveIssue['primary'] =
    bucket === 'retrying' || m.kind === 'info'
      ? { kind: 'status', label: m.suggested_action || (isAr ? 'لا إجراء مطلوب' : 'No action needed') }
      : page
        ? {
            kind: 'navigate',
            page,
            label:
              page === 'onboarding'
                ? isAr
                  ? 'فتح التهيئة'
                  : 'Open Onboarding'
                : page === 'compliance'
                  ? isAr
                    ? 'فتح الامتثال'
                    : 'Open Compliance'
                  : isAr
                    ? 'فتح الوحدة'
                    : 'Open module',
          }
        : { kind: 'status', label: m.suggested_action || (isAr ? 'تواصل مباشرة' : 'Contact directly') }

  return {
    id: `outbound:${m.message_id}`,
    bucket: bucket === 'all' ? 'all' : bucket,
    recipient: m.employee_name || (isAr ? 'موظف' : 'Employee'),
    purpose: m.flow_label || (isAr ? 'رسالة موظف' : 'Employee message'),
    channel: isAr ? 'رسالة موظف' : 'Employee message',
    reason: m.reason,
    when: fmtWhen(m.last_attempt_at, isAr),
    statusLabel,
    primary,
    details: [
      { label: isAr ? 'الحالة' : 'Status', value: String(m.status) },
      { label: isAr ? 'المحاولات' : 'Attempts', value: m.attempts != null ? String(m.attempts) : '—' },
      { label: isAr ? 'معرّف الرسالة' : 'Message id', value: m.message_id },
      { label: isAr ? 'الإرشاد' : 'Guidance', value: m.suggested_action || '—' },
    ],
    source: 'outbound',
  }
}

export function NotificationsPage({
  access,
  permissions = [],
  onNotice,
  onAccessIssue,
  actionItems,
  enabledModules,
  notifications,
  onNavigate,
  posthireEnabled = false,
  notificationsFeedError = false,
}: {
  access?: DashboardAccess
  permissions?: string[]
  role?: string | null
  onNotice?: (message: string, tone?: 'success' | 'error' | 'info') => void
  onAccessIssue?: (issue: AccessIssue) => void
  actionItems: NotificationActionItem[]
  /** @deprecated Delivery now lives in this page; kept for App compatibility. */
  deliveryCenter?: ReactNode
  enabledModules?: string[]
  notifications: NotificationRow[]
  onNavigate: (page: Page) => void
  posthireEnabled?: boolean
  notificationsFeedError?: boolean
}) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [filter, setFilter] = useUrlBackedTab<IssueFilter>('notifications', ALERT_FILTERS, 'needs_follow_up')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [openTasks, setOpenTasks] = useState<HrTask[]>([])
  const [resolvedTasks, setResolvedTasks] = useState<HrTask[]>([])
  const [outbound, setOutbound] = useState<OutboundFollowUpMessage[]>([])
  const [openTotal, setOpenTotal] = useState(0)
  const [outboundTotal, setOutboundTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const alertsRequestIdRef = useRef(0)
  const alertsPaintedRef = useRef(false)
  const canManage = canManageAlertsAndDelivery(permissions)

  const scopedRows = useMemo(
    () => moduleScopedNotificationRows(notifications, enabledModules),
    [notifications, enabledModules],
  )

  const reload = useCallback(async () => {
    if (!canManage) {
      setOpenTasks([])
      setResolvedTasks([])
      setOutbound([])
      setOpenTotal(0)
      setOutboundTotal(0)
      setLoading(false)
      setRefreshing(false)
      setError(null)
      return
    }
    if (!access || !posthireEnabled) {
      setOpenTasks([])
      setResolvedTasks([])
      setOutbound([])
      setOpenTotal(0)
      setOutboundTotal(0)
      setLoading(false)
      setRefreshing(false)
      setError(null)
      return
    }
    const requestId = ++alertsRequestIdRef.current
    const cold = !alertsPaintedRef.current
    if (cold) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const [openRes, resolvedRes, outboundRes] = await Promise.all([
        getHrTasks(access, 'open', { limit: 50 }),
        getHrTasks(access, 'done', { limit: 50 }),
        getOutboundNeedsFollowUp(access, { limit: 50 }),
      ])
      if (requestId !== alertsRequestIdRef.current) return
      setOpenTasks(openRes.tasks ?? [])
      setOpenTotal(openRes.open_count ?? openRes.total ?? openRes.tasks?.length ?? 0)
      setResolvedTasks(resolvedRes.tasks ?? [])
      setOutbound(outboundRes.messages ?? [])
      setOutboundTotal(outboundRes.total ?? outboundRes.messages?.length ?? 0)
      alertsPaintedRef.current = true
    } catch (err) {
      if (requestId !== alertsRequestIdRef.current) return
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        setError(friendlyError(err, isAr ? 'تعذر تحميل التنبيهات والتسليم.' : 'We couldn’t load Alerts & Delivery.'))
        return
      }
      setError(friendlyError(err, isAr ? 'تعذر تحميل التنبيهات والتسليم.' : 'We couldn’t load Alerts & Delivery.'))
    } finally {
      if (requestId === alertsRequestIdRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [access, canManage, posthireEnabled, onAccessIssue, isAr])

  useVisibilitySoftPoll(reload, FRESHNESS_MS.notifications, Boolean(canManage && access && posthireEnabled))

  useEffect(() => {
    void reload()
  }, [reload])

  const liveIssues = useMemo(() => {
    const actionIssues = actionItems
      .map((item) => issueFromActionItem(item, enabledModules, isAr))
      .filter((item): item is LiveIssue => Boolean(item))
    const prehireIssues = scopedRows.map((row) => issueFromPrehireRow(row, isAr))
    const taskIssues = openTasks.map((task) => issueFromHrTask(task, isAr, false))
    const resolvedIssues = resolvedTasks.map((task) => issueFromHrTask(task, isAr, true))
    const outboundIssues = outbound
      .map((m) => issueFromOutbound(m, isAr))
      .filter((item): item is LiveIssue => Boolean(item))

    const merged = [...taskIssues, ...outboundIssues, ...prehireIssues, ...actionIssues, ...resolvedIssues]
    // Stable-ish order: needs_follow_up, failed, retrying, then others; resolved last
    const rank: Record<string, number> = { needs_follow_up: 0, failed: 1, retrying: 2, all: 3, resolved: 4 }
    return merged.sort((a, b) => (rank[a.bucket] ?? 9) - (rank[b.bucket] ?? 9))
  }, [actionItems, enabledModules, isAr, scopedRows, openTasks, resolvedTasks, outbound])

  const filtered = useMemo(() => {
    if (filter === 'all') return liveIssues.filter((i) => i.bucket !== 'resolved')
    if (filter === 'resolved') return liveIssues.filter((i) => i.bucket === 'resolved')
    if (filter === 'retrying') return liveIssues.filter((i) => i.bucket === 'retrying')
    if (filter === 'failed') return liveIssues.filter((i) => i.bucket === 'failed')
    return liveIssues.filter((i) => i.bucket === 'needs_follow_up')
  }, [liveIssues, filter])

  const counts = useMemo(() => {
    const needs = liveIssues.filter((i) => i.bucket === 'needs_follow_up').length
    const failed = liveIssues.filter((i) => i.bucket === 'failed').length
    const retrying = liveIssues.filter((i) => i.bucket === 'retrying').length
    const resolved = liveIssues.filter((i) => i.bucket === 'resolved').length
    const live = liveIssues.filter((i) => i.bucket !== 'resolved').length
    return { needs, failed, retrying, resolved, live }
  }, [liveIssues])

  const resolveTask = async (taskId: string, expectedStatus: string) => {
    if (!access) return
    setResolvingId(taskId)
    try {
      await resolveHrTask(access, taskId, 'done', expectedStatus)
      onNotice?.(isAr ? 'وُسم كمكتمل.' : 'Marked as done.', 'success')
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      if (isStaleDecision(err)) {
        // Another HR user already moved this task; show them the truth instead
        // of overwriting it.
        onNotice?.(
          isAr ? 'تغيّرت هذه المهمة منذ أن راجعتها. تم التحديث.' : 'This task changed since you reviewed it. Refreshed.',
          'error',
        )
        await reload()
        return
      }
      onNotice?.(friendlyError(err, isAr ? 'تعذر تحديث المهمة.' : 'We could not update that task.'), 'error')
    } finally {
      setResolvingId(null)
    }
  }

  const loadMoreOutbound = async () => {
    if (!access) return
    setLoadingMore(true)
    try {
      const res = await getOutboundNeedsFollowUp(access, { limit: 50, offset: outbound.length })
      setOutbound((prev) => [...prev, ...(res.messages ?? [])])
    } catch (err) {
      onNotice?.(friendlyError(err, isAr ? 'تعذر تحميل المزيد.' : 'We couldn’t load more issues.'), 'error')
    } finally {
      setLoadingMore(false)
    }
  }

  const filterChips: Array<{ key: IssueFilter; label: string; count: number }> = [
    { key: 'needs_follow_up', label: isAr ? 'يحتاج متابعة' : 'Needs follow-up', count: counts.needs },
    { key: 'failed', label: isAr ? 'فشل' : 'Failed', count: counts.failed },
    { key: 'retrying', label: isAr ? 'إعادة محاولة' : 'Retrying', count: counts.retrying },
    { key: 'resolved', label: isAr ? 'تم الحل' : 'Resolved', count: counts.resolved },
    { key: 'all', label: isAr ? 'الكل' : 'All', count: counts.live },
  ]

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="alerts-delivery-workspace" data-alerts-delivery>
      {!canManage ? (
        <ResourceState
          kind="forbidden"
          locale={isAr ? 'ar' : 'en'}
          testId="alerts-forbidden"
        />
      ) : null}
      {canManage ? (
      <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="min-w-0 max-w-2xl text-[12px] text-subtle/80" data-alerts-summary>
          {error || notificationsFeedError
            ? isAr
              ? 'تعذر تحميل بعض مشاكل التسليم'
              : 'Some delivery issues could not be loaded'
            : counts.live
            ? isAr
              ? `${counts.live} مشكلة تسليم تحتاج انتباهاً`
              : `${counts.live} delivery issue${counts.live === 1 ? '' : 's'} need attention`
            : isAr
              ? 'لا مشاكل تسليم تحتاج انتباهاً الآن'
              : 'No delivery issues need attention right now'}
          {openTotal ? ` · ${isAr ? 'مهام مفتوحة' : 'open tasks'} ${openTotal}` : ''}
        </p>
      </div>

      <div data-alerts-filters>
        <HrSurfaceTabs
          ariaLabel={isAr ? 'تصفية مشاكل التسليم' : 'Delivery issue filters'}
          items={filterChips.map((chip) => ({
            id: chip.key,
            label: chip.label,
            count: chip.count,
          }))}
          onChange={setFilter}
          trailing={
            <Button variant="ghost" size="sm" onClick={() => void reload()} disabled={loading || refreshing} aria-label={isAr ? 'تحديث' : 'Refresh'}>
              {loading || refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
          }
          value={filter}
        />
      </div>

      {refreshing && !loading ? (
        <p className="text-[11px] text-subtle" data-alerts-refreshing data-rendering-soft-status>
          {isAr ? 'جاري التحديث…' : 'Updating…'}
        </p>
      ) : null}

      {loading && liveIssues.length === 0 ? (
        <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="alerts-delivery-state" />
      ) : error || notificationsFeedError ? (
        <ResourceState
          kind="error"
          locale={isAr ? 'ar' : 'en'}
          title={error || undefined}
          onRetry={() => void reload()}
          retrying={loading || refreshing}
          testId="alerts-delivery-state"
        />
      ) : filtered.length === 0 ? (
        <div data-alerts-empty>
          <EmptyState
            text={
              filter === 'retrying'
                ? isAr
                  ? 'إعادة المحاولة التلقائية تعمل في الخلفية. عندما تحتاجك محاولة، تظهر تحت يحتاج متابعة أو فشل.'
                  : 'Automatic retries run in the background. When a retry needs you, it appears under Needs follow-up or Failed.'
                : filter === 'resolved'
                  ? isAr
                    ? 'لا مهام محلولة في هذه الصفحة بعد.'
                    : 'No resolved follow-ups in this view yet.'
                  : isAr
                    ? 'كل شيء على ما يرام — لا مشاكل تسليم هنا.'
                    : 'All clear — no delivery issues in this view.'
            }
          />
        </div>
      ) : (
        <section className="space-y-3" data-alerts-issues>
          {filtered.map((issue) => {
            const expanded = expandedId === issue.id
            return (
              <div
                key={issue.id}
                className="rounded-[1.25rem] border border-semantic-line/55 bg-semantic-surface/80 px-4 py-3"
                data-alerts-issue
                data-issue-bucket={issue.bucket}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={issue.bucket === 'failed' ? 'danger' : issue.bucket === 'needs_follow_up' ? 'warning' : 'muted'}>
                        {issue.statusLabel}
                      </Badge>
                      <span className="text-[12px] text-subtle/80">{issue.purpose}</span>
                      <span className="text-[12px] text-subtle/70">· {issue.channel}</span>
                    </div>
                    <p className="text-[14px] font-semibold text-ink">{issue.recipient}</p>
                    <p className="text-[13px] text-muted">{issue.reason}</p>
                    {issue.when ? (
                      <p className="text-[12px] text-subtle/85">
                        {isAr ? 'آخر محاولة' : 'Latest attempt'}: {issue.when}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {issue.primary.kind === 'resolve' && canManage ? (
                      <Button
                        size="sm"
                        disabled={resolvingId === issue.primary.taskId}
                        onClick={() =>
                          void resolveTask(
                            issue.primary.kind === 'resolve' ? issue.primary.taskId : '',
                            issue.primary.kind === 'resolve' ? issue.primary.expectedStatus : 'open',
                          )
                        }
                      >
                        {resolvingId === (issue.primary.kind === 'resolve' ? issue.primary.taskId : '') ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        )}
                        {issue.primary.label}
                      </Button>
                    ) : null}
                    {issue.primary.kind === 'resolve' && !canManage ? (
                      <span className="text-[12px] text-subtle">{isAr ? 'للقراءة فقط' : 'Read only'}</span>
                    ) : null}
                    {issue.primary.kind === 'navigate' ? (
                      <Button size="sm" onClick={() => onNavigate(issue.primary.kind === 'navigate' ? issue.primary.page : 'notifications')}>
                        {issue.primary.label}
                      </Button>
                    ) : null}
                    {issue.primary.kind === 'status' ? (
                      <span className="max-w-[220px] text-[12px] leading-5 text-subtle" data-alerts-status-cta>
                        {issue.primary.label}
                      </span>
                    ) : null}
                    <Button variant="ghost" size="sm" onClick={() => setExpandedId(expanded ? null : issue.id)}>
                      {expanded ? (isAr ? 'إخفاء التفاصيل' : 'Hide details') : isAr ? 'التفاصيل' : 'Details'}
                    </Button>
                  </div>
                </div>
                {expanded ? (
                  <div className="mt-3 space-y-1 border-t border-line/50 pt-3 text-[12.5px] text-muted" data-alerts-issue-detail>
                    {issue.details.map((d) => (
                      <p key={d.label}>
                        <span className="font-medium text-text">{d.label}: </span>
                        {d.value}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </section>
      )}

      {posthireEnabled && outbound.length > 0 && outbound.length < outboundTotal ? (
        <LoadMoreBar
          loaded={outbound.length}
          total={outboundTotal}
          loading={loadingMore}
          onLoadMore={() => void loadMoreOutbound()}
          noun={isAr ? 'رسالة' : 'message'}
        />
      ) : null}

      <p className="text-[11.5px] text-subtle/75" data-alerts-ownership>
        {isAr
          ? 'التنبيهات والتسليم تملك فشل التواصل. محتوى الرسالة ومسار العمل يبقى لدى الوحدة الأصلية.'
          : 'Alerts & Delivery owns communication failures. Message content and business workflow stay with the originating module.'}
      </p>
      </>
      ) : null}
    </div>
  )
}
