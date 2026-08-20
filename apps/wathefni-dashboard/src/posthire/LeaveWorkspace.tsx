/**
 * Leave Wave 4 — dashboard leave workspace (queue, file, decide, history).
 * Balances remain non-binding (enforced=false). Does not import from PostHire.tsx.
 */
import { CalendarClock, CalendarDays, Loader2, MoreHorizontal, Plus, RefreshCw, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { useUrlBackedTab, URL_BACKED_VIEW_PAGES } from '@/lib/hrWebUrlTab'

import { useConfirm, type ConfirmOptions } from '@/components/ConfirmDialog'
import { ConfigureInSetupBanner } from '@/components/ConfigureInSetupBanner'
import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/field'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { DashboardApiError, getPosthireEmployees, getPosthireLeave, runPosthireAction } from '@/lib/api'
import { FRESHNESS_MS } from '@/lib/query/freshness'
import { useVisibilitySoftPoll } from '@/lib/query/useVisibilitySoftPoll'
import { touchCalendarProjections } from '@/lib/query/touchCalendarProjections'
import { cn } from '@/lib/utils'
import {
  ApprovalStrip,
  BlockedReason,
  MaskedField,
  useEmployees360Locale,
  WorkflowEmpty,
} from '@/posthire/employees360/chrome'
import {
  durationLabel,
  formatLeaveDates,
  leaveCopy,
  statusLabel,
  statusTone,
  typeLabel,
  type LeaveLocale,
} from '@/posthire/leaveUx'
import { leavePrimaryAction, type LeavePrimaryKind } from '@/posthire/leavePrimaryAction'
import type {
  DashboardAccess,
  LeaveBalance,
  PosthireActionResult,
  PosthireEmployee,
  PosthireLeaveResponse,
  PosthireLeaveRow,
} from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type LeaveWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

const LEAVE_TYPE_OPTIONS = [
  { value: 'annual' },
  { value: 'sick' },
  { value: 'unpaid' },
  { value: 'other' },
] as const

const DURATION_OPTIONS = [
  { value: 'full_day' },
  { value: 'half_day' },
  { value: 'hourly' },
] as const

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

function friendlyError(error: unknown, fallback: string, locale: LeaveLocale): string {
  const c = leaveCopy(locale)
  if (error instanceof DashboardApiError) {
    const code = String(error.code || '').toLowerCase()
    if (code === 'permission_denied' || code === 'leave_real_decision_not_allowlisted') return c.permissionDenied
    if (code === 'stale_row_version' || code === 'stale_leave_version') return c.staleConflict
    if (code === 'leave_overlap' || code === 'overlapping_leave') return c.overlapBlocked
    const message = error.message || ''
    if (message && !/(_|traceback|exception|psycopg)/i.test(message)) return message
  }
  if (error instanceof Error && error.message && !/(_|traceback|exception)/i.test(error.message)) return error.message
  return fallback
}

function actionErrorCode(result: PosthireActionResult | null | undefined): string | null {
  if (!result) return null
  const fromResult = result.result
  if (fromResult && typeof fromResult.error === 'string') return fromResult.error
  if (result.status === 'permission_denied') return 'permission_denied'
  return null
}

function mapActionSurface(code: string | null | undefined, locale: LeaveLocale): string | null {
  if (!code) return null
  const c = leaveCopy(locale)
  const k = String(code).toLowerCase()
  if (k.includes('stale')) return c.staleConflict
  if (k.includes('permission') || k.includes('allowlist') || k.includes('self_')) return c.permissionDenied
  if (k.includes('overlap')) return c.overlapBlocked
  if (k.includes('shift_conflict')) return c.shiftConflicts
  return null
}

function nextActionLabel(row: PosthireLeaveRow, locale: LeaveLocale): string {
  const c = leaveCopy(locale)
  const next = String(row.next_action || '').toLowerCase()
  if (next === 'decide') return c.nextDecide
  if (next === 'await_resubmit') return c.nextResubmit
  if (next === 'may_cancel') return c.nextCancel
  const status = String(row.status || '').toLowerCase()
  if (status === 'needs_review' || status === 'expired_stale') return c.dualInitiate
  if (status === 'needs_info') return c.nextResubmit
  if (status === 'requested') return c.nextDecide
  if (status === 'approved') return c.nextCancel
  return statusLabel(row.status, locale)
}

function decisionArgs(row: PosthireLeaveRow, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    leave_id: row.leave_id,
    expected_row_version: row.row_version,
    employee_name: row.employee_name,
    employee_phone: row.employee_phone,
    start_date: row.start_date,
    end_date: row.end_date,
    ...extra,
  }
}

function useLeaveData(
  access: DashboardAccess,
  view: 'active' | 'history',
  historyStatus: string,
  onAccessIssue?: (issue: AccessIssue) => void,
) {
  const locale = useEmployees360Locale()
  const [data, setData] = useState<PosthireLeaveResponse | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const loader = useCallback(
    () => getPosthireLeave(access, view === 'history' ? { view: 'history', status: historyStatus || undefined } : undefined),
    [access, view, historyStatus],
  )

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
      if (issue) onAccessIssue?.(issue)
      setError(friendlyError(err, leaveCopy(locale).retry, locale))
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false)
    }
  }, [loader, onAccessIssue, locale])

  useEffect(() => {
    // Soft-keep prior leave rows while view/history filters change.
    setError(null)
    void reload()
  }, [reload])

  return { data, loading: refreshing && data === null, refreshing, error, reload }
}

function useLeaveAction(
  access: DashboardAccess,
  reload: () => Promise<void>,
  onNotice: NoticeFn,
  onAccessIssue: ((issue: AccessIssue) => void) | undefined,
  locale: LeaveLocale,
  setSurfaceError: (msg: string | null) => void,
) {
  const askConfirm = useConfirm()
  const [busy, setBusy] = useState(false)
  const [runningKey, setRunningKey] = useState<string | null>(null)

  const execute = useCallback(
    async (actionType: string, args: Record<string, unknown>, key: string, preconfirmed = false): Promise<boolean> => {
      setBusy(true)
      setRunningKey(key)
      setSurfaceError(null)
      try {
        let result = await runPosthireAction(access, { action_type: actionType, args })
        // Registry confirmation OR executor needs_confirmation (e.g. shift conflicts)
        if (result.confirmation || result.status === 'needs_confirmation') {
          const confirmType = result.confirmation?.action_type || actionType
          const confirmArgs = result.confirmation?.args || { ...args, allow_shift_conflicts: true }
          if (preconfirmed || result.status === 'needs_confirmation') {
            result = await runPosthireAction(access, {
              action_type: confirmType,
              args: confirmArgs,
            })
            if (result.confirmation || result.status === 'needs_confirmation') {
              const ok = await askConfirm({
                title: leaveCopy(locale).approve,
                body: result.confirmation?.text || result.message || 'Confirm?',
                confirmLabel: leaveCopy(locale).approve,
                dir: locale === 'ar' ? 'rtl' : 'ltr',
              })
              if (!ok) return false
              result = await runPosthireAction(access, {
                action_type: result.confirmation?.action_type || confirmType,
                args: result.confirmation?.args || confirmArgs,
              })
            }
          } else {
            const ok = await askConfirm({
              title: leaveCopy(locale).approve,
              body: result.confirmation?.text || result.message || 'Confirm?',
              confirmLabel: leaveCopy(locale).approve,
              dir: locale === 'ar' ? 'rtl' : 'ltr',
            })
            if (!ok) return false
            result = await runPosthireAction(access, {
              action_type: result.confirmation!.action_type,
              args: result.confirmation!.args,
            })
          }
        }

        const errCode = actionErrorCode(result)
        const surface = mapActionSurface(errCode, locale)
        if (surface) {
          setSurfaceError(surface)
          onNotice(surface, 'error')
          await reload()
          return false
        }
        if (result.ok === false) {
          const msg = result.message || leaveCopy(locale).permissionDenied
          setSurfaceError(mapActionSurface(errCode, locale) || msg)
          onNotice(msg, 'error')
          await reload()
          return false
        }
        onNotice(result.message || 'Done.', 'success')
        touchCalendarProjections(access)
        await reload()
        return true
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return false
        }
        const msg = friendlyError(err, leaveCopy(locale).retry, locale)
        setSurfaceError(msg)
        onNotice(msg, 'error')
        return false
      } finally {
        setBusy(false)
        setRunningKey(null)
      }
    },
    [access, askConfirm, locale, onAccessIssue, onNotice, reload, setSurfaceError],
  )

  const run = useCallback(
    (
      actionType: string,
      args: Record<string, unknown>,
      options: { key?: string; confirm?: ConfirmOptions; destructive?: boolean } = {},
    ) => {
      const go = (preconfirmed: boolean) => {
        void execute(actionType, args, options.key || actionType, preconfirmed)
      }
      if (options.confirm) {
        void (async () => {
          if (await askConfirm({ ...options.confirm!, destructive: options.destructive, dir: locale === 'ar' ? 'rtl' : 'ltr' })) {
            go(true)
          }
        })()
        return
      }
      go(false)
    },
    [askConfirm, execute, locale],
  )

  return { run, busy, runningKey }
}

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium text-subtle/90">
        {label}
        {required ? <span className="text-rose-500"> *</span> : null}
      </span>
      {children}
    </label>
  )
}

function FileLeaveModal({
  access,
  locale,
  onClose,
  onNotice,
  onDone,
  onAccessIssue,
}: {
  access: DashboardAccess
  locale: LeaveLocale
  onClose: () => void
  onNotice: NoticeFn
  onDone: () => void
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const c = leaveCopy(locale)
  const isAr = locale === 'ar'
  const [employees, setEmployees] = useState<PosthireEmployee[]>([])
  const [loadingEmployees, setLoadingEmployees] = useState(true)
  const [employeeKey, setEmployeeKey] = useState('')
  const [leaveType, setLeaveType] = useState('annual')
  const [durationUnit, setDurationUnit] = useState('full_day')
  const [halfPortion, setHalfPortion] = useState('am')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoadingEmployees(true)
    getPosthireEmployees(access)
      .then((r) => {
        if (alive) {
          setEmployees(
            (r.employees || []).filter((e) => {
              const s = String(e.employment_status || 'active').toLowerCase()
              // Leave subject picker: active only — exclude left and pending_start joiners.
              return s === 'active' || s === ''
            }),
          )
        }
      })
      .catch((err) => {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue?.(issue)
        setError(friendlyError(err, c.retry, locale))
      })
      .finally(() => {
        if (alive) setLoadingEmployees(false)
      })
    return () => {
      alive = false
    }
  }, [access, onAccessIssue, c.retry, locale])

  const selected = employees.find((e) => e.employee_key === employeeKey)
  const ready = Boolean(employeeKey && startDate && endDate)

  const typeOptionLabel = (value: string) => typeLabel(value, locale)
  const durationOptionLabel = (value: string) => {
    if (value === 'half_day') return c.durationHalf
    if (value === 'hourly') return c.durationHourly
    return c.durationFull
  }

  const submit = async () => {
    if (!ready) {
      setError(isAr ? 'اختر موظفاً وتواريخ الإجازة.' : 'Choose an employee and the leave dates.')
      return
    }
    if (endDate < startDate) {
      setError(isAr ? 'تاريخ النهاية يجب أن يكون في أو بعد تاريخ البداية.' : 'The end date must be on or after the start date.')
      return
    }
    if (durationUnit === 'hourly' && (!startTime || !endTime)) {
      setError(isAr ? 'حدد وقت البداية والنهاية للساعات.' : 'Set start and end time for hourly leave.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const args: Record<string, unknown> = {
        employee_name: selected?.name,
        employee_phone: selected?.phone,
        leave_type: leaveType,
        start_date: startDate,
        end_date: endDate,
        reason: reason.trim() || undefined,
        duration_unit: durationUnit,
      }
      if (durationUnit === 'half_day') args.half_portion = halfPortion
      if (durationUnit === 'hourly') {
        args.start_time = startTime
        args.end_time = endTime
      }
      const res = await runPosthireAction(access, { action_type: 'request_leave', args })
      if (res.ok) {
        onNotice(res.message || (isAr ? 'تم تقديم الإجازة للاعتماد.' : 'Leave filed for approval.'), 'success')
        onDone()
        onClose()
      } else {
        const surface = mapActionSurface(actionErrorCode(res), locale)
        setError(surface || res.message || (isAr ? 'تعذر تقديم الإجازة.' : 'We couldn’t file this leave.'))
      }
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(friendlyError(err, isAr ? 'تعذر تقديم الإجازة.' : 'We couldn’t file this leave.', locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm">
      <div
        className="w-full max-w-md rounded-[1.6rem] border border-line/60 bg-panel/97 p-6 shadow-[0_30px_80px_rgba(24,20,15,0.28)] ring-1 ring-white/60"
        dir={isAr ? 'rtl' : 'ltr'}
      >
        <div className="space-y-1">
          <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{c.fileLeave}</p>
          <p className="text-[13px] leading-6 text-subtle/95">
            {isAr
              ? 'سجّل طلب إجازة للموظف. يُقدَّم للاعتماد — الأرصدة لا تُحدَّث إلا عند الاعتماد.'
              : 'Record a leave request for an employee. It’s filed for approval — balances update only when you approve it.'}
          </p>
        </div>
        <div className="mt-5 space-y-3.5">
          <Field label={isAr ? 'الموظف' : 'Employee'} required>
            <Select className="w-full" value={employeeKey} onChange={(e) => setEmployeeKey(e.target.value)} disabled={loadingEmployees}>
              <option value="">{loadingEmployees ? c.loading : isAr ? 'اختر موظفاً' : 'Select an employee'}</option>
              {employees.map((e) => (
                <option key={e.employee_key} value={e.employee_key}>
                  {e.name}
                  {e.position_title ? ` · ${e.position_title}` : ''}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={c.type} required>
            <Select className="w-full" value={leaveType} onChange={(e) => setLeaveType(e.target.value)}>
              {LEAVE_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {typeOptionLabel(o.value)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={c.duration} required>
            <Select className="w-full" value={durationUnit} onChange={(e) => setDurationUnit(e.target.value)}>
              {DURATION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {durationOptionLabel(o.value)}
                </option>
              ))}
            </Select>
          </Field>
          {durationUnit === 'half_day' ? (
            <Field label={isAr ? 'الجزء' : 'Half portion'} required>
              <Select className="w-full" value={halfPortion} onChange={(e) => setHalfPortion(e.target.value)}>
                <option value="am">{isAr ? 'صباحاً' : 'AM'}</option>
                <option value="pm">{isAr ? 'مساءً' : 'PM'}</option>
              </Select>
            </Field>
          ) : null}
          {durationUnit === 'hourly' ? (
            <div className="grid gap-3.5 sm:grid-cols-2">
              <Field label={isAr ? 'وقت البداية' : 'Start time'} required>
                <Input className="w-full" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
              </Field>
              <Field label={isAr ? 'وقت النهاية' : 'End time'} required>
                <Input className="w-full" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
              </Field>
            </div>
          ) : null}
          <div className="grid gap-3.5 sm:grid-cols-2">
            <Field label={isAr ? 'تاريخ البداية' : 'Start date'} required>
              <Input className="w-full" type="date" value={startDate} max={endDate || undefined} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label={isAr ? 'تاريخ النهاية' : 'End date'} required>
              <Input className="w-full" type="date" value={endDate} min={startDate || undefined} onChange={(e) => setEndDate(e.target.value)} />
            </Field>
          </div>
          {leaveType === 'unpaid' ? (
            <p className="rounded-[0.9rem] border border-line/45 bg-panel-muted/40 px-3 py-2 text-[12px] text-subtle/90">{c.unpaidNote}</p>
          ) : null}
          <Field label={isAr ? 'السبب (اختياري)' : 'Reason (optional)'}>
            <Textarea className="w-full" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
        {error ? <p className="mt-3 text-[13px] text-rose-600">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
            {c.cancel}
          </Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !ready}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {c.fileLeave}
          </Button>
        </div>
      </div>
    </div>
  )
}

function LeaveDetailDrawer({
  row,
  locale,
  balances,
  balancesEnabled,
  canManage,
  busy,
  runningKey,
  onClose,
  onAction,
}: {
  row: PosthireLeaveRow
  locale: LeaveLocale
  balances: LeaveBalance[]
  balancesEnabled: boolean
  canManage: boolean
  busy: boolean
  runningKey: string | null
  onClose: () => void
  onAction: (type: string, args: Record<string, unknown>, opts?: { key?: string; confirm?: ConfirmOptions; destructive?: boolean }) => void
}) {
  const c = leaveCopy(locale)
  const isAr = locale === 'ar'
  const status = String(row.status || '').toLowerCase()
  const annual = balances.find((b) => b.leave_type === 'annual')
  const chargeable =
    row.chargeable_days != null
      ? `${row.chargeable_days} ${isAr ? 'يوم' : 'day'}${Number(row.chargeable_days) === 1 ? '' : isAr ? '' : 's'}`
      : row.chargeable_hours != null
        ? `${row.chargeable_hours} ${isAr ? 'ساعة' : 'h'}`
        : null
  const primaryKind = leavePrimaryAction({
    status: row.status,
    next_action: row.next_action,
    dual_control_pending: row.dual_control_pending,
    dual_pending: row.dual_pending,
    dual_control_status: row.dual_control_status,
    canDecide: canManage,
  })

  const runPrimary = () => {
    if (primaryKind === 'approve') {
      onAction('approve_leave_request', decisionArgs(row), { key: `approve:${row.leave_id}` })
      return
    }
    if (primaryKind === 'start_dual') {
      onAction('initiate_leave_stale_dual_control', { leave_id: row.leave_id, action_kind: 'expire_stale' }, {
        key: `dual:${row.leave_id}`,
        confirm: {
          title: c.dualInitiate,
          body: isAr ? 'يبدأ اعتماداً مزدوجاً لحل الطلب المتأخر.' : 'Starts audited dual-control to resolve this stale pending leave.',
          confirmLabel: c.dualInitiate,
        },
      })
      return
    }
    if (primaryKind === 'confirm_dual') {
      onAction(
        'confirm_leave_stale_dual_control',
        { leave_id: row.leave_id, dual_action_id: row.dual_action_id || undefined },
        {
          key: `dual-confirm:${row.leave_id}`,
          confirm: {
            title: c.dualConfirm,
            body: c.dualConfirmBody,
            confirmLabel: c.dualConfirm,
          },
        },
      )
      return
    }
    if (primaryKind === 'cancel') {
      onAction('cancel_leave_request', decisionArgs(row), {
        key: `cancel:${row.leave_id}`,
        destructive: true,
        confirm: {
          title: isAr ? 'إلغاء هذه الإجازة؟' : 'Cancel this leave?',
          body: formatLeaveDates(row.start_date, row.end_date, locale),
          confirmLabel: c.cancel,
        },
      })
    }
  }

  const primaryLabel =
    primaryKind === 'approve'
      ? c.approve
      : primaryKind === 'start_dual'
        ? c.dualInitiate
        : primaryKind === 'confirm_dual'
          ? c.dualConfirm
          : primaryKind === 'cancel'
            ? c.cancel
            : null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/25 backdrop-blur-[2px]" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-md flex-col border-s border-[#e8dfd0] bg-[#fffdf8]/98 shadow-[-20px_0_60px_rgba(24,20,15,0.18)]"
        dir={isAr ? 'rtl' : 'ltr'}
        lang={isAr ? 'ar' : 'en'}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[#e8dfd0] px-5 py-4">
          <div className="min-w-0 space-y-1">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-text">{row.employee_name || (isAr ? 'موظف' : 'Employee')}</p>
            <p className="text-[12px] text-subtle/85">
              {typeLabel(row.leave_type, locale)} · {formatLeaveDates(row.start_date, row.end_date, locale)}
            </p>
          </div>
          <button type="button" className="rounded-full p-1.5 text-subtle hover:bg-[#f7f1e6]" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <ApprovalStrip
            state={statusLabel(row.status, locale)}
            nextApprover={status === 'needs_info' ? c.requester : status === 'requested' || status === 'needs_review' ? c.ownerHr : null}
            locale={locale}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{c.type}</p>
              <p className="mt-1 text-[13px] text-text">{typeLabel(row.leave_type, locale)}</p>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{c.duration}</p>
              <p className="mt-1 text-[13px] text-text">
                {durationLabel(row.duration_unit, locale, row.half_portion)}
                {row.start_time && row.end_time ? ` · ${String(row.start_time).slice(0, 5)}–${String(row.end_time).slice(0, 5)}` : ''}
              </p>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{c.dates}</p>
              <p className="mt-1 text-[13px] text-text">{formatLeaveDates(row.start_date, row.end_date, locale)}</p>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{c.nextAction}</p>
              <p className="mt-1 text-[13px] text-text">{nextActionLabel(row, locale)}</p>
            </div>
          </div>
          {chargeable ? (
            <p className="rounded-[1rem] border border-[#e8dfd0] bg-[#fbf7f0] px-3 py-2 text-[13px] text-subtle/90">
              {isAr ? 'الأيام/الساعات المحتسبة' : 'Chargeable'}: <span className="font-medium text-text">{chargeable}</span>
            </p>
          ) : null}
          <p className="rounded-[1rem] border border-[#e8dfd0] bg-[#fffdf8] px-3 py-2.5 text-[12.5px] leading-5 text-subtle/95">{c.approveSeparate}</p>
          {row.is_unpaid || String(row.leave_type || '').toLowerCase() === 'unpaid' ? (
            <p className="rounded-[1rem] border border-[#e8dfd0] bg-[#fbf7f0] px-3 py-2.5 text-[12.5px] leading-5 text-subtle/95">{c.unpaidNote}</p>
          ) : null}
          {balancesEnabled && annual ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{c.balanceImpact}</p>
              <p className="mt-1 text-[13px] text-text">
                {Math.round(annual.current_balance * 10) / 10}/{Math.round(annual.entitlement_days * 10) / 10}{' '}
                {isAr ? 'يوم سنوي متبقٍ (غير ملزم)' : 'annual days left (non-binding)'}
              </p>
            </div>
          ) : null}
          {row.sensitive_category ? (
            <MaskedField label={c.sensitiveMasked} masked value={row.sensitive_category} />
          ) : null}
          {Number(row.shift_conflict_count || 0) > 0 ? (
            <BlockedReason reason={`${c.shiftConflicts} (${row.shift_conflict_count})`} locale={locale} />
          ) : null}
          {row.reason ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-mist">{isAr ? 'السبب' : 'Reason'}</p>
              <p className="mt-1 text-[13px] text-text">{row.reason}</p>
            </div>
          ) : null}
        </div>
        {canManage ? (
          <div className="flex flex-wrap gap-2 border-t border-[#e8dfd0] px-5 py-4">
            {primaryLabel ? (
              <Button size="sm" disabled={busy} onClick={runPrimary} data-primary-action={primaryKind}>
                {runningKey?.includes(String(row.leave_id)) ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {primaryLabel}
              </Button>
            ) : null}
            {(status === 'requested' || status === 'needs_review') && primaryKind !== 'approve' ? (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAction('approve_leave_request', decisionArgs(row), { key: `approve:${row.leave_id}` })}>
                {c.approve}
              </Button>
            ) : null}
            {(status === 'requested' || status === 'needs_review') && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    onAction('reject_leave_request', decisionArgs(row), {
                      key: `reject:${row.leave_id}`,
                      destructive: true,
                      confirm: {
                        title: isAr ? 'رفض طلب الإجازة؟' : 'Decline this leave request?',
                        body: `${row.employee_name || ''} — ${formatLeaveDates(row.start_date, row.end_date, locale)}`,
                        confirmLabel: c.decline,
                      },
                    })
                  }
                >
                  {c.decline}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    onAction(
                      'return_leave_for_info',
                      decisionArgs(row, { info_request: isAr ? 'يرجى تقديم معلومات إضافية' : 'Please provide additional information' }),
                      { key: `info:${row.leave_id}` },
                    )
                  }
                >
                  {c.needsInfo}
                </Button>
              </>
            )}
            {(status === 'needs_review' || status === 'expired_stale') && primaryKind !== 'start_dual' ? (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() =>
                  onAction('initiate_leave_stale_dual_control', { leave_id: row.leave_id, action_kind: 'expire_stale' }, {
                    key: `dual:${row.leave_id}`,
                    confirm: {
                      title: c.dualInitiate,
                      body: isAr ? 'يبدأ اعتماداً مزدوجاً لحل الطلب المتأخر.' : 'Starts audited dual-control to resolve this stale pending leave.',
                      confirmLabel: c.dualInitiate,
                    },
                  })
                }
              >
                {c.dualInitiate}
              </Button>
            ) : null}
            {primaryKind !== 'confirm_dual' && (row.dual_control_pending || row.dual_pending || row.dual_control_status) ? (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() =>
                  onAction(
                    'confirm_leave_stale_dual_control',
                    { leave_id: row.leave_id, dual_action_id: row.dual_action_id || undefined },
                    {
                      key: `dual-confirm:${row.leave_id}`,
                      confirm: {
                        title: c.dualConfirm,
                        body: c.dualConfirmBody,
                        confirmLabel: c.dualConfirm,
                      },
                    },
                  )
                }
              >
                {c.dualConfirm}
              </Button>
            ) : null}
            {status === 'needs_info' ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() =>
                  onAction('withdraw_leave_request', decisionArgs(row), {
                    key: `withdraw:${row.leave_id}`,
                    destructive: true,
                    confirm: {
                      title: isAr ? 'سحب الطلب؟' : 'Withdraw this request?',
                      body: formatLeaveDates(row.start_date, row.end_date, locale),
                      confirmLabel: c.withdraw,
                    },
                  })
                }
              >
                {c.withdraw}
              </Button>
            ) : null}
            {status === 'approved' && row.next_action === 'may_cancel' && primaryKind !== 'cancel' ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() =>
                  onAction('cancel_leave_request', decisionArgs(row), {
                    key: `cancel:${row.leave_id}`,
                    destructive: true,
                    confirm: {
                      title: isAr ? 'إلغاء هذه الإجازة؟' : 'Cancel this leave?',
                      body: formatLeaveDates(row.start_date, row.end_date, locale),
                      confirmLabel: c.cancel,
                    },
                  })
                }
              >
                {c.cancel}
              </Button>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  )
}

function LeaveRowCard({
  row,
  locale,
  balancesEnabled,
  balances,
  canManage,
  busy,
  runningKey,
  menuOpen,
  onToggleMenu,
  onOpen,
  onAction,
}: {
  row: PosthireLeaveRow
  locale: LeaveLocale
  balancesEnabled: boolean
  balances: Record<string, LeaveBalance[]>
  canManage: boolean
  busy: boolean
  runningKey: string | null
  menuOpen: boolean
  onToggleMenu: () => void
  onOpen: () => void
  onAction: (type: string, args: Record<string, unknown>, opts?: { key?: string; confirm?: ConfirmOptions; destructive?: boolean }) => void
}) {
  const c = leaveCopy(locale)
  const status = String(row.status || '').toLowerCase()
  const annual = row.employee_key ? (balances[row.employee_key] ?? []).find((b) => b.leave_type === 'annual') : null
  const isStale = status === 'needs_review' || status === 'expired_stale'
  const primaryKind: LeavePrimaryKind = leavePrimaryAction({
    status: row.status,
    next_action: row.next_action,
    dual_control_pending: row.dual_control_pending,
    dual_pending: row.dual_pending,
    dual_control_status: row.dual_control_status,
    canDecide: canManage,
  })

  const runPrimary = () => {
    if (primaryKind === 'view_details') {
      onOpen()
      return
    }
    if (primaryKind === 'approve') {
      onAction('approve_leave_request', decisionArgs(row), { key: `approve:${row.leave_id}` })
      return
    }
    if (primaryKind === 'start_dual') {
      onAction('initiate_leave_stale_dual_control', { leave_id: row.leave_id, action_kind: 'expire_stale' }, {
        key: `dual:${row.leave_id}`,
        confirm: {
          title: c.dualInitiate,
          body: locale === 'ar' ? 'يبدأ اعتماداً مزدوجاً لحل الطلب المتأخر.' : 'Starts audited dual-control for this stale request.',
          confirmLabel: c.dualInitiate,
        },
      })
      return
    }
    if (primaryKind === 'confirm_dual') {
      onAction(
        'confirm_leave_stale_dual_control',
        { leave_id: row.leave_id, dual_action_id: row.dual_action_id || undefined },
        {
          key: `dual-confirm:${row.leave_id}`,
          confirm: {
            title: c.dualConfirm,
            body: c.dualConfirmBody,
            confirmLabel: c.dualConfirm,
          },
        },
      )
      return
    }
    if (primaryKind === 'cancel') {
      onAction('cancel_leave_request', decisionArgs(row), {
        key: `cancel:${row.leave_id}`,
        destructive: true,
        confirm: {
          title: locale === 'ar' ? 'إلغاء هذه الإجازة؟' : 'Cancel this leave?',
          body: formatLeaveDates(row.start_date, row.end_date, locale),
          confirmLabel: c.cancel,
        },
      })
    }
  }

  const primaryLabel =
    primaryKind === 'approve'
      ? c.approve
      : primaryKind === 'start_dual'
        ? c.dualInitiate
        : primaryKind === 'confirm_dual'
          ? c.dualConfirm
          : primaryKind === 'cancel'
            ? c.cancel
            : c.viewDetails

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] border border-[#e8dfd0] bg-[#fffdf8]/90 px-4 py-3"
      data-leave-row
      data-status={status}
    >
      <button type="button" className="min-w-0 flex-1 text-start" onClick={onOpen}>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-text">{row.employee_name || (locale === 'ar' ? 'موظف' : 'Employee')}</p>
          <StatusPill tone={statusTone(row.status)}>{statusLabel(row.status, locale)}</StatusPill>
          {annual && balancesEnabled ? (
            <span className="rounded-full border border-[#e8dfd0] bg-white/70 px-2 py-0.5 text-[11px] font-medium text-subtle/90">
              {Math.round(annual.current_balance * 10) / 10}/{Math.round(annual.entitlement_days * 10) / 10}
            </span>
          ) : null}
          {Number(row.shift_conflict_count || 0) > 0 ? (
            <span className="text-[11px] font-medium text-amber-800">{c.shiftConflicts}</span>
          ) : null}
        </div>
        <p className="mt-0.5 text-[12px] text-subtle/85">
          {typeLabel(row.leave_type, locale)} · {durationLabel(row.duration_unit, locale, row.half_portion)} ·{' '}
          {formatLeaveDates(row.start_date, row.end_date, locale)}
        </p>
        <p className="mt-0.5 text-[11px] text-subtle/75">
          {c.nextAction}: {nextActionLabel(row, locale)}
        </p>
      </button>
      <div className="relative flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={primaryKind === 'view_details' ? 'secondary' : 'default'}
          disabled={busy && primaryKind !== 'view_details'}
          onClick={runPrimary}
          data-primary-action={primaryKind}
        >
          {runningKey?.startsWith(`approve:${row.leave_id}`) ||
          runningKey?.startsWith(`dual:${row.leave_id}`) ||
          runningKey?.startsWith(`dual-confirm:${row.leave_id}`) ||
          runningKey?.startsWith(`cancel:${row.leave_id}`) ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : null}
          {primaryLabel}
        </Button>
        {canManage ? (
          <>
            <Button size="sm" variant="ghost" aria-label={c.more} onClick={onToggleMenu}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
            {menuOpen ? (
              <div className="absolute end-0 top-full z-20 mt-1 min-w-[12rem] rounded-xl border border-[#e8dfd0] bg-white p-1 shadow-md">
                {primaryKind !== 'view_details' ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                    onClick={() => {
                      onToggleMenu()
                      onOpen()
                    }}
                  >
                    {c.viewDetails}
                  </button>
                ) : null}
                {(status === 'requested' || status === 'needs_review') && primaryKind !== 'approve' ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                    disabled={busy}
                    onClick={() => {
                      onToggleMenu()
                      onAction('approve_leave_request', decisionArgs(row), { key: `approve:${row.leave_id}` })
                    }}
                  >
                    {c.approve}
                  </button>
                ) : null}
                {(status === 'requested' || status === 'needs_review') && (
                  <>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] text-[#8a3b2a] hover:bg-[#f7f1e6]"
                      disabled={busy}
                      onClick={() => {
                        onToggleMenu()
                        onAction('reject_leave_request', decisionArgs(row), {
                          key: `reject:${row.leave_id}`,
                          destructive: true,
                          confirm: {
                            title: locale === 'ar' ? 'رفض طلب الإجازة؟' : 'Decline this leave request?',
                            body: formatLeaveDates(row.start_date, row.end_date, locale),
                            confirmLabel: c.decline,
                          },
                        })
                      }}
                    >
                      {c.decline}
                    </button>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                      disabled={busy}
                      onClick={() => {
                        onToggleMenu()
                        onAction(
                          'return_leave_for_info',
                          decisionArgs(row, {
                            info_request: locale === 'ar' ? 'يرجى تقديم معلومات إضافية' : 'Please provide additional information',
                          }),
                          { key: `info:${row.leave_id}` },
                        )
                      }}
                    >
                      {c.needsInfo}
                    </button>
                  </>
                )}
                {isStale && primaryKind !== 'start_dual' ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                    disabled={busy}
                    onClick={() => {
                      onToggleMenu()
                      onAction('initiate_leave_stale_dual_control', { leave_id: row.leave_id, action_kind: 'expire_stale' }, {
                        key: `dual:${row.leave_id}`,
                        confirm: {
                          title: c.dualInitiate,
                          body: locale === 'ar' ? 'يبدأ اعتماداً مزدوجاً لحل الطلب المتأخر.' : 'Starts audited dual-control for this stale request.',
                          confirmLabel: c.dualInitiate,
                        },
                      })
                    }}
                  >
                    {c.dualInitiate}
                  </button>
                ) : null}
                {primaryKind !== 'confirm_dual' && (row.dual_control_pending || row.dual_pending || row.dual_control_status) ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] hover:bg-[#f7f1e6]"
                    disabled={busy}
                    onClick={() => {
                      onToggleMenu()
                      onAction(
                        'confirm_leave_stale_dual_control',
                        { leave_id: row.leave_id, dual_action_id: row.dual_action_id || undefined },
                        {
                          key: `dual-confirm:${row.leave_id}`,
                          confirm: {
                            title: c.dualConfirm,
                            body: c.dualConfirmBody,
                            confirmLabel: c.dualConfirm,
                          },
                        },
                      )
                    }}
                  >
                    {c.dualConfirm}
                  </button>
                ) : null}
                {status === 'needs_info' ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] text-[#8a3b2a] hover:bg-[#f7f1e6]"
                    disabled={busy}
                    onClick={() => {
                      onToggleMenu()
                      onAction('withdraw_leave_request', decisionArgs(row), {
                        key: `withdraw:${row.leave_id}`,
                        destructive: true,
                        confirm: {
                          title: locale === 'ar' ? 'سحب الطلب؟' : 'Withdraw this request?',
                          body: formatLeaveDates(row.start_date, row.end_date, locale),
                          confirmLabel: c.withdraw,
                        },
                      })
                    }}
                  >
                    {c.withdraw}
                  </button>
                ) : null}
                {status === 'approved' && primaryKind !== 'cancel' ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-[13px] text-[#8a3b2a] hover:bg-[#f7f1e6]"
                    disabled={busy}
                    onClick={() => {
                      onToggleMenu()
                      onAction('cancel_leave_request', decisionArgs(row), {
                        key: `cancel:${row.leave_id}`,
                        destructive: true,
                        confirm: {
                          title: locale === 'ar' ? 'إلغاء هذه الإجازة؟' : 'Cancel this leave?',
                          body: formatLeaveDates(row.start_date, row.end_date, locale),
                          confirmLabel: c.cancel,
                        },
                      })
                    }}
                  >
                    {c.cancel}
                  </button>
                ) : null}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}

export function LeaveWorkspace({ access, permissions, role: _role, onNotice, onAccessIssue }: LeaveWorkspaceProps) {
  const locale = useEmployees360Locale()
  const c = leaveCopy(locale)
  const isAr = locale === 'ar'
  const [view, setView] = useUrlBackedTab<'active' | 'history'>('leave', URL_BACKED_VIEW_PAGES.leave, 'active', 'view')
  const [historyStatus, setHistoryStatus] = useState('')
  const [showFile, setShowFile] = useState(false)
  const [selected, setSelected] = useState<PosthireLeaveRow | null>(null)
  const [surfaceError, setSurfaceError] = useState<string | null>(null)
  const [menuFor, setMenuFor] = useState<string | null>(null)

  const { data, loading, refreshing, error, reload } = useLeaveData(access, view, historyStatus, onAccessIssue)
  const action = useLeaveAction(access, reload, onNotice, onAccessIssue, locale, setSurfaceError)
  useVisibilitySoftPoll(reload, FRESHNESS_MS.inboundQueue, true)

  const canManage = can(permissions, 'leave.decide')
  const canFile = can(permissions, 'leave.request')

  const [extraPending, setExtraPending] = useState<PosthireLeaveRow[]>([])
  const [extraUpcoming, setExtraUpcoming] = useState<PosthireLeaveRow[]>([])
  const [extraHistory, setExtraHistory] = useState<PosthireLeaveRow[]>([])
  const [extraBalances, setExtraBalances] = useState<Record<string, LeaveBalance[]>>({})
  const [loadingSection, setLoadingSection] = useState<'pending' | 'upcoming' | 'history' | null>(null)

  useEffect(() => {
    setExtraPending([])
    setExtraUpcoming([])
    setExtraHistory([])
    setExtraBalances({})
    setSurfaceError(null)
    setMenuFor(null)
    // Rematch open drawer by leave_id so soft reload after approve/decline
    // does not slam the detail closed mid-flow.
    setSelected((current) => {
      if (!current) return null
      const id = String(current.leave_id || '')
      if (!id || !data) return current
      const pool = [...(data.pending || []), ...(data.upcoming || []), ...(data.history || [])]
      return pool.find((row) => String(row.leave_id || '') === id) || current
    })
  }, [data])

  const pending = useMemo(() => [...(data?.pending ?? []), ...extraPending], [data?.pending, extraPending])
  const upcoming = useMemo(() => [...(data?.upcoming ?? []), ...extraUpcoming], [data?.upcoming, extraUpcoming])
  const history = useMemo(() => [...(data?.history ?? []), ...extraHistory], [data?.history, extraHistory])
  const balances = useMemo(() => ({ ...(data?.balances ?? {}), ...extraBalances }), [data?.balances, extraBalances])
  const balancesEnabled = Boolean(data?.balances_enabled)
  const pendingTotal = data?.pending_total ?? pending.length
  const upcomingTotal = data?.upcoming_total ?? upcoming.length
  const historyTotal = data?.history_total ?? history.length

  const holiday = data?.holiday_year
  const showHolidayBanner = Boolean(holiday && holiday.status && holiday.status !== 'approved')

  const loadMoreLeave = useCallback(
    async (sec: 'pending' | 'upcoming' | 'history') => {
      setLoadingSection(sec)
      try {
        if (sec === 'history') {
          const res = await getPosthireLeave(access, { view: 'history', status: historyStatus || undefined, offset: history.length })
          setExtraHistory((prev) => [...prev, ...(res.history ?? [])])
          if (res.balances) setExtraBalances((prev) => ({ ...prev, ...res.balances }))
        } else {
          const offset = sec === 'pending' ? pending.length : upcoming.length
          const res = await getPosthireLeave(access, { view: 'active', section: sec, offset })
          const rows = (sec === 'pending' ? res.pending : res.upcoming) ?? []
          if (sec === 'pending') setExtraPending((prev) => [...prev, ...rows])
          else setExtraUpcoming((prev) => [...prev, ...rows])
          if (res.balances) setExtraBalances((prev) => ({ ...prev, ...res.balances }))
        }
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        onNotice(friendlyError(err, c.retry, locale), 'error')
      } finally {
        setLoadingSection(null)
      }
    },
    [access, historyStatus, history.length, pending.length, upcoming.length, onAccessIssue, onNotice, c.retry, locale],
  )

  const selectedBalances = selected?.employee_key ? balances[selected.employee_key] ?? [] : []

  return (
    <div
      className="space-y-5"
      dir={isAr ? 'rtl' : 'ltr'}
      lang={isAr ? 'ar' : 'en'}
      data-testid="leave-workspace"
      data-leave-queue
    >
      <ConfigureInSetupBanner
        title={isAr ? 'سياسة الإجازات للشركة' : 'Company leave policy'}
        body={
          isAr
            ? 'أنواع الإجازة والأهلية والاستحقاق تُضبط في وحدة الإعداد. هنا الطلبات والأرصدة والاعتمادات فقط.'
            : 'Leave types, eligibility, and entitlement are configured in Setup Console. This workspace owns requests, balances, and approvals.'
        }
        anchor="classic-module-leave"
        locale={locale}
      />
      {showFile ? (
        <FileLeaveModal
          access={access}
          locale={locale}
          onClose={() => setShowFile(false)}
          onNotice={onNotice}
          onDone={() => void reload()}
          onAccessIssue={onAccessIssue}
        />
      ) : null}
      {selected ? (
        <LeaveDetailDrawer
          row={selected}
          locale={locale}
          balances={selectedBalances}
          balancesEnabled={balancesEnabled}
          canManage={canManage}
          busy={action.busy}
          runningKey={action.runningKey}
          onClose={() => setSelected(null)}
          onAction={action.run}
        />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2" data-leave-filters>
          <Button variant={view === 'active' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('active')}>
            {c.active}
          </Button>
          <Button variant={view === 'history' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('history')}>
            {c.history}
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {canFile ? (
            <Button size="sm" onClick={() => setShowFile(true)}>
              <Plus className="h-4 w-4" /> {c.fileLeave}
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void reload()}
            disabled={refreshing}
            aria-label={isAr ? 'تحديث طلبات الإجازة' : 'Refresh leave requests'}
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {balancesEnabled || data?.balances_enforced === false ? (
        <p className="rounded-[1rem] border border-[#e8dfd0] bg-[#fffdf8]/80 px-4 py-2.5 text-[12px] leading-5 text-subtle/85">{c.balancesBanner}</p>
      ) : null}
      {showHolidayBanner ? (
        <p className="rounded-[1rem] border border-[#e8c9a0] bg-wf-accent-review-soft/70 px-4 py-2.5 text-[12px] leading-5 text-wf-accent-review-ink" role="alert">
          {isAr ? holiday?.message_ar || c.holidayPending : holiday?.message_en || c.holidayPending}
        </p>
      ) : null}
      {surfaceError ? <BlockedReason reason={surfaceError} locale={locale} /> : null}

      {loading ? (
        <div className="flex items-center justify-center gap-2 rounded-[var(--radius-wf-panel)] border border-dashed border-[#e8dfd0] bg-[#fffdf8]/70 px-6 py-16 text-[13px] text-subtle">
          <Loader2 className="h-4 w-4 animate-spin" /> {c.loading}
        </div>
      ) : error ? (
        <div className="space-y-3 rounded-[var(--radius-wf-panel)] border border-rose-200/80 bg-rose-50/50 px-6 py-10 text-center">
          <p className="text-[14px] font-medium text-rose-800">{error}</p>
          <Button size="sm" variant="secondary" onClick={() => void reload()}>
            {c.retry}
          </Button>
        </div>
      ) : view === 'history' ? (
        <div className="space-y-3 rounded-[1.25rem] border border-[#e8dfd0]/80 bg-[#fbf7f0]/55 p-4" data-leave-history>
          <div className="flex flex-row flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[14px] font-semibold text-text">{c.historyTitle}</p>
              <p className="text-[12px] text-subtle/85">{c.historyHint}</p>
            </div>
            <Select className="h-9 w-auto" value={historyStatus} onChange={(e) => setHistoryStatus(e.target.value)}>
              <option value="">{c.allStatuses}</option>
              <option value="approved">{statusLabel('approved', locale)}</option>
              <option value="rejected">{statusLabel('rejected', locale)}</option>
              <option value="cancelled">{statusLabel('cancelled', locale)}</option>
              <option value="withdrawn">{statusLabel('withdrawn', locale)}</option>
              <option value="requested">{statusLabel('requested', locale)}</option>
            </Select>
          </div>
          {history.length === 0 ? (
            <WorkflowEmpty icon={<CalendarDays className="h-5 w-5" />} title={c.emptyHistory} hint={c.historyHint} />
          ) : (
            <div className="overflow-x-auto rounded-[1.1rem] border border-[#e8dfd0] bg-white/50">
              <table className="w-full min-w-[640px] text-start text-[13px]">
                <thead className="bg-[#f7f1e6]/80 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                  <tr>
                    <th className="px-4 py-3 font-medium">{isAr ? 'الموظف' : 'Employee'}</th>
                    <th className="px-4 py-3 font-medium">{c.type}</th>
                    <th className="px-4 py-3 font-medium">{c.duration}</th>
                    <th className="px-4 py-3 font-medium">{c.dates}</th>
                    <th className="px-4 py-3 font-medium">{c.status}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e8dfd0]/70">
                  {history.map((row, idx) => (
                    <tr
                      key={row.leave_id || idx}
                      className="cursor-pointer hover:bg-[#fffdf8]"
                      onClick={() => setSelected(row)}
                    >
                      <td className="px-4 py-3 font-semibold text-text">{row.employee_name || '—'}</td>
                      <td className="px-4 py-3 text-subtle/90">{typeLabel(row.leave_type, locale)}</td>
                      <td className="px-4 py-3 text-subtle/90">{durationLabel(row.duration_unit, locale, row.half_portion)}</td>
                      <td className="px-4 py-3 text-subtle/90">{formatLeaveDates(row.start_date, row.end_date, locale)}</td>
                      <td className="px-4 py-3">
                        <StatusPill tone={statusTone(row.status)}>{statusLabel(row.status, locale)}</StatusPill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <LoadMoreBar
                loaded={history.length}
                total={historyTotal}
                loading={loadingSection === 'history'}
                onLoadMore={() => void loadMoreLeave('history')}
                noun={isAr ? 'سجل' : 'record'}
              />
            </div>
          )}
        </div>
      ) : (
        <>
          <div
            className={cn(
              'flex gap-3 rounded-[1.25rem] border px-4 py-3.5',
              pendingTotal ? 'border-[#e8c9a0] bg-wf-accent-review-soft/50' : 'border-[#e8dfd0] bg-[#fffdf8]/70',
            )}
            data-leave-attention
          >
            <CalendarClock className="mt-0.5 h-5 w-5 shrink-0 text-subtle" />
            <div>
              <p className="text-[14px] font-semibold text-text">
                {pendingTotal ? c.attentionWaiting(pendingTotal) : c.attentionEmpty}
              </p>
              <p className="mt-0.5 text-[12px] text-subtle/90">
                {pendingTotal ? c.pendingHint : `${upcomingTotal} ${isAr ? 'إجازة قادمة معتمدة' : 'upcoming approved leave'}`}
              </p>
            </div>
          </div>

          <section className="space-y-2.5" data-leave-pending>
            <div className="px-0.5">
              <p className="text-[14px] font-semibold text-text">{c.pendingTitle}</p>
              <p className="text-[12px] text-subtle/85">{c.pendingHint}</p>
            </div>
            {pending.length === 0 ? (
              <WorkflowEmpty icon={<CalendarDays className="h-5 w-5" />} title={c.emptyPending} hint={c.pendingHint} />
            ) : (
              <div className="space-y-2.5">
                {pending.map((row, idx) => {
                  const key = String(row.leave_id || idx)
                  return (
                    <LeaveRowCard
                      key={key}
                      row={row}
                      locale={locale}
                      balancesEnabled={balancesEnabled}
                      balances={balances}
                      canManage={canManage}
                      busy={action.busy}
                      runningKey={action.runningKey}
                      menuOpen={menuFor === key}
                      onToggleMenu={() => setMenuFor((cur) => (cur === key ? null : key))}
                      onOpen={() => setSelected(row)}
                      onAction={action.run}
                    />
                  )
                })}
                <LoadMoreBar
                  loaded={pending.length}
                  total={pendingTotal}
                  loading={loadingSection === 'pending'}
                  onLoadMore={() => void loadMoreLeave('pending')}
                  noun={isAr ? 'طلب' : 'request'}
                />
              </div>
            )}
          </section>

          <section className="space-y-2 border-t border-[#e8dfd0]/70 pt-4" data-leave-upcoming>
            <div className="px-0.5">
              <p className="text-[13px] font-semibold text-text/90">{c.upcomingTitle}</p>
              <p className="text-[12px] text-subtle/80">{c.upcomingHint}</p>
            </div>
            {upcoming.length === 0 ? (
              <WorkflowEmpty icon={<CalendarDays className="h-5 w-5" />} title={c.emptyUpcoming} hint={c.upcomingHint} />
            ) : (
              <div className="space-y-2">
                {upcoming.map((row, idx) => {
                  const key = `up:${row.leave_id || idx}`
                  return (
                    <LeaveRowCard
                      key={key}
                      row={row}
                      locale={locale}
                      balancesEnabled={balancesEnabled}
                      balances={balances}
                      canManage={canManage}
                      busy={action.busy}
                      runningKey={action.runningKey}
                      menuOpen={menuFor === key}
                      onToggleMenu={() => setMenuFor((cur) => (cur === key ? null : key))}
                      onOpen={() => setSelected(row)}
                      onAction={action.run}
                    />
                  )
                })}
                <LoadMoreBar
                  loaded={upcoming.length}
                  total={upcomingTotal}
                  loading={loadingSection === 'upcoming'}
                  onLoadMore={() => void loadMoreLeave('upcoming')}
                  noun={isAr ? 'إجازة' : 'leave'}
                />
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default LeaveWorkspace
