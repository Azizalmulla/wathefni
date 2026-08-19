import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ChevronDown, ChevronUp, Download, Loader2, RotateCcw, Search, ShieldAlert } from 'lucide-react'

import { DashboardApiError, downloadCompanyActivityCsv, getCompanyActivity } from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { ResourceState } from '@/pages/shared/dataState'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { ActivityActorOption, ActivityItem, ActivityResponse, DashboardAccess } from '@/types'

const PAGE_SIZE = 50

/** HR-facing verbs for known action types (mirrors backend AUDIT_ACTION_LABELS; display only). */
const ACTION_VERBS_EN: Record<string, string> = {
  approve_leave_request: 'Approved a leave request',
  reject_leave_request: 'Declined a leave request',
  cancel_leave_request: 'Cancelled a leave request',
  request_leave: 'Filed a leave request',
  export_payroll: 'Exported payroll',
  preview_payroll: 'Previewed payroll',
  payroll_export_downloaded: 'Downloaded a payroll export',
  set_payroll_policy: 'Updated the payroll policy',
  create_timesheet_review: 'Started a timesheet review',
  approve_timesheet: 'Approved a timesheet',
  reject_timesheet: 'Rejected a timesheet',
  employee_created: 'Added an employee',
  employee_updated: 'Edited an employee',
  employee_marked_left: 'Marked an employee as left',
  employee_reactivated: 'Reactivated an employee',
  employees_imported: 'Imported employees',
  start_onboarding: 'Started onboarding',
  send_onboarding_reminder: 'Sent an onboarding reminder',
  document_uploaded: 'Uploaded a document',
  document_downloaded: 'Downloaded a document',
  create_shift_assignment: 'Assigned a shift',
  replace_conflicting_shift_assignment: 'Reassigned a shift',
  cancel_shift_assignment: 'Cancelled a shift',
  shift_cancelled: 'Cancelled a shift',
  shift_rescheduled: 'Rescheduled a shift',
  request_shift_swap: 'Requested a shift swap',
  approve_shift_swap: 'Approved a shift swap',
  reject_shift_swap: 'Declined a shift swap',
  check_in_employee: 'Recorded a check-in',
  check_out_employee: 'Recorded a check-out',
  mark_attendance_absent: 'Marked attendance as absent',
  correct_attendance_record: 'Corrected an attendance record',
  attendance_exported: 'Exported attendance',
  hire_candidate: 'Hired a candidate',
  reject_candidate: 'Rejected a candidate',
  shortlist_candidate: 'Shortlisted a candidate',
  notify_candidate: 'Messaged a candidate',
  send_assessment: 'Sent an assessment',
  send_video_interview: 'Sent a video interview',
  schedule_interview: 'Scheduled an interview',
  schedule_candidate_meeting: 'Scheduled a meeting',
  team_member_invited: 'Invited a team member',
  team_member_updated: 'Updated a team member',
  team_member_role_changed: "Changed a team member's role",
  team_member_deactivated: 'Deactivated a team member',
  team_member_reactivated: 'Reactivated a team member',
  team_whatsapp_linked: 'Linked a WhatsApp number',
  org_assignment_saved: "Updated an employee's org placement",
  org_manager_scope_saved: 'Granted a manager scope',
  org_manager_scope_removed: 'Removed a manager scope',
  hr_task_resolved: 'Resolved an HR task',
  create_job_opening: 'Created a job opening',
  close_job_opening: 'Closed a job opening',
  reopen_job_opening: 'Reopened a job opening',
  onboarding_mark_item: 'Marked an onboarding item',
  send_email: 'Sent an email',
  send_custom_employee_message: 'Sent a message to an employee',
  retry_last_employee_message: 'Resent a message to an employee',
}

const ACTION_VERBS_AR: Record<string, string> = {
  approve_leave_request: 'وافق على طلب إجازة',
  reject_leave_request: 'رفض طلب إجازة',
  cancel_leave_request: 'ألغى طلب إجازة',
  request_leave: 'قدّم طلب إجازة',
  export_payroll: 'صدّر الرواتب',
  preview_payroll: 'معاينة الرواتب',
  employee_created: 'أضاف موظفاً',
  employee_updated: 'عدّل موظفاً',
  employee_marked_left: 'وضع علامة مغادر على موظف',
  start_onboarding: 'بدأ التهيئة',
  send_onboarding_reminder: 'أرسل تذكير تهيئة',
  document_uploaded: 'رفع مستنداً',
  hire_candidate: 'وظّف مرشّحاً',
  team_member_invited: 'دعى عضو فريق',
  hr_task_resolved: 'أنهى مهمة موارد بشرية',
}

const STATUS_META: Record<string, { labelEn: string; labelAr: string; tone: 'success' | 'warning' | 'danger' | 'muted' }> = {
  completed: { labelEn: 'Done', labelAr: 'تم', tone: 'success' },
  failed: { labelEn: 'Failed', labelAr: 'فشل', tone: 'danger' },
  needs_confirmation: { labelEn: 'Needs confirmation', labelAr: 'يحتاج تأكيداً', tone: 'warning' },
  needs_clarification: { labelEn: 'Needs clarification', labelAr: 'يحتاج توضيحاً', tone: 'warning' },
  needs_backend_tool: { labelEn: 'In progress', labelAr: 'قيد التنفيذ', tone: 'muted' },
  partial: { labelEn: 'Partly done', labelAr: 'جزئي', tone: 'muted' },
  candidate_ambiguous: { labelEn: 'Candidate unclear', labelAr: 'مرشّح غير واضح', tone: 'warning' },
  candidate_not_found: { labelEn: 'Candidate not found', labelAr: 'المرشّح غير موجود', tone: 'warning' },
  needs_candidate_reference: { labelEn: 'Needs a candidate', labelAr: 'يحتاج مرشّحاً', tone: 'warning' },
}

type Filters = {
  start_date: string
  end_date: string
  actor: string
  category: string
  action_type: string
  status: string
  q: string
}

const EMPTY_FILTERS: Filters = {
  start_date: '',
  end_date: '',
  actor: '',
  category: 'all',
  action_type: '',
  status: 'all',
  q: '',
}

function humanizeActionType(actionType: string, isAr: boolean): string {
  if (isAr && ACTION_VERBS_AR[actionType]) return ACTION_VERBS_AR[actionType]
  if (ACTION_VERBS_EN[actionType]) return ACTION_VERBS_EN[actionType]
  return actionType.replace(/[_\s]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

function statusMeta(status: string | null | undefined, isAr: boolean) {
  const key = String(status || 'completed')
  const known = STATUS_META[key]
  if (known) return { label: isAr ? known.labelAr : known.labelEn, tone: known.tone }
  if (!status) return { label: isAr ? 'تم' : 'Done', tone: 'success' as const }
  const label = status.replace(/[_\s]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  return { label, tone: 'muted' as const }
}

function startOfDay(date: Date): Date {
  const out = new Date(date)
  out.setHours(0, 0, 0, 0)
  return out
}

function dateGroup(at: string | null, isAr: boolean): { key: string; label: string } {
  if (!at) return { key: 'unknown', label: isAr ? 'سابقاً' : 'Earlier' }
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return { key: 'unknown', label: isAr ? 'سابقاً' : 'Earlier' }
  const today = startOfDay(new Date())
  const that = startOfDay(date)
  const diffDays = Math.round((today.getTime() - that.getTime()) / 86_400_000)
  const dayKey = that.toISOString().slice(0, 10)
  const locale = isAr ? 'ar-KW' : 'en-GB'
  if (diffDays <= 0) return { key: 'today', label: isAr ? 'اليوم' : 'Today' }
  if (diffDays === 1) return { key: 'yesterday', label: isAr ? 'أمس' : 'Yesterday' }
  if (diffDays < 7) return { key: dayKey, label: date.toLocaleDateString(locale, { weekday: 'long' }) }
  return {
    key: dayKey,
    label: date.toLocaleDateString(locale, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }),
  }
}

function formatTime(at: string | null, isAr: boolean): string {
  if (!at) return '—'
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString(isAr ? 'ar-KW' : 'en-GB', { hour: 'numeric', minute: '2-digit' })
}

function actorOptionLabel(actor: ActivityActorOption): string {
  const name = actor.name?.trim()
  if (name) return actor.role_label ? `${name} · ${actor.role_label}` : name
  return actor.email || 'Team member'
}

function actorDisplay(item: ActivityItem): string {
  return item.actor.display || item.actor.name || item.actor.email || '—'
}

export function ActivityLog({
  access,
  onAccessIssue,
}: {
  access: DashboardAccess
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [items, setItems] = useState<ActivityItem[]>([])
  const [meta, setMeta] = useState<{ total: number; hasMore: boolean; actors: ActivityActorOption[]; categories: string[] } | null>(
    null,
  )
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hasItemsRef = useRef(false)
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    hasItemsRef.current = items.length > 0
  }, [items.length])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedQuery(filters.q.trim()), 350)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [filters.q])

  const apiFilters = useMemo(
    () => ({
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      actor: filters.actor || undefined,
      category: filters.category,
      action_type: filters.action_type || undefined,
      q: debouncedQuery || undefined,
    }),
    [filters.start_date, filters.end_date, filters.actor, filters.category, filters.action_type, debouncedQuery],
  )

  const load = useCallback(
    async (nextOffset: number, append: boolean) => {
      if (append) setLoadingMore(true)
      else if (!hasItemsRef.current) setLoading(true)
      else setRefreshing(true)
      setError('')
      try {
        const response: ActivityResponse = await getCompanyActivity(access, {
          ...apiFilters,
          limit: PAGE_SIZE,
          offset: nextOffset,
        })
        setItems((current) => (append ? [...current, ...response.items] : response.items))
        setMeta({
          total: response.total,
          hasMore: response.has_more,
          actors: response.actors || [],
          categories: response.categories || [],
        })
        setOffset(nextOffset)
        setPermissionDenied(false)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          setError(isAr ? 'تعذر تحميل سجل النشاط. حاول مرة أخرى.' : 'We couldn’t load the activity log right now. Please try again.')
          return
        }
        if (err instanceof DashboardApiError && err.status === 403) {
          setPermissionDenied(true)
          return
        }
        setError(isAr ? 'تعذر تحميل سجل النشاط. حاول مرة أخرى.' : 'We couldn’t load the activity log right now. Please try again.')
      } finally {
        setLoading(false)
        setLoadingMore(false)
        setRefreshing(false)
      }
    },
    [access, apiFilters, onAccessIssue, isAr],
  )

  useEffect(() => {
    void load(0, false)
  }, [load])

  const actionTypeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const item of items) {
      if (item.action_type) set.add(item.action_type)
    }
    if (filters.action_type) set.add(filters.action_type)
    return [...set].sort()
  }, [items, filters.action_type])

  const visibleItems = useMemo(() => {
    if (filters.status === 'all') return items
    if (filters.status === 'done') return items.filter((i) => !i.status || i.status === 'completed')
    return items.filter((i) => String(i.status || '') === filters.status)
  }, [items, filters.status])

  const groups = useMemo(() => {
    const out: { key: string; label: string; items: ActivityItem[] }[] = []
    const index = new Map<string, number>()
    for (const item of visibleItems) {
      const { key, label } = dateGroup(item.at, isAr)
      let i = index.get(key)
      if (i === undefined) {
        i = out.length
        index.set(key, i)
        out.push({ key, label, items: [] })
      }
      out[i].items.push(item)
    }
    return out
  }, [visibleItems, isAr])

  const filtersActive = Boolean(
    filters.start_date ||
      filters.end_date ||
      filters.actor ||
      (filters.category && filters.category !== 'all') ||
      filters.action_type ||
      (filters.status && filters.status !== 'all') ||
      filters.q,
  )

  async function exportCsv() {
    setExporting(true)
    setError('')
    try {
      await downloadCompanyActivityCsv(access, apiFilters)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(isAr ? 'تعذر تصدير سجل النشاط.' : 'We couldn’t export the activity log. Please try again.')
    } finally {
      setExporting(false)
    }
  }

  if (permissionDenied) {
    return (
      <div
        className="rounded-[1.25rem] border border-line/55 bg-white/80 px-4 py-5 text-[13px] text-muted"
        dir={isAr ? 'rtl' : 'ltr'}
        lang={locale}
        data-testid="activity-workspace"
        data-activity-denied
      >
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 shrink-0 text-subtle" size={18} />
          <div>
            <p className="font-medium text-ink">
              {isAr ? 'النشاط متاح للمالكين ومسؤولي الموارد البشرية' : 'Activity is visible to Owners and HR Admins'}
            </p>
            <p className="mt-1 leading-6">
              {isAr
                ? 'اطلب من مالك الشركة أو مسؤول الموارد البشرية إذا احتجت مراجعة من فعل ماذا.'
                : 'Ask a company Owner or HR Admin if you need to review who did what.'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="activity-workspace" data-activity-timeline>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-2xl space-y-1">
          <p className="text-[13px] text-subtle/90">
            {isAr
              ? 'جدول زمني موثوق للقراءة فقط لأهم نشاط الشركة والموارد البشرية.'
              : 'A clear, trustworthy, read-only timeline of important company and HR activity.'}
          </p>
          <p className="text-[12px] text-subtle/80" data-activity-summary>
            {meta
              ? isAr
                ? `${meta.total} حدث`
                : `${meta.total} event${meta.total === 1 ? '' : 's'}`
              : isAr
                ? 'سجل تدقيق على مستوى الشركة'
                : 'Company-wide audit timeline'}
            {filtersActive && meta ? (isAr ? ' · مطابق للتصفية' : ' · matching filters') : ''}
          </p>
        </div>
        <Button onClick={() => void exportCsv()} type="button" variant="secondary" size="sm" disabled={exporting || loading} data-activity-export>
          {exporting ? <Loader2 className="animate-spin" size={16} /> : <Download size={16} />}
          {isAr ? 'تصدير CSV' : 'Export CSV'}
        </Button>
      </div>

      <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3" data-activity-filters>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'من' : 'From'}
          <Input type="date" value={filters.start_date} onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'إلى' : 'To'}
          <Input type="date" value={filters.end_date} onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'المنفّذ' : 'Actor'}
          <Select value={filters.actor} onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}>
            <option value="">{isAr ? 'الجميع' : 'Everyone'}</option>
            {(meta?.actors || []).map((actor) => (
              <option key={actor.user_id || actor.email || actorOptionLabel(actor)} value={actor.user_id || actor.email || ''}>
                {actorOptionLabel(actor)}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'الوحدة / الفئة' : 'Module / category'}
          <Select value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}>
            <option value="all">{isAr ? 'كل الفئات' : 'All categories'}</option>
            {(meta?.categories || []).map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'الإجراء' : 'Action'}
          <Select value={filters.action_type} onChange={(e) => setFilters((f) => ({ ...f, action_type: e.target.value }))}>
            <option value="">{isAr ? 'كل الإجراءات' : 'All actions'}</option>
            {actionTypeOptions.map((actionType) => (
              <option key={actionType} value={actionType}>
                {humanizeActionType(actionType, isAr)}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle">
          {isAr ? 'النتيجة' : 'Result'}
          <Select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
            <option value="all">{isAr ? 'كل النتائج' : 'All results'}</option>
            <option value="done">{isAr ? 'تم' : 'Done'}</option>
            <option value="failed">{isAr ? 'فشل' : 'Failed'}</option>
            <option value="needs_confirmation">{isAr ? 'يحتاج تأكيداً' : 'Needs confirmation'}</option>
            <option value="partial">{isAr ? 'جزئي' : 'Partly done'}</option>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-subtle md:col-span-2 xl:col-span-3">
          {isAr ? 'بحث' : 'Search'}
          <div className="relative">
            <Search
              className={cn('pointer-events-none absolute top-1/2 -translate-y-1/2 text-subtle/70', isAr ? 'right-3' : 'left-3')}
              size={15}
            />
            <Input
              className={cn('w-full', isAr ? 'pr-9' : 'pl-9')}
              placeholder={isAr ? 'ابحث في النشاط…' : 'Find an activity…'}
              value={filters.q}
              onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
            />
          </div>
        </label>
      </div>

      {filtersActive ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-subtle">
            {meta
              ? isAr
                ? `${visibleItems.length} معروض من ${meta.total}`
                : `${visibleItems.length} shown of ${meta.total}`
              : ''}
          </span>
          <button
            type="button"
            onClick={() => setFilters(EMPTY_FILTERS)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-subtle underline-offset-2 hover:text-text hover:underline"
          >
            <RotateCcw size={13} /> {isAr ? 'مسح التصفية' : 'Clear filters'}
          </button>
        </div>
      ) : null}

      {refreshing && items.length > 0 ? (
        <div className="flex h-7 items-center gap-2 text-xs text-subtle" data-activity-refreshing aria-live="polite">
          <Loader2 className="animate-spin" size={14} /> {isAr ? 'جارٍ التحديث…' : 'Updating…'}
        </div>
      ) : null}

      {loading ? (
        <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="activity-list-state" />
      ) : error ? (
        <div data-activity-error>
          <ResourceState
            kind="error"
            locale={isAr ? 'ar' : 'en'}
            title={error}
            onRetry={() => void load(0, false)}
            retrying={loading}
            testId="activity-list-state"
          />
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="rounded-[1.25rem] border border-line/60 bg-white/45 px-4 py-10 text-center" data-activity-empty>
          <Activity className="mx-auto mb-2 text-subtle/70" size={20} />
          <div className="text-sm font-medium text-text">
            {filtersActive
              ? isAr
                ? 'لا نشاط يطابق هذه التصفية'
                : 'No activity matches these filters'
              : isAr
                ? 'لا نشاط مسجّل بعد'
                : 'No activity recorded yet'}
          </div>
          <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-subtle">
            {filtersActive
              ? isAr
                ? 'وسّع التاريخ أو امسح التصفية.'
                : 'Try widening the date range or clearing filters.'
              : isAr
                ? 'عند موافقة الإجازات وتشغيل الرواتب وتحديث الموظفين، يظهر ذلك هنا.'
                : 'As your team approves leave, runs payroll, updates employees, and more, it will appear here.'}
          </p>
        </div>
      ) : (
        <div className="space-y-5" data-activity-list>
          {groups.map((group) => (
            <section key={group.key}>
              <div className="mb-2 flex items-center gap-3">
                <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{group.label}</h3>
                <span className="h-px flex-1 bg-line/55" />
                <span className="text-[11px] text-subtle/70 tabular-nums">{group.items.length}</span>
              </div>
              <ul className="overflow-hidden rounded-[1.25rem] border border-line/55 divide-y divide-line/40">
                {group.items.map((item) => {
                  const outcome = statusMeta(item.status, isAr)
                  const who = actorDisplay(item)
                  const what = humanizeActionType(item.action_type, isAr)
                  const affected = item.target?.trim() || (isAr ? '—' : '—')
                  const expanded = expandedId === item.id
                  return (
                    <li
                      key={item.id}
                      className={cn(
                        'px-4 py-3 transition-colors',
                        item.sensitive ? 'border-s-2 border-s-[#c89445] bg-[#fffaf0] hover:bg-[#fff6e6]' : 'bg-white/45 hover:bg-white/70',
                      )}
                      data-activity-event
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone={outcome.tone}>{outcome.label}</Badge>
                            {item.sensitive ? <Badge tone="warning">{isAr ? 'حسّاس' : 'Sensitive'}</Badge> : null}
                            <span className="text-[12px] text-subtle/80">{item.category}</span>
                            <span className="text-[12px] text-subtle/70">{formatTime(item.at, isAr)}</span>
                          </div>
                          <p className="text-[14px] font-semibold text-ink">{who}</p>
                          <p className="text-[13px] text-muted">{what}</p>
                          <p className="text-[12.5px] text-subtle/85">
                            <span className="font-medium text-subtle">{isAr ? 'المتأثر' : 'Affected'}: </span>
                            {affected}
                            {item.actor.role_label ? (
                              <>
                                <span aria-hidden> · </span>
                                {item.actor.role_label}
                              </>
                            ) : null}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setExpandedId(expanded ? null : item.id)}
                          data-activity-details-toggle
                        >
                          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          {expanded ? (isAr ? 'إخفاء' : 'Hide') : isAr ? 'التفاصيل' : 'Details'}
                        </Button>
                      </div>
                      {expanded ? (
                        <div className="mt-3 space-y-1 border-t border-line/50 pt-3 text-[12.5px] text-muted" data-activity-details>
                          <p>
                            <span className="font-medium text-text">{isAr ? 'نوع الإجراء' : 'Action type'}: </span>
                            {item.action_type}
                          </p>
                          <p>
                            <span className="font-medium text-text">{isAr ? 'معرّف الحدث' : 'Event id'}: </span>
                            {item.id}
                          </p>
                          <p>
                            <span className="font-medium text-text">{isAr ? 'الحالة الخام' : 'Raw status'}: </span>
                            {item.status || 'completed'}
                          </p>
                          {item.actor.email ? (
                            <p>
                              <span className="font-medium text-text">{isAr ? 'بريد المنفّذ' : 'Actor email'}: </span>
                              {item.actor.email}
                            </p>
                          ) : null}
                          <p className="text-[11.5px] text-subtle/75">
                            {isAr
                              ? 'سجل تدقيق للقراءة فقط — لا يمكن تعديل الأحداث من هذه الصفحة.'
                              : 'Read-only audit record — events cannot be changed from this page.'}
                          </p>
                        </div>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      {meta?.hasMore && !loading ? (
        <div className="flex justify-center pt-1">
          <Button onClick={() => void load(offset + PAGE_SIZE, true)} type="button" variant="secondary" disabled={loadingMore}>
            {loadingMore ? <Loader2 className="animate-spin" size={16} /> : null}
            {isAr ? 'تحميل المزيد' : 'Load more'}
          </Button>
        </div>
      ) : null}

      <p className="text-[11.5px] text-subtle/75" data-activity-ownership>
        {isAr
          ? 'النشاط هو سجل تدقيق على مستوى الشركة للقراءة فقط. سجل الموظف والوحدات المتخصصة تبقى منفصلة.'
          : 'Activity is the company-wide read-only audit timeline. Employee and specialist-module history stay separate.'}
      </p>
    </div>
  )
}
