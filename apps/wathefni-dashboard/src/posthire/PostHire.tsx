import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Clock,
  DollarSign,
  Download,
  Eye,
  FileText,
  Loader2,
  RefreshCw,
  Repeat,
  Search,
  ShieldCheck,
  Upload,
  UserRound,
} from 'lucide-react'
import { type ChangeEvent, Fragment, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/field'
import { useConfirm, type ConfirmOptions } from '@/components/ConfirmDialog'
import {
  DashboardApiError,
  getHrTasks,
  getPosthireAnalytics,
  getPosthireAttendance,
  getEmployeeProfile,
  getPosthireCompliance,
  getPosthireEmployees,
  getOnboardingDetail,
  getPosthireLeave,
  getPosthireOnboarding,
  getPosthirePayroll,
  getPosthireShifts,
  openEmployeeDocument,
  resolveHrTask,
  runPosthireAction,
  uploadEmployeeDocument,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  ComplianceBucket,
  DashboardAccess,
  HrTask,
  HrTasksResponse,
  PosthireAnalyticsResponse,
  PosthireAttendanceResponse,
  PosthireAttendanceRow,
  EmployeeProfileResponse,
  EmployeeProfileNextAction,
  EmployeeProfileNextActionsSummary,
  NextActionSeverity,
  PosthireComplianceResponse,
  PosthireEmployeesResponse,
  PosthireEmployee,
  PosthireLeaveResponse,
  PosthireLeaveRow,
  OnboardingDetailResponse,
  OnboardingItem,
  PosthireOnboardingResponse,
  PosthirePayrollPolicy,
  PosthirePayrollResponse,
  PosthireShiftsResponse,
} from '@/types'

export type PostHireModulePage =
  | 'employees'
  | 'onboarding'
  | 'attendance'
  | 'leave'
  | 'shifts'
  | 'payroll'
  | 'analytics'
  | 'compliance'

type PostHireProps = {
  page: PostHireModulePage
  access: DashboardAccess
  permissions: string[]
  onNotice: (message: string) => void
}

// --- helpers ---------------------------------------------------------------

function can(permissions: string[], permission: string): boolean {
  if (!permissions.length) return true
  return permissions.includes(permission)
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

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const raw = String(value)
  const match = /(\d{1,2}):(\d{2})/.exec(raw)
  if (match) {
    const date = new Date()
    date.setHours(Number(match[1]), Number(match[2]), 0, 0)
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }
  const date = new Date(raw)
  if (!Number.isNaN(date.getTime())) return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return raw
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

function EmptyState({ icon, title, hint, points }: { icon: ReactNode; title: string; hint?: string; points?: string[] }) {
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
  busy,
  destructive,
  onConfirm,
  onCancel,
}: {
  text: string
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
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">Please confirm</p>
            <p className="text-[13px] leading-6 text-subtle/95">{text}</p>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={onConfirm} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Confirm
          </Button>
        </div>
      </div>
    </div>
  )
}

// --- data + action hooks ---------------------------------------------------

function useModuleData<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      setData(await loader())
    } catch (err) {
      setError(friendlyError(err, 'We couldn’t load this section right now.'))
    } finally {
      setRefreshing(false)
    }
  }, [loader])

  useEffect(() => {
    void reload()
  }, [reload])

  // `loading` is the first-load skeleton only (no data yet). Background
  // refreshes keep the current data on screen so a single action never blanks
  // the whole page.
  const loading = refreshing && data === null
  return { data, loading, refreshing, error, reload }
}

type PendingConfirmation = { text: string; actionType: string; args: Record<string, unknown>; destructive: boolean }

function usePosthireAction(access: DashboardAccess, reload: () => Promise<void>, onNotice: (message: string) => void) {
  const askConfirm = useConfirm()
  const [pending, setPending] = useState<PendingConfirmation | null>(null)
  const [busy, setBusy] = useState(false)
  const [runningKey, setRunningKey] = useState<string | null>(null)

  const execute = useCallback(
    async (actionType: string, args: Record<string, unknown>, destructive: boolean, key: string) => {
      setBusy(true)
      setRunningKey(key)
      try {
        const result = await runPosthireAction(access, { action_type: actionType, args })
        if (result.confirmation) {
          setPending({
            text: result.confirmation.text,
            actionType: result.confirmation.action_type,
            args: result.confirmation.args,
            destructive,
          })
          return
        }
        setPending(null)
        onNotice(result.message || 'Done.')
        await reload()
      } catch (err) {
        setPending(null)
        onNotice(friendlyError(err, 'We could not complete that action.'))
      } finally {
        setBusy(false)
        setRunningKey(null)
      }
    },
    [access, reload, onNotice],
  )

  const run = useCallback(
    (
      actionType: string,
      args: Record<string, unknown> = {},
      options: { destructive?: boolean; key?: string; confirm?: ConfirmOptions } = {},
    ) => {
      const go = () => execute(actionType, args, Boolean(options.destructive), options.key || actionType)
      // When a call site supplies confirm copy, ask first (reusing the global
      // confirm system). Otherwise run immediately — the backend can still raise
      // its own confirmation step for actions that need one.
      if (options.confirm) {
        const copy = options.confirm
        void (async () => {
          if (await askConfirm(copy)) void go()
        })()
        return
      }
      void go()
    },
    [execute, askConfirm],
  )

  const confirm = useCallback(() => {
    if (!pending) return
    void execute(pending.actionType, pending.args, pending.destructive, `${pending.actionType}:confirm`)
  }, [pending, execute])

  const dialog = pending ? (
    <ConfirmDialog text={pending.text} busy={busy} destructive={pending.destructive} onConfirm={confirm} onCancel={() => setPending(null)} />
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

function EmployeesPage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (message: string) => void }) {
  const loader = useCallback(() => getPosthireEmployees(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireEmployeesResponse>(loader)
  const [query, setQuery] = useState('')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  if (selectedKey) {
    return <EmployeeProfile access={access} permissions={permissions} employeeKey={selectedKey} onBack={() => setSelectedKey(null)} onNotice={onNotice} />
  }

  const employees = data?.employees ?? []
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return employees
    return employees.filter((e) =>
      [e.name, e.position_title, e.department, e.phone, e.email].filter(Boolean).some((v) => String(v).toLowerCase().includes(term)),
    )
  }, [employees, query])

  const onboarding = employees.filter((e) => !['complete', 'completed', 'done'].includes(e.onboarding_status)).length
  const departments = new Set(employees.map((e) => e.department).filter(Boolean)).size

  return (
    <div className="space-y-6">
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : employees.length === 0 ? (
        <EmptyState
          icon={<UserRound className="h-5 w-5" />}
          title="No employees yet"
          hint="Your directory builds itself as you hire. Here’s how people arrive:"
          points={[
            'Hire candidates from Pre-Hiring — they become employees automatically',
            'Onboarding starts the moment someone is hired',
            'Attendance, shifts, leave, and payroll all flow from this directory',
          ]}
        />
      ) : (
        <>
          <NextAction
            tone={onboarding ? 'warning' : 'success'}
            icon={onboarding ? <UserRound className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
            title={
              onboarding
                ? `${onboarding} new hire${onboarding === 1 ? '' : 's'} still onboarding`
                : 'Your team directory is up to date'
            }
            detail={
              onboarding
                ? 'Open Onboarding to send reminders and clear open documents.'
                : `${employees.length} employee${employees.length === 1 ? '' : 's'} across ${departments} department${departments === 1 ? '' : 's'}`
            }
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard label="Total employees" value={employees.length} />
            <StatCard label="Onboarding in progress" value={onboarding} hint={onboarding ? 'Needs follow-up' : 'All set'} />
            <StatCard label="Departments" value={departments} />
          </div>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
              <div>
                <CardTitle>Directory</CardTitle>
                <CardDescription>{filtered.length} of {employees.length} employees</CardDescription>
              </div>
              <div className="relative w-full max-w-xs">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle/70" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search name, role, department…"
                  className="h-10 w-full rounded-full border border-line/60 bg-white/70 pl-9 pr-3 text-[13px] text-text outline-none transition focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                />
              </div>
            </CardHeader>
            <CardContent>
              {filtered.length === 0 ? (
                <EmptyState icon={<Search className="h-5 w-5" />} title="No employees match your search" hint="Try a different name, role, or department." />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[640px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Department</th>
                        <th className="px-4 py-3 font-medium">Contact</th>
                        <th className="px-4 py-3 font-medium">Onboarding</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {filtered.map((emp) => (
                        <tr
                          key={emp.employee_key || emp.phone || emp.name}
                          className={cn('hover:bg-white/45', emp.employee_key ? 'cursor-pointer' : '')}
                          onClick={emp.employee_key ? () => setSelectedKey(emp.employee_key) : undefined}
                        >
                          <td className="px-4 py-3">
                            <p className="font-semibold text-text">{emp.name}</p>
                            <p className="text-[12px] text-subtle/85">{emp.position_title || '—'}</p>
                          </td>
                          <td className="px-4 py-3 text-subtle/90">{emp.department || '—'}</td>
                          <td className="px-4 py-3 text-subtle/90">
                            <p>{emp.phone || '—'}</p>
                            {emp.email ? <p className="text-[12px] text-subtle/75">{emp.email}</p> : null}
                          </td>
                          <td className="px-4 py-3">
                            <StatusBadge status={emp.onboarding_status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
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

function EmployeeProfile({ access, permissions, employeeKey, onBack, onNotice }: { access: DashboardAccess; permissions: string[]; employeeKey: string; onBack: () => void; onNotice: (message: string) => void }) {
  const loader = useCallback(() => getEmployeeProfile(access, employeeKey), [access, employeeKey])
  const { data, loading, refreshing, error, reload } = useModuleData<EmployeeProfileResponse>(loader)
  const action = usePosthireAction(access, reload, onNotice)
  const confirm = useConfirm()
  const canUpload = can(permissions, 'onboarding.manage') && Boolean(data?.doc_upload_enabled)
  // Same gates the module pages use, so behaviour matches wherever HR acts from.
  const canOnboardingManage = can(permissions, 'onboarding.manage')
  const canOnboardingMutate = canOnboardingManage && Boolean(data?.hr_mutate_enabled)
  const canComplianceManage = can(permissions, 'compliance.manage')
  const canLeaveDecide = can(permissions, 'leave.decide')
  const canPayrollManage = can(permissions, 'payroll.manage')

  const emp = data?.employee
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
      if (a.module === 'onboarding') return canOnboardingManage
      return false
    },
    [canComplianceManage, canOnboardingManage],
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
          <Card>
            <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-[20px] font-semibold text-text">{emp.name}</h2>
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
              <StatusBadge status={emp.onboarding_status} />
            </CardContent>
          </Card>

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

          <div className="grid gap-4 lg:grid-cols-2">
            {sections?.onboarding ? (
              <Card id="emp360-section-onboarding">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><ClipboardList className="h-4 w-4" /> Onboarding</CardTitle>
                  <CardDescription>
                    {sections.onboarding.outstanding_count} outstanding · {sections.onboarding.complete_count} complete
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {sections.onboarding.outstanding.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">All required documents are in.</p>
                  ) : (
                    <ul className="space-y-1.5 text-[13px]">
                      {sections.onboarding.outstanding.map((it, idx) => (
                        <li key={it.item_id || idx} className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-text">{it.label}</span>
                          <span className="flex items-center gap-1.5">
                            <StatusBadge status={it.status} />
                            {canOnboardingMutate && it.item_id ? (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={action.busy}
                                  onClick={() => action.run('onboarding_mark_item', { employee_key: employeeKey, item_id: it.item_id, item_status: 'received' }, { key: `mark:received:${it.item_id}` })}
                                >
                                  {action.runningKey === `mark:received:${it.item_id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Mark received'}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={action.busy}
                                  onClick={() => action.run('onboarding_mark_item', { employee_key: employeeKey, item_id: it.item_id, item_status: 'waived' }, { destructive: true, key: `mark:waived:${it.item_id}`, confirm: { title: 'Waive this item?', body: `“${it.label}” will no longer be required for ${emp.name}'s onboarding. You can mark it received later if needed.`, confirmLabel: 'Waive item' } })}
                                >
                                  {action.runningKey === `mark:waived:${it.item_id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Waive'}
                                </Button>
                              </>
                            ) : null}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {canOnboardingManage && sections.onboarding.outstanding_count > 0 ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={action.busy}
                      onClick={async () => {
                        if (!(await confirm({ title: 'Send onboarding reminder?', body: `${emp.name} will receive an onboarding reminder message now.`, confirmLabel: 'Send reminder' }))) return
                        await action.run('send_onboarding_reminder', employeeRef(emp), { key: 'profile-onboarding-reminder' })
                      }}
                    >
                      {action.runningKey === 'profile-onboarding-reminder' ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" /> Sending…
                        </>
                      ) : (
                        'Send reminder'
                      )}
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {sections?.compliance ? (
              <Card id="emp360-section-compliance">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Compliance</CardTitle>
                  <CardDescription>
                    {sections.compliance.needs_attention
                      ? `${sections.compliance.needs_attention} need attention`
                      : 'All documents up to date'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {sections.compliance.documents.length === 0 ? (
                    <p className="text-[13px] text-subtle/85">No documents are expired, expiring, or missing.</p>
                  ) : (
                    <ul className="space-y-2 text-[13px]">
                      {sections.compliance.documents.map((doc, idx) => {
                        const remindKey = `profile-remind:${doc.document_type || idx}`
                        const reviewKey = `profile-review:${doc.document_type || idx}`
                        const args = { employee_name: emp.name, document_type: doc.document_type }
                        return (
                          <li key={doc.document_type || idx} className="flex flex-wrap items-center justify-between gap-2">
                            <span className="min-w-0">
                              <span className="block text-text">{doc.document_label}</span>
                              <span className="block text-[11.5px] text-subtle/80">
                                {doc.expiry_date ? `Expires ${formatDate(doc.expiry_date)} · ${complianceDaysLabel(doc)}` : 'No expiry on file'}
                                {` · Reminded: ${complianceReminderLabel(doc)}`}
                              </span>
                            </span>
                            <span className="flex items-center gap-1.5">
                              <Badge tone={doc.tone}>{doc.status_label}</Badge>
                              {canComplianceManage && doc.status === 'needs_review' ? (
                                <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => action.run('compliance_mark_reviewed', args, { key: reviewKey })}>
                                  {action.runningKey === reviewKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Mark reviewed'}
                                </Button>
                              ) : null}
                              {canComplianceManage ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={action.busy}
                                  onClick={async () => {
                                    if (!(await confirm({ title: 'Send document reminder?', body: `${emp.name} will receive a reminder about their ${doc.document_label}.`, confirmLabel: 'Send reminder' }))) return
                                    await action.run('compliance_send_reminder', args, { key: remindKey })
                                  }}
                                >
                                  {action.runningKey === remindKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send reminder'}
                                </Button>
                              ) : null}
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {sections?.attendance ? (
              <Card id="emp360-section-attendance">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Clock className="h-4 w-4" /> Attendance</CardTitle>
                  <CardDescription>Last {sections.attendance.window_days} days</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
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
                </CardContent>
              </Card>
            ) : null}

            {sections?.leave ? (
              <Card id="emp360-section-leave">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><CalendarDays className="h-4 w-4" /> Leave</CardTitle>
                  <CardDescription>
                    {sections.leave.pending_count ? `${sections.leave.pending_count} awaiting decision` : 'No pending requests'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
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
                      {sections.leave.items.map((it, idx) => {
                        const leaveArgs = { employee_name: emp.name, employee_phone: emp.phone, start_date: it.start_date, end_date: it.end_date }
                        const approveKey = `profile-approve-leave:${idx}`
                        const rejectKey = `profile-reject-leave:${idx}`
                        return (
                          <li key={idx} className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-text">{titleCase(it.leave_type || 'leave')} · {formatDate(it.start_date)}–{formatDate(it.end_date)}</span>
                            {it.status === 'requested' && canLeaveDecide ? (
                              <span className="flex items-center gap-1.5">
                                <StatusBadge status={it.status} />
                                <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => action.run('reject_leave_request', leaveArgs, { destructive: true, key: rejectKey, confirm: { title: 'Decline this leave request?', body: `${emp.name}'s ${(it.leave_type || 'leave').replace('_', ' ')} request for ${formatDate(it.start_date)}–${formatDate(it.end_date)} will be declined and they'll be notified.`, confirmLabel: 'Decline request' } })}>
                                  {action.runningKey === rejectKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Decline'}
                                </Button>
                                <Button size="sm" disabled={action.busy} onClick={() => action.run('approve_leave_request', leaveArgs, { key: approveKey })}>
                                  {action.runningKey === approveKey ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Approve'}
                                </Button>
                              </span>
                            ) : (
                              <StatusBadge status={it.status} />
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {sections?.shifts ? (
              <Card id="emp360-section-shifts">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><CalendarClock className="h-4 w-4" /> Upcoming shifts</CardTitle>
                  <CardDescription>{sections.shifts.upcoming_count} scheduled</CardDescription>
                </CardHeader>
                <CardContent>
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
                </CardContent>
              </Card>
            ) : null}

            {sections?.payroll ? (
              <Card id="emp360-section-payroll">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><DollarSign className="h-4 w-4" /> Payroll</CardTitle>
                  <CardDescription>Recent timesheets</CardDescription>
                </CardHeader>
                <CardContent>
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
                </CardContent>
              </Card>
            ) : null}

            {sections?.documents && sections.documents.items.length > 0 ? (
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4" /> Documents</CardTitle>
                  <CardDescription>
                    {sections.documents.count} file{sections.documents.count === 1 ? '' : 's'} submitted
                    {sections.onboarding && sections.onboarding.outstanding_count > 0
                      ? ` · ${sections.onboarding.outstanding_count} required document${sections.onboarding.outstanding_count === 1 ? '' : 's'} still missing`
                      : ' · nothing missing'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
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
                              hasFile={Boolean(doc.has_file)}
                              onUploaded={(message) => { onNotice(message); void reload() }}
                              onError={onNotice}
                            />
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
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

function DocumentUploadButton({
  access,
  employeeKey,
  itemId,
  hasFile,
  onUploaded,
  onError,
}: {
  access: DashboardAccess
  employeeKey: string
  itemId: string
  hasFile: boolean
  onUploaded: (message: string) => void
  onError: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const inputId = `doc-upload-${employeeKey}-${itemId}`
  const onPick = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // allow re-picking the same file
    if (!file) return
    setBusy(true)
    try {
      await uploadEmployeeDocument(access, employeeKey, { file, itemId })
      onUploaded(hasFile ? 'Document replaced.' : 'Document uploaded.')
    } catch (err) {
      onError(friendlyError(err, 'We could not upload that document.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <input id={inputId} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.heic" onChange={onPick} disabled={busy} />
      <Button variant="ghost" size="sm" disabled={busy} onClick={() => document.getElementById(inputId)?.click()} title={hasFile ? 'Replace document' : 'Upload document'}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        <span className="ml-1.5">{hasFile ? 'Replace' : 'Upload'}</span>
      </Button>
    </>
  )
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
  busy,
  runningKey,
  onMark,
}: {
  access: DashboardAccess
  item: OnboardingItem
  fileId?: string | null
  canMutate: boolean
  canUpload?: boolean
  employeeKey?: string
  onUploaded?: (message: string) => void
  onError?: (message: string) => void
  busy: boolean
  runningKey: string | null
  onMark: (item: OnboardingItem, status: 'received' | 'waived') => void
  done?: boolean
}) {
  const key = item.item_id || item.document_type || item.label || ''
  const reminded = Number(item.reminder_count || 0)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[0.9rem] border border-line/45 bg-panel/55 px-3.5 py-2.5">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-text">
          {item.label || (item.document_type ? titleCase(item.document_type) : item.item_id)}
          {item.required ? null : <span className="ml-1.5 text-[11px] font-normal text-subtle/70">(optional)</span>}
        </p>
        <p className="mt-0.5 text-[11.5px] text-subtle/80">
          {reminded > 0 ? `${reminded} reminder${reminded === 1 ? '' : 's'} sent` : 'No reminders sent'}
          {item.last_reminded_at ? ` · last ${formatDate(item.last_reminded_at)}` : ''}
          {item.escalated_at ? ' · escalated' : ''}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={item.status} />
        <DocumentActions access={access} fileId={fileId} filename={item.label || item.document_type || undefined} compact />
        {canUpload && employeeKey && item.item_id && onUploaded && onError ? (
          <DocumentUploadButton
            access={access}
            employeeKey={employeeKey}
            itemId={item.item_id}
            hasFile={Boolean(fileId)}
            onUploaded={onUploaded}
            onError={onError}
          />
        ) : null}
        {canMutate ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => onMark(item, 'received')}
            >
              {runningKey === `mark:received:${key}` ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Mark received'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => onMark(item, 'waived')}
            >
              {runningKey === `mark:waived:${key}` ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Waive'}
            </Button>
          </>
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
}) {
  if (loading && !detail) {
    return <div className="px-4 py-3 text-[12.5px] text-subtle/80">Loading checklist…</div>
  }
  if (error && !detail) {
    return (
      <div className="flex flex-wrap items-center gap-3 border-t border-line/45 bg-panel-muted/30 px-4 py-3 text-[12.5px] text-subtle/80">
        <span>We couldn’t load this checklist. Please try again.</span>
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button>
        ) : null}
      </div>
    )
  }
  if (!detail) return null
  const pending = detail.pending ?? []
  const received = detail.received ?? []
  const documentIndex = detail.document_index ?? {}
  const canUpload = canMutate && Boolean(detail.doc_upload_enabled)
  const employeeKey = detail.employee_key
  const fileIdFor = (item: OnboardingItem) =>
    documentIndex[item.item_id || ''] || documentIndex[item.document_type || ''] || null
  return (
    <div className="space-y-4 border-t border-line/45 bg-panel-muted/30 px-4 py-4">
      {pending.length === 0 && received.length === 0 ? (
        <p className="text-[12.5px] text-subtle/80">No checklist items recorded for this employee yet.</p>
      ) : null}
      {pending.length ? (
        <div className="space-y-2">
          <p className="text-[11.5px] font-semibold uppercase tracking-[0.07em] text-subtle/80">Outstanding ({pending.length})</p>
          {pending.map((item) => (
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
              busy={busy}
              runningKey={runningKey}
              onMark={onMark}
            />
          ))}
        </div>
      ) : null}
      {received.length ? (
        <div className="space-y-2">
          <p className="text-[11.5px] font-semibold uppercase tracking-[0.07em] text-subtle/80">Received ({received.length})</p>
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
              busy={busy}
              runningKey={runningKey}
              onMark={onMark}
              done
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function OnboardingPage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getPosthireOnboarding(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireOnboardingResponse>(loader)
  const confirm = useConfirm()
  const canManage = can(permissions, 'onboarding.manage')

  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<OnboardingDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)

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

  // After any mutation, refresh both the list (progress counts) and the open panel.
  const reloadAll = useCallback(async () => {
    await reload()
    if (expanded) await loadDetail(expanded)
  }, [reload, expanded, loadDetail])

  const action = usePosthireAction(access, reloadAll, onNotice)

  const inProgress = data?.in_progress ?? []
  const hrMutate = Boolean(data?.hr_mutate_enabled)
  const canMutate = canManage && hrMutate

  const toggleExpand = useCallback(
    (key: string) => {
      if (expanded === key) {
        setExpanded(null)
        setDetail(null)
        setDetailError(false)
        return
      }
      setExpanded(key)
      setDetail(null)
      setDetailError(false)
      void loadDetail(key)
    },
    [expanded, loadDetail],
  )

  const markItem = useCallback(
    (emp: PosthireEmployee, item: OnboardingItem, status: 'received' | 'waived') => {
      const key = item.item_id || item.document_type || item.label || ''
      action.run(
        'onboarding_mark_item',
        { employee_key: emp.employee_key, item_id: item.item_id, item_status: status },
        {
          destructive: status === 'waived',
          key: `mark:${status}:${key}`,
          confirm:
            status === 'waived'
              ? {
                  title: 'Waive this item?',
                  body: `“${item.label}” will no longer be required for ${emp.name || 'this employee'}'s onboarding. You can mark it received later if needed.`,
                  confirmLabel: 'Waive item',
                }
              : undefined,
        },
      )
    },
    [action],
  )

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <NextAction
            tone={inProgress.length ? 'warning' : 'success'}
            icon={inProgress.length ? <ClipboardList className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
            title={inProgress.length ? `${inProgress.length} new hire${inProgress.length === 1 ? '' : 's'} still onboarding` : 'Everyone is fully onboarded'}
            detail={inProgress.length ? 'Open a new hire to see their checklist, send a reminder, or resolve items.' : `${data?.completed_count ?? 0} completed of ${data?.total ?? 0}`}
          />
          <Card>
            <CardHeader>
              <CardTitle>In progress</CardTitle>
              <CardDescription>New hires who have not completed onboarding yet.</CardDescription>
            </CardHeader>
            <CardContent>
              {inProgress.length === 0 ? (
                <EmptyState icon={<CheckCircle2 className="h-5 w-5" />} title="Nothing pending" hint="New hires will appear here while they finish onboarding." />
              ) : (
                <div className="space-y-2.5">
                  {inProgress.map((emp) => {
                    const isOpen = expanded === emp.employee_key
                    const pendingCount = Number(emp.pending_count || 0)
                    const receivedCount = Number(emp.received_count || 0)
                    const total = pendingCount + receivedCount
                    return (
                      <div key={emp.employee_key || emp.phone || emp.name} className="overflow-hidden rounded-[1.1rem] border border-line/50 bg-panel/70">
                        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                          <button type="button" onClick={() => toggleExpand(emp.employee_key)} className="min-w-0 flex-1 text-left">
                            <p className="font-semibold text-text">{emp.name}</p>
                            <p className="text-[12px] text-subtle/85">
                              {emp.position_title || 'Team member'}{emp.department ? ` · ${emp.department}` : ''}
                              {total > 0 ? ` · ${receivedCount}/${total} documents` : ''}
                            </p>
                          </button>
                          <div className="flex items-center gap-2.5">
                            <StatusBadge status={emp.onboarding_status} />
                            {canMutate ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={action.busy}
                                onClick={() =>
                                  action.run(
                                    'start_onboarding',
                                    { employee_key: emp.employee_key },
                                    { key: `start:${emp.employee_key}` },
                                  )
                                }
                              >
                                {action.runningKey === `start:${emp.employee_key}` ? (
                                  <>
                                    <Loader2 className="h-4 w-4 animate-spin" /> Working…
                                  </>
                                ) : emp.onboarding_status === 'not_started' ? (
                                  'Start'
                                ) : (
                                  'Restart'
                                )}
                              </Button>
                            ) : null}
                            {canManage ? (
                              <Button
                                variant="secondary"
                                size="sm"
                                disabled={action.busy}
                                onClick={async () => {
                                  if (!(await confirm({ title: 'Send onboarding reminder?', body: `${emp.name} will receive an onboarding reminder message now.`, confirmLabel: 'Send reminder' }))) return
                                  await action.run('send_onboarding_reminder', employeeRef(emp), { key: `reminder:${emp.employee_key}` })
                                }}
                              >
                                {action.runningKey === `reminder:${emp.employee_key}` ? (
                                  <>
                                    <Loader2 className="h-4 w-4 animate-spin" /> Sending…
                                  </>
                                ) : (
                                  'Send reminder'
                                )}
                              </Button>
                            ) : null}
                            <Button variant="ghost" size="sm" onClick={() => toggleExpand(emp.employee_key)}>
                              {isOpen ? 'Hide' : 'Checklist'}
                            </Button>
                          </div>
                        </div>
                        {isOpen ? (
                          <OnboardingDetailPanel
                            access={access}
                            detail={detail}
                            loading={detailLoading}
                            error={detailError}
                            onRetry={() => { if (emp.employee_key) void loadDetail(emp.employee_key) }}
                            canMutate={canMutate}
                            busy={action.busy}
                            runningKey={action.runningKey}
                            onMark={(item, status) => markItem(emp, item, status)}
                            onUploaded={(message) => { onNotice(message); void reloadAll() }}
                            onError={onNotice}
                          />
                        ) : null}
                      </div>
                    )
                  })}
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

const ATTENDANCE_CORRECTION_STATUSES = ['present', 'late', 'absent', 'completed'] as const

function AttendanceCorrectionRow({
  row,
  busy,
  onSubmit,
  onCancel,
}: {
  row: PosthireAttendanceRow
  busy: boolean
  onSubmit: (values: { status: string; time: string; notes: string }) => void
  onCancel: () => void
}) {
  const [status, setStatus] = useState<string>(() => {
    const current = String(row.status || '').toLowerCase()
    return (ATTENDANCE_CORRECTION_STATUSES as readonly string[]).includes(current) ? current : 'present'
  })
  const [time, setTime] = useState('')
  const [notes, setNotes] = useState('')
  const timeRelevant = status !== 'absent'

  return (
    <tr className="bg-panel-muted/40">
      <td colSpan={4} className="px-4 py-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[12px] font-medium text-subtle/85">
            Status
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-10 w-36">
              <option value="present">Present</option>
              <option value="late">Late</option>
              <option value="completed">Completed</option>
              <option value="absent">Absent</option>
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] font-medium text-subtle/85">
            {status === 'completed' ? 'Check-out time' : 'Check-in time'}
            <Input
              type="time"
              value={time}
              disabled={!timeRelevant}
              onChange={(e) => setTime(e.target.value)}
              className="h-10 w-36"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-[12px] font-medium text-subtle/85" style={{ minWidth: 200 }}>
            Note (optional)
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason for correction" className="h-10" />
          </label>
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={busy} onClick={() => onSubmit({ status, time, notes })}>
              Save correction
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      </td>
    </tr>
  )
}

function AttendancePage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getPosthireAttendance(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireAttendanceResponse>(loader)
  const action = usePosthireAction(access, reload, onNotice)
  const canManage = can(permissions, 'attendance.manage')
  const [correcting, setCorrecting] = useState<string | null>(null)

  const rows = data?.attendance ?? []
  const late = rows.filter((r) => Number(r.late_minutes || 0) > 0 || String(r.status).toLowerCase() === 'late')
  const absent = rows.filter((r) => String(r.status).toLowerCase() === 'absent')
  const present = rows.filter((r) => ['present', 'completed'].includes(String(r.status).toLowerCase()))

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <NextAction
            tone={absent.length || late.length ? 'danger' : rows.length === 0 ? 'default' : 'success'}
            icon={<Clock className="h-5 w-5" />}
            title={
              absent.length || late.length
                ? `${absent.length} absent · ${late.length} late today`
                : rows.length === 0
                  ? 'No check-ins recorded yet today'
                  : 'Attendance looks clean today'
            }
            detail={
              absent.length || late.length
                ? 'Review the exceptions below and correct records if needed.'
                : rows.length === 0
                  ? 'Attendance appears here as employees check in against their shifts.'
                  : `${present.length} checked in`
            }
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard label="Checked in" value={present.length} />
            <StatCard label="Late" value={late.length} />
            <StatCard label="Absent" value={absent.length} />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Today · {formatDate(data?.date)}</CardTitle>
              <CardDescription>{rows.length} attendance record{rows.length === 1 ? '' : 's'}</CardDescription>
            </CardHeader>
            <CardContent>
              {rows.length === 0 ? (
                <EmptyState
                  icon={<CalendarCheckIcon />}
                  title="No check-ins recorded yet today"
                  hint="Attendance appears once employees check in against their shifts. If you haven't set up shifts yet, add them in Shifts so check-ins can be tracked."
                />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[560px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Check-in</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                        {canManage ? <th className="px-4 py-3 text-right font-medium">Action</th> : null}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {rows.map((row, idx) => {
                        const rowKey = row.attendance_id || `${row.employee_key}-${idx}`
                        const isEditing = correcting === rowKey
                        return (
                          <Fragment key={rowKey}>
                            <tr className="hover:bg-white/45">
                              <td className="px-4 py-3 font-semibold text-text">{row.employee_name || '—'}</td>
                              <td className="px-4 py-3 text-subtle/90">
                                {formatTime(row.check_in_at)}
                                {Number(row.late_minutes || 0) > 0 ? <span className="ml-1 text-[12px] text-rose-600">+{row.late_minutes}m</span> : null}
                              </td>
                              <td className="px-4 py-3">
                                <StatusBadge status={row.status} />
                              </td>
                              {canManage ? (
                                <td className="px-4 py-3 text-right">
                                  <div className="flex items-center justify-end gap-2">
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      disabled={action.busy}
                                      onClick={() => setCorrecting(isEditing ? null : rowKey)}
                                    >
                                      {isEditing ? 'Close' : 'Correct'}
                                    </Button>
                                    {String(row.status).toLowerCase() !== 'absent' ? (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        disabled={action.busy}
                                        onClick={() =>
                                          action.run(
                                            'mark_attendance_absent',
                                            { employee_name: row.employee_name, date: data?.date },
                                            {
                                              destructive: true,
                                              key: `absent:${rowKey}`,
                                              confirm: {
                                                title: 'Mark this employee absent?',
                                                body: `${row.employee_name || 'This employee'} will be marked absent for ${data?.date ? formatDate(data.date) : 'this day'}. You can correct it later if needed.`,
                                                confirmLabel: 'Mark absent',
                                              },
                                            },
                                          )
                                        }
                                      >
                                        {action.runningKey === `absent:${rowKey}` ? (
                                          <>
                                            <Loader2 className="h-4 w-4 animate-spin" /> Saving…
                                          </>
                                        ) : (
                                          'Mark absent'
                                        )}
                                      </Button>
                                    ) : null}
                                  </div>
                                </td>
                              ) : null}
                            </tr>
                            {canManage && isEditing ? (
                              <AttendanceCorrectionRow
                                row={row}
                                busy={action.busy}
                                onCancel={() => setCorrecting(null)}
                                onSubmit={({ status, time, notes }) => {
                                  action.run(
                                    'correct_attendance_record',
                                    {
                                      employee_name: row.employee_name,
                                      date: data?.date,
                                      status,
                                      time: time || undefined,
                                      notes: notes || undefined,
                                    },
                                    { destructive: true, key: `correct:${rowKey}` },
                                  )
                                  setCorrecting(null)
                                }}
                              />
                            ) : null}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function CalendarCheckIcon() {
  return <CalendarDays className="h-5 w-5" />
}

// --- Leave -----------------------------------------------------------------

function LeavePage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getPosthireLeave(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireLeaveResponse>(loader)
  const action = usePosthireAction(access, reload, onNotice)
  const canManage = can(permissions, 'leave.decide')

  const pending = data?.pending ?? []
  const upcoming = data?.upcoming ?? []
  const balancesEnabled = Boolean(data?.balances_enabled)

  const annualChip = (row: PosthireLeaveRow) => {
    if (!balancesEnabled || !row.employee_key) return null
    const annual = (data?.balances?.[row.employee_key] ?? []).find((b) => b.leave_type === 'annual')
    if (!annual) return null
    const remaining = Math.round(annual.current_balance * 10) / 10
    const entitlement = Math.round(annual.entitlement_days * 10) / 10
    return (
      <span className="rounded-full border border-line/50 bg-panel/70 px-2 py-0.5 text-[11px] font-medium text-subtle/90">
        Annual: {remaining}/{entitlement} days left
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <NextAction
            tone={pending.length ? 'warning' : 'success'}
            icon={<CalendarClock className="h-5 w-5" />}
            title={pending.length ? `${pending.length} leave request${pending.length === 1 ? '' : 's'} awaiting your decision` : 'No leave requests waiting'}
            detail={pending.length ? 'Approve or decline below — each decision is confirmed before it applies.' : `${upcoming.length} upcoming approved leave`}
          />
          {balancesEnabled ? (
            <p className="rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-2.5 text-[12px] text-subtle/85">
              Leave balances shown are tracked from configurable policy presets and are <span className="font-medium text-text">not enforced</span> — they never block an approval. Figures require legal review before enforcement.
            </p>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>Pending requests</CardTitle>
              <CardDescription>Requests that need an approval decision.</CardDescription>
            </CardHeader>
            <CardContent>
              {pending.length === 0 ? (
                <EmptyState icon={<CheckCircle2 className="h-5 w-5" />} title="Nothing to approve" hint="New leave requests will show up here." />
              ) : (
                <div className="space-y-2.5">
                  {pending.map((row, idx) => (
                    <div key={row.leave_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] border border-line/50 bg-panel/70 px-4 py-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-text">{row.employee_name || 'Employee'}</p>
                          {annualChip(row)}
                        </div>
                        <p className="text-[12px] text-subtle/85">
                          {titleCase(row.leave_type || 'leave')} · {formatDate(row.start_date)} → {formatDate(row.end_date)}
                        </p>
                      </div>
                      {canManage ? (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={action.busy}
                            onClick={() =>
                              action.run(
                                'reject_leave_request',
                                { employee_name: row.employee_name, employee_phone: row.employee_phone, start_date: row.start_date, end_date: row.end_date },
                                {
                                  destructive: true,
                                  key: `reject-leave:${row.leave_id || idx}`,
                                  confirm: {
                                    title: 'Decline this leave request?',
                                    body: `${row.employee_name || 'This employee'}'s ${titleCase(row.leave_type || 'leave')} request for ${formatDate(row.start_date)} → ${formatDate(row.end_date)} will be declined and they'll be notified.`,
                                    confirmLabel: 'Decline request',
                                  },
                                },
                              )
                            }
                          >
                            {action.runningKey === `reject-leave:${row.leave_id || idx}` ? (
                              <>
                                <Loader2 className="h-4 w-4 animate-spin" /> Declining…
                              </>
                            ) : (
                              'Decline'
                            )}
                          </Button>
                          <Button
                            size="sm"
                            disabled={action.busy}
                            onClick={() =>
                              action.run(
                                'approve_leave_request',
                                { employee_name: row.employee_name, employee_phone: row.employee_phone, start_date: row.start_date, end_date: row.end_date },
                                { key: `approve-leave:${row.leave_id || idx}` },
                              )
                            }
                          >
                            {action.runningKey === `approve-leave:${row.leave_id || idx}` ? (
                              <>
                                <Loader2 className="h-4 w-4 animate-spin" /> Approving…
                              </>
                            ) : (
                              'Approve'
                            )}
                          </Button>
                        </div>
                      ) : (
                        <StatusBadge status={row.status} />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Upcoming leave</CardTitle>
              <CardDescription>Approved time off in the weeks ahead.</CardDescription>
            </CardHeader>
            <CardContent>
              {upcoming.length === 0 ? (
                <EmptyState icon={<CalendarDays className="h-5 w-5" />} title="No upcoming leave" />
              ) : (
                <div className="space-y-2">
                  {upcoming.map((row, idx) => (
                    <div key={row.leave_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-2.5 text-[13px]">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-text">{row.employee_name || 'Employee'}</span>
                        {annualChip(row)}
                      </div>
                      <span className="text-subtle/90">{formatDate(row.start_date)} → {formatDate(row.end_date)}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// --- Shifts ----------------------------------------------------------------

function ShiftsPage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getPosthireShifts(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireShiftsResponse>(loader)
  const action = usePosthireAction(access, reload, onNotice)
  const canManage = can(permissions, 'shifts.manage')

  const shifts = data?.shifts ?? []
  const swaps = data?.swaps ?? []

  const [form, setForm] = useState({ employee_name: '', shift_date: '', start_time: '', end_time: '' })
  const formReady = form.employee_name.trim() && form.shift_date && form.start_time && form.end_time

  const submitShift = () => {
    if (!formReady) return
    action.run(
      'create_shift_assignment',
      { employee_name: form.employee_name.trim(), shift_date: form.shift_date, start_time: form.start_time, end_time: form.end_time },
      { key: 'create-shift' },
    )
    setForm({ employee_name: '', shift_date: '', start_time: '', end_time: '' })
  }

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : (
        <>
          <NextAction
            tone={swaps.length ? 'warning' : 'success'}
            icon={<Repeat className="h-5 w-5" />}
            title={swaps.length ? `${swaps.length} swap request${swaps.length === 1 ? '' : 's'} to review` : 'No swap requests pending'}
            detail={swaps.length ? 'Approve or decline swaps below.' : `${shifts.length} shifts scheduled this week`}
          />
          {canManage ? (
            <Card>
              <CardHeader>
                <CardTitle>Schedule a shift</CardTitle>
                <CardDescription>Assign an employee to a shift. They are notified automatically.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  <input
                    value={form.employee_name}
                    onChange={(e) => setForm((f) => ({ ...f, employee_name: e.target.value }))}
                    placeholder="Employee name"
                    className="h-10 rounded-full border border-line/60 bg-white/70 px-4 text-[13px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15 lg:col-span-2"
                  />
                  <input
                    type="date"
                    value={form.shift_date}
                    onChange={(e) => setForm((f) => ({ ...f, shift_date: e.target.value }))}
                    className="h-10 rounded-full border border-line/60 bg-white/70 px-4 text-[13px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                  />
                  <input
                    type="time"
                    value={form.start_time}
                    onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
                    className="h-10 rounded-full border border-line/60 bg-white/70 px-4 text-[13px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                  />
                  <input
                    type="time"
                    value={form.end_time}
                    onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
                    className="h-10 rounded-full border border-line/60 bg-white/70 px-4 text-[13px] text-text outline-none focus:border-[#c89445]/40 focus:ring-2 focus:ring-[#c89445]/15"
                  />
                </div>
                <div className="mt-3 flex justify-end">
                  <Button size="sm" disabled={!formReady || action.busy} onClick={submitShift}>
                    {action.runningKey === 'create-shift' ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" /> Scheduling…
                      </>
                    ) : (
                      <>
                        <ArrowRight className="h-4 w-4" /> Schedule shift
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
          {swaps.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Swap requests</CardTitle>
                <CardDescription>Requests waiting for a decision.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2.5">
                  {swaps.map((swap, idx) => (
                    <div key={swap.swap_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] border border-line/50 bg-panel/70 px-4 py-3">
                      <div>
                        <p className="font-semibold text-text">{swap.employee_name || 'Employee'}</p>
                        <p className="text-[12px] text-subtle/85">{formatDate(swap.shift_date)}</p>
                      </div>
                      {canManage ? (
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="sm" disabled={action.busy} onClick={() => action.run('reject_shift_swap', { swap_id: swap.swap_id }, { destructive: true, key: `reject-swap:${swap.swap_id || idx}`, confirm: { title: 'Decline this swap request?', body: `${swap.employee_name || 'This employee'}'s shift swap for ${formatDate(swap.shift_date)} will be declined. The shift stays as scheduled.`, confirmLabel: 'Decline swap' } })}>
                            {action.runningKey === `reject-swap:${swap.swap_id || idx}` ? (
                              <>
                                <Loader2 className="h-4 w-4 animate-spin" /> Declining…
                              </>
                            ) : (
                              'Decline'
                            )}
                          </Button>
                          <Button size="sm" disabled={action.busy} onClick={() => action.run('approve_shift_swap', { swap_id: swap.swap_id }, { key: `approve-swap:${swap.swap_id || idx}` })}>
                            {action.runningKey === `approve-swap:${swap.swap_id || idx}` ? (
                              <>
                                <Loader2 className="h-4 w-4 animate-spin" /> Approving…
                              </>
                            ) : (
                              'Approve'
                            )}
                          </Button>
                        </div>
                      ) : (
                        <StatusBadge status={swap.status} />
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>This week's schedule</CardTitle>
              <CardDescription>{shifts.length} shift{shifts.length === 1 ? '' : 's'} scheduled.</CardDescription>
            </CardHeader>
            <CardContent>
              {shifts.length === 0 ? (
                <EmptyState icon={<CalendarDays className="h-5 w-5" />} title="No shifts this week" hint={canManage ? 'Schedule a shift above to get started.' : undefined} />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[640px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Date</th>
                        <th className="px-4 py-3 font-medium">Time</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {shifts.map((shift, idx) => (
                        <tr key={shift.shift_id || idx} className="hover:bg-white/45">
                          <td className="px-4 py-3 font-semibold text-text">{shift.employee_name || '—'}</td>
                          <td className="px-4 py-3 text-subtle/90">{formatDate(shift.shift_date)}</td>
                          <td className="px-4 py-3 text-subtle/90">{formatTime(shift.start_time)} – {formatTime(shift.end_time)}</td>
                          <td className="px-4 py-3"><StatusBadge status={shift.status || 'scheduled'} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
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

function PayrollPage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getPosthirePayroll(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthirePayrollResponse>(loader)
  const action = usePosthireAction(access, reload, onNotice)
  const confirm = useConfirm()
  const canManage = can(permissions, 'payroll.manage')
  const [editingPolicy, setEditingPolicy] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [preview, setPreview] = useState<{ rows: PayrollPreviewRow[]; count: number } | null>(null)

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
      onNotice(res.message || `Preview ready · ${rows.length} timesheet${rows.length === 1 ? '' : 's'}.`)
    } catch (err) {
      onNotice(friendlyError(err, 'We could not preview payroll right now.'))
    } finally {
      setPreviewBusy(false)
    }
  }, [access, periodArgs, onNotice])

  const timesheets = data?.timesheets ?? []
  const exports = data?.exports ?? []
  const policy = data?.policy ?? {}
  const draft = timesheets.filter((t) => String(t.status).toLowerCase() === 'draft')
  const canExport = Boolean(data?.can_export)
  const periodLabel = data?.period.start_date ? `${formatDate(data.period.start_date)} → ${formatDate(data.period.end_date)}` : ''

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
            {canManage ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={action.busy}
                onClick={() => action.run('create_timesheet_review', periodArgs, { key: 'generate-timesheets' })}
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
                size="sm"
                disabled={action.busy}
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
            tone={draft.length ? 'warning' : 'success'}
            icon={<DollarSign className="h-5 w-5" />}
            title={draft.length ? `${draft.length} timesheet${draft.length === 1 ? '' : 's'} need review` : 'All timesheets reviewed'}
            detail={
              data?.period.start_date
                ? `Period ${formatDate(data?.period.start_date)} → ${formatDate(data?.period.end_date)}`
                : 'No active payroll period'
            }
          />
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
                    onSubmit={async (values) => {
                      const ok = await confirm({
                        title: 'Apply payroll policy?',
                        body: 'These payroll rules will apply to this company’s pay calculations going forward. You can update them again anytime.',
                        confirmLabel: 'Apply changes',
                      })
                      if (!ok) return
                      action.run(
                        'set_payroll_policy',
                        { structured_policy: true, ...values },
                        { destructive: true, key: 'set-policy' },
                      )
                      setEditingPolicy(false)
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
              <CardDescription>A record of payroll runs that have been exported.</CardDescription>
            </CardHeader>
            <CardContent>
              {exports.length === 0 ? (
                <EmptyState icon={<Download className="h-5 w-5" />} title="No exports yet" />
              ) : (
                <div className="space-y-2">
                  {exports.map((row, idx) => (
                    <div key={row.export_id || idx} className="flex items-center justify-between gap-3 rounded-[1rem] border border-line/45 bg-panel/55 px-4 py-2.5 text-[13px]">
                      <span className="font-medium text-text">{formatDate(row.period_start)} → {formatDate(row.period_end)}</span>
                      <StatusBadge status={row.status || 'exported'} />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// --- Analytics -------------------------------------------------------------

// Headline metrics are surfaced as stat cards from `counts`; suppress the
// matching single-row insights so we don't show the same number twice.
const ANALYTICS_HEADLINE_METRICS = new Set(['Scheduled shifts', 'Absences', 'Late records', 'Pending review'])

function AnalyticsPage({ access }: { access: DashboardAccess }) {
  const loader = useCallback(() => getPosthireAnalytics(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireAnalyticsResponse>(loader)

  const counts = data?.counts ?? {}
  const insights = Array.isArray(data?.insights) ? data?.insights ?? [] : []
  const pendingReview = Number(counts.pending_leave || 0) + Number(counts.pending_availability || 0) + Number(counts.pending_swaps || 0)

  const headlineStats = [
    { label: 'Scheduled shifts', value: Number(counts.scheduled_shifts || 0) },
    { label: 'Absences', value: Number(counts.absent_records || 0) },
    { label: 'Late records', value: Number(counts.late_records || 0), hint: counts.late_minutes ? `${counts.late_minutes} late minutes` : undefined },
    { label: 'Pending review', value: pendingReview, hint: 'Leave · availability · swaps' },
  ]

  // Group the detailed insights (top lateness, overtime risk, branch absences, …)
  // by their metric label so each becomes a small leaderboard card.
  const groups = useMemo(() => {
    const map = new Map<string, typeof insights>()
    for (const insight of insights) {
      if (ANALYTICS_HEADLINE_METRICS.has(insight.metric)) continue
      const list = map.get(insight.metric) ?? []
      list.push(insight)
      map.set(insight.metric, list)
    }
    return Array.from(map.entries())
  }, [insights])

  const period =
    data?.start_date && data?.end_date ? `${formatDate(data.start_date)} → ${formatDate(data.end_date)}` : undefined
  const hasData = headlineStats.some((stat) => Number(stat.value) > 0) || groups.length > 0

  return (
    <div className="space-y-6">
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : !hasData ? (
        <EmptyState
          icon={<ClipboardList className="h-5 w-5" />}
          title={period ? `No workforce activity for ${period}` : 'No workforce activity yet'}
          hint="This page turns day-to-day operations into an executive view. As your team logs activity, it fills in automatically:"
          points={[
            'Attendance exceptions — lateness, absences, and early leaves',
            'Overtime risk and your best-attendance employees',
            'Pending items across leave, availability, and shift swaps',
            'Absence trends by branch',
          ]}
        />
      ) : (
        <>
          <NextAction
            tone={pendingReview ? 'warning' : 'success'}
            icon={<ClipboardList className="h-5 w-5" />}
            title={
              pendingReview
                ? `${pendingReview} item${pendingReview === 1 ? '' : 's'} need review`
                : 'Workforce is up to date'
            }
            detail={period ? `Period ${period}` : undefined}
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {headlineStats.map((stat) => (
              <StatCard key={stat.label} label={stat.label} value={stat.value} hint={stat.hint} />
            ))}
          </div>
          {groups.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {groups.map(([metric, rows]) => (
                <Card key={metric}>
                  <CardHeader>
                    <CardTitle>{metric}</CardTitle>
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
          ) : null}
        </>
      )}
    </div>
  )
}

// --- Compliance ------------------------------------------------------------

const COMPLIANCE_FILTERS: Array<{ key: 'all' | ComplianceBucket; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'expired', label: 'Expired' },
  { key: 'expiring_soon', label: 'Expiring soon' },
  { key: 'missing', label: 'Missing' },
  { key: 'needs_review', label: 'Needs review' },
  { key: 'valid', label: 'Valid' },
]

function complianceDaysLabel(doc: { days_until_expiry?: number | null }): string {
  const days = doc.days_until_expiry
  if (days == null) return '—'
  if (days < 0) return `${Math.abs(days)}d overdue`
  if (days === 0) return 'Today'
  return `${days}d left`
}

function complianceReminderLabel(doc: { last_reminded_at?: string | null; reminder_count?: number }): string {
  if (!doc.last_reminded_at) return 'Never'
  const when = formatDate(doc.last_reminded_at)
  return (doc.reminder_count ?? 0) > 0 ? `${when} · ${doc.reminder_count} sent` : when
}

function CompliancePage({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (message: string) => void }) {
  const loader = useCallback(() => getPosthireCompliance(access), [access])
  const { data, loading, refreshing, error, reload } = useModuleData<PosthireComplianceResponse>(loader)
  const [filter, setFilter] = useState<'all' | ComplianceBucket>('all')
  const action = usePosthireAction(access, reload, onNotice)
  const confirm = useConfirm()
  const canManage = can(permissions, 'compliance.manage')
  const canUpload = can(permissions, 'onboarding.manage') && Boolean(data?.doc_upload_enabled)

  const summary = data?.summary
  const documents = data?.documents ?? []
  const filtered = useMemo(
    () => (filter === 'all' ? documents : documents.filter((d) => d.status === filter)),
    [documents, filter],
  )

  const needsAttention = summary?.needs_attention ?? 0
  const bannerTone: Tone = needsAttention ? (summary && summary.expired ? 'danger' : 'warning') : 'success'
  const bannerTitle = needsAttention
    ? `${needsAttention} document${needsAttention === 1 ? '' : 's'} need attention`
    : 'Compliance looks up to date'
  const bannerDetail = needsAttention
    ? [
        summary?.expired ? `${summary.expired} expired` : '',
        summary?.expiring_soon ? `${summary.expiring_soon} expiring soon` : '',
        summary?.missing ? `${summary.missing} missing` : '',
        summary?.needs_review ? `${summary.needs_review} need review` : '',
      ]
        .filter(Boolean)
        .join(' · ')
    : 'No employee documents are expired, expiring, or missing.'

  return (
    <div className="space-y-6">
      {action.dialog}
      <ModuleToolbar onRefresh={() => void reload()} refreshing={refreshing} />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : !summary || summary.total_documents === 0 ? (
        summary && summary.employees_total > 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title="No compliance documents tracked yet"
            hint="Compliance fills in as you upload employee documents — expiring and missing items will surface here automatically."
            points={[
              'Upload civil IDs, passports, residency/work permits, medical documents, and certificates',
              'Open Employees to see who is on your team',
              'Open Onboarding to collect documents from new hires',
            ]}
          />
        ) : (
          <EmptyState
            icon={<ShieldCheck className="h-5 w-5" />}
            title="Compliance tracking starts when employee documents are uploaded"
            hint="Upload civil IDs, passports, residency/work permits, medical documents, and certificates to track missing and expiring documents."
            points={[
              'Open Employees to build your team directory',
              'Open Onboarding to collect documents from new hires',
              'Documents are checked automatically once uploaded',
            ]}
          />
        )
      ) : (
        <>
          <NextAction
            tone={bannerTone}
            icon={needsAttention ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
            title={bannerTitle}
            detail={bannerDetail}
          />
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard label="Missing" value={summary.missing} hint={summary.missing ? 'Request from employees' : 'None'} />
            <StatCard label="Expiring soon" value={summary.expiring_soon} hint={summary.expiring_soon ? 'Send reminders' : 'None'} />
            <StatCard label="Expired" value={summary.expired} hint={summary.expired ? 'Start renewals' : 'None'} />
            <StatCard label="Needs review" value={summary.needs_review} hint={summary.needs_review ? 'Check expiry dates' : 'None'} />
            <StatCard label="Valid" value={summary.valid} hint="Up to date" />
          </div>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
              <div>
                <CardTitle>Employee documents</CardTitle>
                <CardDescription>
                  {filtered.length} of {documents.length} document{documents.length === 1 ? '' : 's'} across {summary.employees_checked} employee
                  {summary.employees_checked === 1 ? '' : 's'}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {COMPLIANCE_FILTERS.map((chip) => {
                  const count =
                    chip.key === 'all' ? documents.length : (summary[chip.key as ComplianceBucket] as number)
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
              {filtered.length === 0 ? (
                <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title="Nothing in this view" hint="Try a different status filter." />
              ) : (
                <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                  <table className="w-full min-w-[920px] text-left text-[13px]">
                    <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                      <tr>
                        <th className="px-4 py-3 font-medium">Employee</th>
                        <th className="px-4 py-3 font-medium">Document</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                        <th className="px-4 py-3 font-medium">Expiry</th>
                        <th className="px-4 py-3 font-medium">Days left</th>
                        <th className="px-4 py-3 font-medium">Last reminder</th>
                        <th className="px-4 py-3 font-medium">Next action</th>
                        {canManage ? <th className="px-4 py-3 text-right font-medium">Action</th> : null}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/45">
                      {filtered.map((doc, idx) => {
                        const rowKey = `${doc.employee_key}-${doc.document_type}-${idx}`
                        const remindKey = `remind:${doc.employee_key}:${doc.document_type}`
                        const reviewKey = `review:${doc.employee_key}:${doc.document_type}`
                        const args = { employee_name: doc.employee_name, document_type: doc.document_type }
                        return (
                          <tr key={rowKey} className="hover:bg-white/45">
                            <td className="px-4 py-3">
                              <p className="font-semibold text-text">{doc.employee_name}</p>
                              {doc.department ? <p className="text-[12px] text-subtle/85">{doc.department}</p> : null}
                            </td>
                            <td className="px-4 py-3 text-subtle/90">
                              <div className="flex items-center gap-2">
                                <span>{doc.document_label}</span>
                                <DocumentActions access={access} fileId={doc.file_id} filename={doc.document_label} compact />
                                {canUpload && doc.document_type ? (
                                  <DocumentUploadButton
                                    access={access}
                                    employeeKey={doc.employee_key}
                                    itemId={doc.document_type}
                                    hasFile={Boolean(doc.file_id)}
                                    onUploaded={(message) => { onNotice(message); void reload() }}
                                    onError={onNotice}
                                  />
                                ) : null}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={doc.tone}>{doc.status_label}</Badge>
                            </td>
                            <td className="px-4 py-3 text-subtle/90">{formatDate(doc.expiry_date)}</td>
                            <td className="px-4 py-3 text-subtle/90">{complianceDaysLabel(doc)}</td>
                            <td className="px-4 py-3 text-subtle/90">{complianceReminderLabel(doc)}</td>
                            <td className="px-4 py-3 text-subtle/90">{doc.next_action}</td>
                            {canManage ? (
                              <td className="px-4 py-3 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  {doc.status === 'needs_review' ? (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      disabled={action.busy}
                                      onClick={() => action.run('compliance_mark_reviewed', args, { key: reviewKey })}
                                    >
                                      {action.runningKey === reviewKey ? (
                                        <>
                                          <Loader2 className="h-4 w-4 animate-spin" /> Saving…
                                        </>
                                      ) : (
                                        'Mark reviewed'
                                      )}
                                    </Button>
                                  ) : null}
                                  {doc.status !== 'valid' ? (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      disabled={action.busy}
                                      onClick={async () => {
                                        if (!(await confirm({ title: 'Send document reminder?', body: `${doc.employee_name} will receive a reminder about their ${doc.document_label}.`, confirmLabel: 'Send reminder' }))) return
                                        await action.run('compliance_send_reminder', args, { key: remindKey })
                                      }}
                                    >
                                      {action.runningKey === remindKey ? (
                                        <>
                                          <Loader2 className="h-4 w-4 animate-spin" /> Sending…
                                        </>
                                      ) : (
                                        'Send reminder'
                                      )}
                                    </Button>
                                  ) : null}
                                </div>
                              </td>
                            ) : null}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
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
function DeliveryFollowUpCard({ access, permissions, onNotice }: { access: DashboardAccess; permissions: string[]; onNotice: (m: string) => void }) {
  const loader = useCallback(() => getHrTasks(access, 'open'), [access])
  const { data, error, reload } = useModuleData<HrTasksResponse>(loader)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const canManage =
    can(permissions, 'users.manage') ||
    ['leave', 'onboarding', 'compliance', 'attendance', 'shifts', 'payroll'].some((m) => can(permissions, `${m}.manage`))

  const tasks: HrTask[] = data?.tasks ?? []
  // The endpoint can 403 on workspaces without a post-hire module / read access;
  // treat that as "nothing to surface" rather than showing an error here.
  if (error || tasks.length === 0) return null

  const resolve = async (task: HrTask) => {
    setResolvingId(task.task_id)
    try {
      await resolveHrTask(access, task.task_id, 'done')
      onNotice('Marked as done.')
      await reload()
    } catch (err) {
      onNotice(friendlyError(err, 'We could not update that task.'))
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
            {tasks.length}
          </Badge>
        </div>
        <CardDescription>
          We couldn’t reach {tasks.length === 1 ? 'an employee' : 'some employees'} for {tasks.length === 1 ? 'this' : 'these'} message{tasks.length === 1 ? '' : 's'}. Please follow up directly, then mark it done.
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
      </CardContent>
    </Card>
  )
}

export function PostHirePage({ page, access, permissions, onNotice }: PostHireProps) {
  const followUp = <DeliveryFollowUpCard access={access} permissions={permissions} onNotice={onNotice} />
  return (
    <>
      {followUp}
      <PostHireModuleBody page={page} access={access} permissions={permissions} onNotice={onNotice} />
    </>
  )
}

function PostHireModuleBody({ page, access, permissions, onNotice }: PostHireProps) {
  switch (page) {
    case 'employees':
      return <EmployeesPage access={access} permissions={permissions} onNotice={onNotice} />
    case 'onboarding':
      return <OnboardingPage access={access} permissions={permissions} onNotice={onNotice} />
    case 'attendance':
      return <AttendancePage access={access} permissions={permissions} onNotice={onNotice} />
    case 'leave':
      return <LeavePage access={access} permissions={permissions} onNotice={onNotice} />
    case 'shifts':
      return <ShiftsPage access={access} permissions={permissions} onNotice={onNotice} />
    case 'payroll':
      return <PayrollPage access={access} permissions={permissions} onNotice={onNotice} />
    case 'analytics':
      return <AnalyticsPage access={access} />
    case 'compliance':
      return <CompliancePage access={access} permissions={permissions} onNotice={onNotice} />
    default:
      return null
  }
}
