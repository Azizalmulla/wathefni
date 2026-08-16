import {
  AlertTriangle,
  MoreHorizontal,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Clock,
  Inbox,
  DollarSign,
  Download,
  Eye,
  FileText,
  Info,
  Loader2,
  BarChart3,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  UserRound,
} from 'lucide-react'
import { type ChangeEvent, Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/field'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import { SearchInput, useDebouncedValue } from '@/components/ui/search-input'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { StatusPill } from '@/components/ui/page-chrome'
import { useConfirm, type ConfirmOptions } from '@/components/ConfirmDialog'
import { useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import {
  createEmployee,
  createEmployeeAppHandoff,
  DashboardApiError,
  type EmployeeImportResult,
  getHrTasks,
  getOutboundNeedsFollowUp,
  importEmployees,
  getPosthireAnalytics,
  getPosthireActionInbox,
  getPosthireAttendance,
  exportAttendanceCsv,
  getEmployeeProfile,
  updateEmployee,
  setEmployeeStatus,
  getEmployeeStatusApprovalPolicy,
  listEmployeeStatusPending,
  createEmployeeStatusApprovalRequest,
  cancelEmployeeStatusApprovalRequest,
  decideEmployeeStatusApprovalRequest,
  getPosthireCompliance,
  getPosthireEmployees,
  getEmployeeOrgUnits,
  getOnboardingDetail,
  getPosthireOnboarding,
  getPosthirePayroll,
  getPayrollExportDetail,
  downloadPayrollExportCsv,
  openEmployeeDocument,
  resolveHrTask,
  reviewEmployeeDocument,
  runPosthireAction,
  uploadEmployeeDocument,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { cn } from '@/lib/utils'
import { AttendanceImportDialog } from '@/posthire/AttendanceImport'
import { AttendanceCaptureOpsPanel } from '@/posthire/AttendanceCaptureOps'
import { AttendanceOpsPanel } from '@/posthire/AttendanceOpsPanel'
import { AttendanceAttentionStrip, AttendanceDailyTable } from '@/posthire/AttendanceDailyBoard'
import { AssignmentHistoryPanel, EssBankMaskPanel } from '@/posthire/employees360/ProfilePanels'
import { WorkforcePage } from '@/posthire/employees360/WorkforcePage'
import { LeaveWorkspace } from '@/posthire/LeaveWorkspace'
import { ShiftsWorkspace } from '@/posthire/ShiftsWorkspace'
import { ExternalPayrollWorkspace } from '@/posthire/ExternalPayrollWorkspace'
import { PayslipWorkspace } from '@/posthire/PayslipWorkspace'
import { CloseExportWorkspace } from '@/posthire/CloseExportWorkspace'
import { StatutoryWorksheetWorkspace } from '@/posthire/StatutoryWorksheetWorkspace'
import { payrollExternalCopy } from '@/posthire/payrollExternalUx'
import { onboardingPrimaryAction, type OnboardingPrimaryKind } from '@/posthire/onboardingPrimaryAction'
import type {
  ComplianceBucket,
  ComplianceDocument,
  ComplianceFinding,
  DashboardAccess,
  HrTask,
  HrTasksResponse,
  OutboundFollowUpMessage,
  OutboundNeedsFollowUpResponse,
  PosthireAnalyticsResponse,
  ActionInboxItem,
  PosthireActionInboxResponse,
  PosthireAttendanceResponse,
  PosthireAttendanceRow,
  EmployeeProfileResponse,
  EmployeeProfileNextAction,
  EmployeeProfileNextActionsSummary,
  NextActionSeverity,
  PosthireComplianceResponse,
  PosthireEmployeesResponse,
  PosthireEmployee,
  OnboardingDetailResponse,
  OnboardingItem,
  PosthireOnboardingResponse,
  PosthirePayrollPolicy,
  PosthirePayrollResponse,
  PosthireTimesheetRow,
  PayrollExportDetail,
} from '@/types'

export type PostHireModulePage =
  | 'employees'
  | 'workforce'
  | 'inbox'
  | 'onboarding'
  | 'attendance'
  | 'leave'
  | 'shifts'
  | 'payroll'
  | 'analytics'
  | 'compliance'

export type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

const MAX_EMPLOYEE_DOC_BYTES = 15 * 1024 * 1024
const SENSITIVE_DOC_KEYS = new Set([
  'civil_id',
  'passport',
  'residence',
  'residency',
  'residency_iqama',
  'work_permit',
  'medical',
  'personal_photo',
])

type PostHireProps = {
  page: PostHireModulePage
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue: (issue: AccessIssue) => void
  onOpenNotifications?: () => void
  onNavigate?: (page: string, opts?: { employee?: string }) => void
}

type PostHireCommonProps = Pick<PostHireProps, 'access' | 'permissions' | 'role' | 'onNotice' | 'onAccessIssue'>

// --- helpers ---------------------------------------------------------------

function can(permissions: string[], permission: string, _role?: string | null): boolean {
  return permissions.includes(permission)
}

function isSensitiveIdentityDocument(itemId: string, label?: string | null): boolean {
  const key = itemId.trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (SENSITIVE_DOC_KEYS.has(key)) return true
  const text = String(label || '').toLowerCase()
  return /\bcivil id\b|\bpassport\b|\bresidence\b|\bresidency\b|\bwork permit\b|\bmedical\b/.test(text)
}

// HR-facing copy for the error codes the post-hire backend can return, so we
// never surface a raw code, tool name, or technical message to the user.
const POSTHIRE_ERROR_MESSAGES: Record<string, string> = {
  permission_denied: 'You don’t have permission to do this.',
  module_disabled: 'This feature isn’t enabled for your company yet.',
  employee_not_found: 'We couldn’t find that employee.',
  employee_required: 'Please choose an employee first.',
  employee_outside_manager_scope: 'That employee is outside the team you manage.',
  timesheet_not_found: 'That timesheet is no longer available — try refreshing.',
  leave_not_found: 'That leave request is no longer available — try refreshing.',
  swap_not_found: 'That swap request is no longer available — try refreshing.',
  shift_conflict: 'That shift overlaps with another one. Adjust the time and try again.',
  invalid_date: 'Please check the dates and try again.',
  dashboard_auth_failed: 'Your session needs to be verified again. Please sign in.',
  dashboard_company_required: 'We couldn’t confirm your company. Please sign in again.',
}

// A message is "technical" if it looks like a code/identifier or carries
// backend internals — those must never reach the user.
function looksTechnical(message: string): boolean {
  return /(_|[{}[\]"<>]|backend|traceback|exception|psycopg|sql|stack|null|undefined|tool_|registry|module_disabled|auth_failed|not_found|permission_denied)/i.test(
    message,
  )
}

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof DashboardApiError) {
    const mapped = POSTHIRE_ERROR_MESSAGES[error.code]
    if (mapped) return mapped
    const message = error.message || ''
    return message && !looksTechnical(message) ? message : fallback
  }
  if (error instanceof Error && error.message && !looksTechnical(error.message)) return error.message
  return fallback
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'muted'

function statusTone(status?: string | null): Tone {
  const value = String(status || '').toLowerCase()
  if (['approved', 'present', 'complete', 'completed', 'done', 'active', 'exported'].includes(value)) return 'success'
  if (['late', 'requested', 'pending', 'draft', 'in_progress', 'review'].includes(value)) return 'warning'
  if (['absent', 'rejected', 'cancelled', 'overdue', 'failed', 'not_started'].includes(value)) return 'danger'
  return 'default'
}

function StatusBadge({ status }: { status?: string | null }) {
  const value = String(status || '').trim()
  if (!value) return <Badge tone="muted">Unknown</Badge>
  return <Badge tone={statusTone(value)}>{titleCase(value)}</Badge>
}

// --- shared layout ---------------------------------------------------------

function ModuleToolbar({ onRefresh, refreshing, actions }: { onRefresh: () => void; refreshing: boolean; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {actions}
      <Button variant="secondary" size="sm" onClick={onRefresh} disabled={refreshing}>
        <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
        Refresh
      </Button>
    </div>
  )
}

function NextAction({ tone, icon, title, detail }: { tone: Tone; icon: ReactNode; title: string; detail?: string }) {
  const toneClass =
    tone === 'danger'
      ? 'border-rose-200/70 bg-rose-50/60'
      : tone === 'warning'
        ? 'border-[#e2bd78]/70 bg-[#fff7e8]/70'
        : tone === 'success'
          ? 'border-emerald-200/70 bg-emerald-50/60'
          : 'border-line/60 bg-panel/70'
  return (
    <div className={cn('flex items-center gap-3 rounded-[1.4rem] border px-5 py-4 ring-1 ring-white/55', toneClass)}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/80 text-text shadow-sm">{icon}</div>
      <div className="min-w-0">
        <p className="text-[14px] font-semibold tracking-[-0.01em] text-text">{title}</p>
        {detail ? <p className="truncate text-[12.5px] text-subtle/90">{detail}</p> : null}
      </div>
    </div>
  )
}

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-[1.3rem] border border-line/55 bg-panel/75 px-5 py-4 ring-1 ring-white/50">
      <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">{label}</p>
      <p className="mt-1.5 text-[26px] font-semibold tracking-[-0.02em] text-text">{value}</p>
      {hint ? <p className="mt-0.5 text-[12px] text-subtle/85">{hint}</p> : null}
    </div>
  )
}

function EmptyState({ icon, title, hint, points, action }: { icon: ReactNode; title: string; hint?: string; points?: string[]; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-[1.3rem] border border-dashed border-line/70 bg-panel/50 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white/80 text-subtle shadow-sm">{icon}</div>
      <p className="text-[14px] font-semibold text-text">{title}</p>
      {hint ? <p className="max-w-md text-[12.5px] text-subtle/85">{hint}</p> : null}
      {points?.length ? (
        <ul className="mt-1 space-y-1 text-left text-[12.5px] text-subtle/85">
          {points.map((point) => (
            <li key={point} className="flex items-start gap-2">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-subtle/60" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-2 rounded-[1.3rem] border border-line/55 bg-panel/60 px-6 py-16 text-subtle">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span className="text-[13px]">Loading…</span>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[1.3rem] border border-rose-200/70 bg-rose-50/50 px-6 py-12 text-center">
      <AlertTriangle className="h-6 w-6 text-rose-500" />
      <p className="text-[13.5px] font-medium text-rose-900">{message}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}

function ConfirmDialog({
  text,
  title,
  confirmLabel,
  busy,
  destructive,
  onConfirm,
  onCancel,
}: {
  text: string
  title?: string
  confirmLabel?: string
  busy: boolean
  destructive: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
              destructive ? 'bg-rose-50 text-rose-600' : 'bg-[#fff7e8] text-[#8a5a16]',
            )}
          >
            {destructive ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
          </div>
          <div className="space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{title || 'Confirm this action'}</p>
            <p className="text-[13px] leading-6 text-subtle/95">{text}</p>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            className={destructive ? 'bg-rose-600 hover:bg-rose-600/90' : undefined}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            {confirmLabel || (destructive ? 'Confirm' : 'Continue')}
          </Button>
        </div>
      </div>
    </div>
  )
}

// Contextual copy for the backend-driven confirmation modal (shown when the
// server asks for an explicit confirmation step). The body text still comes
// from the backend; this only gives the modal a clear header + action label
// instead of a generic "Please confirm" / "Confirm".
const BACKEND_CONFIRM_COPY: Record<string, { title: string; confirmLabel: string }> = {
  approve_leave_request: { title: 'Approve this leave request?', confirmLabel: 'Approve' },
  reject_leave_request: { title: 'Decline this leave request?', confirmLabel: 'Decline' },
  approve_timesheet: { title: 'Approve this timesheet?', confirmLabel: 'Approve' },
  reject_timesheet: { title: 'Reject this timesheet?', confirmLabel: 'Reject' },
  approve_shift_swap: { title: 'Approve this swap request?', confirmLabel: 'Approve' },
  reject_shift_swap: { title: 'Decline this swap request?', confirmLabel: 'Decline' },
  mark_attendance_absent: { title: 'Mark this employee absent?', confirmLabel: 'Mark absent' },
  correct_attendance_record: { title: 'Save this attendance correction?', confirmLabel: 'Save correction' },
  onboarding_mark_item: { title: 'Update this onboarding item?', confirmLabel: 'Confirm' },
  set_payroll_policy: { title: 'Apply payroll policy?', confirmLabel: 'Apply changes' },
  export_payroll: { title: 'Export this payroll period?', confirmLabel: 'Export' },
  create_shift_assignment: { title: 'Schedule this shift?', confirmLabel: 'Schedule shift' },
  create_timesheet_review: { title: 'Generate timesheets?', confirmLabel: 'Generate timesheets' },
  compliance_mark_reviewed: { title: 'Mark document as reviewed?', confirmLabel: 'Mark reviewed' },
  compliance_send_reminder: { title: 'Send document reminder?', confirmLabel: 'Send reminder' },
  send_onboarding_reminder: { title: 'Send onboarding reminder?', confirmLabel: 'Send reminder' },
}

// --- data + action hooks ---------------------------------------------------

function useModuleData<T>(loader: () => Promise<T>, onAccessIssue?: (issue: AccessIssue) => void) {
  const [data, setData] = useState<T | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setRefreshing(true)
    setError(null)
    try {
      const next = await loader()
      if (requestId !== requestIdRef.current) return
      setData(next)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(friendlyError(err, 'We couldn’t load this section right now.'))
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false)
    }
  }, [loader, onAccessIssue])

  useEffect(() => {
    // Param/view changes get a new loader identity — clear stale rows so the
    // skeleton shows instead of the previous filter's content.
    setData(null)
    setError(null)
    void reload()
  }, [reload])

  // `loading` is the first-load / param-change skeleton (no matching data yet).
  // Soft refreshes call reload() without changing loader, so data stays painted.
  const loading = refreshing && data === null
  return { data, loading, refreshing, error, reload }
}

type PendingConfirmation = { text: string; actionType: string; args: Record<string, unknown>; destructive: boolean }

function usePosthireAction(access: DashboardAccess, reload: () => Promise<void>, onNotice: NoticeFn, onAccessIssue?: (issue: AccessIssue) => void) {
  const askConfirm = useConfirm()
  const [pending, setPending] = useState<PendingConfirmation | null>(null)
  const [busy, setBusy] = useState(false)
  const [runningKey, setRunningKey] = useState<string | null>(null)

  const dashboardActionError = (message: string | undefined | null, status?: string | null) => {
    const raw = String(message || '').trim()
    if (status === 'mutations_disabled' || /assistant session/i.test(raw) || /mutations are disabled/i.test(raw)) {
      return 'This dashboard action could not run because a platform assistant safety switch is blocking shared mutation tools. Ordinary HR workflows should not be affected — contact support.'
    }
    return raw || 'We couldn’t complete that action.'
  }

  const execute = useCallback(
    async (actionType: string, args: Record<string, unknown>, destructive: boolean, key: string, preconfirmed = false): Promise<boolean> => {
      setBusy(true)
      setRunningKey(key)
      try {
        const result = await runPosthireAction(access, { action_type: actionType, args })
        if (result.confirmation) {
          // The user already confirmed with a polished frontend dialog — don't
          // stack a second generic modal on top. Auto-confirm the server's step
          // once by re-sending the identical request (server-side safety stays).
          if (preconfirmed) {
            const confirmed = await runPosthireAction(access, {
              action_type: result.confirmation.action_type,
              args: result.confirmation.args,
            })
            if (confirmed.confirmation) {
              // Still asking after the retry — fall back to the modal so we
              // never silently run something the server wants reconfirmed.
              setPending({
                text: confirmed.confirmation.text,
                actionType: confirmed.confirmation.action_type,
                args: confirmed.confirmation.args,
                destructive,
              })
              return false
            }
            setPending(null)
            if (confirmed.ok === false) {
              onNotice(dashboardActionError(confirmed.message, confirmed.status), 'error')
              await reload()
              return false
            }
            onNotice(confirmed.message || 'Done.', 'success')
            await reload()
            return true
          }
          setPending({
            text: result.confirmation.text,
            actionType: result.confirmation.action_type,
            args: result.confirmation.args,
            destructive,
          })
          return false
        }
        setPending(null)
        // A 200 with ok:false means the action ran but delivery (e.g. a manual
        // reminder) didn't land. Show the server's failure text with an error
        // tone instead of a green "success" so HR is never misled.
        if (result.ok === false) {
          onNotice(dashboardActionError(result.message, result.status), 'error')
          await reload()
          return false
        }
        onNotice(result.message || 'Done.', 'success')
        await reload()
        return true
      } catch (err) {
        setPending(null)
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return false
        }
        onNotice(friendlyError(err, 'We could not complete that action.'), 'error')
        return false
      } finally {
        setBusy(false)
        setRunningKey(null)
      }
    },
    [access, reload, onNotice, onAccessIssue],
  )

  const run = useCallback(
    (
      actionType: string,
      args: Record<string, unknown> = {},
      options: { destructive?: boolean; key?: string; confirm?: ConfirmOptions; onSuccess?: () => void } = {},
    ): Promise<boolean> => {
      const go = async (preconfirmed: boolean) => {
        const ok = await execute(actionType, args, Boolean(options.destructive), options.key || actionType, preconfirmed)
        // Success-only callback lets call sites reset/close forms only once the
        // save actually lands — entered values survive a failure.
        if (ok) options.onSuccess?.()
        return ok
      }
      // When a call site supplies confirm copy, ask first (reusing the global
      // confirm system). Otherwise run immediately — the backend can still raise
      // its own confirmation step for actions that need one.
      if (options.confirm) {
        const copy = options.confirm
        return (async () => {
          if (!(await askConfirm(copy))) {
            onNotice('Action cancelled — nothing changed.', 'info')
            return false
          }
          return go(true)
        })()
      }
      return go(false)
    },
    [execute, askConfirm, onNotice],
  )

  const confirm = useCallback(() => {
    if (!pending) return
    void execute(pending.actionType, pending.args, pending.destructive, `${pending.actionType}:confirm`)
  }, [pending, execute])

  const dialog = pending ? (
    <ConfirmDialog
      text={pending.text}
      title={BACKEND_CONFIRM_COPY[pending.actionType]?.title}
      confirmLabel={BACKEND_CONFIRM_COPY[pending.actionType]?.confirmLabel}
      busy={busy}
      destructive={pending.destructive}
      onConfirm={confirm}
      onCancel={() => {
        setPending(null)
        onNotice('Action cancelled — nothing changed.', 'info')
      }}
    />
  ) : null

  return { run, busy, runningKey, dialog }
}

function employeeRef(emp: { phone?: string; name?: string; employee_phone?: string; employee_name?: string }): Record<string, string> {
  const phone = emp.phone || emp.employee_phone
  if (phone) return { employee_phone: phone }
  const name = emp.name || emp.employee_name
  return name ? { employee_name: name } : {}
}

// --- Employees -------------------------------------------------------------

type EmployeesLocale = 'en' | 'ar'

function employeesCopy(locale: EmployeesLocale) {
  const isAr = locale === 'ar'
  return {
    isAr,
    addEmployee: isAr ? 'إضافة موظف' : 'Add employee',
    importEmployees: isAr ? 'استيراد موظفين' : 'Import employees',
    refresh: isAr ? 'تحديث' : 'Refresh',
    cancel: isAr ? 'إلغاء' : 'Cancel',
    close: isAr ? 'إغلاق' : 'Close',
    directory: isAr ? 'الدليل' : 'Directory',
    searchPlaceholder: isAr ? 'ابحث بالاسم أو الدور أو القسم أو الهاتف…' : 'Search name, role, department, phone…',
    status: isAr ? 'الحالة' : 'Status',
    department: isAr ? 'القسم' : 'Department',
    contact: isAr ? 'التواصل' : 'Contact',
    onboarding: isAr ? 'التهيئة' : 'Onboarding',
    employee: isAr ? 'الموظف' : 'Employee',
    active: isAr ? 'نشط' : 'Active',
    left: isAr ? 'غادر' : 'Left',
    allStatuses: isAr ? 'كل الحالات' : 'All statuses',
    allDepartments: isAr ? 'كل الأقسام' : 'All departments',
    moreFilters: isAr ? 'المزيد' : 'More filters',
    hideFilters: isAr ? 'إخفاء' : 'Hide filters',
    onboardingAny: isAr ? 'أي تهيئة' : 'Any onboarding',
    onboardingOpen: isAr ? 'قيد التهيئة' : 'In progress',
    onboardingDone: isAr ? 'مكتملة' : 'Complete',
    onboardingNotStarted: isAr ? 'لم تبدأ' : 'Not started',
    noEmployees: isAr ? 'لا يوجد موظفون بعد' : 'No employees yet',
    emptyHintManage: isAr
      ? 'أضف فريقك يدوياً أو استورده من CSV/XLSX. يصل الموظفون أيضاً تلقائياً عند التوظيف.'
      : 'Add your team manually, or import them from a CSV/XLSX. People also arrive when you hire.',
    emptyHintRead: isAr
      ? 'يُبنى الدليل تلقائياً عند التوظيف.'
      : 'Your directory builds itself as you hire.',
    emptyPoints: isAr
      ? ['أضف موظفين مباشرة أو استورد القوى العاملة الحالية', 'وظّف المرشحين من ما قبل التوظيف — يصبحون موظفين تلقائياً']
      : ['Add employees directly, or import your existing workforce', 'Hire candidates from Pre-Hiring — they become employees automatically'],
    noMatch: (q: string) => (isAr ? `لا يوجد موظف يطابق «${q}»` : `No employees match “${q}”`),
    noShow: isAr ? 'لا يوجد موظفون للعرض' : 'No employees to show',
    trySearch: isAr ? 'جرّب اسماً أو دوراً أو قسماً أو رقماً آخر.' : 'Try a different name, role, department, or phone number.',
    addOrImport: isAr ? 'أضف أو استورد موظفين للبدء.' : 'Add or import employees to get started.',
    resultsFor: (n: number, q: string) =>
      isAr ? `${n} نتيجة لـ «${q}»` : `${n} result${n === 1 ? '' : 's'} for “${q}”`,
    showingOf: (shown: number, total: number, activeOnly: boolean) =>
      isAr
        ? `${shown} من ${total} ${activeOnly ? 'نشط' : 'موظف'}`
        : `${shown} of ${total} ${activeOnly ? 'active employees' : 'employees'}`,
    loadMoreFailed: isAr ? 'تعذّر تحميل المزيد. حاول مرة أخرى.' : 'We couldn’t load more employees. Please try again.',
    fullName: isAr ? 'الاسم الكامل' : 'Full name',
    phone: isAr ? 'الهاتف' : 'Phone',
    email: isAr ? 'البريد' : 'Email',
    jobTitle: isAr ? 'المسمى الوظيفي' : 'Job title',
    departmentTeam: isAr ? 'القسم / الفريق' : 'Department / team',
    startDate: isAr ? 'تاريخ البدء' : 'Start date',
    optional: isAr ? 'اختياري' : 'Optional',
    addIntro: isAr
      ? 'أضف شخصاً موجوداً في فريقك. سيظهر في الوحدات المفعّلة فوراً.'
      : 'Add someone already on your team. They’ll appear across your enabled modules right away.',
    phoneHint: isAr
      ? 'يُستخدم للتواصل، ويمكن ربطه بواتساب عند تفعيل الرسائل. لن نرسل أي رسالة تلقائياً.'
      : 'Used for contact, and as WhatsApp when messaging is enabled. We won’t message them automatically.',
    whatsappNote: isAr ? 'واتساب (عند التفعيل)' : 'WhatsApp when enabled',
    nameRequired: isAr ? 'أدخل الاسم الكامل.' : 'Enter a full name.',
    phoneRequired: isAr ? 'أدخل رقم هاتف صالحاً.' : 'Enter a valid phone number.',
    phoneDigits: isAr ? 'استخدم أرقاماً فقط، 8 أرقام على الأقل.' : 'Use digits only, at least 8 numbers.',
    emailInvalid: isAr ? 'أدخل بريداً إلكترونياً صالحاً.' : 'Enter a valid email address.',
    addFailed: isAr ? 'تعذّرت إضافة هذا الموظف. حاول مرة أخرى.' : 'We couldn’t add this employee. Please try again.',
    existsPhone: isAr ? 'يوجد موظف بهذا الرقم مسبقاً.' : 'An employee with this phone number already exists.',
    addedOk: (name: string) => (isAr ? `تمت إضافة ${name} إلى القوى العاملة.` : `${name} was added to your workforce.`),
    selectDepartment: isAr ? 'اختر قسماً' : 'Select a department',
    otherDepartment: isAr ? 'قسم آخر…' : 'Other department…',
    importIntro: isAr
      ? 'ارفع CSV أو XLSX لفريقك الحالي. لن نرسل أي رسائل أثناء الاستيراد.'
      : 'Upload a CSV or XLSX of your existing team. We never message anyone during an import.',
    requiredCols: isAr ? 'الأعمدة المطلوبة:' : 'Required columns:',
    optionalCols: isAr
      ? 'اختياري: البريد، المسمى، القسم، تاريخ البدء. نسّق عمود الهاتف كنص للحفاظ على الأرقام الأولى.'
      : 'Optional: email, job title, department, start date. Format phone columns as text to keep leading digits.',
    chooseFile: isAr ? 'اختر ملف CSV أو XLSX أولاً.' : 'Choose a CSV or XLSX file first.',
    preview: isAr ? 'معاينة' : 'Preview',
    confirmImport: isAr ? 'تأكيد الاستيراد' : 'Confirm import',
    import: isAr ? 'استيراد' : 'Import',
    previewFirst: isAr ? 'عاين الملف قبل التأكيد.' : 'Preview the file before confirming.',
    importComplete: isAr ? 'اكتمل الاستيراد' : 'Import complete',
    previewRows: (n: number) => (isAr ? `معاينة · ${n} صف` : `Preview · ${n} row${n === 1 ? '' : 's'} found`),
    willAdd: isAr ? 'سيُضاف' : 'Will be added',
    added: isAr ? 'أُضيف' : 'Added',
    skipped: isAr ? 'تم التخطي (موجود مسبقاً)' : 'Skipped (already in workforce)',
    needsReview: isAr ? 'يحتاج مراجعة' : 'Needs review',
    failedRows: isAr ? 'تعذّرت إضافته' : 'Couldn’t be added',
    importFailed: isAr ? 'تعذّر استيراد الملف. تحقق من التنسيق وحاول مرة أخرى.' : 'We couldn’t import this file. Please check the format and try again.',
    importedOk: (n: number) => (isAr ? `تم استيراد ${n} موظف.` : `Imported ${n} employee${n === 1 ? '' : 's'}.`),
    importedNone: isAr ? 'لم يُضف أي موظف جديد.' : 'No new employees were added.',
    unknown: isAr ? 'غير معروف' : 'Unknown',
    loading: isAr ? 'جارٍ التحميل…' : 'Loading…',
    loadMore: isAr ? 'تحميل المزيد' : 'Load more',
    showingNoun: isAr ? 'موظف' : 'employee',
  }
}

function normalizePhoneDigits(value: string): string {
  return value.replace(/[^\d+]/g, '').replace(/(?!^)\+/g, '')
}

function isOnboardingComplete(status?: string | null): boolean {
  return ['complete', 'completed', 'done'].includes(String(status || '').toLowerCase())
}

function isOnboardingNotStarted(status?: string | null): boolean {
  const value = String(status || '').toLowerCase()
  return !value || value === 'not_started' || value === 'not-started' || value === 'pending'
}

function RosterField({ label, required, hint, error, children }: {
  label: string
  required?: boolean
  hint?: string
  error?: string | null
  children: ReactNode
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium text-subtle/90">
        {label}
        {required ? <span className="text-rose-500"> *</span> : null}
      </span>
      {children}
      {error ? <span className="block text-[12px] text-rose-600">{error}</span> : null}
      {!error && hint ? <span className="block text-[11.5px] leading-4 text-subtle/75">{hint}</span> : null}
    </label>
  )
}

function AddEmployeeModal({ access, onClose, onNotice, onAdded }: {
  access: DashboardAccess
  onClose: () => void
  onNotice: NoticeFn
  onAdded: () => void
}) {
  const locale = useEmployees360Locale()
  const copy = employeesCopy(locale)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState('')
  const [departmentMode, setDepartmentMode] = useState<'select' | 'other'>('select')
  const [startDate, setStartDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [orgDepartments, setOrgDepartments] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await getEmployeeOrgUnits(access, { unit_type: 'department' })
        if (cancelled) return
        const names = (res.units || [])
          .filter((u) => String(u.status || 'active').toLowerCase() !== 'inactive')
          .map((u) => String(u.name || '').trim())
          .filter(Boolean)
        setOrgDepartments([...new Set(names)].sort((a, b) => a.localeCompare(b)))
      } catch {
        if (!cancelled) setOrgDepartments([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [access])

  const phoneDigits = normalizePhoneDigits(phone)
  const nameError = touched.name && !name.trim() ? copy.nameRequired : null
  const phoneError = touched.phone
    ? !phone.trim()
      ? copy.phoneRequired
      : phoneDigits.replace(/\D/g, '').length < 8
        ? copy.phoneDigits
        : null
    : null
  const emailError = touched.email && email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
    ? copy.emailInvalid
    : null
  const ready = Boolean(name.trim() && phone.trim() && phoneDigits.replace(/\D/g, '').length >= 8 && !emailError)

  const submit = async () => {
    setTouched({ name: true, phone: true, email: true })
    if (!ready) {
      setSubmitError(copy.phoneRequired)
      return
    }
    setBusy(true)
    setSubmitError(null)
    try {
      const res = await createEmployee(access, {
        name: name.trim(),
        phone: phoneDigits,
        email: email.trim() || undefined,
        position_title: title.trim() || undefined,
        department: department.trim() || undefined,
        start_date: startDate || undefined,
      })
      if (res.ok && res.status === 'created') {
        onNotice(copy.addedOk(name.trim()), 'success')
        onAdded()
        onClose()
        return
      }
      setSubmitError(res.message || copy.existsPhone)
    } catch (err) {
      setSubmitError(friendlyError(err, copy.addFailed))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div
        className="w-full max-w-lg overflow-y-auto rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60"
        dir={copy.isAr ? 'rtl' : 'ltr'}
        lang={locale}
      >
        <div className="space-y-1">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{copy.addEmployee}</p>
          <p className="text-[13px] leading-6 text-subtle/95">{copy.addIntro}</p>
        </div>
        <div className="mt-5 grid gap-3.5 sm:grid-cols-2">
          <RosterField label={copy.fullName} required error={nameError}>
            <Input
              className="w-full"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, name: true }))}
              placeholder={copy.isAr ? 'مثال: سارة العلي' : 'e.g. Sara Al-Ali'}
              autoFocus
            />
          </RosterField>
          <RosterField label={copy.phone} required hint={copy.whatsappNote} error={phoneError}>
            <Input
              className="w-full"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, phone: true }))}
              placeholder={copy.isAr ? 'مثال: 96550000000' : 'e.g. 96550000000'}
              inputMode="tel"
              autoComplete="tel"
            />
          </RosterField>
          <RosterField label={copy.email} error={emailError}>
            <Input
              className="w-full"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setTouched((t) => ({ ...t, email: true }))}
              placeholder={copy.optional}
              type="email"
            />
          </RosterField>
          <RosterField label={copy.jobTitle}>
            <Input className="w-full" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={copy.optional} />
          </RosterField>
          <RosterField label={copy.departmentTeam}>
            {orgDepartments.length > 0 && departmentMode === 'select' ? (
              <Select
                className="w-full"
                value={department && orgDepartments.includes(department) ? department : ''}
                onChange={(e) => {
                  const next = e.target.value
                  if (next === '__other__') {
                    setDepartmentMode('other')
                    setDepartment('')
                    return
                  }
                  setDepartment(next)
                }}
              >
                <option value="">{copy.selectDepartment}</option>
                {orgDepartments.map((dept) => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
                <option value="__other__">{copy.otherDepartment}</option>
              </Select>
            ) : (
              <Input
                className="w-full"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                placeholder={copy.optional}
                list={orgDepartments.length ? 'wf-employee-departments' : undefined}
              />
            )}
            {orgDepartments.length ? (
              <datalist id="wf-employee-departments">
                {orgDepartments.map((dept) => (
                  <option key={dept} value={dept} />
                ))}
              </datalist>
            ) : null}
          </RosterField>
          <RosterField label={copy.startDate}>
            <Input className="w-full" value={startDate} onChange={(e) => setStartDate(e.target.value)} type="date" />
          </RosterField>
        </div>
        {submitError ? <p className="mt-3 text-[13px] text-rose-600">{submitError}</p> : null}
        <p className="mt-3 text-[12px] leading-5 text-subtle/80">{copy.phoneHint}</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>{copy.cancel}</Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !ready}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {copy.addEmployee}
          </Button>
        </div>
      </div>
    </div>
  )
}

function EditEmployeeModal({ access, employee, onClose, onNotice, onSaved }: {
  access: DashboardAccess
  employee: PosthireEmployee
  onClose: () => void
  onNotice: NoticeFn
  onSaved: () => void
}) {
  const [name, setName] = useState(employee.name || '')
  const [phone, setPhone] = useState(employee.phone || '')
  const [email, setEmail] = useState(employee.email || '')
  const [title, setTitle] = useState(employee.position_title || '')
  const [department, setDepartment] = useState(employee.department || '')
  const [startDate, setStartDate] = useState(employee.start_date ? String(employee.start_date).slice(0, 10) : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = name.trim().length > 0 && phone.trim().length > 0

  const submit = async () => {
    if (!ready) {
      setError('A full name and a WhatsApp phone number are required.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await updateEmployee(access, employee.employee_key, {
        name: name.trim(),
        phone: phone.trim(),
        email: email.trim(),
        position_title: title.trim(),
        department: department.trim(),
        start_date: startDate || null,
        expected_updated_at: String(employee.updated_at || ''),
      })
      if (res.ok && res.status === 'updated') {
        onNotice(`${name.trim()}'s details were updated.`, 'success')
        onSaved()
        onClose()
        return
      }
      // Duplicate phone or other soft failure — keep the form so HR can fix it.
      setError(res.message || 'Another employee already uses this phone number.')
    } catch (err) {
      setError(friendlyError(err, 'We couldn’t save these changes. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm">
      <div className="w-full max-w-lg overflow-y-auto rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60">
        <div className="space-y-1">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">Edit employee</p>
          <p className="text-[13px] leading-6 text-subtle/95">Correct this employee’s details. History stays linked even if the phone number changes.</p>
        </div>
        <div className="mt-5 grid gap-3.5 sm:grid-cols-2">
          <RosterField label="Full name" required>
            <Input className="w-full" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </RosterField>
          <RosterField label="Phone / WhatsApp" required>
            <Input className="w-full" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
          </RosterField>
          <RosterField label="Email">
            <Input className="w-full" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Recommended for notifications" type="email" />
          </RosterField>
          <RosterField label="Job title">
            <Input className="w-full" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional" />
          </RosterField>
          <RosterField label="Department / team">
            <Input className="w-full" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Optional" />
          </RosterField>
          <RosterField label="Start date">
            <Input className="w-full" value={startDate} onChange={(e) => setStartDate(e.target.value)} type="date" />
          </RosterField>
        </div>
        {error ? <p className="mt-3 text-[13px] text-rose-600">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !ready}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save changes
          </Button>
        </div>
      </div>
    </div>
  )
}

type ActivationHandoff = {
  invite_id: string
  task_id: string
  expires_at: string
  activation_code: string
}

export function ActivationHandoffModal({ handoff, onClose }: { handoff: ActivationHandoff; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60">
        <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">One-time activation handoff</p>
        <p className="mt-2 text-[13px] leading-6 text-subtle/95">
          Show this code directly to the employee. Wathefni does not save or distribute the displayed value. Closing this window clears it.
        </p>
        <div className="mt-5 rounded-2xl border border-line/70 bg-canvas/70 px-5 py-6 text-center">
          <p className="font-mono text-3xl font-semibold tracking-[0.35em] text-text" data-testid="activation-handoff-code">
            {handoff.activation_code}
          </p>
        </div>
        <p className="mt-3 text-[12px] leading-5 text-subtle/80">
          Expires {formatDate(handoff.expires_at)}. If this window is lost, explicitly supersede invite {handoff.invite_id} and issue a new code.
        </p>
        <div className="mt-6 flex justify-end">
          <Button size="sm" onClick={onClose}>Close and clear</Button>
        </div>
      </div>
    </div>
  )
}

function ImportSummaryRow({ label, rows, tone }: { label: string; rows: EmployeeImportResult['results']['created']; tone: 'success' | 'warning' | 'danger' | 'muted' }) {
  if (!rows.length) return null
  const toneClass = tone === 'success'
    ? 'text-emerald-700'
    : tone === 'danger'
      ? 'text-rose-600'
      : tone === 'warning'
        ? 'text-[#8a5a16]'
        : 'text-subtle/85'
  return (
    <div className="rounded-2xl border border-line/50 bg-white/55 p-3">
      <p className={cn('text-[13px] font-semibold', toneClass)}>{label} · {rows.length}</p>
      <ul className="mt-1 space-y-0.5 text-[12px] leading-5 text-subtle/85">
        {rows.slice(0, 8).map((r) => (
          <li key={`${label}-${r.row}`}>{r.name}{r.reason ? ` — ${r.reason}` : ''}</li>
        ))}
        {rows.length > 8 ? <li className="text-subtle/70">+{rows.length - 8} more</li> : null}
      </ul>
    </div>
  )
}

function ImportEmployeesModal({ access, onClose, onNotice, onImported }: {
  access: DashboardAccess
  onClose: () => void
  onNotice: NoticeFn
  onImported: () => void
}) {
  const locale = useEmployees360Locale()
  const copy = employeesCopy(locale)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<EmployeeImportResult | null>(null)
  const [result, setResult] = useState<EmployeeImportResult | null>(null)
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload')

  const pickFile = (next: File | null) => {
    setFile(next)
    setPreview(null)
    setResult(null)
    setError(null)
    setStep('upload')
  }

  const run = async (dryRun: boolean) => {
    if (!file) {
      setError(copy.chooseFile)
      return
    }
    if (!dryRun && !preview) {
      setError(copy.previewFirst)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await importEmployees(access, { file, dryRun })
      if (dryRun) {
        setPreview(res)
        setStep('preview')
      } else {
        setResult(res)
        setPreview(null)
        setStep('done')
        if (res.counts.created > 0) {
          onNotice(copy.importedOk(res.counts.created), 'success')
          onImported()
        } else {
          onNotice(copy.importedNone, 'info')
        }
      }
    } catch (err) {
      setError(friendlyError(err, copy.importFailed))
    } finally {
      setBusy(false)
    }
  }

  const summary = result ?? preview

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div
        className="w-full max-w-lg overflow-y-auto rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60"
        dir={copy.isAr ? 'rtl' : 'ltr'}
        lang={locale}
      >
        <div className="space-y-1">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{copy.importEmployees}</p>
          <p className="text-[13px] leading-6 text-subtle/95">{copy.importIntro}</p>
        </div>
        <ol className="mt-4 flex flex-wrap gap-2 text-[11.5px] font-medium uppercase tracking-[0.06em] text-subtle/70">
          <li className={cn('rounded-full px-2.5 py-1', step === 'upload' ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>1 · {copy.isAr ? 'رفع' : 'Upload'}</li>
          <li className={cn('rounded-full px-2.5 py-1', step === 'preview' ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>2 · {copy.preview}</li>
          <li className={cn('rounded-full px-2.5 py-1', step === 'done' ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>3 · {copy.confirmImport}</li>
        </ol>
        <div className="mt-4 rounded-2xl border border-line/50 bg-white/55 p-3 text-[12px] leading-5 text-subtle/85">
          <p className="font-medium text-subtle/95">
            {copy.requiredCols}{' '}
            <span className="font-semibold text-text">name</span>, <span className="font-semibold text-text">phone</span>
          </p>
          <p className="mt-0.5">{copy.optionalCols}</p>
        </div>
        <div className="mt-4">
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            disabled={busy || Boolean(result)}
            className="block w-full text-[13px] text-subtle/90 file:me-3 file:rounded-full file:border-0 file:bg-[#fff7e8] file:px-4 file:py-2 file:text-[13px] file:font-medium file:text-[#8a5a16] hover:file:bg-[#fdeecb]"
          />
          {file ? <p className="mt-2 text-[12px] text-subtle/80">{file.name}</p> : null}
        </div>
        {error ? <p className="mt-3 text-[13px] text-rose-600">{error}</p> : null}
        {summary ? (
          <div className="mt-4 space-y-2">
            <p className="text-[12px] font-medium text-subtle/90">
              {result ? copy.importComplete : copy.previewRows(summary.total_rows)}
            </p>
            <ImportSummaryRow label={result ? copy.added : copy.willAdd} rows={summary.results.created} tone="success" />
            <ImportSummaryRow label={copy.skipped} rows={summary.results.skipped} tone="muted" />
            <ImportSummaryRow label={copy.needsReview} rows={summary.results.needs_review} tone="warning" />
            <ImportSummaryRow label={copy.failedRows} rows={summary.results.failed} tone="danger" />
          </div>
        ) : null}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>{result ? copy.close : copy.cancel}</Button>
          {!result ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => void run(true)} disabled={busy || !file}>
                {busy && !preview ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                {copy.preview}
              </Button>
              <Button size="sm" onClick={() => void run(false)} disabled={busy || !file || !preview}>
                {busy && preview ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {copy.confirmImport}
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function EmployeesPage({ access, permissions, role, onNotice, onAccessIssue, onNavigate }: PostHireCommonProps & Pick<PostHireProps, 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const copy = employeesCopy(locale)
  const [query, setQuery] = useState('')
  // Search runs on the server so it reaches the whole workforce, not just the
  // pages already loaded. Debounce the raw input so we fetch on the settled term.
  const debouncedQuery = useDebouncedValue(query.trim(), 350)
  const loader = useCallback(
    () => getPosthireEmployees(access, debouncedQuery ? { search: debouncedQuery } : undefined),
    [access, debouncedQuery],
  )
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireEmployeesResponse>(loader, onAccessIssue)
  const [selectedKey, setSelectedKey] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    return new URLSearchParams(window.location.search).get('employee')
  })
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'active' | 'left' | 'all'>('active')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [onboardingFilter, setOnboardingFilter] = useState<'any' | 'open' | 'complete' | 'not_started'>('any')
  const [showMoreFilters, setShowMoreFilters] = useState(false)
  const canManageRoster = can(permissions, 'employees.manage', role)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.set('page', 'employees')
    if (selectedKey) url.searchParams.set('employee', selectedKey)
    else url.searchParams.delete('employee')
    window.history.replaceState({}, '', `${url.pathname}${url.search}`)
  }, [selectedKey])

  // All hooks (including this useMemo) must run unconditionally on every
  // render — the "open a profile" early return below must come after every
  // hook call, or React throws "Rendered fewer hooks than expected" the
  // moment a row is clicked and selectedKey flips from null to a value.
  //
  // Pagination: page 1 comes from useModuleData; extra pages accumulate here and
  // reset whenever the base data reloads (refresh / roster change) so we page
  // through the whole workforce instead of silently stopping at a cap.
  const [extraEmployees, setExtraEmployees] = useState<PosthireEmployee[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraEmployees([])
  }, [data])

  const baseEmployees = data?.employees ?? []
  const employees = useMemo(() => [...baseEmployees, ...extraEmployees], [baseEmployees, extraEmployees])
  const isLeft = (e: PosthireEmployee) => String(e.employment_status || 'active').toLowerCase() === 'left'
  const totalEmployees = data?.total_count ?? employees.length
  const activeTotal = data?.active_count ?? employees.filter((e) => !isLeft(e)).length
  const leftTotal = data?.left_count ?? employees.length - activeTotal
  const searching = debouncedQuery.length > 0

  const departmentOptions = useMemo(() => {
    const names = employees.map((e) => String(e.department || '').trim()).filter(Boolean)
    return [...new Set(names)].sort((a, b) => a.localeCompare(b))
  }, [employees])

  const filtered = useMemo(() => {
    return employees.filter((emp) => {
      if (!searching) {
        if (statusFilter === 'active' && isLeft(emp)) return false
        if (statusFilter === 'left' && !isLeft(emp)) return false
      }
      if (departmentFilter && String(emp.department || '').trim() !== departmentFilter) return false
      const onboarding = String(emp.onboarding_status || '').toLowerCase()
      if (onboardingFilter === 'complete' && !isOnboardingComplete(onboarding)) return false
      if (onboardingFilter === 'open' && (isOnboardingComplete(onboarding) || isOnboardingNotStarted(onboarding))) return false
      if (onboardingFilter === 'not_started' && !isOnboardingNotStarted(onboarding)) return false
      return true
    })
  }, [employees, searching, statusFilter, departmentFilter, onboardingFilter])

  const loadMoreEmployees = useCallback(async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthireEmployees(access, {
        offset: employees.length,
        ...(debouncedQuery ? { search: debouncedQuery } : {}),
      })
      setExtraEmployees((prev) => [...prev, ...(res.employees ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, copy.loadMoreFailed), 'error')
    } finally {
      setLoadingMore(false)
    }
  }, [access, employees.length, debouncedQuery, onAccessIssue, onNotice, copy.loadMoreFailed])

  if (selectedKey) {
    return <EmployeeProfile access={access} permissions={permissions} role={role} employeeKey={selectedKey} onBack={() => setSelectedKey(null)} onNotice={onNotice} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
  }

  const openProfile = (emp: PosthireEmployee) => {
    if (emp.employee_key) setSelectedKey(emp.employee_key)
  }

  const filterSelectClass =
    'h-10 rounded-full border border-line/60 bg-white/70 px-3 text-[13px] text-text outline-none transition focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15'

  return (
    <div className="space-y-4" dir={copy.isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="employees-directory">
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : employees.length === 0 && !searching ? (
        <EmptyState
          icon={<UserRound className="h-5 w-5" />}
          title={copy.noEmployees}
          hint={canManageRoster ? copy.emptyHintManage : copy.emptyHintRead}
          points={copy.emptyPoints}
          action={canManageRoster ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => setShowAdd(true)}>
                <Plus className="h-4 w-4" /> {copy.addEmployee}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowImport(true)}>
                <Upload className="h-4 w-4" /> {copy.importEmployees}
              </Button>
            </div>
          ) : undefined}
        />
      ) : (
        <Card tone="board" data-testid="employees-directory-board">
          <CardHeader className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle>{copy.directory}</CardTitle>
                <CardDescription>
                  {searching
                    ? copy.resultsFor(totalEmployees, debouncedQuery)
                    : copy.showingOf(filtered.length, statusFilter === 'active' ? activeTotal : totalEmployees, statusFilter === 'active')}
                  {leftTotal && statusFilter === 'active' && !searching
                    ? copy.isAr
                      ? ` · ${leftTotal} غادر`
                      : ` · ${leftTotal} left`
                    : null}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {canManageRoster ? (
                  <>
                    <Button variant="secondary" size="sm" onClick={() => setShowImport(true)}>
                      <Upload className="h-4 w-4" /> {copy.importEmployees}
                    </Button>
                    <Button size="sm" onClick={() => setShowAdd(true)}>
                      <Plus className="h-4 w-4" /> {copy.addEmployee}
                    </Button>
                  </>
                ) : null}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void reload()}
                  disabled={refreshing}
                  aria-label={copy.refresh}
                  title={copy.refresh}
                >
                  <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
                  <span className="sr-only sm:not-sr-only sm:ms-1">{copy.refresh}</span>
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={query}
                onChange={setQuery}
                placeholder={copy.searchPlaceholder}
                className="max-w-sm flex-1"
              />
              <select
                className={filterSelectClass}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'active' | 'left' | 'all')}
                aria-label={copy.status}
              >
                <option value="active">{copy.active}</option>
                <option value="left">{copy.left}</option>
                <option value="all">{copy.allStatuses}</option>
              </select>
              <select
                className={cn(filterSelectClass, 'max-w-[11rem]')}
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
                aria-label={copy.department}
              >
                <option value="">{copy.allDepartments}</option>
                {departmentOptions.map((dept) => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
              </select>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowMoreFilters((v) => !v)}
                aria-expanded={showMoreFilters}
              >
                <ChevronDown className={cn('h-4 w-4 transition', showMoreFilters && 'rotate-180')} />
                {showMoreFilters ? copy.hideFilters : copy.moreFilters}
              </Button>
            </div>
            {showMoreFilters ? (
              <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-[#f7f1e6]/70 px-3 py-2.5">
                <select
                  className={filterSelectClass}
                  value={onboardingFilter}
                  onChange={(e) => setOnboardingFilter(e.target.value as typeof onboardingFilter)}
                  aria-label={copy.onboarding}
                >
                  <option value="any">{copy.onboardingAny}</option>
                  <option value="open">{copy.onboardingOpen}</option>
                  <option value="not_started">{copy.onboardingNotStarted}</option>
                  <option value="complete">{copy.onboardingDone}</option>
                </select>
              </div>
            ) : null}
          </CardHeader>
          <CardContent>
            {filtered.length === 0 ? (
              <EmptyState
                icon={<Search className="h-5 w-5" />}
                title={searching ? copy.noMatch(debouncedQuery) : copy.noShow}
                hint={searching ? copy.trySearch : copy.addOrImport}
              />
            ) : (
              <>
                <div className="space-y-2 md:hidden" data-testid="employees-mobile-cards">
                  {filtered.map((emp) => (
                    <button
                      key={emp.employee_key || emp.phone || emp.name}
                      type="button"
                      onClick={() => openProfile(emp)}
                      disabled={!emp.employee_key}
                      className="flex w-full items-start gap-3 rounded-[1.15rem] border border-[#e8dfd0]/80 bg-white/55 px-3.5 py-3 text-start transition hover:bg-white/80 disabled:cursor-default disabled:opacity-70"
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#eee5d4] text-[13px] font-semibold text-[#5c554a]">
                        {(emp.name || '?').trim().slice(0, 1).toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-text">{emp.name}</p>
                          <Badge tone={isLeft(emp) ? 'muted' : 'success'}>{isLeft(emp) ? copy.left : copy.active}</Badge>
                        </div>
                        <p className="mt-0.5 truncate text-[12.5px] text-subtle/85">
                          {[emp.position_title, emp.department].filter(Boolean).join(' · ') || '—'}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <StatusBadge status={emp.onboarding_status} />
                          {emp.phone ? <span className="text-[12px] text-subtle/75">{emp.phone}</span> : null}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                <div className="hidden overflow-x-auto rounded-[1.1rem] border border-[#e8dfd0]/80 md:block" data-testid="employees-desktop-table">
                  <table className="w-full min-w-[640px] text-start text-[13px]">
                    <thead className="bg-[#f7f1e6] text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">{copy.employee}</th>
                        <th className="px-4 py-3 font-medium">{copy.department}</th>
                        <th className="px-4 py-3 font-medium">{copy.contact}</th>
                        <th className="px-4 py-3 font-medium">{copy.status}</th>
                        <th className="px-4 py-3 font-medium">{copy.onboarding}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#e8dfd0]/70">
                      {filtered.map((emp) => (
                        <tr
                          key={emp.employee_key || emp.phone || emp.name}
                          className={cn('min-h-[3.25rem] hover:bg-white/45', emp.employee_key ? 'cursor-pointer' : '')}
                          onClick={emp.employee_key ? () => openProfile(emp) : undefined}
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#eee5d4] text-[12px] font-semibold text-[#5c554a]">
                                {(emp.name || '?').trim().slice(0, 1).toUpperCase()}
                              </div>
                              <div>
                                <p className="flex items-center gap-2 font-semibold text-text">
                                  {emp.name}
                                  {isLeft(emp) ? <Badge tone="muted">{copy.left}</Badge> : null}
                                </p>
                                <p className="text-[12px] text-subtle/85">{emp.position_title || '—'}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-subtle/90">{emp.department || '—'}</td>
                          <td className="px-4 py-3 text-subtle/90">
                            <p>{emp.phone || '—'}</p>
                            {emp.email ? <p className="text-[12px] text-subtle/75">{emp.email}</p> : null}
                          </td>
                          <td className="px-4 py-3">
                            <Badge tone={isLeft(emp) ? 'muted' : 'success'}>{isLeft(emp) ? copy.left : copy.active}</Badge>
                          </td>
                          <td className="px-4 py-3">
                            <StatusBadge status={emp.onboarding_status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <LoadMoreBar
              loaded={employees.length}
              total={totalEmployees}
              loading={loadingMore}
              onLoadMore={() => void loadMoreEmployees()}
              noun={copy.showingNoun}
              showingLabel={
                copy.isAr
                  ? `عرض ${employees.length} من ${totalEmployees} موظف`
                  : `Showing ${employees.length} of ${totalEmployees} employees`
              }
              loadMoreLabel={copy.loadMore}
              loadingLabel={copy.loading}
            />
          </CardContent>
        </Card>
      )}
      {showAdd ? (
        <AddEmployeeModal access={access} onClose={() => setShowAdd(false)} onNotice={onNotice} onAdded={() => void reload()} />
      ) : null}
      {showImport ? (
        <ImportEmployeesModal access={access} onClose={() => setShowImport(false)} onNotice={onNotice} onImported={() => void reload()} />
      ) : null}
    </div>
  )
}

// --- Employee 360 ----------------------------------------------------------

function tenureLabel(hiredAt?: string | null): string | null {
  if (!hiredAt) return null
  const hired = new Date(hiredAt)
  if (Number.isNaN(hired.getTime())) return null
  const months = Math.max(0, Math.floor((Date.now() - hired.getTime()) / (1000 * 60 * 60 * 24 * 30.44)))
  if (months < 1) return 'joined this month'
  if (months < 12) return `${months} month${months === 1 ? '' : 's'}`
  const years = Math.floor(months / 12)
  const rem = months % 12
  return rem ? `${years}y ${rem}m` : `${years} year${years === 1 ? '' : 's'}`
}

const NEXT_ACTION_SEVERITY: Record<NextActionSeverity, { label: string; dot: string; badge: 'danger' | 'warning' | 'muted' }> = {
  critical: { label: 'Critical', dot: 'bg-rose-500', badge: 'danger' },
  high: { label: 'High', dot: 'bg-amber-500', badge: 'warning' },
  medium: { label: 'Medium', dot: 'bg-amber-300', badge: 'warning' },
  low: { label: 'Low', dot: 'bg-slate-300', badge: 'muted' },
}
const NEXT_ACTION_SEVERITY_ORDER: NextActionSeverity[] = ['critical', 'high', 'medium', 'low']

function NextActionsSummary({ summary }: { summary: EmployeeProfileNextActionsSummary }) {
  const parts = NEXT_ACTION_SEVERITY_ORDER
    .filter((s) => (summary.by_severity?.[s] || 0) > 0)
    .map((s) => `${summary.by_severity[s]} ${s}`)
  if (!parts.length) return null
  return <span className="shrink-0 text-[12px] font-medium text-subtle/85">{parts.join(' · ')}</span>
}

// Ranked "what to do next" panel (flag ON). Severity-first order comes from the
// backend; the panel only renders an action button for rows the backend marked
// executable AND the viewer is permitted to run — everything else falls back to
// a "View" link that scrolls to the relevant module card (where the existing
// approve/reject controls live). No new actions, no client-side ranking.
function NextActionsPanel({
  actions,
  summary,
  canRun,
  onRun,
  onNavigate,
  busy,
  runningKey,
}: {
  actions: EmployeeProfileNextAction[]
  summary?: EmployeeProfileNextActionsSummary | null
  canRun: (a: EmployeeProfileNextAction) => boolean
  onRun: (a: EmployeeProfileNextAction) => void
  onNavigate: (section: string) => void
  busy: boolean
  runningKey: string | null
}) {
  const [showAll, setShowAll] = useState(false)
  const cap = summary?.visible_cap ?? 5
  const visible = showAll ? actions : actions.slice(0, cap)
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>What to do next</CardTitle>
            <CardDescription>Ranked by seriousness — the most urgent items first.</CardDescription>
          </div>
          {summary ? <NextActionsSummary summary={summary} /> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {visible.map((a) => {
          const sev = NEXT_ACTION_SEVERITY[a.severity ?? 'low'] ?? NEXT_ACTION_SEVERITY.low
          const runnable = canRun(a)
          const runKey = `next:${a.id}`
          return (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-[1rem] border border-line/45 bg-panel-muted/30 px-3 py-2.5">
              <div className="flex min-w-0 items-start gap-2.5">
                <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${sev.dot}`} />
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-text">
                    {a.title}
                    <Badge tone={sev.badge} className="ml-2 align-middle">{sev.label}</Badge>
                  </p>
                  {a.reason ? <p className="mt-0.5 text-[12px] text-subtle/85">{a.reason}</p> : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {runnable && a.action_type ? (
                  <Button size="sm" disabled={busy} onClick={() => onRun(a)}>
                    {runningKey === runKey ? <Loader2 className="h-4 w-4 animate-spin" /> : (a.action_label || 'Run')}
                  </Button>
                ) : null}
                <Button variant="ghost" size="sm" onClick={() => onNavigate(a.target?.section || a.module)}>
                  View
                </Button>
              </div>
            </div>
          )
        })}
        {actions.length > cap ? (
          <div className="pt-1">
            <Button variant="ghost" size="sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Show fewer' : `View all (${actions.length})`}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

// A module card that collapses to just its header when there is nothing to act
// on, and opens by default when the caller marks it as needing attention.
// Keeps every action exactly as-is — this only changes what's visible by default.
function CollapsibleSection({
  id,
  icon,
  title,
  description,
  defaultOpen,
  className,
  children,
}: {
  id?: string
  icon: ReactNode
  title: string
  description: ReactNode
  defaultOpen: boolean
  className?: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card id={id} className={className}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 border-b border-line/50 pb-5 text-left"
        aria-expanded={open}
      >
        <div className="space-y-2">
          <CardTitle className="flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <ChevronDown className={cn('mt-1 h-4 w-4 shrink-0 text-subtle/60 transition-transform duration-200', open && 'rotate-180')} />
      </button>
      {open ? <div className="pt-5">{children}</div> : null}
    </Card>
  )
}

function EmployeeProfile({ access, permissions, role, employeeKey, onBack, onNotice, onAccessIssue, onNavigate }: PostHireCommonProps & { employeeKey: string; onBack: () => void } & Pick<PostHireProps, 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const loader = useCallback(() => getEmployeeProfile(access, employeeKey), [access, employeeKey])
  const { data, loading, refreshing, error, reload } = useModuleData<EmployeeProfileResponse>(loader, onAccessIssue)
  const action = usePosthireAction(access, reload, onNotice, onAccessIssue)
  const confirm = useConfirm()
  const canUpload = can(permissions, 'onboarding.manage', role) && Boolean(data?.doc_upload_enabled)
  // Same gates the module pages use, so behaviour matches wherever HR acts from.
  const canOnboardingManage = can(permissions, 'onboarding.manage', role)
  const canComplianceManage = can(permissions, 'compliance.manage', role)
  const canPayrollManage = can(permissions, 'payroll.manage', role)
  const canManageRoster = can(permissions, 'employees.manage', role)
  const canApproveStatusOnly = can(permissions, 'employees.status.approve', role)
  const canRequestStatusChange = canManageRoster
  const canApproveStatus = canManageRoster && canApproveStatusOnly
  const canIssueActivation = canManageRoster && canOnboardingManage
  const [showEdit, setShowEdit] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [pendingStatusRequests, setPendingStatusRequests] = useState<Array<Record<string, unknown>>>([])
  const [activationBusy, setActivationBusy] = useState(false)
  const [activationHandoff, setActivationHandoff] = useState<ActivationHandoff | null>(null)

  const emp = data?.employee
  const hasLeft = String(emp?.employment_status || 'active').toLowerCase() === 'left'

  useEffect(() => {
    setActivationHandoff(null)
  }, [employeeKey])

  const reloadPendingStatus = useCallback(async () => {
    if (!canRequestStatusChange && !canApproveStatusOnly) return
    try {
      const res = await listEmployeeStatusPending(access, employeeKey)
      setPendingStatusRequests(Array.isArray(res.requests) ? res.requests : [])
    } catch {
      setPendingStatusRequests([])
    }
  }, [access, employeeKey, canRequestStatusChange, canApproveStatusOnly])

  useEffect(() => {
    void reloadPendingStatus()
  }, [reloadPendingStatus, data?.employee?.updated_at])

  const changeStatus = useCallback(
    async (next: 'left' | 'active') => {
      if (!emp) return
      if (!emp.updated_at) {
        onNotice('Refresh this employee before changing their status.', 'error')
        return
      }
      if (next === 'left') {
        const ok = await confirm({
          title: 'Mark this employee as left?',
          body: 'They will be removed from active rosters, but their history and documents will stay available.',
          confirmLabel: 'Mark as left',
          destructive: true,
        })
        if (!ok) return
      }
      const reason = await confirm.withReason({
        title: 'Reason required',
        body: 'Employment status changes need a durable reason for audit.',
        confirmLabel: 'Continue',
        requireReason: true,
        reasonLabel: 'Reason',
        reasonPlaceholder: 'Why is this change needed?',
      })
      if (!reason) return
      const approvalReference = await confirm.withReason({
        title: 'Approval reference',
        body: 'Enter the approval reference for this two-person status change.',
        confirmLabel: 'Continue',
        requireReason: true,
        reasonLabel: 'Approval reference',
        reasonPlaceholder: 'Ticket / email / decision id',
      })
      if (!approvalReference) return
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `status-${Date.now()}-${Math.random().toString(16).slice(2)}`
      setStatusBusy(true)
      try {
        const policy = await getEmployeeStatusApprovalPolicy(access)
        if (!policy.status_change_available) {
          onNotice(
            policy.blocked_reason === 'no_eligible_approver'
              ? 'No eligible separate approver is available. Grant employees.status.approve to another teammate before changing status.'
              : 'Employment status changes are unavailable right now.',
            'error',
          )
          return
        }

        // Production-safe default: two-person pending request. Canary is only used
        // when the server explicitly allowlists this company/environment.
        if (policy.canary_allowed && policy.self_approval_allowed && canApproveStatus) {
          const useCanary = await confirm({
            title: 'Use internal canary self-approval?',
            body: 'This environment allows self-approved internal canary. Prefer a separate approver in production.',
            confirmLabel: 'Self-approve (canary)',
          })
          if (useCanary) {
            const result = await setEmployeeStatus(access, emp.employee_key, {
              status: next,
              reason,
              idempotency_key: idempotencyKey,
              expected_status: hasLeft ? 'left' : 'active',
              expected_updated_at: emp.updated_at,
              approver_user_id: 'self',
              approval_reference: approvalReference,
              approval_mode: 'self_approved_internal_canary',
            })
            if (result.verified) {
              onNotice(next === 'left' ? `${emp.name} was marked as left.` : `${emp.name} was reactivated.`, 'success')
            } else {
              onNotice(`The change committed as ${result.result_id}, but independent verification is still pending.`, 'info')
            }
            await reload()
            await reloadPendingStatus()
            return
          }
        }

        const approvers = policy.eligible_approvers || []
        if (!approvers.length) {
          onNotice('No eligible separate approver is available for this status change.', 'error')
          return
        }
        const choices = approvers
          .map((a, idx) => `${idx + 1}. ${(a.name || a.email || a.user_id).trim()} (${a.user_id})`)
          .join('\n')
        const picked = window.prompt(`Choose approver number:\n${choices}`)?.trim()
        if (!picked) return
        const index = Number(picked) - 1
        const approver = approvers[index]
        if (!approver) {
          onNotice('Pick a valid approver from the list.', 'error')
          return
        }
        await createEmployeeStatusApprovalRequest(access, emp.employee_key, {
          status: next,
          reason,
          idempotency_key: idempotencyKey,
          expected_status: hasLeft ? 'left' : 'active',
          expected_updated_at: emp.updated_at,
          designated_approver_user_id: approver.user_id,
          approval_reference: approvalReference,
        })
        onNotice(`Status change requested. Waiting for approval from ${approver.name || approver.email || 'the designated approver'}.`, 'info')
        await reloadPendingStatus()
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue(issue)
          return
        }
        onNotice(friendlyError(err, 'We couldn’t update this employee. Please try again.'), 'error')
      } finally {
        setStatusBusy(false)
      }
    },
    [access, emp, hasLeft, confirm, onNotice, onAccessIssue, reload, reloadPendingStatus, canApproveStatus],
  )

  const issueActivationHandoff = useCallback(async () => {
    if (!emp) return
    const reason = window.prompt('Required reason for this secure activation handoff:')?.trim()
    if (!reason) return
    const newKey = () => globalThis.crypto?.randomUUID?.() || `invite-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const create = (supersedeInviteId?: string) => createEmployeeAppHandoff(access, emp.employee_key, {
      delivery_mode: 'hr_task_only',
      idempotency_key: newKey(),
      reason: supersedeInviteId ? `${reason} (explicit supersede and reissue)` : reason,
      ...(supersedeInviteId ? { supersede_invite_id: supersedeInviteId } : {}),
    })
    setActivationBusy(true)
    try {
      let result
      try {
        result = await create()
      } catch (err) {
        if (!(err instanceof DashboardApiError) || err.code !== 'pending_activation_invite_exists') throw err
        const detail = typeof err.detail === 'object' && err.detail ? err.detail as Record<string, unknown> : {}
        const pendingInviteId = String(detail.pending_invite_id || '')
        if (!pendingInviteId) throw err
        const approved = await confirm({
          title: 'Supersede the pending activation invite?',
          body: 'The previous code will stop working. A new one-time code will be shown once in this window.',
          confirmLabel: 'Supersede and reissue',
          destructive: true,
        })
        if (!approved) return
        result = await create(pendingInviteId)
      }
      setActivationHandoff(result)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, 'We couldn’t create the secure activation handoff.'), 'error')
    } finally {
      setActivationBusy(false)
    }
  }, [access, confirm, emp, onAccessIssue, onNotice])

  const sections = data?.sections
  const nextActions = data?.next_actions ?? []
  const nextActionsEnabled = Boolean(data?.next_actions_enabled)
  const tenure = tenureLabel(emp?.hired_at)

  // Only safe one-click nudges are executable from the panel, and only when the
  // viewer holds the same permission the module page requires. Everything else
  // (two-sided decisions, judgment calls) stays navigation-only.
  const canRunNextAction = useCallback(
    (a: EmployeeProfileNextAction) => {
      if (!a.executable || !a.action_type) return false
      if (a.module === 'compliance') return canComplianceManage
      // Onboarding mutations belong on the Onboarding page — profile only routes.
      if (a.module === 'onboarding') return false
      return false
    },
    [canComplianceManage],
  )

  const runNextAction = useCallback(
    async (a: EmployeeProfileNextAction) => {
      if (!a.action_type) return
      if (a.requires_confirmation) {
        const ok = await confirm({
          title: a.action_label ? `${a.action_label}?` : 'Please confirm',
          body: a.reason ? `${a.title} — ${a.reason}` : a.title || 'Run this action?',
          confirmLabel: a.action_label || 'Confirm',
          destructive: Boolean(a.destructive),
        })
        if (!ok) return
      }
      await action.run(a.action_type, a.args || {}, { destructive: Boolean(a.destructive), key: `next:${a.id}` })
    },
    [action, confirm],
  )

  const goToSection = useCallback((section: string) => {
    if (typeof document === 'undefined') return
    const el = document.getElementById(`emp360-section-${section}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  return (
    <div className="space-y-6">
      {action.dialog}
      {showEdit && emp ? (
        <EditEmployeeModal access={access} employee={emp} onClose={() => setShowEdit(false)} onNotice={onNotice} onSaved={() => void reload()} />
      ) : null}
      {activationHandoff ? (
        <ActivationHandoffModal handoff={activationHandoff} onClose={() => setActivationHandoff(null)} />
      ) : null}
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← Back to directory
        </Button>
        <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : !emp ? (
        <EmptyState icon={<UserRound className="h-5 w-5" />} title="Employee not found" hint="This employee may have been removed." />
      ) : (
        <>
          <Card tone="board">
            <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-[20px] font-semibold tracking-[-0.03em] text-text">{emp.name}</h2>
                <p className="text-[13px] text-subtle/90">
                  {[emp.position_title, emp.department].filter(Boolean).join(' · ') || 'No role on file'}
                </p>
                <p className="mt-1 text-[12.5px] text-subtle/80">
                  {emp.phone || 'No phone'}
                  {emp.email ? ` · ${emp.email}` : ''}
                </p>
                {emp.hired_at ? (
                  <p className="mt-1 text-[12.5px] text-subtle/80">
                    Hired {formatDate(emp.hired_at)}
                    {tenure ? ` · ${tenure} with the company` : ''}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-col items-start gap-2 sm:items-end">
                <div className="flex items-center gap-2">
                  {hasLeft ? <Badge tone="muted">Left</Badge> : null}
                  <StatusBadge status={emp.onboarding_status} />
                </div>
                {canManageRoster ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button variant="secondary" size="sm" disabled={statusBusy} onClick={() => setShowEdit(true)}>
                      Edit
                    </Button>
                    {canIssueActivation && !hasLeft ? (
                      <Button variant="secondary" size="sm" disabled={activationBusy} onClick={() => void issueActivationHandoff()}>
                        {activationBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Activation handoff
                      </Button>
                    ) : null}
                    {canRequestStatusChange ? (
                      hasLeft ? (
                        <Button variant="ghost" size="sm" disabled={statusBusy} onClick={() => void changeStatus('active')}>
                          {statusBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Reactivate
                        </Button>
                      ) : (
                        <Button variant="ghost" size="sm" disabled={statusBusy} onClick={() => void changeStatus('left')}>
                          {statusBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Mark as left
                        </Button>
                      )
                    ) : null}
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          {pendingStatusRequests.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Pending status approvals</CardTitle>
                <CardDescription>Two-person employment status changes waiting for a decision. Rejected or cancelled requests leave the employee unchanged.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {pendingStatusRequests.map((req) => {
                  const requestId = String(req.request_id || '')
                  const requested = String(req.requested_status || '')
                  return (
                    <div key={requestId} className="flex flex-col gap-2 rounded-xl border border-line/50 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="text-[13px] text-text">
                        <p className="font-medium">Request to mark as {requested}</p>
                        <p className="text-subtle/90">{String(req.reason || '')}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {canRequestStatusChange ? (
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={statusBusy}
                            onClick={() => {
                              void (async () => {
                                setStatusBusy(true)
                                try {
                                  await cancelEmployeeStatusApprovalRequest(access, requestId)
                                  onNotice('Status approval request cancelled. Employee status was not changed.', 'info')
                                  await reloadPendingStatus()
                                } catch (err) {
                                  onNotice(friendlyError(err, 'Could not cancel that request.'), 'error')
                                } finally {
                                  setStatusBusy(false)
                                }
                              })()
                            }}
                          >
                            Cancel
                          </Button>
                        ) : null}
                        {canApproveStatusOnly ? (
                          <>
                            <Button
                              variant="secondary"
                              size="sm"
                              disabled={statusBusy}
                              onClick={() => {
                                void (async () => {
                                  setStatusBusy(true)
                                  try {
                                    await decideEmployeeStatusApprovalRequest(access, requestId, { action: 'reject', decision_reason: 'rejected_in_dashboard' })
                                    onNotice('Status change rejected. Employee status was not changed.', 'info')
                                    await reloadPendingStatus()
                                  } catch (err) {
                                    onNotice(friendlyError(err, 'Could not reject that request.'), 'error')
                                  } finally {
                                    setStatusBusy(false)
                                  }
                                })()
                              }}
                            >
                              Reject
                            </Button>
                            <Button
                              size="sm"
                              disabled={statusBusy}
                              onClick={() => {
                                void (async () => {
                                  setStatusBusy(true)
                                  try {
                                    const res = await decideEmployeeStatusApprovalRequest(access, requestId, { action: 'approve' })
                                    if (res.committed) {
                                      onNotice('Status change approved and applied.', 'success')
                                      await reload()
                                    }
                                    await reloadPendingStatus()
                                  } catch (err) {
                                    onNotice(friendlyError(err, 'Could not approve that request.'), 'error')
                                  } finally {
                                    setStatusBusy(false)
                                  }
                                })()
                              }}
                            >
                              Approve
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          ) : null}

          {nextActions.length === 0 ? (
            <NextAction tone="success" icon={<CheckCircle2 className="h-5 w-5" />} title="Nothing needs attention" detail={`${emp.name} has no open items across the enabled modules.`} />
          ) : nextActionsEnabled ? (
            <NextActionsPanel
              actions={nextActions}
              summary={data?.next_actions_summary}
              canRun={canRunNextAction}
              onRun={runNextAction}
              onNavigate={goToSection}
              busy={action.busy}
              runningKey={action.runningKey}
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>What to do next</CardTitle>
                <CardDescription>The open items HR should clear for this employee.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {nextActions.map((a, idx) => (
                  <div key={`${a.module}-${idx}`} className="flex items-center gap-2 text-[13px] text-text">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    <span>{a.label}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <AssignmentHistoryPanel access={access} employeeKey={employeeKey} onAccessIssue={onAccessIssue} />
          <EssBankMaskPanel access={access} employeeKey={employeeKey} onAccessIssue={onAccessIssue} />

          <div className="space-y-4">
            {sections?.onboarding ? (
              <CollapsibleSection
                id="emp360-section-onboarding"
                icon={<ClipboardList className="h-4 w-4" />}
                title="Onboarding"
                description={`${sections.onboarding.outstanding_count} outstanding · ${sections.onboarding.complete_count} complete`}
                defaultOpen={sections.onboarding.outstanding_count > 0}
              >
                <div className="space-y-3">
                  {sections.onboarding.outstanding.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">All required documents are in.</p>
                  ) : (
                    <ul className="space-y-1.5 text-[13px]">
                      {sections.onboarding.outstanding.map((it, idx) => (
                        <li key={it.item_id || idx} className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-text">{it.label}</span>
                          <StatusBadge status={it.status} />
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-[12.5px] text-subtle/85">
                    Checklist updates, reminders, reschedule, and cancel live on Onboarding.
                  </p>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onNavigate?.('onboarding', { employee: employeeKey })}
                  >
                    Open in Onboarding
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.compliance ? (
              <CollapsibleSection
                id="emp360-section-compliance"
                icon={<ShieldCheck className="h-4 w-4" />}
                title="Compliance"
                description={
                  sections.compliance.needs_attention
                    ? `${sections.compliance.needs_attention} need attention`
                    : 'All documents up to date'
                }
                defaultOpen={sections.compliance.documents.length > 0}
              >
                <div>
                  <p className="mb-2 text-[12.5px] text-subtle/85">
                    {isAr
                      ? 'المراجعة والتذكير تتم في الامتثال.'
                      : 'Review and reminders happen in Compliance.'}
                  </p>
                  {sections.compliance.documents.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">No documents are expired, expiring, or missing.</p>
                  ) : (
                    <ul className="space-y-2 text-[13px]">
                      {sections.compliance.documents.map((doc, idx) => (
                        <li key={doc.document_type || idx} className="flex flex-wrap items-center justify-between gap-2">
                          <span className="min-w-0">
                            <span className="block text-text">{doc.document_label}</span>
                            <span className="block text-[11.5px] text-subtle/80">
                              {doc.expiry_date ? `Expires ${formatDate(doc.expiry_date)} · ${complianceDaysLabel(doc)}` : 'No expiry on file'}
                            </span>
                          </span>
                          <Badge tone={doc.tone}>{doc.status_label}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                  <Button
                    className="mt-3"
                    variant="secondary"
                    size="sm"
                    onClick={() => onNavigate?.('compliance', { employee: emp.employee_key })}
                  >
                    {isAr ? 'فتح في الامتثال' : 'Open in Compliance'}
                  </Button>
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.attendance ? (
              <CollapsibleSection
                id="emp360-section-attendance"
                icon={<Clock className="h-4 w-4" />}
                title="Attendance"
                description={`Last ${sections.attendance.window_days} days`}
                defaultOpen={sections.attendance.absent > 0}
              >
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-2">
                    <StatCard label="Present" value={sections.attendance.present} />
                    <StatCard label="Late" value={sections.attendance.late} />
                    <StatCard label="Absent" value={sections.attendance.absent} />
                  </div>
                  {sections.attendance.recent.length > 0 ? (
                    <ul className="space-y-1 text-[12.5px] text-subtle/90">
                      {sections.attendance.recent.slice(0, 5).map((r, idx) => (
                        <li key={idx} className="flex items-center justify-between gap-2">
                          <span>{formatDate(r.date)}</span>
                          <span>{titleCase(r.status || '')}{r.late_minutes ? ` · +${r.late_minutes}m` : ''}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.leave ? (
              <CollapsibleSection
                id="emp360-section-leave"
                icon={<CalendarDays className="h-4 w-4" />}
                title="Leave"
                description={sections.leave.pending_count ? `${sections.leave.pending_count} awaiting decision` : 'No pending requests'}
                defaultOpen={sections.leave.pending_count > 0}
              >
                <div className="space-y-3">
                  {sections.leave.balances_enabled && (sections.leave.balances?.length ?? 0) > 0 ? (
                    <div className="mb-3 space-y-1.5">
                      {sections.leave.balances!.map((b, idx) => (
                        <div key={idx} className="flex items-center justify-between gap-2 rounded-[0.9rem] border border-line/45 bg-panel/55 px-3 py-2 text-[12px]">
                          <span className="text-subtle/90">{titleCase(b.leave_type)} balance</span>
                          <span className="font-medium text-text">
                            {Math.round(b.current_balance * 10) / 10}
                            {b.entitlement_days ? ` / ${Math.round(b.entitlement_days * 10) / 10} days` : ' days'}
                          </span>
                        </div>
                      ))}
                      <p className="text-[11px] text-subtle/70">Preset figures, not enforced — for reference only.</p>
                    </div>
                  ) : null}
                  {sections.leave.items.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">No pending or upcoming leave.</p>
                  ) : (
                    <ul className="space-y-2 text-[13px]">
                      {sections.leave.items.map((it, idx) => (
                        <li key={idx} className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-text">{titleCase(it.leave_type || 'leave')} · {formatDate(it.start_date)}–{formatDate(it.end_date)}</span>
                          <StatusBadge status={it.status} />
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-[12.5px] text-subtle/85">
                    Approve, decline, request info, dual-control, and cancel live on Leave.
                  </p>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onNavigate?.('leave', { employee: employeeKey })}
                  >
                    Open in Leave
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.shifts ? (
              <CollapsibleSection
                id="emp360-section-shifts"
                icon={<CalendarClock className="h-4 w-4" />}
                title="Upcoming shifts"
                description={`${sections.shifts.upcoming_count} scheduled`}
                defaultOpen={false}
              >
                <div>
                  {sections.shifts.items.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">No upcoming shifts.</p>
                  ) : (
                    <ul className="space-y-1.5 text-[13px]">
                      {sections.shifts.items.slice(0, 6).map((it, idx) => (
                        <li key={idx} className="flex items-center justify-between gap-2">
                          <span className="text-text">{formatDate(it.date)}</span>
                          <span className="text-subtle/90">{it.start_time?.slice(0, 5)}–{it.end_time?.slice(0, 5)}{it.location ? ` · ${it.location}` : ''}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.payroll ? (
              <CollapsibleSection
                id="emp360-section-payroll"
                icon={<DollarSign className="h-4 w-4" />}
                title="Payroll"
                description="Recent timesheets"
                defaultOpen={sections.payroll.items.some((it) => canPayrollManage && String(it.status || '').toLowerCase() === 'draft')}
              >
                <div>
                  {sections.payroll.items.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">No timesheets yet.</p>
                  ) : (
                    <ul className="space-y-2 text-[13px]">
                      {sections.payroll.items.map((it, idx) => {
                        const needsDecision = canPayrollManage && it.timesheet_id && String(it.status || '').toLowerCase() === 'draft'
                        const tsArgs = { timesheet_id: it.timesheet_id, employee_name: emp.name }
                        const approveKey = `profile-approve-ts:${it.timesheet_id || idx}`
                        const rejectKey = `profile-reject-ts:${it.timesheet_id || idx}`
                        return (
                          <li key={it.timesheet_id || idx} className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-text">{formatDate(it.period_start)}–{formatDate(it.period_end)}</span>
                            <span className="flex items-center gap-1.5 text-subtle/90">
                              <span>{it.worked_hours}h{it.overtime_hours ? ` · OT ${it.overtime_hours}h` : ''}</span>
                              <StatusBadge status={it.status} />
                              {needsDecision ? (
                                <>
                                  <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => action.run('reject_timesheet', tsArgs, { destructive: true, key: rejectKey, confirm: { title: 'Reject this timesheet?', body: `${emp.name}'s timesheet for ${formatDate(it.period_start)}–${formatDate(it.period_end)} will be sent back and won't count toward payroll until it's corrected and approved.`, confirmLabel: 'Reject timesheet' } })}>
                                    {action.runningKey === rejectKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Reject'}
                                  </Button>
                                  <Button size="sm" disabled={action.busy} onClick={() => action.run('approve_timesheet', tsArgs, { key: approveKey })}>
                                    {action.runningKey === approveKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Approve'}
                                  </Button>
                                </>
                              ) : null}
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              </CollapsibleSection>
            ) : null}

            {sections?.documents && sections.documents.items.length > 0 ? (
              <CollapsibleSection
                icon={<FileText className="h-4 w-4" />}
                title="Documents"
                description={
                  <>
                    {sections.documents.count} file{sections.documents.count === 1 ? '' : 's'} submitted
                    {sections.onboarding && sections.onboarding.outstanding_count > 0
                      ? ` · ${sections.onboarding.outstanding_count} required document${sections.onboarding.outstanding_count === 1 ? '' : 's'} still missing`
                      : ' · nothing missing'}
                  </>
                }
                defaultOpen={false}
              >
                <div>
                  <ul className="divide-y divide-line/45">
                    {sections.documents.items.map((doc) => (
                      <li key={doc.file_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium text-text">{doc.label || (doc.document_type ? titleCase(doc.document_type) : '') || doc.filename || 'Document'}</p>
                          <p className="text-[11.5px] text-subtle/80">
                            {doc.filename ? `${doc.filename}` : doc.document_type ? titleCase(doc.document_type) : ''}
                            {doc.stored_at ? ` · ${formatDate(doc.stored_at)}` : ''}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          {doc.has_file ? (
                            <DocumentActions access={access} fileId={doc.file_id} filename={doc.filename || doc.label || undefined} />
                          ) : (
                            <span className="text-[11.5px] text-subtle/70">File unavailable</span>
                          )}
                          {canUpload && doc.document_type ? (
                            <DocumentUploadButton
                              access={access}
                              employeeKey={employeeKey}
                              itemId={doc.document_type}
                              documentLabel={doc.label || doc.document_type}
                              hasFile={Boolean(doc.has_file)}
                              onUploaded={(message) => { onNotice(message, 'success'); void reload() }}
                              onError={(message) => onNotice(message, 'error')}
                              onAccessIssue={onAccessIssue}
                            />
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                  {canUpload ? <DocumentPrivacyNote className="mt-3" /> : null}
                </div>
              </CollapsibleSection>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

// --- Onboarding ------------------------------------------------------------

function DocumentActions({
  access,
  fileId,
  filename,
  compact,
}: {
  access: DashboardAccess
  fileId?: string | null
  filename?: string | null
  compact?: boolean
}) {
  const [busy, setBusy] = useState<'inline' | 'attachment' | null>(null)
  const [failed, setFailed] = useState(false)
  if (!fileId) return null
  const open = async (disposition: 'inline' | 'attachment') => {
    setBusy(disposition)
    setFailed(false)
    try {
      await openEmployeeDocument(access, fileId, { disposition, filename: filename || undefined })
    } catch (err) {
      // Raw detail stays in the console; the user gets a calm inline notice
      // instead of a silently-failing button.
      console.error('Could not open document', err)
      setFailed(true)
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        <Button variant="ghost" size="sm" disabled={busy !== null} onClick={() => open('inline')} title="View document">
          {busy === 'inline' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
          {compact ? null : <span className="ml-1.5">View</span>}
        </Button>
        <Button variant="ghost" size="sm" disabled={busy !== null} onClick={() => open('attachment')} title="Download document">
          {busy === 'attachment' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {compact ? null : <span className="ml-1.5">Download</span>}
        </Button>
      </div>
      {failed ? (
        <span className="text-[11px] leading-4 text-rose-600">Couldn’t open this document. Please try again.</span>
      ) : null}
    </div>
  )
}

function DocumentHrReviewButtons({
  access,
  employeeKey,
  documentType,
  documentLabel,
  employeeName,
  showApprove,
  primaryOnly,
  onDone,
  onError,
  onAccessIssue,
  locale = 'en',
}: {
  access: DashboardAccess
  employeeKey: string
  documentType: string
  documentLabel?: string | null
  employeeName?: string | null
  showApprove?: boolean
  /** When true, show only the primary approve action (reject/dates behind More). */
  primaryOnly?: boolean
  onDone: (message: string) => void
  onError: (message: string) => void
  onAccessIssue?: (issue: AccessIssue) => void
  locale?: 'en' | 'ar'
}) {
  const confirm = useConfirm()
  const isAr = locale === 'ar'
  const [busy, setBusy] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [datesOpen, setDatesOpen] = useState(false)
  const [expiryDate, setExpiryDate] = useState('')
  const [issueDate, setIssueDate] = useState('')
  const [metaReason, setMetaReason] = useState('')
  const [dateError, setDateError] = useState<string | null>(null)
  const datesPanelRef = useRef<HTMLDivElement>(null)
  useBodyScrollLock(datesOpen)
  useOverlayFocus(datesOpen, () => setDatesOpen(false), datesPanelRef)
  const label = documentLabel || titleCase(documentType)
  const who = employeeName || (isAr ? 'هذا الموظف' : 'this employee')

  const run = async (action: 'approve' | 'reject' | 'request_reupload' | 'correct_metadata', extra: Record<string, string | boolean | null> = {}) => {
    setBusy(true)
    try {
      await reviewEmployeeDocument(access, employeeKey, documentType, { action, ...extra })
      onDone(
        action === 'approve'
          ? isAr
            ? 'وُسمت كمراجعة موارد بشرية (ليست تحققاً حكومياً).'
            : 'Marked as HR reviewed (not government verified).'
          : action === 'correct_metadata'
            ? isAr
              ? 'تم تحديث بيانات المستند.'
              : 'Document metadata updated.'
            : isAr
              ? 'مرفوض — يلزم إعادة الرفع.'
              : 'Rejected — re-upload required.',
      )
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onError(friendlyError(err, isAr ? 'تعذر تحديث مراجعة المستند.' : 'We could not update that document review.'))
    } finally {
      setBusy(false)
    }
  }

  const onReject = async () => {
    const reason = await confirm.withReason({
      title: isAr ? 'رفض — يلزم إعادة الرفع؟' : 'Reject — re-upload required?',
      body: isAr
        ? `سيُرفض الرفع الحالي لـ ${label} لـ ${who}. أي نسخة مراجعة سابقاً تبقى سارية حتى اعتماد البديل.`
        : `The pending upload for ${label} for ${who} will be rejected. Any previously HR-reviewed version stays current.`,
      confirmLabel: isAr ? 'رفض' : 'Reject',
      cancelLabel: isAr ? 'إلغاء' : 'Cancel',
      destructive: true,
      reasonLabel: isAr ? 'سبب الرفض' : 'Rejection reason',
      reasonPlaceholder: isAr ? 'مثال: الصورة غير واضحة' : 'Example: image is unreadable',
      minReasonLength: 3,
      dir: isAr ? 'rtl' : 'ltr',
    })
    if (!reason) return
    await run('reject', { reason })
  }

  const onApprove = async () => {
    if (
      !(await confirm({
        title: isAr ? 'وسم كمراجعة موارد بشرية؟' : 'Mark as HR reviewed?',
        body: isAr
          ? `${label} لـ ${who} سيُوسم كمراجعة موارد بشرية. هذا يؤكد مراجعة الدليل — وليس تحقق PACI أو MOI أو PAM.`
          : `${label} for ${who} will be marked HR reviewed. This confirms authorized HR reviewed the uploaded evidence — it is not PACI, MOI, or PAM verification.`,
        confirmLabel: isAr ? 'مراجعة موارد بشرية' : 'HR reviewed',
        dir: isAr ? 'rtl' : 'ltr',
      }))
    )
      return
    await run('approve')
  }

  const submitDates = async () => {
    const expiry = expiryDate.trim()
    const issue = issueDate.trim()
    const dateRe = /^\d{4}-\d{2}-\d{2}$/
    if (!expiry && !issue) {
      setDateError(isAr ? 'أدخل تاريخ انتهاء أو إصدار.' : 'Enter an expiry or issue date.')
      return
    }
    if (expiry && !dateRe.test(expiry)) {
      setDateError(isAr ? 'صيغة الانتهاء: YYYY-MM-DD' : 'Expiry must be YYYY-MM-DD')
      return
    }
    if (issue && !dateRe.test(issue)) {
      setDateError(isAr ? 'صيغة الإصدار: YYYY-MM-DD' : 'Issue date must be YYYY-MM-DD')
      return
    }
    setDateError(null)
    setDatesOpen(false)
    await run('correct_metadata', {
      expiry_date: expiry || null,
      issue_date: issue || null,
      reason: metaReason.trim() || null,
    })
    setExpiryDate('')
    setIssueDate('')
    setMetaReason('')
  }

  const secondary = (
    <>
      <Button variant="ghost" size="sm" disabled={busy} onClick={() => void onReject()}>
        {isAr ? 'رفض' : 'Reject'}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => {
          setDateError(null)
          setDatesOpen(true)
        }}
      >
        {isAr ? 'تصحيح التواريخ' : 'Correct dates'}
      </Button>
    </>
  )

  return (
    <span className="flex flex-wrap items-center gap-1">
      {showApprove ? (
        <Button variant={primaryOnly ? 'default' : 'ghost'} size="sm" disabled={busy} onClick={() => void onApprove()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : isAr ? 'مراجعة موارد بشرية' : 'HR reviewed'}
        </Button>
      ) : null}
      {primaryOnly ? (
        <>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setMoreOpen((v) => !v)}>
            {isAr ? 'المزيد' : 'More'}
          </Button>
          {moreOpen ? secondary : null}
        </>
      ) : (
        secondary
      )}

      {datesOpen ? (
        <div
          aria-modal="true"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/35 px-4 backdrop-blur-sm"
          dir={isAr ? 'rtl' : 'ltr'}
          onClick={() => (busy ? null : setDatesOpen(false))}
          role="dialog"
        >
          <div
            ref={datesPanelRef}
            className="w-full max-w-md rounded-[1.6rem] border border-[#e8dfd0] bg-[#fffaf0] p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)]"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-[15px] font-semibold text-ink">
              {isAr ? `تصحيح تواريخ ${label}` : `Correct dates for ${label}`}
            </p>
            <p className="mt-1 text-[13px] text-muted">
              {isAr ? `${who} · ليس تحققاً حكومياً` : `${who} · not government verification`}
            </p>
            <div className="mt-4 space-y-3">
              <label className="block space-y-1 text-[12px] font-medium text-muted">
                {isAr ? 'تاريخ الانتهاء' : 'Expiry date'}
                <Input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
              </label>
              <label className="block space-y-1 text-[12px] font-medium text-muted">
                {isAr ? 'تاريخ الإصدار' : 'Issue date'}
                <Input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
              </label>
              <label className="block space-y-1 text-[12px] font-medium text-muted">
                {isAr ? 'سبب التصحيح (اختياري)' : 'Correction reason (optional)'}
                <Textarea
                  value={metaReason}
                  onChange={(e) => setMetaReason(e.target.value)}
                  placeholder={isAr ? 'مثال: تصحيح بعد مراجعة الملف' : 'Example: corrected after file review'}
                  className="min-h-[72px]"
                />
              </label>
              {dateError ? <p className="text-[12px] text-rose-700">{dateError}</p> : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" size="sm" disabled={busy} onClick={() => setDatesOpen(false)}>
                {isAr ? 'إلغاء' : 'Cancel'}
              </Button>
              <Button size="sm" disabled={busy} onClick={() => void submitDates()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {isAr ? 'حفظ التواريخ' : 'Save dates'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </span>
  )
}

function DocumentUploadButton({
  access,
  employeeKey,
  itemId,
  documentLabel,
  hasFile,
  onUploaded,
  onError,
  onAccessIssue,
  compact,
}: {
  access: DashboardAccess
  employeeKey: string
  itemId: string
  documentLabel?: string | null
  hasFile: boolean
  onUploaded: (message: string) => void
  onError: (message: string) => void
  onAccessIssue?: (issue: AccessIssue) => void
  compact?: boolean
}) {
  const confirm = useConfirm()
  const [busy, setBusy] = useState(false)
  const inputId = `doc-upload-${employeeKey}-${itemId}`
  const label = documentLabel || titleCase(itemId) || 'document'
  const onPick = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow re-picking the same file
    if (!file) return
    if (file.size > MAX_EMPLOYEE_DOC_BYTES) {
      onError('This file is too large. Please upload a file up to 15 MB.')
      return
    }
    if (hasFile && isSensitiveIdentityDocument(itemId, documentLabel)) {
      const ok = await confirm({
        title: 'Replace this document?',
        body: `The new file will be stored as a pending version of ${label} for HR review. The prior HR-reviewed file stays current until the replacement is approved. This is not government verification.`,
        confirmLabel: 'Replace document',
        destructive: true,
      })
      if (!ok) return
    }
    setBusy(true)
    try {
      await uploadEmployeeDocument(access, employeeKey, { file, itemId })
      onUploaded(hasFile ? 'Document replaced.' : 'Document uploaded.')
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onError(friendlyError(err, 'We could not upload that document.'))
    } finally {
      setBusy(false)
    }
  }
  const hint = 'PDF, JPG, PNG, DOC · up to 15 MB'
  const actionLabel = hasFile ? 'Replace' : 'Upload'
  return (
    <div className={cn('flex', compact ? 'items-center' : 'flex-col items-end gap-0.5')}>
      <input id={inputId} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.heic" onChange={onPick} disabled={busy} />
      <Button variant="ghost" size="sm" disabled={busy} onClick={() => document.getElementById(inputId)?.click()} title={`${actionLabel} document (${hint})`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {compact ? null : <span className="ml-1.5">{actionLabel}</span>}
      </Button>
      {compact ? null : <span className="text-[10px] text-subtle/70">{hint}</span>}
    </div>
  )
}

// Calm, accurate reassurance shown where HR uploads employee documents. We only
// state what the system actually does — RBAC-scoped access + an audit trail — and
// deliberately avoid encryption/compliance claims the code doesn't back.
function DocumentPrivacyNote({ className }: { className?: string }) {
  return (
    <p className={cn('flex items-start gap-1.5 text-[11px] leading-4 text-subtle/75', className)}>
      <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle/60" />
      <span>Only permitted HR and admin users can view uploaded employee documents. Wathefni records document activity for accountability.</span>
    </p>
  )
}

function onboardingOwnerGroup(item: OnboardingItem): string {
  if (item.owner_group) return String(item.owner_group)
  const auth = String(item.authority || '').toLowerCase()
  const cat = String(item.category || '').toLowerCase()
  const id = String(item.item_id || '').toLowerCase()
  if (auth === 'ess' || cat === 'payroll_bank' || id === 'bank_details') return 'payroll'
  if (auth === 'compliance_mirror' || cat === 'compliance_gov') return 'compliance'
  if (['account_access_created', 'attendance_device_id', 'access_card_issued', 'asset_handover', 'app_invite_sent'].includes(id)) return 'it'
  if (String(item.owner || '').toLowerCase() === 'employee') return 'employee'
  return 'hr'
}

const ONBOARDING_GROUP_ORDER = ['employee', 'hr', 'it', 'payroll', 'compliance'] as const
const ONBOARDING_GROUP_LABELS: Record<string, { en: string; ar: string }> = {
  employee: { en: 'Employee', ar: 'الموظف' },
  hr: { en: 'HR', ar: 'الموارد البشرية' },
  it: { en: 'IT', ar: 'تقنية المعلومات' },
  payroll: { en: 'Payroll', ar: 'الرواتب' },
  compliance: { en: 'Compliance', ar: 'الامتثال' },
}

function OnboardingChecklistItem({
  access,
  item,
  fileId,
  canMutate,
  canUpload,
  employeeKey,
  onUploaded,
  onError,
  onAccessIssue,
  busy,
  runningKey,
  onMark,
  locale = 'en',
}: {
  access: DashboardAccess
  item: OnboardingItem
  fileId?: string | null
  canMutate: boolean
  canUpload?: boolean
  employeeKey?: string
  onUploaded?: (message: string) => void
  onError?: (message: string) => void
  onAccessIssue?: (issue: AccessIssue) => void
  busy: boolean
  runningKey: string | null
  onMark: (item: OnboardingItem, status: 'received' | 'waived') => void
  done?: boolean
  locale?: 'en' | 'ar'
}) {
  const isAr = locale === 'ar'
  const key = item.item_id || item.document_type || item.label || ''
  const reminded = Number(item.reminder_count || 0)
  const ess = String(item.item_id || '') === 'bank_details' || String(item.authority || '') === 'ess'
  const mirror = String(item.authority || '') === 'compliance_mirror'
  const blocked = Boolean(item.blocked_by?.length)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[0.9rem] border border-[#e8dfd0] bg-[#fffdf8] px-3.5 py-2.5">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-text">
          {item.label || (item.document_type ? titleCase(item.document_type) : item.item_id)}
          {item.required ? (
            <span className="ms-1.5 text-[11px] font-normal text-wf-ink/70">{isAr ? 'إلزامي' : 'Required'}</span>
          ) : (
            <span className="ms-1.5 text-[11px] font-normal text-subtle/70">{isAr ? 'اختياري' : 'Optional'}</span>
          )}
        </p>
        <p className="mt-0.5 text-[11.5px] text-subtle/80">
          {reminded > 0
            ? isAr
              ? `${reminded} تذكير`
              : `${reminded} reminder${reminded === 1 ? '' : 's'} sent`
            : isAr
              ? 'لا تذكيرات'
              : 'No reminders sent'}
          {item.last_reminded_at ? ` · ${formatDate(item.last_reminded_at)}` : ''}
          {item.due_date ? ` · ${isAr ? 'الاستحقاق' : 'Due'} ${formatDate(String(item.due_date))}` : ''}
        </p>
        {blocked ? (
          <p className="mt-1 text-[11.5px] text-wf-ink">
            {item.blocked_reason || (isAr ? 'أكمل المتطلبات أولاً' : 'Complete prerequisites first')}
          </p>
        ) : null}
        {ess ? (
          <p className="mt-1 text-[11.5px] text-subtle/85">
            {isAr
              ? 'إعداد البنك عبر الخدمة الذاتية المشفّرة للموظف — وليس كنص هنا.'
              : 'Bank setup happens in secure Employee Self-Service — not as plain text here.'}
          </p>
        ) : null}
        {mirror ? (
          <p className="mt-1 text-[11.5px] text-subtle/85">
            {isAr ? 'يُدار في الامتثال — هذا الصف تذكير فقط.' : 'Tracked in Compliance — this row is a reminder only.'}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={item.status} />
        <DocumentActions access={access} fileId={fileId} filename={item.label || item.document_type || undefined} compact />
        {canUpload && employeeKey && item.item_id && onUploaded && onError && !ess && !mirror ? (
          <DocumentUploadButton
            access={access}
            employeeKey={employeeKey}
            itemId={item.item_id}
            documentLabel={item.label || item.document_type}
            hasFile={Boolean(fileId)}
            onUploaded={onUploaded}
            onError={onError}
            onAccessIssue={onAccessIssue}
          />
        ) : null}
        {canMutate && !ess && !mirror ? (
          <>
            <Button variant="ghost" size="sm" disabled={busy || blocked} onClick={() => onMark(item, 'received')}>
              {runningKey === `mark:received:${key}` ? <Loader2 className="h-4 w-4 animate-spin" /> : isAr ? 'تم الاستلام' : 'Mark complete'}
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => onMark(item, 'waived')}>
              {runningKey === `mark:waived:${key}` ? <Loader2 className="h-4 w-4 animate-spin" /> : isAr ? 'استثناء' : 'Waive'}
            </Button>
          </>
        ) : null}
        {canMutate && ess ? (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => onMark(item, 'waived')}>
            {isAr ? 'استثناء' : 'Waive'}
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function OnboardingDetailPanel({
  access,
  detail,
  loading,
  error,
  onRetry,
  canMutate,
  busy,
  runningKey,
  onMark,
  onUploaded,
  onError,
  onAccessIssue,
  locale = 'en',
}: {
  access: DashboardAccess
  detail: OnboardingDetailResponse | null
  loading: boolean
  error?: boolean
  onRetry?: () => void
  canMutate: boolean
  busy: boolean
  runningKey: string | null
  onMark: (item: OnboardingItem, status: 'received' | 'waived') => void
  onUploaded?: (message: string) => void
  onError?: (message: string) => void
  onAccessIssue?: (issue: AccessIssue) => void
  locale?: 'en' | 'ar'
}) {
  const isAr = locale === 'ar'
  if (loading && !detail) {
    return <div className="px-4 py-3 text-[12.5px] text-subtle/80">{isAr ? 'جارٍ تحميل القائمة…' : 'Loading checklist…'}</div>
  }
  if (error && !detail) {
    return (
      <div className="flex flex-wrap items-center gap-3 border-t border-[#e8dfd0] bg-[#fbf7f0]/40 px-4 py-3 text-[12.5px] text-subtle/80">
        <span>{isAr ? 'تعذّر تحميل القائمة.' : 'We couldn’t load this checklist. Please try again.'}</span>
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {isAr ? 'إعادة المحاولة' : 'Try again'}
          </Button>
        ) : null}
      </div>
    )
  }
  if (!detail) return null
  const allItems = (detail.items && detail.items.length ? detail.items : [...(detail.pending || []), ...(detail.received || [])]) as OnboardingItem[]
  const closed = new Set(['received', 'complete', 'completed', 'verified', 'waived', 'cancelled_onboarding', 'abandoned_employment_ended', 'retired_legacy'])
  const pending = allItems.filter((i) => !closed.has(String(i.status || '').toLowerCase()))
  const received = allItems.filter((i) => ['received', 'complete', 'completed', 'verified'].includes(String(i.status || '').toLowerCase()))
  const documentIndex = detail.document_index ?? {}
  const canUpload = canMutate && Boolean(detail.doc_upload_enabled)
  const employeeKey = detail.employee_key
  const fileIdFor = (item: OnboardingItem) => documentIndex[item.item_id || ''] || documentIndex[item.document_type || ''] || null
  const grouped: Record<string, OnboardingItem[]> = {}
  for (const g of ONBOARDING_GROUP_ORDER) grouped[g] = []
  for (const item of pending) {
    const g = onboardingOwnerGroup(item)
    if (!grouped[g]) grouped[g] = []
    grouped[g].push(item)
  }
  return (
    <div className="space-y-4 border-t border-[#e8dfd0] bg-[#fbf7f0]/35 px-4 py-4" dir={isAr ? 'rtl' : 'ltr'}>
      {detail.bank_collection?.plaintext_forbidden ? (
        <p className="flex items-start gap-1.5 text-[12px] leading-5 text-subtle/80">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            {detail.bank_collection.message ||
              (isAr ? 'إعداد البنك عبر الخدمة الذاتية المشفّرة للموظف.' : 'Bank setup happens through secure Employee Self-Service.')}
          </span>
        </p>
      ) : null}
      {pending.length === 0 && received.length === 0 ? (
        <p className="text-[12.5px] text-subtle/80">{isAr ? 'لا بنود بعد.' : 'No checklist items recorded for this employee yet.'}</p>
      ) : null}
      {ONBOARDING_GROUP_ORDER.map((g) => {
        const list = grouped[g] || []
        if (!list.length) return null
        return (
          <div key={g} className="space-y-2">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.07em] text-mist">
              {ONBOARDING_GROUP_LABELS[g][locale]} ({list.length})
            </p>
            {list.map((item) => (
              <OnboardingChecklistItem
                key={`p-${item.item_id || item.document_type || item.label}`}
                access={access}
                item={item}
                fileId={fileIdFor(item)}
                canMutate={canMutate}
                canUpload={canUpload}
                employeeKey={employeeKey}
                onUploaded={onUploaded}
                onError={onError}
                onAccessIssue={onAccessIssue}
                busy={busy}
                runningKey={runningKey}
                onMark={onMark}
                locale={locale}
              />
            ))}
          </div>
        )
      })}
      {received.length ? (
        <div className="space-y-2">
          <p className="text-[11.5px] font-semibold uppercase tracking-[0.07em] text-subtle/80">
            {isAr ? 'مستلم' : 'Received'} ({received.length})
          </p>
          {received.map((item) => (
            <OnboardingChecklistItem
              key={`r-${item.item_id || item.document_type || item.label}`}
              access={access}
              item={item}
              fileId={fileIdFor(item)}
              canMutate={false}
              canUpload={canUpload}
              employeeKey={employeeKey}
              onUploaded={onUploaded}
              onError={onError}
              onAccessIssue={onAccessIssue}
              busy={busy}
              runningKey={runningKey}
              onMark={onMark}
              done
              locale={locale}
            />
          ))}
        </div>
      ) : null}
      {canUpload ? <DocumentPrivacyNote /> : null}
    </div>
  )
}

function OnboardingPage({ access, permissions, role, onNotice, onAccessIssue, onNavigate }: PostHireCommonProps & Pick<PostHireProps, 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query.trim(), 350)
  const loader = useCallback(
    () => getPosthireOnboarding(access, debouncedQuery ? { search: debouncedQuery } : undefined),
    [access, debouncedQuery],
  )
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireOnboardingResponse>(loader, onAccessIssue)
  const canManage = can(permissions, 'onboarding.manage', role)
  const [extraInProgress, setExtraInProgress] = useState<PosthireEmployee[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  const [filter, setFilter] = useState<'needs_attention' | 'in_progress' | 'not_started' | 'completed' | 'all'>('needs_attention')
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [focusMissing, setFocusMissing] = useState(false)
  const [focusPin, setFocusPin] = useState<PosthireEmployee | null>(null)
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({})

  useEffect(() => {
    setExtraInProgress([])
  }, [data])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<OnboardingDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [rescheduleFor, setRescheduleFor] = useState<string | null>(null)
  const [rescheduleDate, setRescheduleDate] = useState('')

  const loadDetail = useCallback(
    async (key: string) => {
      setDetailLoading(true)
      setDetailError(false)
      try {
        setDetail(await getOnboardingDetail(access, key))
      } catch {
        setDetail(null)
        setDetailError(true)
      } finally {
        setDetailLoading(false)
      }
    },
    [access],
  )

  const syncEmployeeParam = useCallback((key: string | null) => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.set('page', 'onboarding')
    if (key) url.searchParams.set('employee', key)
    else url.searchParams.delete('employee')
    window.history.replaceState({}, '', `${url.pathname}${url.search}`)
  }, [])

  const focusEmployee = useCallback(
    async (focusKey: string) => {
      setExpanded(focusKey)
      setFocusMissing(false)
      syncEmployeeParam(focusKey)
      void loadDetail(focusKey)
      const known =
        (data?.in_progress ?? []).some((e) => e.employee_key === focusKey) ||
        extraInProgress.some((e) => e.employee_key === focusKey) ||
        focusPin?.employee_key === focusKey
      if (!known) {
        try {
          const d = await getOnboardingDetail(access, focusKey)
          setFocusPin({
            employee_key: d.employee_key,
            name: String(d.name || focusKey),
            phone: String(d.phone || ''),
            email: '',
            position_title: '',
            department: '',
            onboarding_status: String(d.status || 'in_progress'),
            assignment_status: String(d.status || 'in_progress'),
            planned_start_date: d.planned_start_date,
            pending_count: d.pending_count,
            received_count: d.received_count,
            required_total: d.required_total,
            overdue_count: d.overdue_count,
            next_owner: d.next_owner,
            next_owner_group: d.next_owner_group,
            next_item_label: d.next_item_label,
            next_item_status: d.next_item_status,
            next_item_storage_status: d.next_item_storage_status,
          })
          setDetail(d)
        } catch {
          setFocusMissing(true)
          setFocusPin(null)
        }
      }
      requestAnimationFrame(() => {
        rowRefs.current[focusKey]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
    },
    [access, data?.in_progress, extraInProgress, focusPin?.employee_key, loadDetail, syncEmployeeParam],
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const focusKey = new URLSearchParams(window.location.search).get('employee')
    if (!focusKey) return
    void focusEmployee(focusKey)
    // Intentional: honor deep-link once loader is ready.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadDetail])

  const reloadAll = useCallback(async () => {
    await reload()
    if (expanded) await loadDetail(expanded)
  }, [reload, expanded, loadDetail])
  const action = usePosthireAction(access, reloadAll, onNotice, onAccessIssue)
  const baseInProgress = data?.in_progress ?? []
  const merged = useMemo(() => {
    const rows = [...baseInProgress, ...extraInProgress]
    if (focusPin && !rows.some((r) => r.employee_key === focusPin.employee_key)) {
      return [focusPin, ...rows]
    }
    return rows
  }, [baseInProgress, extraInProgress, focusPin])
  const totalInProgress = data?.total_count ?? baseInProgress.length
  const searching = debouncedQuery.length > 0
  const hrMutate = Boolean(data?.hr_mutate_enabled)
  const canMutate = canManage && hrMutate
  const completedCount = data?.completed_count ?? 0

  const isNeedsAttentionRow = (emp: PosthireEmployee) => {
    const overdue = Number(emp.overdue_count || 0)
    const status = String(emp.assignment_status || emp.onboarding_status || '').toLowerCase()
    return overdue > 0 || status === 'delayed' || Number(emp.pending_count || 0) > 0
  }

  const filtered = useMemo(() => {
    if (filter === 'completed') return [] as PosthireEmployee[]
    if (filter === 'all') return merged
    if (filter === 'needs_attention') return merged.filter(isNeedsAttentionRow)
    if (filter === 'not_started') {
      return merged.filter((e) => String(e.assignment_status || e.onboarding_status || '').toLowerCase() === 'not_started')
    }
    return merged.filter((e) => {
      const s = String(e.assignment_status || e.onboarding_status || '').toLowerCase()
      return s === 'in_progress' || s === 'delayed' || s === 'pending' || (!s && Number(e.pending_count || 0) > 0)
    })
  }, [merged, filter])

  const filterCounts = useMemo(
    () => ({
      needs_attention: merged.filter(isNeedsAttentionRow).length,
      in_progress: merged.filter((e) => {
        const s = String(e.assignment_status || e.onboarding_status || '').toLowerCase()
        return s === 'in_progress' || s === 'delayed' || s === 'pending' || (!s && Number(e.pending_count || 0) > 0)
      }).length,
      not_started: merged.filter((e) => String(e.assignment_status || e.onboarding_status || '').toLowerCase() === 'not_started').length,
      completed: completedCount,
      all: merged.length,
    }),
    [merged, completedCount],
  )

  const loadMoreFixed = useCallback(async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthireOnboarding(access, {
        offset: baseInProgress.length + extraInProgress.length,
        ...(debouncedQuery ? { search: debouncedQuery } : {}),
      })
      setExtraInProgress((prev) => [...prev, ...(res.in_progress ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, isAr ? 'تعذّر التحميل.' : 'We couldn’t load more people. Please try again.'), 'error')
    } finally {
      setLoadingMore(false)
    }
  }, [access, baseInProgress.length, extraInProgress.length, debouncedQuery, onAccessIssue, onNotice, isAr])

  const toggleExpand = useCallback(
    (key: string) => {
      if (expanded === key) {
        setExpanded(null)
        setDetail(null)
        setDetailError(false)
        setRescheduleFor(null)
        setMenuFor(null)
        syncEmployeeParam(null)
        return
      }
      setExpanded(key)
      setDetail(null)
      setDetailError(false)
      setMenuFor(null)
      syncEmployeeParam(key)
      void loadDetail(key)
    },
    [expanded, loadDetail, syncEmployeeParam],
  )

  const markItem = useCallback(
    (emp: PosthireEmployee, item: OnboardingItem, status: 'received' | 'waived') => {
      const key = item.item_id || item.document_type || item.label || ''
      if (String(item.item_id || '') === 'bank_details' && status === 'received') {
        onNotice(
          isAr
            ? 'إعداد البنك عبر الخدمة الذاتية المشفّرة — لا يمكن تأكيده كنص هنا.'
            : 'Bank setup uses secure Employee Self-Service — it cannot be marked complete with plain text here.',
          'info',
        )
        return
      }
      void action.run(
        'onboarding_mark_item',
        {
          employee_key: emp.employee_key,
          item_id: item.item_id,
          item_status: status,
          expected_row_version: item.row_version,
        },
        {
          destructive: status === 'waived',
          key: `mark:${status}:${key}`,
          confirm:
            status === 'waived'
              ? {
                  title: isAr ? 'استثناء هذا البند؟' : 'Waive this item?',
                  body: isAr
                    ? `«${item.label}» لن يكون مطلوباً لتهيئة ${emp.name || 'هذا الموظف'}.`
                    : `“${item.label}” will no longer be required for ${emp.name || 'this employee'}'s onboarding.`,
                  confirmLabel: isAr ? 'استثناء البند' : 'Waive item',
                }
              : {
                  title: isAr ? 'تأكيد استلام البند؟' : 'Mark this item received?',
                  body: isAr
                    ? `سيُعلَّم «${item.label}» كمكتمل لـ ${emp.name || 'هذا الموظف'}.`
                    : `“${item.label}” will be marked complete for ${emp.name || 'this employee'}.`,
                  confirmLabel: isAr ? 'تأكيد الاستلام' : 'Mark received',
                },
        },
      )
    },
    [action, isAr, onNotice],
  )

  const stateLabel = (status?: string | null) => {
    const s = String(status || '').toLowerCase()
    const map: Record<string, { en: string; ar: string }> = {
      not_started: { en: 'Not started', ar: 'لم يبدأ' },
      delayed: { en: 'Delayed', ar: 'مؤجّل' },
      in_progress: { en: 'In progress', ar: 'جارٍ' },
      completed: { en: 'Completed', ar: 'مكتمل' },
      cancelled: { en: 'Cancelled', ar: 'ملغى' },
      abandoned: { en: 'Abandoned', ar: 'متروك' },
    }
    return map[s]?.[locale] || status || '—'
  }

  const urgencyFor = (emp: PosthireEmployee) => {
    const overdue = Number(emp.overdue_count || 0)
    const status = String(emp.assignment_status || emp.onboarding_status || '').toLowerCase()
    if (overdue > 0 || status === 'delayed') {
      return { tone: 'danger' as const, en: 'Overdue', ar: 'متأخر' }
    }
    if (Number(emp.pending_count || 0) > 0) {
      return { tone: 'warning' as const, en: 'Needs attention', ar: 'يحتاج متابعة' }
    }
    return { tone: 'muted' as const, en: 'On track', ar: 'على المسار' }
  }

  const copy = {
    queue: isAr ? 'قائمة التهيئة' : 'Onboarding queue',
    queueHint: isAr
      ? 'من العرض إلى جاهز للبدء — قائمة واضحة، عوائق، ومالك، والإجراء التالي.'
      : 'From accepted offer to ready-to-start — checklist, blockers, ownership, and next action.',
    search: isAr ? 'ابحث بالاسم أو الدور أو القسم…' : 'Search name, role, department…',
    filterNeeds: isAr ? 'يحتاج متابعة' : 'Needs attention',
    filterInProg: isAr ? 'جارٍ' : 'In progress',
    filterNotStarted: isAr ? 'لم يبدأ' : 'Not started',
    filterDone: isAr ? 'مكتمل' : 'Completed',
    filterAll: isAr ? 'الكل' : 'All',
    start: isAr ? 'تاريخ البدء' : 'Start',
    progress: isAr ? 'التقدّم' : 'Progress',
    next: isAr ? 'التالي' : 'Next',
    remind: isAr ? 'تذكير' : 'Remind',
    openChecklist: isAr ? 'فتح القائمة' : 'Open checklist',
    review: isAr ? 'مراجعة' : 'Review',
    viewDetails: isAr ? 'عرض التفاصيل' : 'View details',
    checklist: isAr ? 'القائمة' : 'Checklist',
    hide: isAr ? 'إخفاء' : 'Hide',
    more: isAr ? 'المزيد' : 'More',
    reschedule: isAr ? 'إعادة جدولة' : 'Reschedule',
    cancel: isAr ? 'إلغاء' : 'Cancel',
    readOnly: isAr
      ? 'يمكنك المراجعة والتذكير فقط — التعديل غير متاح هنا حالياً.'
      : 'You can review and remind only — checklist edits aren’t available here yet.',
    noPerm: isAr ? 'ليست لديك صلاحية تغيير التهيئة.' : 'You don’t have permission to change onboarding.',
    focusMissing: isAr ? 'لم نتمكن من فتح هذا الموظف في قائمة التهيئة.' : 'We couldn’t open that hire in the onboarding queue.',
    completedEmpty: isAr
      ? `${completedCount} مكتملون — لا يظهرون في قائمة العمل النشطة.`
      : `${completedCount} completed — they don’t appear in the active queue.`,
    emptyTitle: searching
      ? isAr
        ? `لا نتائج لـ «${debouncedQuery}»`
        : `No matches for “${debouncedQuery}”`
      : isAr
        ? 'لا يوجد معلّق في هذا التصفية'
        : 'Nothing in this filter',
    emptyHint: searching
      ? isAr
        ? 'جرّب بحثاً آخر.'
        : 'Try a different name, role, or department.'
      : isAr
        ? 'يظهر الموظفون الجدد هنا أثناء التهيئة.'
        : 'New hires appear here while they finish onboarding.',
  }

  const filterChip = (id: typeof filter, label: string, count: number) => (
    <button
      key={id}
      type="button"
      onClick={() => setFilter(id)}
      className={cn(
        'rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition',
        filter === id ? 'bg-[#23211d] text-white' : 'bg-[#eee5d4]/80 text-[#5c554a] hover:bg-[#eee5d4]',
      )}
    >
      {label}
      <span className="ms-1.5 tabular-nums opacity-80">{count}</span>
    </button>
  )

  return (
    <div className="space-y-4" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="onboarding-page">
      {action.dialog}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-[13px] leading-5 text-subtle/90">{copy.queueHint}</p>
        <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          {!canManage ? (
            <p className="text-[12.5px] text-subtle/85">{copy.noPerm}</p>
          ) : !hrMutate ? (
            <p className="text-[12.5px] text-subtle/85">{copy.readOnly}</p>
          ) : null}
          {focusMissing ? (
            <div className="rounded-[1.05rem] border border-[#e2bd78]/70 bg-[#fff7e8]/70 px-4 py-3 text-[13px] text-text">{copy.focusMissing}</div>
          ) : null}
          <Card tone="board" data-testid="onboarding-queue">
            <CardHeader className="space-y-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <CardTitle>{copy.queue}</CardTitle>
                  <CardDescription>
                    {searching
                      ? isAr
                        ? `${totalInProgress} نتيجة لـ «${debouncedQuery}»`
                        : `${totalInProgress} active · “${debouncedQuery}”`
                      : isAr
                        ? `${totalInProgress} نشط · ${completedCount} مكتمل`
                        : `${totalInProgress} active · ${completedCount} completed`}
                  </CardDescription>
                </div>
                <SearchInput value={query} onChange={setQuery} placeholder={copy.search} />
              </div>
              <div className="flex flex-wrap gap-1.5" data-testid="onboarding-filters" role="tablist">
                {filterChip('needs_attention', copy.filterNeeds, filterCounts.needs_attention)}
                {filterChip('in_progress', copy.filterInProg, filterCounts.in_progress)}
                {filterChip('not_started', copy.filterNotStarted, filterCounts.not_started)}
                {filterChip('completed', copy.filterDone, filterCounts.completed)}
                {filterChip('all', copy.filterAll, filterCounts.all)}
              </div>
            </CardHeader>
            <CardContent>
              {filter === 'completed' ? (
                <WorkflowEmpty title={isAr ? 'المكتملون' : 'Completed'} hint={copy.completedEmpty} />
              ) : filtered.length === 0 ? (
                <WorkflowEmpty title={copy.emptyTitle} hint={copy.emptyHint} />
              ) : (
                <div className="space-y-2">
                  {filtered.map((emp) => {
                    const isOpen = expanded === emp.employee_key
                    const pendingCount = Number(emp.pending_count || 0)
                    const receivedCount = Number(emp.received_count || 0)
                    const totalReq = Number(emp.required_total || pendingCount + receivedCount)
                    const overdue = Number(emp.overdue_count || 0)
                    const status = emp.assignment_status || emp.onboarding_status
                    const planned = emp.planned_start_date || emp.start_date
                    const urgency = urgencyFor(emp)
                    const menuOpen = menuFor === emp.employee_key
                    const rowDetail = isOpen && detail?.employee_key === emp.employee_key ? detail : null
                    const primaryKind: OnboardingPrimaryKind = onboardingPrimaryAction({
                      employee_key: emp.employee_key,
                      pending_count: emp.pending_count,
                      next_owner: emp.next_owner,
                      next_owner_group: emp.next_owner_group,
                      next_item_label: emp.next_item_label,
                      next_item_status: emp.next_item_status,
                      next_item_storage_status: emp.next_item_storage_status,
                      detail: rowDetail,
                      canRemind: canManage,
                    })
                    const primaryLabel =
                      primaryKind === 'remind'
                        ? copy.remind
                        : primaryKind === 'review'
                          ? isOpen
                            ? copy.hide
                            : copy.review
                          : primaryKind === 'open_checklist'
                            ? isOpen
                              ? copy.hide
                              : copy.openChecklist
                            : isOpen
                              ? copy.hide
                              : copy.viewDetails
                    const blocker =
                      emp.next_item_label ||
                      (overdue > 0
                        ? isAr
                          ? `${overdue} بند متأخر`
                          : `${overdue} overdue item${overdue === 1 ? '' : 's'}`
                        : pendingCount > 0
                          ? isAr
                            ? `${pendingCount} مطلوب`
                            : `${pendingCount} still required`
                          : null)
                    return (
                      <div
                        key={emp.employee_key || emp.phone || emp.name}
                        ref={(node) => {
                          if (emp.employee_key) rowRefs.current[emp.employee_key] = node
                        }}
                        className={cn(
                          'overflow-hidden rounded-[1.05rem] border bg-[#fffdf8] transition',
                          isOpen ? 'border-[#23211d]/35 shadow-[0_1px_0_rgba(35,33,29,0.06)]' : 'border-[#e8dfd0]',
                        )}
                        data-testid="onboarding-row"
                        data-employee-key={emp.employee_key}
                        data-primary-action={primaryKind}
                      >
                        <div className="flex flex-col gap-3 px-3.5 py-3 sm:flex-row sm:items-start sm:justify-between">
                          <button type="button" onClick={() => toggleExpand(emp.employee_key)} className="min-w-0 flex-1 text-start">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone={urgency.tone}>{isAr ? urgency.ar : urgency.en}</Badge>
                              <StatusPill
                                tone={
                                  String(status).toLowerCase() === 'completed'
                                    ? 'success'
                                    : String(status).toLowerCase() === 'delayed'
                                      ? 'follow'
                                      : String(status).toLowerCase() === 'cancelled' || String(status).toLowerCase() === 'abandoned'
                                        ? 'paused'
                                        : 'priority'
                                }
                              >
                                {stateLabel(status)}
                              </StatusPill>
                            </div>
                            <p className="mt-1.5 text-[14px] font-semibold tracking-[-0.01em] text-text">{emp.name}</p>
                            <p className="truncate text-[12.5px] text-subtle/85">
                              {emp.position_title || (isAr ? 'عضو الفريق' : 'Team member')}
                              {emp.department ? ` · ${emp.department}` : ''}
                            </p>
                            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-subtle/75">
                              <span>
                                {copy.start}: {planned ? formatDate(String(planned)) : '—'}
                              </span>
                              <span>
                                {copy.progress}: {receivedCount}/{totalReq || '—'}
                              </span>
                              {blocker ? (
                                <span className="font-medium text-text">
                                  {copy.next}:{' '}
                                  {(emp.next_owner_group && ONBOARDING_GROUP_LABELS[emp.next_owner_group]?.[locale]) || emp.next_owner || ''}
                                  {emp.next_item_label ? ` · ${emp.next_item_label}` : ` · ${blocker}`}
                                </span>
                              ) : null}
                            </div>
                          </button>
                          <div className="relative flex shrink-0 flex-wrap items-center gap-2">
                            {primaryKind === 'remind' ? (
                              <Button
                                size="sm"
                                disabled={action.busy}
                                onClick={() => {
                                  void action.run('send_onboarding_reminder', employeeRef(emp), {
                                    key: `reminder:${emp.employee_key}`,
                                    confirm: {
                                      title: isAr ? 'إرسال تذكير التهيئة؟' : 'Send onboarding reminder?',
                                      body: isAr
                                        ? `${emp.name} سيستلم تذكيراً الآن.`
                                        : `${emp.name} will receive an onboarding reminder message now.`,
                                      confirmLabel: isAr ? 'إرسال التذكير' : 'Send reminder',
                                    },
                                  })
                                }}
                              >
                                {action.runningKey === `reminder:${emp.employee_key}` ? (
                                  <>
                                    <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جارٍ…' : 'Sending…'}
                                  </>
                                ) : (
                                  primaryLabel
                                )}
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant={primaryKind === 'view_details' ? 'secondary' : 'default'}
                                onClick={() => toggleExpand(emp.employee_key)}
                              >
                                {primaryLabel}
                                {primaryKind === 'view_details' && !isOpen ? (
                                  <Eye className="h-4 w-4" />
                                ) : (
                                  <ChevronDown className={cn('h-4 w-4 transition', isOpen && 'rotate-180')} />
                                )}
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={copy.more}
                              onClick={() => setMenuFor((cur) => (cur === emp.employee_key ? null : emp.employee_key))}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                            {menuOpen ? (
                              <div className="absolute end-0 top-full z-20 mt-1 min-w-[11rem] rounded-xl border border-[#e8dfd0] bg-white p-1 shadow-md">
                                {primaryKind !== 'remind' && canManage ? (
                                  <button
                                    type="button"
                                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                                    disabled={action.busy}
                                    onClick={() => {
                                      setMenuFor(null)
                                      void action.run('send_onboarding_reminder', employeeRef(emp), {
                                        key: `reminder:${emp.employee_key}`,
                                        confirm: {
                                          title: isAr ? 'إرسال تذكير التهيئة؟' : 'Send onboarding reminder?',
                                          body: isAr
                                            ? `${emp.name} سيستلم تذكيراً الآن.`
                                            : `${emp.name} will receive an onboarding reminder message now.`,
                                          confirmLabel: isAr ? 'إرسال التذكير' : 'Send reminder',
                                        },
                                      })
                                    }}
                                  >
                                    {copy.remind}
                                  </button>
                                ) : null}
                                {primaryKind === 'remind' || primaryKind === 'view_details' ? (
                                  <button
                                    type="button"
                                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                                    onClick={() => {
                                      setMenuFor(null)
                                      toggleExpand(emp.employee_key)
                                    }}
                                  >
                                    {isOpen ? copy.hide : copy.checklist}
                                  </button>
                                ) : null}
                                {canMutate ? (
                                  <>
                                    <button
                                      type="button"
                                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                                      onClick={() => {
                                        setMenuFor(null)
                                        setRescheduleFor(emp.employee_key)
                                        setRescheduleDate(String(planned || '').slice(0, 10))
                                        if (!isOpen) toggleExpand(emp.employee_key)
                                      }}
                                    >
                                      <CalendarClock className="h-3.5 w-3.5" /> {copy.reschedule}
                                    </button>
                                    <button
                                      type="button"
                                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] text-[#8a3b2a] hover:bg-[#f7f1e6]"
                                      disabled={action.busy}
                                      onClick={() => {
                                        setMenuFor(null)
                                        void action.run(
                                          'cancel_onboarding',
                                          { employee_key: emp.employee_key, reason: 'hr_cancelled' },
                                          {
                                            key: `cancel:${emp.employee_key}`,
                                            destructive: true,
                                            confirm: {
                                              title: isAr ? 'إلغاء التهيئة؟' : 'Cancel onboarding?',
                                              body: isAr
                                                ? `سيتم إلغاء تهيئة ${emp.name}. يُحفظ السجل.`
                                                : `Onboarding for ${emp.name} will be cancelled. Checklist history is kept.`,
                                              confirmLabel: isAr ? 'إلغاء التهيئة' : 'Cancel onboarding',
                                              destructive: true,
                                            },
                                          },
                                        )
                                      }}
                                    >
                                      {copy.cancel}
                                    </button>
                                  </>
                                ) : null}
                                {onNavigate ? (
                                  <button
                                    type="button"
                                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                                    onClick={() => {
                                      setMenuFor(null)
                                      onNavigate('employees', { employee: emp.employee_key })
                                    }}
                                  >
                                    <UserRound className="h-3.5 w-3.5" /> {isAr ? 'الملف' : 'Profile'}
                                  </button>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        </div>
                        {isOpen && rescheduleFor === emp.employee_key && canMutate ? (
                          <div className="flex flex-wrap items-end gap-2 border-t border-[#e8dfd0] bg-[#fbf7f0] px-3.5 py-3">
                            <label className="flex flex-col gap-1 text-[12px] text-subtle/85">
                              {isAr ? 'تاريخ البدء' : 'Start date'}
                              <Input type="date" value={rescheduleDate} onChange={(e) => setRescheduleDate(e.target.value)} className="h-10 w-44" />
                            </label>
                            <Button
                              size="sm"
                              disabled={!rescheduleDate || action.busy}
                              onClick={() => {
                                void action.run(
                                  'reschedule_onboarding',
                                  { employee_key: emp.employee_key, planned_start_date: rescheduleDate },
                                  {
                                    key: `reschedule:${emp.employee_key}`,
                                    confirm: {
                                      title: isAr ? 'تغيير تاريخ البدء؟' : 'Change start date?',
                                      body: isAr
                                        ? 'ستُحدَّث تواريخ الاستحقاق للبنود غير المكتملة.'
                                        : 'Open due dates for unfinished items will update to the new start date.',
                                      confirmLabel: isAr ? 'تحديث' : 'Update start date',
                                    },
                                    onSuccess: () => setRescheduleFor(null),
                                  },
                                )
                              }}
                            >
                              {isAr ? 'تحديث' : 'Update'}
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setRescheduleFor(null)}>
                              {copy.hide}
                            </Button>
                          </div>
                        ) : null}
                        {isOpen ? (
                          <OnboardingDetailPanel
                            access={access}
                            detail={detail}
                            loading={detailLoading}
                            error={detailError}
                            onRetry={() => {
                              if (emp.employee_key) void loadDetail(emp.employee_key)
                            }}
                            canMutate={canMutate}
                            busy={action.busy}
                            runningKey={action.runningKey}
                            onMark={(item, status) => markItem(emp, item, status)}
                            onUploaded={(message) => {
                              onNotice(message, 'success')
                              void reloadAll()
                            }}
                            onError={(message) => onNotice(message, 'error')}
                            onAccessIssue={onAccessIssue}
                            locale={locale}
                          />
                        ) : null}
                      </div>
                    )
                  })}
                  <LoadMoreBar
                    loaded={baseInProgress.length + extraInProgress.length}
                    total={totalInProgress}
                    loading={loadingMore}
                    onLoadMore={() => void loadMoreFixed()}
                    noun={isAr ? 'موظف' : 'new hire'}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// --- Attendance ------------------------------------------------------------

function attendanceAddDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function attendanceMonthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`
}

function AttendancePage({ access, permissions, role, onNotice, onAccessIssue }: PostHireCommonProps) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [range, setRange] = useState<{ start: string; end: string } | null>(null)
  const loader = useCallback(
    () => getPosthireAttendance(access, range ? { start_date: range.start, end_date: range.end } : undefined),
    [access, range],
  )
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireAttendanceResponse>(loader, onAccessIssue)
  const canManage = can(permissions, 'attendance.manage', role)
  const canExport = can(permissions, 'attendance.read', role)
  const [exporting, setExporting] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [operationsOpen, setOperationsOpen] = useState(false)
  const [exceptionCount, setExceptionCount] = useState(0)
  const [focusEmployeeKey, setFocusEmployeeKey] = useState<string | null>(null)
  const [focusWorkDate, setFocusWorkDate] = useState<string | null>(null)

  const [extraRows, setExtraRows] = useState<PosthireAttendanceRow[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraRows([])
  }, [data])

  const rows = [...(data?.attendance ?? []), ...extraRows]
  const totalRows = data?.total_count ?? rows.length

  const loadMore = useCallback(async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthireAttendance(
        access,
        range ? { start_date: range.start, end_date: range.end } : { start_date: data?.start_date, end_date: data?.end_date },
        { offset: rows.length },
      )
      setExtraRows((prev) => [...prev, ...(res.attendance ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(friendlyError(err, isAr ? 'تعذر تحميل المزيد.' : 'We couldn’t load more attendance. Please try again.'), 'error')
    } finally {
      setLoadingMore(false)
    }
  }, [access, range, data?.start_date, data?.end_date, rows.length, onAccessIssue, onNotice, isAr])

  const today = data?.date || ''
  const effStart = range?.start || data?.start_date || today
  const effEnd = range?.end || data?.end_date || today
  const isSingleDay = effStart === effEnd
  const isToday = Boolean(data?.is_today) && !range

  const rangeLabel = isToday
    ? isAr
      ? `اليوم · ${formatDate(today)}`
      : `Today · ${formatDate(today)}`
    : isSingleDay
      ? formatDate(effStart)
      : `${formatDate(effStart)} → ${formatDate(effEnd)}`

  const runExport = async () => {
    if (!effStart || !effEnd) return
    setExporting(true)
    try {
      await exportAttendanceCsv(access, { start_date: effStart, end_date: effEnd })
      onNotice(isAr ? 'تم تنزيل تصدير الحضور.' : 'Attendance export downloaded.', 'success')
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(friendlyError(err, isAr ? 'تعذر تصدير الحضور.' : 'We couldn’t export attendance. Please try again.'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const resolveFromBoard = useCallback(
    (row: PosthireAttendanceRow) => {
      setFocusEmployeeKey(String(row.employee_key || '') || null)
      setFocusWorkDate(String(row.attendance_date || data?.date || '').slice(0, 10) || null)
    },
    [data?.date],
  )

  const copy = {
    hint: isAr
      ? 'افهم حالة اليوم، حدّد الاستثناءات، وحلّها بمسار واحد محكوم.'
      : 'Understand today’s attendance, spot exceptions, and resolve them through one governed path.',
    board: isAr ? 'لوحة الحضور' : 'Attendance board',
    operations: isAr ? 'العمليات' : 'Operations',
    operationsHint: isAr
      ? 'الاستيراد والأجهزة والموصّلات والتشخيص — خارج مساحة العمل اليومية.'
      : 'Imports, devices, connectors, and diagnostics — outside the daily HR workspace.',
    showOps: isAr ? 'إظهار العمليات' : 'Show Operations',
    hideOps: isAr ? 'إخفاء العمليات' : 'Hide Operations',
    import: isAr ? 'استيراد من جهاز' : 'Import from device',
    export: isAr ? 'تصدير CSV' : 'Export CSV',
    noPerm: isAr ? 'يمكنك المراجعة فقط — حل الاستثناءات يتطلب صلاحية الإدارة.' : 'View only — resolving exceptions needs manage permission.',
  }

  return (
    <div className="space-y-4" data-testid="attendance-page" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      {showImport ? (
        <AttendanceImportDialog
          access={access}
          onClose={() => setShowImport(false)}
          onImported={() => {
            void reload()
          }}
        />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-[13px] leading-5 text-subtle/90">{copy.hint}</p>
        <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      </div>

      {!canManage ? <p className="text-[12.5px] text-subtle/85">{copy.noPerm}</p> : null}

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <AttendanceAttentionStrip rows={rows} exceptionCount={exceptionCount} />

          <Card tone="board" data-testid="attendance-board">
            <CardHeader className="space-y-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <CardTitle>{copy.board}</CardTitle>
                  <CardDescription>
                    {rangeLabel} · {isAr ? `${totalRows} سجل` : `${totalRows} record${totalRows === 1 ? '' : 's'}`}
                  </CardDescription>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2" data-testid="attendance-date-chrome">
                <Button variant={isToday ? 'secondary' : 'ghost'} size="sm" disabled={refreshing} onClick={() => setRange(null)}>
                  {isAr ? 'اليوم' : 'Today'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={refreshing || !today}
                  onClick={() => setRange({ start: attendanceAddDays(today, -6), end: today })}
                >
                  {isAr ? 'آخر 7 أيام' : 'Last 7 days'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={refreshing || !today}
                  onClick={() => setRange({ start: attendanceMonthStart(today), end: today })}
                >
                  {isAr ? 'هذا الشهر' : 'This month'}
                </Button>
                <div className="flex items-center gap-1.5">
                  <input
                    type="date"
                    value={effStart}
                    max={effEnd || undefined}
                    onChange={(e) => e.target.value && setRange({ start: e.target.value, end: effEnd < e.target.value ? e.target.value : effEnd })}
                    className="h-9 rounded-full border border-line/60 bg-white/70 px-3 text-[12.5px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                  />
                  <span className="text-[12px] text-subtle/70">→</span>
                  <input
                    type="date"
                    value={effEnd}
                    min={effStart || undefined}
                    onChange={(e) => e.target.value && setRange({ start: effStart, end: e.target.value })}
                    className="h-9 rounded-full border border-line/60 bg-white/70 px-3 text-[12.5px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <AttendanceDailyTable rows={rows} canManage={canManage} onResolve={canManage ? resolveFromBoard : undefined} />
              <LoadMoreBar
                loaded={rows.length}
                total={totalRows}
                loading={loadingMore}
                onLoadMore={() => void loadMore()}
                noun={isAr ? 'سجل' : 'record'}
              />
            </CardContent>
          </Card>

          {canManage ? (
            <AttendanceOpsPanel
              access={access}
              canManage={canManage}
              onNotice={onNotice}
              onAccessIssue={onAccessIssue}
              compact
              focusEmployeeKey={focusEmployeeKey}
              focusWorkDate={focusWorkDate}
              onOpenCount={setExceptionCount}
            />
          ) : null}

          <div className="rounded-[1.05rem] border border-[#e8dfd0] bg-[#fffdf8]/70" data-testid="attendance-operations">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-start"
              onClick={() => setOperationsOpen((o) => !o)}
              aria-expanded={operationsOpen}
            >
              <div>
                <p className="text-[14px] font-semibold text-text">{copy.operations}</p>
                <p className="text-[12.5px] text-subtle/85">{copy.operationsHint}</p>
              </div>
              <span className="text-[12.5px] font-semibold text-subtle">{operationsOpen ? copy.hideOps : copy.showOps}</span>
            </button>
            {operationsOpen ? (
              <div className="space-y-4 border-t border-[#e8dfd0] px-4 py-4">
                <div className="flex flex-wrap gap-2">
                  {canManage && data?.import_enabled ? (
                    <Button variant="secondary" size="sm" onClick={() => setShowImport(true)}>
                      <Upload className="h-4 w-4" /> {copy.import}
                    </Button>
                  ) : null}
                  {canExport ? (
                    <Button variant="secondary" size="sm" disabled={exporting || rows.length === 0} onClick={() => void runExport()}>
                      {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                      {copy.export}
                    </Button>
                  ) : null}
                </div>
                {canManage ? (
                  <AttendanceCaptureOpsPanel access={access} canManage={canManage} onNotice={onNotice} onAccessIssue={onAccessIssue} />
                ) : null}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

// --- Leave -----------------------------------------------------------------

function LeavePage(props: PostHireCommonProps) {
  return <LeaveWorkspace {...props} />
}

// --- Shifts ----------------------------------------------------------------

function ShiftsPage(props: PostHireCommonProps) {
  return <ShiftsWorkspace {...props} />
}

// --- Payroll ---------------------------------------------------------------

type PayrollPolicyForm = {
  employee_pay_type: string
  leave_policy: string
  overtime_policy: string
  overtime_cap_hours?: number
  default_hourly_rate_kwd?: number
  currency: string
  absence_deduction_enabled: boolean
  late_deduction_enabled: boolean
  early_leave_deduction_enabled: boolean
}

type PayrollPreviewRow = {
  employee_name?: string
  payable_minutes?: number | null
  worked_minutes?: number | null
  estimated_amount_kwd?: number | null
  amount_status?: string
}

function minutesToHours(value: number | null | undefined): string {
  return (Number(value || 0) / 60).toFixed(1)
}

const PAYROLL_FLOW_STEPS = [
  'Choose period',
  'Generate timesheets',
  'Approve / reject',
  'Preview payroll',
  'Export',
  'Download / view',
]

function PayrollFlowGuide() {
  return (
    <div className="rounded-[1.1rem] border border-line/45 bg-panel/55 px-4 py-3">
      <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">How payroll works</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12.5px] text-subtle/90">
        {PAYROLL_FLOW_STEPS.map((step, idx) => (
          <Fragment key={step}>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-panel-muted/80 text-[11px] font-semibold text-text">{idx + 1}</span>
              {step}
            </span>
            {idx < PAYROLL_FLOW_STEPS.length - 1 ? <span className="text-subtle/45">→</span> : null}
          </Fragment>
        ))}
      </div>
    </div>
  )
}

function PayrollExportDetailModal({ access, exportId, currency, onClose, onNotice, onAccessIssue }: {
  access: DashboardAccess
  exportId: string
  currency: string
  onClose: () => void
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const [detail, setDetail] = useState<PayrollExportDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    getPayrollExportDetail(access, exportId)
      .then((d) => {
        if (alive) setDetail(d)
      })
      .catch((err) => {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        setError(friendlyError(err, 'We couldn’t load this export. Please try again.'))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [access, exportId, onAccessIssue])

  const runDownload = async () => {
    setDownloading(true)
    try {
      await downloadPayrollExportCsv(access, exportId)
      onNotice('Payroll export downloaded.', 'success')
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(friendlyError(err, 'We couldn’t download the export. Please try again.'), 'error')
    } finally {
      setDownloading(false)
    }
  }

  const rows = detail?.preview_rows ?? []
  const totalAmount = detail?.totals && typeof detail.totals.estimated_amount_kwd === 'number' ? (detail.totals.estimated_amount_kwd as number) : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">Payroll export</p>
            <p className="text-[13px] leading-6 text-subtle/95">
              {detail ? `${formatDate(detail.period.start_date)} → ${formatDate(detail.period.end_date)}` : 'Loading…'}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>

        {loading ? (
          <div className="py-10"><LoadingState /></div>
        ) : error ? (
          <div className="py-6"><ErrorState message={error} onRetry={() => setDetail(null)} /></div>
        ) : (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-3">
                <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">Employees</p>
                <p className="mt-1 text-[14px] font-semibold text-text">{detail?.row_count ?? rows.length}</p>
              </div>
              <div className="rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-3">
                <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">Est. total</p>
                <p className="mt-1 text-[14px] font-semibold text-text">{totalAmount != null ? `${totalAmount.toFixed(3)} ${currency}` : '—'}</p>
              </div>
              <div className="rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-3">
                <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">Status</p>
                <p className="mt-1 text-[14px] font-semibold text-text">{titleCase(detail?.status || 'exported')}</p>
              </div>
            </div>

            <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
              {rows.length === 0 ? (
                <EmptyState icon={<FileText className="h-5 w-5" />} title="No rows in this export" />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[520px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Payable hrs</th>
                        <th className="px-4 py-3 font-medium">Est. amount</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {rows.map((row, idx) => (
                        <tr key={`${row.employee_name || idx}`} className="hover:bg-white/45">
                          <td className="px-4 py-3 font-semibold text-text">{row.employee_name || '—'}</td>
                          <td className="px-4 py-3 text-subtle/90">{minutesToHours(row.payable_minutes)}</td>
                          <td className="px-4 py-3 text-subtle/90">{row.estimated_amount_kwd != null ? `${Number(row.estimated_amount_kwd).toFixed(3)} ${currency}` : '—'}</td>
                          <td className="px-4 py-3"><StatusBadge status={row.amount_status || 'estimated'} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
              <Button size="sm" disabled={downloading || rows.length === 0} onClick={() => void runDownload()}>
                {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Download CSV
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function PayrollPolicyEditor({
  policy,
  busy,
  onSubmit,
  onCancel,
}: {
  policy: PosthirePayrollPolicy
  busy: boolean
  onSubmit: (values: PayrollPolicyForm) => void
  onCancel: () => void
}) {
  const [payType, setPayType] = useState(String(policy.employee_pay_type || 'monthly'))
  const [leave, setLeave] = useState(String(policy.leave_policy || 'paid'))
  const [overtime, setOvertime] = useState(String(policy.overtime_policy || 'review_only'))
  const [capHours, setCapHours] = useState(
    policy.overtime_cap_minutes ? String(Number(policy.overtime_cap_minutes) / 60) : '',
  )
  const [rate, setRate] = useState(policy.default_hourly_rate_kwd != null ? String(policy.default_hourly_rate_kwd) : '')
  const [currency, setCurrency] = useState(String(policy.currency || 'KWD'))
  const [absence, setAbsence] = useState(Boolean(policy.absence_deduction_enabled))
  const [late, setLate] = useState(Boolean(policy.late_deduction_enabled))
  const [early, setEarly] = useState(Boolean(policy.early_leave_deduction_enabled))

  const labelCls = 'flex flex-col gap-1.5 text-[12px] font-medium text-subtle/85'
  const checkboxRow = 'flex items-center gap-2 text-[13px] text-text'

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className={labelCls}>
          Pay type
          <Select value={payType} onChange={(e) => setPayType(e.target.value)}>
            <option value="monthly">Monthly</option>
            <option value="hourly">Hourly</option>
            <option value="mixed">Mixed</option>
          </Select>
        </label>
        <label className={labelCls}>
          Leave policy
          <Select value={leave} onChange={(e) => setLeave(e.target.value)}>
            <option value="paid">Paid</option>
            <option value="unpaid">Unpaid</option>
            <option value="review_only">Review only</option>
          </Select>
        </label>
        <label className={labelCls}>
          Overtime policy
          <Select value={overtime} onChange={(e) => setOvertime(e.target.value)}>
            <option value="review_only">Review only</option>
            <option value="paid">Paid</option>
            <option value="capped">Capped</option>
            <option value="ignored">Ignored</option>
          </Select>
        </label>
        {overtime === 'capped' ? (
          <label className={labelCls}>
            Overtime cap (hours)
            <Input type="number" min="0" step="0.5" value={capHours} onChange={(e) => setCapHours(e.target.value)} />
          </label>
        ) : null}
        <label className={labelCls}>
          Default hourly rate
          <Input type="number" min="0" step="0.001" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="—" />
        </label>
        <label className={labelCls}>
          Currency
          <Input value={currency} onChange={(e) => setCurrency(e.target.value)} maxLength={8} />
        </label>
      </div>
      <div className="flex flex-wrap gap-5">
        <label className={checkboxRow}>
          <input type="checkbox" checked={absence} onChange={(e) => setAbsence(e.target.checked)} /> Deduct for absence
        </label>
        <label className={checkboxRow}>
          <input type="checkbox" checked={late} onChange={(e) => setLate(e.target.checked)} /> Deduct for late
        </label>
        <label className={checkboxRow}>
          <input type="checkbox" checked={early} onChange={(e) => setEarly(e.target.checked)} /> Deduct for early leave
        </label>
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            onSubmit({
              employee_pay_type: payType,
              leave_policy: leave,
              overtime_policy: overtime,
              overtime_cap_hours: overtime === 'capped' && capHours !== '' ? Number(capHours) : undefined,
              default_hourly_rate_kwd: rate === '' ? undefined : Number(rate),
              currency: currency.toUpperCase(),
              absence_deduction_enabled: absence,
              late_deduction_enabled: late,
              early_leave_deduction_enabled: early,
            })
          }
        >
          Apply changes
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function PayrollPage({ access, permissions, role, onNotice, onAccessIssue }: PostHireCommonProps) {
  const locale = useEmployees360Locale()
  const px = payrollExternalCopy(locale)
  const isAr = locale === 'ar'
  const [surface, setSurface] = useState<'run' | 'hours' | 'records'>('run')
  const [recordsPanel, setRecordsPanel] = useState<'payslips' | 'close' | 'statutory'>('payslips')

  return (
    <div className="space-y-4" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="payroll-workspace" data-payroll-queue>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-[13px] text-subtle/90">{px.payrollHint}</p>
      </div>

      <div className="flex flex-wrap gap-2" data-payroll-surfaces role="tablist" aria-label={px.surfaceRun}>
        {(
          [
            ['run', px.surfaceRun],
            ['hours', px.surfaceHours],
            ['records', px.surfaceRecords],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={surface === id}
            data-surface={id}
            data-testid={
              id === 'run'
                ? 'payroll-tab-external-run'
                : id === 'hours'
                  ? 'payroll-tab-hours-review'
                  : 'payroll-tab-records'
            }
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${
              surface === id ? 'bg-wf-ink text-white' : 'bg-[#f3ebe0] text-subtle'
            }`}
            onClick={() => setSurface(id)}
            title={id === 'run' ? px.tabExternalHint : id === 'hours' ? px.tabTimesheetsHint : undefined}
          >
            {label}
          </button>
        ))}
      </div>

      {surface === 'records' ? (
        <div className="flex flex-wrap gap-2" data-payroll-records-panels role="tablist">
          {(
            [
              ['payslips', px.recordsPayslips, 'payroll-tab-payslips'],
              ['close', px.recordsClose, 'payroll-tab-close-export'],
              ['statutory', px.recordsStatutory, 'payroll-tab-statutory'],
            ] as const
          ).map(([id, label, testId]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={recordsPanel === id}
              data-testid={testId}
              className={`rounded-full px-3 py-1.5 text-sm ${
                recordsPanel === id ? 'bg-wf-ink text-white' : 'bg-[#f3ebe0] text-subtle'
              }`}
              onClick={() => setRecordsPanel(id)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {surface === 'run' ? (
        <ExternalPayrollWorkspace
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : surface === 'hours' ? (
        <PayrollTimesheetsPage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
      ) : recordsPanel === 'payslips' ? (
        <PayslipWorkspace
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : recordsPanel === 'close' ? (
        <CloseExportWorkspace
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : (
        <StatutoryWorksheetWorkspace
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      )}
    </div>
  )
}

function PayrollTimesheetsPage({ access, permissions, role, onNotice, onAccessIssue }: PostHireCommonProps) {
  const [period, setPeriod] = useState<{ start: string; end: string } | null>(null)
  const loader = useCallback(
    () => getPosthirePayroll(access, period ? { start_date: period.start, end_date: period.end } : undefined),
    [access, period],
  )
  const { data, loading, refreshing, error, reload } = useModuleData<PosthirePayrollResponse>(loader, onAccessIssue)
  const action = usePosthireAction(access, reload, onNotice, onAccessIssue)
  const canManage = can(permissions, 'payroll.manage', role)
  const [editingPolicy, setEditingPolicy] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [preview, setPreview] = useState<{ rows: PayrollPreviewRow[]; count: number } | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)

  const periods = data?.periods ?? []
  const periodValue = data?.period.start_date && data?.period.end_date ? `${data.period.start_date}|${data.period.end_date}` : ''

  const periodArgs = useMemo(
    () => ({ start_date: data?.period.start_date || undefined, end_date: data?.period.end_date || undefined }),
    [data?.period.start_date, data?.period.end_date],
  )

  const runPreview = useCallback(async () => {
    setPreviewBusy(true)
    try {
      const res = await runPosthireAction(access, { action_type: 'preview_payroll', args: periodArgs })
      const payload = (res.result as { preview_rows?: PayrollPreviewRow[]; timesheet_count?: number } | null) || null
      const rows = payload?.preview_rows ?? []
      setPreview({ rows, count: payload?.timesheet_count ?? rows.length })
      onNotice(res.message || `Preview ready · ${rows.length} timesheet${rows.length === 1 ? '' : 's'}.`, 'success')
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, 'We could not preview payroll right now.'), 'error')
    } finally {
      setPreviewBusy(false)
    }
  }, [access, periodArgs, onNotice, onAccessIssue])

  // Pagination: page 1 comes from useModuleData (period-scoped); more pages
  // accumulate here and reset whenever the base data reloads (period change or
  // manual refresh) so we never mix timesheets from different periods.
  const [extraTimesheets, setExtraTimesheets] = useState<PosthireTimesheetRow[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraTimesheets([])
  }, [data])

  const baseTimesheets = data?.timesheets ?? []
  const timesheets = [...baseTimesheets, ...extraTimesheets]
  const totalTimesheets = data?.total_count ?? baseTimesheets.length
  const exports = data?.exports ?? []
  const policy = data?.policy ?? {}
  const draft = timesheets.filter((t) => String(t.status).toLowerCase() === 'draft')
  // True count of drafts across the whole period (from the backend), so the
  // "need review" banner doesn't shrink to the loaded page at scale.
  const draftCount = data?.draft_count ?? draft.length
  const canExport = Boolean(data?.can_export)
  const periodLabel = data?.period.start_date ? `${formatDate(data.period.start_date)} → ${formatDate(data.period.end_date)}` : ''

  const loadMoreTimesheets = useCallback(async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthirePayroll(access, {
        start_date: data?.period.start_date || undefined,
        end_date: data?.period.end_date || undefined,
        offset: timesheets.length,
      })
      setExtraTimesheets((prev) => [...prev, ...(res.timesheets ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, 'We couldn’t load more timesheets. Please try again.'), 'error')
    } finally {
      setLoadingMore(false)
    }
  }, [access, data?.period.start_date, data?.period.end_date, timesheets.length, onAccessIssue, onNotice])

  const policyItems: Array<{ label: string; value: string }> = []
  if (policy.employee_pay_type) policyItems.push({ label: 'Pay type', value: titleCase(String(policy.employee_pay_type)) })
  if (policy.leave_policy) policyItems.push({ label: 'Leave', value: titleCase(String(policy.leave_policy)) })
  if (policy.overtime_policy) policyItems.push({ label: 'Overtime', value: titleCase(String(policy.overtime_policy)) })
  if (policy.currency) policyItems.push({ label: 'Currency', value: String(policy.currency).toUpperCase() })
  if (policy.default_hourly_rate_kwd != null)
    policyItems.push({ label: 'Hourly rate', value: `${policy.default_hourly_rate_kwd} ${String(policy.currency || 'KWD').toUpperCase()}` })
  const deductions = [
    policy.absence_deduction_enabled ? 'Absence' : null,
    policy.late_deduction_enabled ? 'Late' : null,
    policy.early_leave_deduction_enabled ? 'Early leave' : null,
  ].filter(Boolean) as string[]
  policyItems.push({ label: 'Deductions', value: deductions.length ? deductions.join(' · ') : 'None' })

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar
        onRefresh={() => void reload()}
        refreshing={refreshing}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {periods.length ? (
              <Select
                className="h-9 w-auto"
                value={periodValue}
                onChange={(e) => {
                  const [start, end] = e.target.value.split('|')
                  if (start && end) setPeriod({ start, end })
                }}
                aria-label="Pay period"
              >
                {periods.map((p) => (
                  <option key={`${p.start_date}|${p.end_date}`} value={`${p.start_date}|${p.end_date}`}>
                    {formatDate(p.start_date)} → {formatDate(p.end_date)}{p.has_timesheets ? '' : ' · no timesheets'}
                  </option>
                ))}
              </Select>
            ) : null}
            {canManage ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={action.busy}
                onClick={() =>
                  action.run('create_timesheet_review', periodArgs, {
                    key: 'generate-timesheets',
                    confirm: {
                      title: 'Generate timesheets?',
                      body: `This builds timesheets for review from approved attendance and completed shifts${data?.period.start_date ? ` for ${formatDate(data.period.start_date)}–${formatDate(data.period.end_date)}` : ''}. Existing reviewed timesheets aren’t changed.`,
                      confirmLabel: 'Generate timesheets',
                    },
                  })
                }
              >
                {action.runningKey === 'generate-timesheets' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Generating…
                  </>
                ) : (
                  <>
                    <ClipboardList className="h-4 w-4" /> Generate timesheets
                  </>
                )}
              </Button>
            ) : null}
            <Button variant="ghost" size="sm" disabled={previewBusy} onClick={() => void runPreview()}>
              {previewBusy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Previewing…
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4" /> Preview payroll
                </>
              )}
            </Button>
            {canExport ? (
              <Button
                variant="secondary"
                size="sm"
                disabled={action.busy}
                data-payroll-hours-export
                onClick={() =>
                  action.run('export_payroll', periodArgs, {
                    destructive: true,
                    key: 'export-payroll',
                    confirm: {
                      title: 'Export this payroll period?',
                      body: `This creates a locked payroll export from the approved timesheets for ${data?.period.start_date ? `${formatDate(data.period.start_date)}–${formatDate(data.period.end_date)}` : 'this period'}. It doesn’t transfer money or create bank files.`,
                      confirmLabel: 'Export payroll',
                    },
                  })
                }
              >
                {action.runningKey === 'export-payroll' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Exporting…
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" /> Export payroll
                  </>
                )}
              </Button>
            ) : null}
          </div>
        }
      />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <NextAction
            tone={draftCount ? 'warning' : 'success'}
            icon={<DollarSign className="h-5 w-5" />}
            title={draftCount ? `${draftCount} timesheet${draftCount === 1 ? '' : 's'} need review` : 'All timesheets reviewed'}
            detail={
              data?.period.start_date
                ? `Period ${formatDate(data?.period.start_date)} → ${formatDate(data?.period.end_date)}`
                : 'No active payroll period'
            }
          />
          <PayrollFlowGuide />
          <Card>
            <CardHeader>
              <CardTitle>Timesheets</CardTitle>
              <CardDescription>Review hours before approving for payroll.</CardDescription>
            </CardHeader>
            <CardContent>
              {timesheets.length === 0 ? (
                <EmptyState
                  icon={<ClipboardList className="h-5 w-5" />}
                  title={periodLabel ? `No timesheets for ${periodLabel}` : 'No timesheets yet'}
                  hint="Timesheets are generated from approved attendance and completed shifts, then reviewed here before payroll."
                  points={[
                    'Record shifts and attendance — hours roll up into timesheets',
                    'Approve or reject each timesheet before it counts toward payroll',
                    'Overtime and deductions follow the payroll policy below',
                    'Export a finalized run once timesheets are approved',
                  ]}
                />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[560px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Hours</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                        {canManage ? <th className="px-4 py-3 text-right font-medium">Action</th> : null}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {timesheets.map((ts, idx) => (
                        <tr key={ts.timesheet_id || idx} className="hover:bg-white/45">
                          <td className="px-4 py-3 font-semibold text-text">{ts.employee_name || '—'}</td>
                          <td className="px-4 py-3 text-subtle/90">
                            {ts.total_hours ?? '—'}
                            {Number(ts.overtime_hours || 0) > 0 ? <span className="ml-1 text-[12px] text-[#8a5a16]">+{ts.overtime_hours} OT</span> : null}
                          </td>
                          <td className="px-4 py-3"><StatusBadge status={ts.status} /></td>
                          {canManage ? (
                            <td className="px-4 py-3 text-right">
                              {String(ts.status).toLowerCase() === 'draft' ? (
                                <div className="flex items-center justify-end gap-2">
                                  <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => action.run('reject_timesheet', { timesheet_id: ts.timesheet_id, employee_name: ts.employee_name }, { destructive: true, key: `reject-ts:${ts.timesheet_id || idx}`, confirm: { title: 'Reject this timesheet?', body: `${ts.employee_name || 'This employee'}'s timesheet will be sent back and won't count toward payroll until it's corrected and approved.`, confirmLabel: 'Reject timesheet' } })}>
                                    {action.runningKey === `reject-ts:${ts.timesheet_id || idx}` ? (
                                      <>
                                        <Loader2 className="h-4 w-4 animate-spin" /> Rejecting…
                                      </>
                                    ) : (
                                      'Reject'
                                    )}
                                  </Button>
                                  <Button size="sm" disabled={action.busy} onClick={() => action.run('approve_timesheet', { timesheet_id: ts.timesheet_id, employee_name: ts.employee_name }, { key: `approve-ts:${ts.timesheet_id || idx}` })}>
                                    {action.runningKey === `approve-ts:${ts.timesheet_id || idx}` ? (
                                      <>
                                        <Loader2 className="h-4 w-4 animate-spin" /> Approving…
                                      </>
                                    ) : (
                                      'Approve'
                                    )}
                                  </Button>
                                </div>
                              ) : null}
                            </td>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <LoadMoreBar
                    loaded={timesheets.length}
                    total={totalTimesheets}
                    loading={loadingMore}
                    onLoadMore={() => void loadMoreTimesheets()}
                    noun="timesheet"
                  />
                </div>
              )}
            </CardContent>
          </Card>
          {preview ? (
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Payroll preview</CardTitle>
                    <CardDescription>
                      {preview.count} approved timesheet{preview.count === 1 ? '' : 's'} for {periodLabel || 'this period'} — estimate only, nothing is exported.
                    </CardDescription>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
                    Dismiss
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {preview.rows.length === 0 ? (
                  <EmptyState
                    icon={<FileText className="h-5 w-5" />}
                    title="Nothing to preview yet"
                    hint="Preview reflects approved timesheets for the period. Approve timesheets first, then preview."
                  />
                ) : (
                  <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                    <table className="w-full min-w-[640px] text-left text-[13px]">
                      <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                        <tr>
                          <th className="px-4 py-3 font-medium">Employee</th>
                          <th className="px-4 py-3 font-medium">Payable hrs</th>
                          <th className="px-4 py-3 font-medium">Est. amount</th>
                          <th className="px-4 py-3 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line/45">
                        {preview.rows.map((row, idx) => (
                          <tr key={`${row.employee_name || idx}`} className="hover:bg-white/45">
                            <td className="px-4 py-3 font-semibold text-text">{row.employee_name || '—'}</td>
                            <td className="px-4 py-3 text-subtle/90">{minutesToHours(row.payable_minutes)}</td>
                            <td className="px-4 py-3 text-subtle/90">
                              {row.estimated_amount_kwd != null ? `${Number(row.estimated_amount_kwd).toFixed(3)} ${String(policy.currency || 'KWD').toUpperCase()}` : '—'}
                            </td>
                            <td className="px-4 py-3"><StatusBadge status={row.amount_status || 'estimated'} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}
          {policyItems.length || canManage ? (
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle>Payroll policy</CardTitle>
                    <CardDescription>How hours and deductions are calculated for this company.</CardDescription>
                  </div>
                  {canManage && !editingPolicy ? (
                    <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => setEditingPolicy(true)}>
                      Edit policy
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent>
                {editingPolicy ? (
                  <PayrollPolicyEditor
                    policy={policy}
                    busy={action.busy}
                    onCancel={() => setEditingPolicy(false)}
                    onSubmit={(values) => {
                      action.run(
                        'set_payroll_policy',
                        { structured_policy: true, ...values },
                        {
                          destructive: true,
                          key: 'set-policy',
                          confirm: {
                            title: 'Apply payroll policy?',
                            body: 'These payroll rules will apply to this company’s pay calculations going forward. You can update them again anytime.',
                            confirmLabel: 'Apply changes',
                          },
                          // Keep the editor open with entered values if applying fails.
                          onSuccess: () => setEditingPolicy(false),
                        },
                      )
                    }}
                  />
                ) : policyItems.length ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {policyItems.map((item) => (
                      <div key={item.label} className="rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-3">
                        <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">{item.label}</p>
                        <p className="mt-1 text-[14px] font-semibold text-text">{item.value}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState icon={<DollarSign className="h-5 w-5" />} title="No payroll policy set" hint="Set how hours, overtime and deductions are calculated." />
                )}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>Recent exports</CardTitle>
              <CardDescription>
                {canExport ? 'Open an export to review its detail or download the CSV.' : 'A record of payroll runs that have been exported.'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {exports.length === 0 ? (
                <EmptyState icon={<Download className="h-5 w-5" />} title="No exports yet" hint="Export an approved payroll period above and it will appear here for download." />
              ) : (
                <div className="space-y-2">
                  {exports.map((row, idx) => (
                    <div key={row.export_id || idx} className="flex items-center justify-between gap-3 rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-2.5 text-[13px]">
                      <div className="flex flex-col">
                        <span className="font-medium text-text">{formatDate(row.period_start)} → {formatDate(row.period_end)}</span>
                        {row.created_at ? <span className="text-[11.5px] text-subtle/75">Exported {formatDate(row.created_at)}</span> : null}
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={row.status || 'exported'} />
                        {canExport && row.export_id ? (
                          <Button variant="ghost" size="sm" onClick={() => setDetailId(String(row.export_id))}>
                            <Eye className="h-4 w-4" /> View
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
      {detailId ? (
        <PayrollExportDetailModal
          access={access}
          exportId={detailId}
          currency={String(policy.currency || 'KWD').toUpperCase()}
          onClose={() => setDetailId(null)}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
        />
      ) : null}
    </div>
  )
}

// --- Analytics (Wave 1 Attention Contract) ---------------------------------

const ANALYTICS_PATTERN_SKIP = new Set(['Absences', 'Late records', 'Pending review', 'Scheduled shifts', 'Best attendance'])

// --- Action Inbox (Post-Hire Differentiation Wave 1) ----------------------

function ActionInboxPage({
  access,
  onAccessIssue,
  onNavigate,
}: Pick<PostHireProps, 'access' | 'onAccessIssue' | 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const loader = useCallback(() => getPosthireActionInbox(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireActionInboxResponse>(loader, onAccessIssue)
  const [fetchedAtMs, setFetchedAtMs] = useState<number | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [showDefinitions, setShowDefinitions] = useState(false)
  const [filter, setFilter] = useState<'all' | 'needs_action' | 'due_soon' | 'blocked'>('needs_action')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    if (data?.as_of || data?.items) setFetchedAtMs(Date.now())
  }, [data])

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const items = Array.isArray(data?.items) ? data?.items ?? [] : []
  const definitions = Array.isArray(data?.definitions) ? data?.definitions ?? [] : []
  const sourcesPack = data?.sources
  const unavailable = Array.isArray(sourcesPack?.unavailable_source_keys) ? sourcesPack?.unavailable_source_keys ?? [] : []
  const partial = Boolean(sourcesPack?.partial)
  const sourceErrors = [
    sourcesPack?.analytics?.error,
    sourcesPack?.compliance?.error,
    sourcesPack?.employees && (sourcesPack.employees as { error?: unknown }).error,
  ].filter(Boolean)
  const hasSourceError = sourceErrors.length > 0 || unavailable.some((key) => {
    const row = sourcesPack?.[key as 'analytics' | 'compliance' | 'employees']
    return row && typeof row === 'object' && (row as { status?: string }).status === 'error'
  })
  const staleAfter = Number(data?.freshness?.stale_after_seconds ?? 300)
  const isStale = fetchedAtMs != null && nowMs - fetchedAtMs > staleAfter * 1000

  const asOfLabel = data?.as_of
    ? (() => {
        try {
          return new Date(data.as_of).toLocaleString(isAr ? 'ar-KW' : 'en-GB', {
            timeZone: data.timezone || 'Asia/Kuwait',
            dateStyle: 'medium',
            timeStyle: 'short',
          })
        } catch {
          return data.as_of
        }
      })()
    : null

  const openDeepLink = useCallback(
    (item: ActionInboxItem) => {
      const page = String(item.deep_link?.page || item.system_of_action || '').trim()
      if (!page) return
      // Prefer person focus only for destinations that honor it today.
      const honorsEmployee = page === 'employees' || page === 'onboarding'
      const employee = honorsEmployee
        ? (item.deep_link?.employee || item.employee_key || undefined)
        : undefined
      onNavigate?.(page, employee ? { employee: String(employee) } : undefined)
    },
    [onNavigate],
  )

  const moduleLabel = (mod: string) => {
    const map: Record<string, { en: string; ar: string }> = {
      analytics: { en: 'Analytics', ar: 'التحليلات' },
      compliance: { en: 'Compliance', ar: 'الامتثال' },
      employees: { en: 'Employees', ar: 'الموظفون' },
      onboarding: { en: 'Onboarding', ar: 'التهيئة' },
      attendance: { en: 'Attendance', ar: 'الحضور' },
      leave: { en: 'Leave', ar: 'الإجازات' },
      shifts: { en: 'Shifts', ar: 'الورديات' },
      payroll: { en: 'Payroll', ar: 'الرواتب' },
    }
    return isAr ? map[mod]?.ar || mod : map[mod]?.en || mod
  }

  const deadlineText = (item: ActionInboxItem) =>
    `${item.deadline || ''} ${item.deadline_label_en || ''} ${item.deadline_label_ar || ''}`.toLowerCase()

  const blockedText = (item: ActionInboxItem) =>
    `${item.why_en || ''} ${item.why_ar || ''} ${item.authority_status || ''} ${item.authority_status_label_en || ''} ${item.evidence_status || ''} ${item.escalation_step || ''}`.toLowerCase()

  const isDueSoon = (item: ActionInboxItem) => {
    const d = deadlineText(item)
    if (/\b(overdue|due soon|due today|expires|expiring|قريب|متأخر|استحقاق|ينتهي)/.test(d)) return true
    if (item.deadline && String(item.severity || '').toLowerCase() === 'medium') return true
    return false
  }

  const isBlocked = (item: ActionInboxItem) => {
    const t = blockedText(item)
    return /\b(block|blocked|prerequisite|cannot proceed|معلّق|معلق|محظور|متوقف|متطلب سابق)/.test(t)
  }

  const isNeedsAction = (item: ActionInboxItem) => {
    const sev = String(item.severity || '').toLowerCase()
    return sev === 'critical' || sev === 'high' || isBlocked(item)
  }

  const urgencyMeta = (item: ActionInboxItem) => {
    if (isBlocked(item)) return { key: 'blocked' as const, en: 'Blocked', ar: 'معلّق', tone: 'danger' as const }
    const sev = String(item.severity || '').toLowerCase()
    if (sev === 'critical' || sev === 'high') return { key: 'urgent' as const, en: 'Urgent', ar: 'عاجل', tone: 'danger' as const }
    if (isDueSoon(item) || sev === 'medium') return { key: 'due_soon' as const, en: 'Due soon', ar: 'قريب الاستحقاق', tone: 'warning' as const }
    return { key: 'info' as const, en: 'Watch', ar: 'للمتابعة', tone: 'muted' as const }
  }

  const filtered = useMemo(() => {
    if (filter === 'all') return items
    if (filter === 'needs_action') return items.filter(isNeedsAction)
    if (filter === 'due_soon') return items.filter(isDueSoon)
    if (filter === 'blocked') return items.filter(isBlocked)
    return items
  }, [items, filter])

  const copy = {
    refresh: isAr ? 'تحديث' : 'Refresh',
    loadingErr: isAr ? 'تعذر تحميل الأمور التي تحتاج متابعة.' : 'We couldn’t load Needs Attention.',
    emptyTitle: isAr ? 'لا يوجد ما يحتاج متابعتك الآن' : 'Nothing needs your attention right now',
    emptyHint: isAr
      ? 'هذه الصفحة ترتّب ما يحتاج متابعة وتوجّهك إلى الوحدة الصحيحة — دون تنفيذ الإجراء هنا.'
      : 'This page ranks what needs follow-up and routes you to the right module — it does not resolve work here.',
    emptyPoints: isAr
      ? [
          'نفّذ الإجراء في وحدة التنفيذ',
          'يختفي العنصر بعد حل المصدر',
          'التنبيهات والتسليم تملك أعطال التواصل',
        ]
      : [
          'Resolve the work in the specialist module',
          'Items clear after the source is resolved',
          'Alerts & Delivery owns communication failures',
        ],
    emptyFilter: isAr ? 'لا عناصر في هذا التصفية' : 'No items in this filter',
    title: isAr ? 'الأمور التي تحتاج متابعتك' : 'Needs Attention',
    detail: isAr
      ? 'مرتّبة حسب الأهمية. افتح العنصر للانتقال إلى الوحدة المسؤولة.'
      : 'Ranked by importance. Open an item to go to the owning module.',
    definitions: isAr ? 'تعريفات' : 'Definitions',
    hideDefinitions: isAr ? 'إخفاء التعريفات' : 'Hide definitions',
    sourcesPartial: isAr ? 'بعض المصادر غير متاحة — عرض جزئي' : 'Some sources unavailable — partial view',
    sourcesError: isAr ? 'تعذر تحميل أحد المصادر — عرض جزئي' : 'A source failed to load — partial view',
    stale: isAr ? 'البيانات قد تكون قديمة — حدّث' : 'Data may be stale — refresh',
    asOf: isAr ? 'كما في' : 'As of',
    open: isAr ? 'متابعة' : 'Follow up',
    more: isAr ? 'التفاصيل' : 'Details',
    hideMore: isAr ? 'إخفاء' : 'Hide',
    owner: isAr ? 'المالك' : 'Owner',
    deadline: isAr ? 'الموعد' : 'Due',
    why: isAr ? 'لماذا' : 'Why',
    who: isAr ? 'المتأثر' : 'Affects',
    resolveIn: isAr ? 'التنفيذ في' : 'Resolve in',
    evidence: isAr ? 'الدليل' : 'Evidence',
    authority: isAr ? 'الصلاحية' : 'Authority',
    groupedDocs: isAr ? 'المستندات' : 'Documents',
    filterAll: isAr ? 'الكل' : 'All',
    filterNeeds: isAr ? 'يحتاج إجراء' : 'Needs action',
    filterDue: isAr ? 'قريب الاستحقاق' : 'Due soon',
    filterBlocked: isAr ? 'معلّق' : 'Blocked',
    countLabel: (n: number) =>
      isAr ? `${n} يحتاج متابعة` : `${n} need${n === 1 ? 's' : ''} attention`,
    honesty: isAr
      ? 'هذه الصفحة ترتّب وتوجّه فقط. نفّذ الإجراء في الوحدة المسؤولة؛ أعطال التواصل تُعالج في التنبيهات والتسليم.'
      : 'This page only prioritizes and routes. Resolve work in the owning module; communication failures live under Alerts & Delivery.',
  }

  const filterChip = (id: typeof filter, label: string, count: number) => (
    <button
      key={id}
      type="button"
      onClick={() => setFilter(id)}
      className={cn(
        'rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition',
        filter === id ? 'bg-[#23211d] text-white' : 'bg-[#eee5d4]/80 text-[#5c554a] hover:bg-[#eee5d4]',
      )}
    >
      {label}
      <span className="ms-1.5 tabular-nums opacity-80">{count}</span>
    </button>
  )

  const counts = {
    all: items.length,
    needs_action: items.filter(isNeedsAction).length,
    due_soon: items.filter(isDueSoon).length,
    blocked: items.filter(isBlocked).length,
  }

  return (
    <div className="space-y-4" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="needs-attention-page">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => void reload()} disabled={refreshing} aria-label={copy.refresh}>
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="sr-only sm:not-sr-only sm:ms-1">{copy.refresh}</span>
        </Button>
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error || copy.loadingErr} onRetry={() => void reload()} />
      ) : items.length === 0 && !partial && !hasSourceError ? (
        <EmptyState icon={<Inbox className="h-5 w-5" />} title={copy.emptyTitle} hint={copy.emptyHint} points={copy.emptyPoints} />
      ) : (
        <>
          {isStale ? (
            <div className="rounded-[1.1rem] border border-[#e2bd78]/70 bg-[#fff7e8]/70 px-4 py-3 text-[13px] text-text">
              {copy.stale}
              {asOfLabel ? <span className="text-subtle/85"> · {copy.asOf} {asOfLabel}</span> : null}
            </div>
          ) : null}

          {hasSourceError || partial || unavailable.length ? (
            <div className="rounded-[1.1rem] border border-line/55 bg-panel/60 px-4 py-3">
              <p className="text-[13px] font-semibold text-text">{hasSourceError ? copy.sourcesError : copy.sourcesPartial}</p>
              <p className="mt-0.5 text-[12.5px] text-subtle/85">
                {unavailable
                  .map((key) => {
                    const row = sourcesPack?.[key as 'analytics' | 'compliance' | 'employees']
                    if (!row || typeof row !== 'object') return key
                    return isAr
                      ? String((row as { note_ar?: string }).note_ar || key)
                      : String((row as { note_en?: string }).note_en || key)
                  })
                  .join(' · ')}
              </p>
            </div>
          ) : null}

          <Card tone="board" data-testid="needs-attention-board">
            <CardHeader className="space-y-3">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <CardTitle>{copy.countLabel(filtered.length)}</CardTitle>
                  <CardDescription>
                    {asOfLabel ? `${copy.asOf} ${asOfLabel}` : copy.honesty}
                  </CardDescription>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5" data-testid="needs-attention-filters" role="tablist">
                {filterChip('needs_action', copy.filterNeeds, counts.needs_action)}
                {filterChip('due_soon', copy.filterDue, counts.due_soon)}
                {filterChip('blocked', copy.filterBlocked, counts.blocked)}
                {filterChip('all', copy.filterAll, counts.all)}
              </div>
            </CardHeader>
            <CardContent>
              {filtered.length === 0 ? (
                <EmptyState icon={<Inbox className="h-5 w-5" />} title={copy.emptyFilter} hint={copy.emptyHint} />
              ) : (
                <div className="space-y-2">
                  {filtered.map((item) => {
                    const what = isAr ? item.what_ar || item.what_en : item.what_en || item.what_ar
                    const why = isAr ? item.why_ar || item.why_en : item.why_en || item.why_ar
                    const owner = isAr ? item.owner_label_ar || item.owner_label_en : item.owner_label_en || item.owner_label_ar
                    const deadline =
                      (isAr ? item.deadline_label_ar || item.deadline_label_en : item.deadline_label_en || item.deadline_label_ar) ||
                      item.deadline ||
                      null
                    const place = [item.employee_name, item.team, item.location].filter(Boolean).join(' · ')
                    const urgency = urgencyMeta(item)
                    const soa = moduleLabel(String(item.system_of_action || item.source_module || ''))
                    const expanded = expandedId === item.id
                    const evidence =
                      (isAr
                        ? item.evidence_status_label_ar || item.evidence_status_label_en
                        : item.evidence_status_label_en || item.evidence_status_label_ar) || item.evidence_status
                    const authority =
                      (isAr
                        ? item.authority_status_label_ar || item.authority_status_label_en
                        : item.authority_status_label_en || item.authority_status_label_ar) || item.authority_status
                    return (
                      <div
                        key={item.id}
                        className="rounded-[1.15rem] border border-[#e8dfd0]/80 bg-white/55 transition hover:bg-white/80"
                        data-testid="needs-attention-row"
                      >
                        <div className="flex flex-col gap-3 px-3.5 py-3 sm:flex-row sm:items-start sm:justify-between">
                          <button
                            type="button"
                            className="min-w-0 flex-1 text-start"
                            onClick={() => openDeepLink(item)}
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge tone={urgency.tone}>{isAr ? urgency.ar : urgency.en}</Badge>
                              <span className="text-[11.5px] text-subtle/75">
                                {copy.resolveIn} {soa}
                              </span>
                            </div>
                            <p className="mt-1.5 text-[14px] font-semibold tracking-[-0.01em] text-text">{what}</p>
                            {place ? (
                              <p className="mt-0.5 truncate text-[12.5px] text-subtle/85">
                                {copy.who}: {place}
                              </p>
                            ) : null}
                            {why ? (
                              <p className="mt-1 line-clamp-2 text-[12.5px] text-subtle/85">
                                {copy.why}: {why}
                              </p>
                            ) : null}
                            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-subtle/75">
                              {deadline ? (
                                <span>
                                  {copy.deadline}: {deadline}
                                </span>
                              ) : null}
                              {owner ? (
                                <span>
                                  {copy.owner}: {owner}
                                </span>
                              ) : null}
                            </div>
                          </button>
                          <div className="flex shrink-0 flex-wrap items-center gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setExpandedId((cur) => (cur === item.id ? null : item.id))}
                            >
                              <ChevronDown className={cn('h-4 w-4 transition', expanded && 'rotate-180')} />
                              {expanded ? copy.hideMore : copy.more}
                            </Button>
                            <Button size="sm" onClick={() => openDeepLink(item)}>
                              {copy.open}
                              <ArrowRight className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                        {expanded ? (
                          <div className="border-t border-[#e8dfd0]/80 bg-[#f7f1e6]/45 px-3.5 py-3 text-[12.5px] text-subtle/90">
                            <div className="grid gap-2 sm:grid-cols-2">
                              <p>
                                <span className="font-medium text-text">{copy.evidence}: </span>
                                {evidence || '—'}
                              </p>
                              <p>
                                <span className="font-medium text-text">{copy.authority}: </span>
                                {authority || '—'}
                              </p>
                            </div>
                            {item.grouped && Array.isArray(item.grouped_document_types) && item.grouped_document_types.length ? (
                              <p className="mt-2" data-testid="needs-attention-grouped-docs">
                                <span className="font-medium text-text">{copy.groupedDocs}: </span>
                                {item.grouped_document_types.join(', ')}
                                {item.grouped_count && item.grouped_count > item.grouped_document_types.length
                                  ? ` (+${item.grouped_count - item.grouped_document_types.length})`
                                  : null}
                              </p>
                            ) : null}
                            <p className="mt-2 text-[12px] text-subtle/75">{copy.honesty}</p>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="space-y-2">
            <Button variant="ghost" size="sm" onClick={() => setShowDefinitions((v) => !v)}>
              {showDefinitions ? copy.hideDefinitions : copy.definitions}
            </Button>
            {showDefinitions && definitions.length ? (
              <Card>
                <CardContent className="space-y-3 pt-4">
                  {definitions.map((def) => (
                    <div key={def.key} className="space-y-0.5">
                      <p className="text-[13px] font-medium text-text">{isAr ? def.label_ar : def.label_en}</p>
                      <p className="text-[12.5px] text-subtle/85">{isAr ? def.definition_ar : def.definition_en}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

// --- Analytics ------------------------------------------------------------

function analyticsPatternLabel(metric: string, isAr: boolean): string {
  const map: Record<string, { en: string; ar: string }> = {
    'Branch absences': { en: 'Absence by branch', ar: 'الغياب حسب الفرع' },
    'Top lateness': { en: 'Highest lateness', ar: 'أعلى التأخر' },
    'Top absences': { en: 'Highest absence', ar: 'أعلى الغياب' },
    'Hours above schedule': { en: 'Hours above schedule', ar: 'ساعات فوق الجدول' },
    'Pending leave': { en: 'Leave awaiting decision', ar: 'إجازات بانتظار القرار' },
    'Pending swaps': { en: 'Swap requests awaiting decision', ar: 'تبديلات بانتظار القرار' },
    'Pending availability': { en: 'Availability awaiting decision', ar: 'توفر بانتظار القرار' },
  }
  const hit = map[metric]
  if (hit) return isAr ? hit.ar : hit.en
  return metric.replace(/_/g, ' ')
}

function AnalyticsPage({
  access,
  onAccessIssue,
  onNavigate,
}: Pick<PostHireProps, 'access' | 'onAccessIssue' | 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const loader = useCallback(() => getPosthireAnalytics(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireAnalyticsResponse>(loader, onAccessIssue)
  const [fetchedAtMs, setFetchedAtMs] = useState<number | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [showMethodology, setShowMethodology] = useState(false)

  useEffect(() => {
    if (data?.as_of || data?.counts) setFetchedAtMs(Date.now())
  }, [data])

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const attention = Array.isArray(data?.attention) ? data?.attention ?? [] : []
  const headlines = Array.isArray(data?.headlines) ? data?.headlines ?? [] : []
  const insights = Array.isArray(data?.insights) ? data?.insights ?? [] : []
  const definitions = Array.isArray(data?.definitions) ? data?.definitions ?? [] : []
  const sourcesPack = data?.sources
  const unavailable = Array.isArray(sourcesPack?.unavailable_source_keys) ? sourcesPack?.unavailable_source_keys ?? [] : []
  const partial = Boolean(sourcesPack?.partial)
  const staleAfter = Number(data?.freshness?.stale_after_seconds ?? 300)
  const isStale = fetchedAtMs != null && nowMs - fetchedAtMs > staleAfter * 1000

  const patternGroups = useMemo(() => {
    const map = new Map<string, typeof insights>()
    for (const insight of insights) {
      if (insight.demoted || ANALYTICS_PATTERN_SKIP.has(insight.metric)) continue
      const list = map.get(insight.metric) ?? []
      list.push(insight)
      map.set(insight.metric, list)
    }
    return Array.from(map.entries())
  }, [insights])

  const period =
    data?.window?.label_en || data?.window?.label_ar
      ? isAr
        ? data?.window?.label_ar || data?.window?.label_en
        : data?.window?.label_en || data?.window?.label_ar
      : data?.start_date && data?.end_date
        ? `${formatDate(data.start_date)} → ${formatDate(data.end_date)}`
        : isAr
          ? 'من بداية الشهر حتى اليوم'
          : 'Month to date'

  const rangeLabel =
    data?.start_date && data?.end_date
      ? `${formatDate(data.start_date)} → ${formatDate(data.end_date)}`
      : period

  const asOfLabel = data?.as_of
    ? (() => {
        try {
          return new Date(data.as_of).toLocaleString(isAr ? 'ar-KW' : 'en-GB', {
            timeZone: data.timezone || 'Asia/Kuwait',
            dateStyle: 'medium',
            timeStyle: 'short',
          })
        } catch {
          return data.as_of
        }
      })()
    : null

  const hasInsightData = headlines.some((h) => Number(h.value) > 0) || patternGroups.length > 0
  const hasAnyPayload = hasInsightData || attention.length > 0 || partial || unavailable.length > 0

  const narrative = useMemo(() => {
    const parts: string[] = []
    const byKey = Object.fromEntries(headlines.map((h) => [h.key, Number(h.value || 0)]))
    const absences = byKey.absences ?? byKey.absent_records
    const late = byKey.late_records ?? byKey.late
    const pending = byKey.pending_review ?? byKey.pending_leave
    if (isAr) {
      if (absences != null) parts.push(`الغياب في الفترة: ${absences}`)
      if (late != null) parts.push(`سجلات التأخر: ${late}`)
      if (pending != null) parts.push(`عناصر بانتظار المراجعة: ${pending}`)
      if (patternGroups.length) parts.push(`أنماط التركّز تظهر في ${patternGroups.length} مجموعة أدناه`)
      if (attention.length) {
        parts.push(
          `${attention.length} إشارة يومية مُدارة في «يحتاج انتباهاً» — التحليلات تفسّر الاتجاه لا قائمة المهام`,
        )
      } else if (parts.length) {
        parts.push('لا إشارات يومية عالية الآن — راقب الاتجاهات أدناه')
      }
      return parts.join(' · ')
    }
    if (absences != null) parts.push(`${absences} absence${absences === 1 ? '' : 's'} in this period`)
    if (late != null) parts.push(`${late} late record${late === 1 ? '' : 's'}`)
    if (pending != null) parts.push(`${pending} item${pending === 1 ? '' : 's'} awaiting review`)
    if (patternGroups.length) {
      parts.push(`concentration shows in ${patternGroups.length} pattern group${patternGroups.length === 1 ? '' : 's'} below`)
    }
    if (attention.length) {
      parts.push(
        `${attention.length} daily signal${attention.length === 1 ? '' : 's'} live in Needs Attention — Analytics explains the trend, not the task list`,
      )
    } else if (parts.length) {
      parts.push('No high daily signals right now — watch the trends below')
    }
    return parts.join(' · ')
  }, [headlines, patternGroups, attention.length, isAr])

  const copy = {
    refresh: isAr ? 'تحديث' : 'Refresh',
    subtitle: isAr
      ? 'افهم أنماط القوى العاملة والتغيّرات والمخاطر — لا قائمة المهام اليومية.'
      : 'Understand workforce patterns, changes, and risks — not the daily task queue.',
    loadingErr: isAr ? 'تعذر تحميل التحليلات.' : 'We couldn’t load analytics.',
    emptyTitle: isAr ? 'لا أنماط بارزة في هذه الفترة' : 'No standout patterns in this period',
    emptyHint: isAr
      ? 'عندما يتراكم الحضور أو الإجازة أو الورديات، تظهر الاتجاهات هنا. المهام اليومية تبقى في «يحتاج انتباهاً».'
      : 'When attendance, leave, or shifts accumulate signal, trends appear here. Daily triage stays in Needs Attention.',
    insightsTitle: isAr ? 'ملخص الفترة' : 'Period snapshot',
    narrativeTitle: isAr ? 'ما تغيّر ولماذا يهم' : 'What changed and why it matters',
    patternsTitle: isAr ? 'اتجاهات وتركّز' : 'Trends & concentration',
    methodology: isAr ? 'التعريفات والمصادر' : 'Definitions & sources',
    hideMethodology: isAr ? 'إخفاء التعريفات' : 'Hide definitions',
    sourcesPartial: isAr
      ? 'بعض مصادر البيانات غير مفعّلة — الأرقام قد تكون ناقصة'
      : 'Some data sources are unavailable — figures may be incomplete',
    stale: isAr ? 'البيانات قد تكون قديمة — حدّث' : 'Data may be stale — refresh',
    asOf: isAr ? 'كما في' : 'As of',
    period: isAr ? 'الفترة' : 'Period',
    compare: isAr ? 'المقارنة' : 'Comparison',
    compareThis: isAr ? 'هذه الفترة' : 'This period',
    compareNote: isAr
      ? 'نافذة الكويت من بداية الشهر حتى اليوم (عرض فقط في هذه الموجة).'
      : 'Kuwait month-to-date window (display-only in this wave).',
    triageHint: isAr
      ? 'المهام اليومية مرتّبة في «يحتاج انتباهاً». التحليلات تفسّر الأنماط فقط.'
      : 'Daily triage lives in Needs Attention. Analytics explains patterns only.',
    openInbox: isAr ? 'فتح يحتاج انتباهاً' : 'Open Needs Attention',
    signalsCount: (n: number) =>
      isAr ? `${n} إشارة يومية في يحتاج انتباهاً` : `${n} daily signal${n === 1 ? '' : 's'} in Needs Attention`,
    readOnlyShort: isAr
      ? 'قراءة فقط · تقارير التوظيف منفصلة · التنبيهات تملك التواصل'
      : 'Read-only · Hiring Reports stay separate · Alerts & Delivery owns communication',
  }

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="analytics-workspace" data-analytics-insights>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-2xl space-y-1">
          <p className="text-[13px] text-subtle/90">{copy.subtitle}</p>
          <div className="flex flex-wrap items-center gap-2" data-analytics-period>
            <span className="rounded-full bg-[#f3ebe0] px-3 py-1 text-[12px] font-medium text-ink">
              {copy.period}: {rangeLabel}
            </span>
            <span
              className="rounded-full border border-dashed border-line/70 px-3 py-1 text-[12px] text-subtle"
              title={copy.compareNote}
              data-analytics-comparison
            >
              {copy.compare}: {copy.compareThis}
            </span>
            {asOfLabel ? (
              <span className="text-[12px] text-subtle/80">
                {copy.asOf} {asOfLabel}
              </span>
            ) : null}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => void reload()} disabled={refreshing} aria-label={copy.refresh}>
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error || copy.loadingErr} onRetry={() => void reload()} />
      ) : !hasAnyPayload ? (
        <EmptyState icon={<BarChart3 className="h-5 w-5" />} title={copy.emptyTitle} hint={copy.emptyHint} />
      ) : (
        <>
          {isStale ? (
            <p className="rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-[13px] text-amber-950" data-analytics-stale>
              {copy.stale}
              {asOfLabel ? ` · ${copy.asOf} ${asOfLabel}` : ''}
            </p>
          ) : null}

          {partial || unavailable.length ? (
            <div className="rounded-xl border border-dashed border-line/70 bg-[#fffaf0]/70 px-3.5 py-3 text-[13px] text-muted" data-analytics-partial>
              <p className="font-medium text-ink">{copy.sourcesPartial}</p>
              <p className="mt-1 text-[12px]">
                {unavailable
                  .map((key) => {
                    const row = sourcesPack?.sources?.[key]
                    return isAr ? row?.note_ar || key : row?.note_en || key
                  })
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            </div>
          ) : null}

          {headlines.length ? (
            <section className="space-y-2" data-analytics-snapshot>
              <h2 className="text-[13px] font-semibold text-ink">{copy.insightsTitle}</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {headlines.map((stat) => (
                  <StatCard
                    key={stat.key}
                    label={isAr ? stat.label_ar : stat.label_en}
                    value={Number(stat.value || 0)}
                    hint={(isAr ? stat.hint_ar : stat.hint_en) || undefined}
                  />
                ))}
              </div>
            </section>
          ) : null}

          {narrative ? (
            <section
              className="rounded-[1.25rem] border border-line/55 bg-white/80 px-4 py-3.5 shadow-[0_12px_28px_rgba(35,33,29,0.06)]"
              data-analytics-narrative
            >
              <h2 className="text-[13px] font-semibold text-ink">{copy.narrativeTitle}</h2>
              <p className="mt-1.5 text-[13.5px] leading-6 text-muted">{narrative}</p>
            </section>
          ) : null}

          {attention.length > 0 ? (
            <div
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[#f3ebe0]/70 px-3.5 py-2.5"
              data-analytics-triage-link
            >
              <p className="text-[12.5px] text-muted">
                {copy.signalsCount(attention.length)} · {copy.triageHint}
              </p>
              <Button size="sm" variant="secondary" onClick={() => onNavigate?.('inbox')}>
                {copy.openInbox}
              </Button>
            </div>
          ) : (
            <p className="text-[12px] text-subtle/80">{copy.triageHint}</p>
          )}

          {patternGroups.length ? (
            <section className="space-y-3" data-analytics-patterns>
              <h2 className="text-[13px] font-semibold text-ink">{copy.patternsTitle}</h2>
              <div className="grid gap-4 lg:grid-cols-2">
                {patternGroups.map(([metric, rows]) => (
                  <Card key={metric}>
                    <CardHeader>
                      <CardTitle>{analyticsPatternLabel(metric, isAr)}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {rows.map((row, idx) => (
                          <div
                            key={`${metric}-${row.subject}-${idx}`}
                            className="flex items-center justify-between gap-3 rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-2.5 text-[13px]"
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium text-text">{row.subject}</p>
                              {row.detail ? <p className="truncate text-[12px] text-subtle/80">{row.detail}</p> : null}
                            </div>
                            <span className="shrink-0 text-[15px] font-semibold tabular-nums text-text">{row.value}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>
          ) : !hasInsightData ? (
            <EmptyState icon={<BarChart3 className="h-5 w-5" />} title={copy.emptyTitle} hint={copy.emptyHint} />
          ) : null}

          <div className="space-y-2" data-analytics-methodology>
            <button
              type="button"
              className="text-[12px] font-medium text-subtle underline"
              onClick={() => setShowMethodology((v) => !v)}
            >
              {showMethodology ? copy.hideMethodology : copy.methodology}
            </button>
            {showMethodology ? (
              <div className="space-y-3 rounded-[1.25rem] border border-dashed border-line/70 bg-[#fffaf0]/60 px-4 py-3">
                <p className="text-[12px] text-muted">{copy.readOnlyShort}</p>
                <p className="text-[12px] text-muted">{copy.compareNote}</p>
                {definitions.length ? (
                  <div className="space-y-3">
                    {definitions.map((def) => (
                      <div key={def.key} className="space-y-0.5">
                        <p className="text-[13px] font-medium text-text">{isAr ? def.label_ar : def.label_en}</p>
                        <p className="text-[12.5px] text-subtle/85">{isAr ? def.definition_ar : def.definition_en}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

// --- Compliance ------------------------------------------------------------

function complianceDaysLabel(doc: { days_until_expiry?: number | null }, isAr = false): string {
  const days = doc.days_until_expiry
  if (days == null) return '—'
  if (days < 0) return isAr ? `${Math.abs(days)}ي متأخر` : `${Math.abs(days)}d overdue`
  if (days === 0) return isAr ? 'اليوم' : 'Today'
  return isAr ? `${days}ي متبقية` : `${days}d left`
}

function CompliancePage({
  access,
  permissions,
  role,
  onNotice,
  onAccessIssue,
  onNavigate,
}: PostHireCommonProps & Pick<PostHireProps, 'onNavigate'>) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const [surface, setSurface] = useState<'findings' | 'register'>('findings')
  const [filter, setFilter] = useState<'all' | ComplianceBucket>('needs_review')
  const [query, setQuery] = useState('')
  const [showMethodology, setShowMethodology] = useState(false)
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null)
  const [fetchedAtMs, setFetchedAtMs] = useState<number | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const debouncedQuery = useDebouncedValue(query.trim(), 350)
  const loader = useCallback(
    () =>
      getPosthireCompliance(access, {
        bucket: filter,
        ...(debouncedQuery ? { search: debouncedQuery } : {}),
      }),
    [access, filter, debouncedQuery],
  )
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireComplianceResponse>(loader, onAccessIssue)
  const [extraDocuments, setExtraDocuments] = useState<ComplianceDocument[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraDocuments([])
  }, [data])
  useEffect(() => {
    if (data?.as_of || data?.summary) setFetchedAtMs(Date.now())
  }, [data])
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  const action = usePosthireAction(access, reload, onNotice, onAccessIssue)
  const confirm = useConfirm()
  const canManage = can(permissions, 'compliance.manage', role)
  const canUpload = can(permissions, 'onboarding.manage', role) && Boolean(data?.doc_upload_enabled)

  const summary = data?.summary
  const findings = Array.isArray(data?.findings) ? data?.findings ?? [] : []
  const definitions = Array.isArray(data?.definitions) ? data?.definitions ?? [] : []
  const sourcesPack = data?.sources
  const unavailable = Array.isArray(sourcesPack?.unavailable_source_keys) ? sourcesPack?.unavailable_source_keys ?? [] : []
  const partial = Boolean(sourcesPack?.partial)
  const staleAfter = Number(data?.freshness?.stale_after_seconds ?? 300)
  const isStale = fetchedAtMs != null && nowMs - fetchedAtMs > staleAfter * 1000
  const documents = useMemo(
    () => [...(data?.documents ?? []), ...extraDocuments],
    [data?.documents, extraDocuments],
  )
  const totalDocuments = data?.filtered_total ?? documents.length
  const searching = debouncedQuery.length > 0

  const filterLabels: Array<{ key: 'all' | ComplianceBucket; label: string }> = [
    { key: 'needs_review', label: isAr ? 'تحتاج مراجعة' : 'Needs review' },
    { key: 'missing', label: isAr ? 'ناقصة' : 'Missing' },
    { key: 'expiring_soon', label: isAr ? 'تنتهي قريباً' : 'Expiring' },
    { key: 'expired', label: isAr ? 'منتهية' : 'Expired' },
    { key: 'all', label: isAr ? 'الكل' : 'All' },
  ]

  const filteredFindings = useMemo(() => {
    if (filter === 'all') return findings.filter((f) => String(f.bucket || '') !== 'valid')
    return findings.filter((f) => String(f.bucket || '') === filter)
  }, [findings, filter])

  const asOfLabel = data?.as_of
    ? (() => {
        try {
          return new Date(data.as_of).toLocaleString(isAr ? 'ar-KW' : 'en-GB', {
            timeZone: data.timezone || 'Asia/Kuwait',
            dateStyle: 'medium',
            timeStyle: 'short',
          })
        } catch {
          return data.as_of
        }
      })()
    : null

  const loadMoreDocuments = useCallback(async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthireCompliance(access, {
        offset: documents.length,
        bucket: filter,
        ...(debouncedQuery ? { search: debouncedQuery } : {}),
      })
      setExtraDocuments((prev) => [...prev, ...(res.documents ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(
        friendlyError(err, isAr ? 'تعذر تحميل المزيد من المستندات.' : 'We couldn’t load more documents. Please try again.'),
        'error',
      )
    } finally {
      setLoadingMore(false)
    }
  }, [access, documents.length, filter, debouncedQuery, onAccessIssue, onNotice, isAr])

  const needsAttention = summary?.needs_attention ?? findings.length
  const docLabel = (doc: ComplianceDocument) =>
    isAr ? doc.document_label_ar || doc.document_label : doc.document_label_en || doc.document_label

  const findingDocLabel = (item: ComplianceFinding) =>
    isAr ? item.document_label_ar || item.document_label || item.document_type : item.document_label_en || item.document_label || item.document_type

  const bucketLabel = (bucket: string) => {
    const map: Record<string, { en: string; ar: string }> = {
      needs_review: { en: 'Needs review', ar: 'تحتاج مراجعة' },
      missing: { en: 'Missing', ar: 'ناقصة' },
      expiring_soon: { en: 'Expiring', ar: 'تنتهي قريباً' },
      expired: { en: 'Expired', ar: 'منتهية' },
      valid: { en: 'HR reviewed', ar: 'مراجعة موارد بشرية' },
    }
    return isAr ? map[bucket]?.ar || bucket : map[bucket]?.en || bucket
  }

  const sendFindingReminder = async (item: ComplianceFinding) => {
    const name = item.employee_name || item.subject || ''
    const dtype = item.document_type || ''
    if (!name || !dtype) return
    const ok = await confirm({
      title: isAr ? 'إرسال تذكير بالمستند؟' : 'Send document reminder?',
      body: isAr
        ? `سيستلم ${name} تذكيراً بخصوص ${findingDocLabel(item)}. التوصيل عبر التنبيهات والتسليم.`
        : `${name} will receive a reminder about their ${findingDocLabel(item)}. Delivery via Alerts & Delivery.`,
      confirmLabel: isAr ? 'أرسل التذكير' : 'Send reminder',
      dir: isAr ? 'rtl' : 'ltr',
    })
    if (!ok) return
    await action.run(
      'compliance_send_reminder',
      { employee_name: name, document_type: dtype },
      { key: `remind:${item.employee_key || name}:${dtype}` },
    )
  }

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="compliance-workspace" data-compliance-findings>
      {action.dialog}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-2xl space-y-1">
          <p className="text-[13px] text-subtle/90">
            {isAr
              ? 'حل المستندات الناقصة والمنتهية والتي تحتاج مراجعة — عبر مسار واحد واضح.'
              : 'Resolve missing, expiring, expired, and review-required documents through one clear workflow.'}
          </p>
          <p className="text-[12px] text-subtle/80" data-compliance-summary>
            {needsAttention
              ? isAr
                ? `${needsAttention} مستند يحتاج إجراءً`
                : `${needsAttention} document${needsAttention === 1 ? '' : 's'} need action`
              : isAr
                ? 'لا مستندات تحتاج إجراءً الآن'
                : 'No documents need action right now'}
            {asOfLabel ? ` · ${isAr ? 'اعتباراً من' : 'As of'} ${asOfLabel}` : ''}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => void reload()} disabled={refreshing} aria-label={isAr ? 'تحديث' : 'Refresh'}>
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={error || (isAr ? 'تعذر تحميل الامتثال.' : 'We couldn’t load compliance.')}
          onRetry={() => void reload()}
        />
      ) : !summary || summary.total_documents === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title={isAr ? 'لا مستندات امتثال متتبَّعة بعد' : 'No compliance documents tracked yet'}
          hint={
            isAr
              ? 'يظهر الناقص والمنتهي هنا بعد رفع مستندات الموظفين. المراجعة ليست تحققاً حكومياً.'
              : 'Missing and expiring items surface here after employee documents are uploaded. HR review is not government verification.'
          }
        />
      ) : (
        <>
          {(isStale || partial) ? (
            <div className="flex flex-wrap gap-2 text-[12px]" data-compliance-health>
              {isStale ? <Badge tone="warning">{isAr ? 'البيانات قد تكون قديمة — حدّث' : 'Data may be stale — refresh'}</Badge> : null}
              {partial ? (
                <Badge tone="warning">
                  {isAr ? `مصادر جزئية: ${unavailable.join(', ') || '—'}` : `Partial sources: ${unavailable.join(', ') || '—'}`}
                </Badge>
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2" data-compliance-surfaces role="tablist">
            {(
              [
                ['findings', isAr ? 'النتائج' : 'Findings'],
                ['register', isAr ? 'كل المستندات' : 'All documents'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={surface === id}
                data-surface={id}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${
                  surface === id ? 'bg-wf-ink text-white' : 'bg-[#f3ebe0] text-subtle'
                }`}
                onClick={() => setSurface(id)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2" data-compliance-filters>
            {filterLabels.map((chip) => {
              const count =
                chip.key === 'all' ? summary.needs_attention : (summary[chip.key as ComplianceBucket] as number)
              const activeChip = filter === chip.key
              return (
                <button
                  key={chip.key}
                  type="button"
                  onClick={() => setFilter(chip.key)}
                  className={cn(
                    'rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium transition',
                    activeChip
                      ? 'border-ink bg-ink text-white'
                      : 'border-line/60 bg-white/60 text-subtle hover:border-[#c89445]/40 hover:text-ink',
                  )}
                >
                  {chip.label} {count ? <span className="tabular-nums">({count})</span> : null}
                </button>
              )
            })}
          </div>

          {surface === 'findings' ? (
            <section className="space-y-3" data-compliance-findings-list>
              {filteredFindings.length === 0 ? (
                <EmptyState
                  icon={<CheckCircle2 className="h-5 w-5" />}
                  title={isAr ? 'لا نتائج في هذا العرض' : 'No findings in this view'}
                  hint={isAr ? 'جرّب تصفية أخرى أو افتح كل المستندات.' : 'Try another filter or open All documents.'}
                />
              ) : (
                filteredFindings.map((item) => {
                  const reason = isAr ? item.reason_ar || item.reason_en : item.reason_en || item.reason
                  const deadline = isAr ? item.deadline_label_ar : item.deadline_label_en
                  const expanded = expandedFindingId === item.id
                  const bucket = String(item.bucket || '')
                  const who = item.employee_name || item.subject || '—'
                  const remindKey = `remind:${item.employee_key || who}:${item.document_type || ''}`
                  return (
                    <div
                      key={item.id}
                      className="rounded-[1.25rem] border border-line/55 bg-white/80 px-4 py-3 shadow-[0_10px_24px_rgba(35,33,29,0.05)]"
                      data-finding-id={item.id}
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone={bucket === 'expired' || bucket === 'missing' ? 'danger' : bucket === 'needs_review' ? 'warning' : 'warning'}>
                              {bucketLabel(bucket)}
                            </Badge>
                            <span className="text-[12px] text-subtle/80">{findingDocLabel(item)}</span>
                          </div>
                          <p className="text-[14px] font-semibold text-ink">{who}</p>
                          <p className="text-[13px] text-muted">{reason}</p>
                          {deadline ? <p className="text-[12px] text-subtle/85">{isAr ? 'الموعد' : 'Deadline'}: {deadline}</p> : null}
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {canManage && bucket === 'needs_review' && item.employee_key && item.document_type ? (
                            <DocumentHrReviewButtons
                              access={access}
                              employeeKey={String(item.employee_key)}
                              documentType={String(item.document_type)}
                              documentLabel={findingDocLabel(item)}
                              employeeName={who}
                              showApprove
                              primaryOnly
                              locale={locale}
                              onDone={(message) => {
                                onNotice(message, 'success')
                                void reload()
                              }}
                              onError={(message) => onNotice(message, 'error')}
                              onAccessIssue={onAccessIssue}
                            />
                          ) : null}
                          {canManage && bucket !== 'needs_review' && bucket !== 'valid' ? (
                            <Button
                              size="sm"
                              disabled={action.busy}
                              data-compliance-remind
                              onClick={() => void sendFindingReminder(item)}
                            >
                              {action.runningKey === remindKey ? (
                                <>
                                  <Loader2 className="h-4 w-4 animate-spin" /> {isAr ? 'جارٍ الإرسال…' : 'Sending…'}
                                </>
                              ) : isAr ? (
                                'أرسل تذكيراً'
                              ) : (
                                'Send reminder'
                              )}
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setExpandedFindingId(expanded ? null : item.id)}
                          >
                            {expanded ? (isAr ? 'إخفاء التفاصيل' : 'Hide details') : isAr ? 'التفاصيل' : 'Details'}
                          </Button>
                        </div>
                      </div>
                      {expanded ? (
                        <div className="mt-3 space-y-2 border-t border-line/50 pt-3 text-[12.5px] text-muted" data-compliance-finding-detail>
                          {(isAr ? item.why_it_matters_ar : item.why_it_matters_en) ? (
                            <p>{isAr ? item.why_it_matters_ar : item.why_it_matters_en}</p>
                          ) : null}
                          {(isAr ? item.evidence_status_label_ar : item.evidence_status_label_en) ? (
                            <p>
                              {isAr ? 'الدليل' : 'Evidence'}:{' '}
                              {isAr ? item.evidence_status_label_ar : item.evidence_status_label_en}
                            </p>
                          ) : null}
                          {(isAr ? item.owner_label_ar : item.owner_label_en) ? (
                            <p>
                              {isAr ? 'المالك' : 'Owner'}: {isAr ? item.owner_label_ar : item.owner_label_en}
                            </p>
                          ) : null}
                          <p>{isAr ? 'ليست تحققاً حكومياً' : 'Not government verified'}</p>
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() =>
                                onNavigate?.(
                                  'employees',
                                  item.employee_key || item.subject_key
                                    ? { employee: String(item.employee_key || item.subject_key) }
                                    : undefined,
                                )
                              }
                            >
                              {isAr ? 'فتح الموظف' : 'Open employee'}
                            </Button>
                            {(item.secondary_links || []).map((link, idx) => (
                              <Button
                                key={`${item.id}-sec-${idx}`}
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  onNavigate?.(
                                    link.page,
                                    link.employee ? { employee: String(link.employee) } : undefined,
                                  )
                                }
                              >
                                {isAr ? link.label_ar || link.page : link.label_en || link.page}
                              </Button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )
                })
              )}
            </section>
          ) : (
            <section className="space-y-4" data-compliance-register>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] text-muted">
                  {searching
                    ? isAr
                      ? `${totalDocuments} نتيجة لـ «${debouncedQuery}»`
                      : `${totalDocuments} result${totalDocuments === 1 ? '' : 's'} for “${debouncedQuery}”`
                    : isAr
                      ? `${documents.length} من ${totalDocuments} مستند`
                      : `${documents.length} of ${totalDocuments} document${totalDocuments === 1 ? '' : 's'}`}
                </p>
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder={isAr ? 'ابحث بالاسم أو المستند…' : 'Search name or document…'}
                />
              </div>
              {documents.length === 0 ? (
                <EmptyState
                  icon={searching ? <Search className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />}
                  title={searching ? (isAr ? 'لا نتائج' : 'No matches') : isAr ? 'لا شيء في هذا العرض' : 'Nothing in this view'}
                  hint={isAr ? 'جرّب تصفية أو بحثاً آخر.' : 'Try another filter or search.'}
                />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[760px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">{isAr ? 'الموظف' : 'Employee'}</th>
                        <th className="px-4 py-3 font-medium">{isAr ? 'المستند' : 'Document'}</th>
                        <th className="px-4 py-3 font-medium">{isAr ? 'الحالة' : 'Status'}</th>
                        <th className="px-4 py-3 font-medium">{isAr ? 'الانتهاء' : 'Expiry'}</th>
                        <th className="px-4 py-3 text-right font-medium">{isAr ? 'إجراء' : 'Action'}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {documents.map((doc, idx) => {
                        const rowKey = `${doc.employee_key}-${doc.document_type}-${idx}`
                        return (
                          <tr key={rowKey} className="hover:bg-white/45">
                            <td className="px-4 py-3">
                              <p className="font-semibold text-text">{doc.employee_name}</p>
                              {doc.department ? <p className="text-[12px] text-subtle/85">{doc.department}</p> : null}
                            </td>
                            <td className="px-4 py-3 text-subtle/90">{docLabel(doc)}</td>
                            <td className="px-4 py-3">
                              <Badge tone={doc.tone}>{doc.status_label}</Badge>
                            </td>
                            <td className="px-4 py-3 text-subtle/90">{formatDate(doc.expiry_date)}</td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex flex-wrap items-center justify-end gap-1.5">
                                {canManage && doc.document_type && doc.status === 'needs_review' ? (
                                  <DocumentHrReviewButtons
                                    access={access}
                                    employeeKey={doc.employee_key}
                                    documentType={doc.document_type}
                                    documentLabel={docLabel(doc)}
                                    employeeName={doc.employee_name}
                                    showApprove
                                    primaryOnly
                                    locale={locale}
                                    onDone={(message) => {
                                      onNotice(message, 'success')
                                      void reload()
                                    }}
                                    onError={(message) => onNotice(message, 'error')}
                                    onAccessIssue={onAccessIssue}
                                  />
                                ) : null}
                                {canManage && doc.status !== 'valid' && doc.status !== 'needs_review' ? (
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => {
                                      setFilter(
                                        doc.status === 'expired'
                                          ? 'expired'
                                          : doc.status === 'expiring_soon'
                                            ? 'expiring_soon'
                                            : 'missing',
                                      )
                                      setSurface('findings')
                                    }}
                                  >
                                    {isAr ? 'فتح في النتائج' : 'Open in Findings'}
                                  </Button>
                                ) : null}
                                <DocumentActions access={access} fileId={doc.file_id} filename={docLabel(doc)} compact />
                                {canUpload && doc.document_type ? (
                                  <DocumentUploadButton
                                    access={access}
                                    employeeKey={doc.employee_key}
                                    itemId={doc.document_type}
                                    documentLabel={docLabel(doc) || doc.document_type}
                                    hasFile={Boolean(doc.file_id)}
                                    onUploaded={(message) => {
                                      onNotice(message, 'success')
                                      void reload()
                                    }}
                                    onError={(message) => onNotice(message, 'error')}
                                    onAccessIssue={onAccessIssue}
                                    compact
                                  />
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {documents.length > 0 ? (
                <LoadMoreBar
                  loaded={documents.length}
                  total={totalDocuments}
                  loading={loadingMore}
                  onLoadMore={() => void loadMoreDocuments()}
                  noun={isAr ? 'مستند' : 'document'}
                />
              ) : null}
              {canUpload ? <DocumentPrivacyNote /> : null}
            </section>
          )}

          <div className="space-y-2" data-compliance-methodology>
            <button
              type="button"
              className="text-[12px] font-medium text-subtle underline"
              onClick={() => setShowMethodology((v) => !v)}
            >
              {showMethodology
                ? isAr
                  ? 'إخفاء التعريفات'
                  : 'Hide definitions'
                : isAr
                  ? 'التعريفات والصلاحية'
                  : 'Definitions & authority'}
            </button>
            {showMethodology ? (
              <div className="space-y-3 rounded-[1.25rem] border border-dashed border-line/70 bg-[#fffaf0]/60 px-4 py-3 text-[12.5px] text-muted">
                <p>
                  {isAr
                    ? 'قراءة للمراجعة فقط · ليست تحققاً حكومياً · التنبيهات والتسليم تملك فشل التوصيل'
                    : 'Review only · never government verified · Alerts & Delivery owns failed delivery'}
                </p>
                {definitions.map((d) => (
                  <div key={d.key}>
                    <p className="font-semibold text-text">{isAr ? d.label_ar : d.label_en}</p>
                    <p>{isAr ? d.definition_ar : d.definition_en}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}


// --- dispatcher ------------------------------------------------------------

// Shows HR follow-up tasks raised by the shared outbound delivery layer — e.g.
// "couldn't reach an employee, please follow up". Renders nothing when there is
// nothing to do (and stays silent until flows are wired in a later phase), so it
// never adds noise to a clean workspace.
function DeliveryFollowUpCard({ access, permissions, role, onNotice, onAccessIssue }: PostHireCommonProps) {
  const loader = useCallback(() => getHrTasks(access, 'open', { limit: 50 }), [access])
  const { data, error, reload } = useModuleData<HrTasksResponse>(loader, onAccessIssue)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  // Page 1 comes from useModuleData; extra pages accumulate here and reset
  // whenever the base page reloads, so a company with more open tasks than fit
  // on one page can page through all of them instead of the badge/list
  // silently freezing at the page cap.
  const [extraTasks, setExtraTasks] = useState<HrTask[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraTasks([])
  }, [data])
  const canManage =
    can(permissions, 'users.manage', role) ||
    ['leave', 'onboarding', 'compliance', 'attendance', 'shifts', 'payroll'].some((m) => can(permissions, `${m}.manage`, role))

  const baseTasks: HrTask[] = data?.tasks ?? []
  const tasks = useMemo(() => [...baseTasks, ...extraTasks], [baseTasks, extraTasks])
  // Always the true company-wide open count, never the length of a page that
  // may be capped — otherwise the badge silently freezes once a company
  // crosses the page size.
  const total = data?.open_count ?? data?.total ?? tasks.length
  // The endpoint can 403 on workspaces without a post-hire module / read access;
  // treat that as "nothing to surface" rather than showing an error here.
  if (error || (tasks.length === 0 && total === 0)) return null

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await getHrTasks(access, 'open', { limit: 50, offset: tasks.length })
      setExtraTasks((prev) => [...prev, ...(res.tasks ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, 'We couldn’t load more follow-ups. Please try again.'), 'error')
    } finally {
      setLoadingMore(false)
    }
  }

  const resolve = async (task: HrTask) => {
    setResolvingId(task.task_id)
    try {
      await resolveHrTask(access, task.task_id, 'done')
      onNotice('Marked as done.', 'success')
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue(issue)
        return
      }
      onNotice(friendlyError(err, 'We could not update that task.'), 'error')
    } finally {
      setResolvingId(null)
    }
  }

  return (
    <Card className="mb-5 border-amber-200/70 bg-[#fffaf0]">
      <CardHeader>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-[#8a5a16]" />
          <CardTitle className="text-[15px]">Needs your follow-up</CardTitle>
          <Badge tone="warning" className="ml-1">
            {total}
          </Badge>
        </div>
        <CardDescription>
          Wathefni could not reach {total === 1 ? 'this employee' : 'these employees'} through the currently enabled channels. Please follow up directly, then mark it done.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {tasks.map((task) => (
          <div key={task.task_id} className="flex items-start justify-between gap-3 rounded-xl border border-amber-200/60 bg-white/70 px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-medium text-text">{task.title}</p>
              {task.employee_name ? <p className="text-[12px] text-subtle">{task.employee_name}</p> : null}
              {task.detail ? <p className="mt-0.5 line-clamp-2 text-[12px] leading-5 text-subtle/90">{task.detail}</p> : null}
            </div>
            {canManage ? (
              <Button size="sm" variant="secondary" disabled={resolvingId === task.task_id} onClick={() => void resolve(task)}>
                {resolvingId === task.task_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                Mark done
              </Button>
            ) : null}
          </div>
        ))}
        <LoadMoreBar loaded={tasks.length} total={total} loading={loadingMore} onLoadMore={() => void loadMore()} noun="task" />
      </CardContent>
    </Card>
  )
}

// Surfaces employee messages that failed to deliver but did NOT raise an HR task
// (typically standard/informational reminders like shift nudges). These would
// otherwise be invisible to HR. Reasons are plain-language and carry a suggested
// next action; raw provider/error strings are never shown. Renders nothing when
// there is nothing to surface, so a clean workspace stays clean.
function DeliveryIssuesCard({ access, onAccessIssue }: Pick<PostHireCommonProps, 'access' | 'onAccessIssue'>) {
  const loader = useCallback(() => getOutboundNeedsFollowUp(access, { limit: 50 }), [access])
  const { data, error } = useModuleData<OutboundNeedsFollowUpResponse>(loader, onAccessIssue)
  // Page 1 comes from useModuleData; extra pages accumulate here and reset
  // whenever the base page reloads — throttled/dashboard-only rows never get
  // "resolved" the way HR tasks do, so this list can realistically grow past
  // one page for an active company and must stay fully reachable.
  const [extraMessages, setExtraMessages] = useState<OutboundFollowUpMessage[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  useEffect(() => {
    setExtraMessages([])
  }, [data])

  // The endpoint can 403 on workspaces without a post-hire module / read access;
  // treat that as "nothing to surface" rather than showing an error.
  if (error || !data) return null
  const allMessages = [...(data.messages ?? []), ...extraMessages]
  const total = data.total ?? allMessages.length
  // Critical follow-ups already appear in the HR-tasks card above; only show the
  // delivery rows that have no task so HR isn't shown the same row twice.
  const rows = allMessages.filter((m) => !m.has_task)
  // Real delivery FAILURES stay in the amber "issues" card; intentional states
  // (reminders paused by the frequency cap, employees who opted out) render in a
  // separate calm/neutral section so they never look like scary errors.
  const issues = rows.filter((m) => (m.kind ?? 'issue') === 'issue')
  const infos = rows.filter((m) => (m.kind ?? 'issue') === 'info')
  if (issues.length === 0 && infos.length === 0 && allMessages.length >= total) return null

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await getOutboundNeedsFollowUp(access, { limit: 50, offset: allMessages.length })
      setExtraMessages((prev) => [...prev, ...(res.messages ?? [])])
    } catch {
      // Silent: this is a background "load more" for a secondary card; a
      // failed page fetch just leaves the button available to retry.
    } finally {
      setLoadingMore(false)
    }
  }

  const fmtWhen = (iso: string) => {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  return (
    <>
      {issues.length > 0 ? (
        <Card className="mb-5 border-amber-200/70 bg-[#fffaf0]">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-[#8a5a16]" />
              <CardTitle className="text-[15px]">Delivery issues</CardTitle>
              <Badge tone="warning" className="ml-1">
                {issues.length}
              </Badge>
            </div>
            <CardDescription>
              Wathefni could not reach these employees through the currently enabled channels. Add an email, invite the employee to the app, or contact them directly.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {issues.map((m) => (
              <div key={m.message_id} className="rounded-xl border border-amber-200/60 bg-white/70 px-3.5 py-2.5">
                <div className="flex items-center gap-2">
                  <Badge tone="default" className="shrink-0">{m.flow_label}</Badge>
                  <p className="truncate text-[13.5px] font-medium text-text">{m.employee_name || 'Employee'}</p>
                  {m.last_attempt_at ? <span className="ml-auto shrink-0 text-[11.5px] text-subtle/80">{fmtWhen(m.last_attempt_at)}</span> : null}
                </div>
                <p className="mt-1 text-[12.5px] leading-5 text-subtle/90">{m.reason}</p>
                <p className="mt-0.5 text-[12.5px] leading-5 text-[#8a5a16]">{m.suggested_action}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {infos.length > 0 ? (
        <Card className="mb-5 border-border/70 bg-surface">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-subtle" />
              <CardTitle className="text-[15px]">Reminder activity</CardTitle>
              <Badge tone="muted" className="ml-1">
                {infos.length}
              </Badge>
            </div>
            <CardDescription>
              Nothing to fix here — Wathefni intentionally stayed quiet to avoid over-messaging employees.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {infos.map((m) => (
              <div key={m.message_id} className="rounded-xl border border-border/60 bg-white/60 px-3.5 py-2.5">
                <div className="flex items-center gap-2">
                  <Badge tone="muted" className="shrink-0">{m.flow_label}</Badge>
                  <p className="truncate text-[13.5px] font-medium text-text">{m.employee_name || 'Employee'}</p>
                  {m.last_attempt_at ? <span className="ml-auto shrink-0 text-[11.5px] text-subtle/80">{fmtWhen(m.last_attempt_at)}</span> : null}
                </div>
                <p className="mt-1 text-[12.5px] leading-5 text-subtle/90">{m.reason}</p>
                <p className="mt-0.5 text-[12.5px] leading-5 text-subtle/75">{m.suggested_action}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {allMessages.length < total ? (
        <div className="mb-5 rounded-2xl border border-line/50 bg-panel/70">
          <LoadMoreBar loaded={allMessages.length} total={total} loading={loadingMore} onLoadMore={() => void loadMore()} noun="message" />
        </div>
      ) : null}
    </>
  )
}

// Full delivery monitoring view (follow-up tasks + delivery issues + reminder
// activity). Rendered only on the Alerts & Delivery page so
// post-hire module pages stay focused on their own content.
export function PostHireDeliveryCenter({ access, permissions, role, onNotice, onAccessIssue }: PostHireCommonProps) {
  return (
    <>
      <DeliveryFollowUpCard access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
      <DeliveryIssuesCard access={access} onAccessIssue={onAccessIssue} />
    </>
  )
}

// Compact one-line indicator shown on post-hire module pages. Summarises how
// many employee messages need another channel and links to Alerts & Delivery
// (page id: notifications), without pushing the module's own content down.
// Renders nothing when delivery is clean.
function DeliveryStatusStrip({ access, onAccessIssue, onOpenNotifications }: Pick<PostHireProps, 'access' | 'onAccessIssue' | 'onOpenNotifications'>) {
  const tasksLoader = useCallback(() => getHrTasks(access, 'open'), [access])
  const followUpLoader = useCallback(() => getOutboundNeedsFollowUp(access), [access])
  const { data: tasksData, error: tasksError, loading: tasksLoading } = useModuleData<HrTasksResponse>(tasksLoader, onAccessIssue)
  const { data: followUpData, error: followUpError, loading: followUpLoading } = useModuleData<OutboundNeedsFollowUpResponse>(followUpLoader, onAccessIssue)

  // Wait until both queries settle before mounting — avoids a late strip inserting
  // above content when delivery is dirty (clean workspaces stay null→null).
  if (tasksLoading || followUpLoading) return null

  // Either endpoint can 403 on workspaces without post-hire read access; treat
  // that as "nothing to surface" rather than an error.
  const tasks: HrTask[] = tasksError ? [] : tasksData?.tasks ?? []
  const issues = followUpError
    ? []
    : (followUpData?.messages ?? []).filter((m) => !m.has_task && (m.kind ?? 'issue') === 'issue')
  // Use the true company-wide open-task count for the HR-tasks half of this
  // number (never a page length); the needs-follow-up half doesn't have an
  // equally precise "issues only, excluding tasked ones" count from the
  // server, so it stays a same-page estimate — this banner only teases the
  // full picture, which lives (accurately, with pagination) on the
  // Notifications page.
  const openTaskCount = tasksError ? 0 : tasksData?.open_count ?? tasks.length
  const total = openTaskCount + issues.length
  if (total === 0) return null

  const names = [...tasks.map((t) => t.employee_name), ...issues.map((m) => m.employee_name)]
    .map((n) => String(n || '').trim())
    .filter(Boolean)
  const uniqueNames = [...new Set(names)]
  const preview = uniqueNames.slice(0, 2).join(', ')
  const remaining = uniqueNames.length - Math.min(uniqueNames.length, 2)

  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-amber-200/70 bg-[#fffaf0] px-3.5 py-2.5">
      <AlertTriangle className="h-4 w-4 shrink-0 text-[#8a5a16]" />
      <p className="min-w-0 flex-1 truncate text-[13px] text-text">
        <span className="font-medium">{total} employee message{total === 1 ? '' : 's'} need{total === 1 ? 's' : ''} another channel.</span>
        {preview ? (
          <span className="text-subtle"> Latest: {preview}{remaining > 0 ? ` +${remaining} more` : ''}</span>
        ) : null}
      </p>
      {onOpenNotifications ? (
        <Button size="sm" variant="secondary" className="shrink-0" onClick={onOpenNotifications}>
          Open Alerts & Delivery
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      ) : null}
    </div>
  )
}

export function PostHirePage({ page, access, permissions, role, onNotice, onAccessIssue, onOpenNotifications, onNavigate }: PostHireProps) {
  return (
    <>
      {page === 'employees' || page === 'inbox' || page === 'onboarding' || page === 'shifts' || page === 'payroll' || page === 'analytics' || page === 'compliance' ? null : (
        <DeliveryStatusStrip access={access} onAccessIssue={onAccessIssue} onOpenNotifications={onOpenNotifications} />
      )}
      <PostHireModuleBody
        page={page}
        access={access}
        permissions={permissions}
        role={role}
        onNotice={onNotice}
        onAccessIssue={onAccessIssue}
        onNavigate={onNavigate}
      />
    </>
  )
}

function PostHireModuleBody({ page, access, permissions, role, onNotice, onAccessIssue, onNavigate }: PostHireProps) {
  switch (page) {
    case 'employees':
      return <EmployeesPage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
    case 'workforce':
      return (
        <WorkforcePage
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
          onNavigate={onNavigate}
        />
      )
    case 'inbox':
      return <ActionInboxPage access={access} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
    case 'onboarding':
      return <OnboardingPage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
    case 'attendance':
      return <AttendancePage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
    case 'leave':
      return <LeavePage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
    case 'shifts':
      return <ShiftsPage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
    case 'payroll':
      return <PayrollPage access={access} permissions={permissions} role={role} onNotice={onNotice} onAccessIssue={onAccessIssue} />
    case 'analytics':
      return <AnalyticsPage access={access} onAccessIssue={onAccessIssue} onNavigate={onNavigate} />
    case 'compliance':
      return (
        <CompliancePage
          access={access}
          permissions={permissions}
          role={role}
          onNotice={onNotice}
          onAccessIssue={onAccessIssue}
          onNavigate={onNavigate}
        />
      )
    default:
      return null
  }
}
