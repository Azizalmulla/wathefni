/**
 * Shifts Wave 3 — controlled scheduling workspace (HR + scoped managers).
 * Direct assign without enterprise templates. Does not import PostHire.tsx.
 */
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  History,
  Loader2,
  RefreshCw,
  Repeat,
  ShieldAlert,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Textarea } from '@/components/ui/field'
import { LoadMoreBar } from '@/components/ui/load-more-bar'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  cancelShift,
  DashboardApiError,
  getPosthireShiftHistory,
  getPosthireShifts,
  rescheduleShift,
  resolveShiftReconciliation,
  runPosthireAction,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { BlockedReason, useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import {
  formatShiftWindow,
  shiftStatusLabel,
  shiftStatusTone,
  shiftsCopy,
  type ShiftsLocale,
} from '@/posthire/shiftsUx'
import type {
  DashboardAccess,
  PosthireActionResult,
  PosthireShiftHistoryResponse,
  PosthireShiftRow,
  PosthireShiftsResponse,
  PosthireSwapRow,
} from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type ShiftsWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

type Tab = 'board' | 'swaps' | 'availability' | 'reconciliation' | 'reminders'

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

function friendlyError(error: unknown, fallback: string, locale: ShiftsLocale): string {
  const c = shiftsCopy(locale)
  if (error instanceof DashboardApiError) {
    const code = String(error.code || '').toLowerCase()
    if (code.includes('allowlist') || code === 'permission_denied') return c.allowlistDenied
    if (code === 'out_of_scope') return c.outOfScope
    if (code.includes('stale')) return c.staleConflict
    if (code.includes('self_')) return c.selfDecisionDenied
    const message = error.message || ''
    if (message && !/(_|traceback|exception|psycopg)/i.test(message)) return message
  }
  if (error instanceof Error && error.message && !/(_|traceback|exception)/i.test(error.message)) return error.message
  return fallback
}

function mapActionSurface(code: string | null | undefined, locale: ShiftsLocale): string | null {
  if (!code) return null
  const c = shiftsCopy(locale)
  const k = String(code).toLowerCase()
  if (k.includes('stale')) return c.staleConflict
  if (k.includes('allowlist') || k.includes('permission')) return c.allowlistDenied
  if (k.includes('out_of_scope') || k.includes('outside_manager')) return c.outOfScope
  if (k.includes('self_')) return c.selfDecisionDenied
  return null
}

function actionErrorCode(result: PosthireActionResult | null | undefined): string | null {
  if (!result) return null
  const fromResult = result.result
  if (fromResult && typeof fromResult.error === 'string') return fromResult.error
  if (result.status === 'permission_denied') return 'permission_denied'
  return null
}

function useShiftsData(
  access: DashboardAccess,
  week: number,
  view: 'day' | 'week',
  filters: Record<string, string>,
  onAccessIssue?: (issue: AccessIssue) => void,
) {
  const locale = useEmployees360Locale()
  const [data, setData] = useState<PosthireShiftsResponse | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setRefreshing(true)
    setError(null)
    try {
      const next = await getPosthireShifts(access, week, { view, ...filters })
      if (requestId !== requestIdRef.current) return
      setData(next)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(friendlyError(err, shiftsCopy(locale).retry, locale))
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false)
    }
  }, [access, week, view, filters, onAccessIssue, locale])

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, refreshing, error, reload, loading: refreshing && !data }
}

function HonestyBanner({ locale, wave3 }: { locale: ShiftsLocale; wave3?: PosthireShiftsResponse['wave3'] }) {
  const c = shiftsCopy(locale)
  if (!wave3?.enabled) return null
  return (
    <div
      className="space-y-2 rounded-[1.1rem] border border-[#e8dfd0] bg-[#fffdf8] px-4 py-3 text-[13px] leading-6 text-subtle/95"
      data-testid="shifts-honesty-banner"
    >
      <p>{c.honesty}</p>
      <div className="flex flex-wrap gap-2">
        {wave3.real_mutation_gate ? <StatusPill tone="warning">{c.realGateOn}</StatusPill> : null}
        <StatusPill tone="paused">{c.timersDisabled}</StatusPill>
        <StatusPill tone="info">{c.remindersSynthetic}</StatusPill>
        <StatusPill tone="neutral">{c.talalReadOnly}</StatusPill>
      </div>
    </div>
  )
}

function RescheduleModal({
  access,
  shift,
  locale,
  onClose,
  onNotice,
  onDone,
  onAccessIssue,
  requireReason,
}: {
  access: DashboardAccess
  shift: PosthireShiftRow
  locale: ShiftsLocale
  onClose: () => void
  onNotice: NoticeFn
  onDone: () => void
  onAccessIssue?: (issue: AccessIssue) => void
  requireReason: boolean
}) {
  const c = shiftsCopy(locale)
  const confirm = useConfirm()
  const [shiftDate, setShiftDate] = useState((shift.shift_date || '').slice(0, 10))
  const [startTime, setStartTime] = useState((shift.start_time || '').toString().slice(0, 5))
  const [endTime, setEndTime] = useState((shift.end_time || '').toString().slice(0, 5))
  const [reason, setReason] = useState('')
  const [ackAvail, setAckAvail] = useState(false)
  const [ackLeave, setAckLeave] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const overnight = Boolean(startTime && endTime && endTime <= startTime)
  const ready = Boolean(shiftDate && startTime && endTime && (!requireReason || reason.trim().length >= 3))

  const submit = async () => {
    if (!ready || !shift.updated_at) {
      setError(requireReason ? c.reasonRequired : c.staleConflict)
      return
    }
    if (
      !(await confirm({
        title: c.reschedule,
        body: formatShiftWindow(shiftDate, startTime, endTime, overnight, locale),
        confirmLabel: c.save,
      }))
    )
      return
    setBusy(true)
    setError(null)
    try {
      const res = await rescheduleShift(access, shift.shift_id || '', {
        shift_date: shiftDate,
        start_time: startTime,
        end_time: endTime,
        expected_updated_at: String(shift.updated_at),
        acknowledge_availability: ackAvail,
        allow_leave_conflicts: ackLeave,
        reason: reason || undefined,
      })
      onNotice(res.message || c.reschedule, 'success')
      onDone()
      onClose()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(friendlyError(err, c.retry, locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/35 px-3 py-4 backdrop-blur-sm sm:items-center sm:px-4" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-[1.6rem] border border-line/60 bg-panel/97 p-5 shadow-[0_30px_80px_rgba(24,20,15,0.28)] sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[15px] font-semibold text-text">{c.reschedule}</p>
            <p className="text-[13px] text-subtle/90">{shift.employee_name}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={c.close}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-[12px] text-subtle">
            {c.date}
            <Input type="date" value={shiftDate} onChange={(e) => setShiftDate(e.target.value)} />
          </label>
          <label className="space-y-1 text-[12px] text-subtle">
            {c.start}
            <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
          </label>
          <label className="space-y-1 text-[12px] text-subtle">
            {c.end}
            <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
          </label>
        </div>
        {overnight ? <p className="mt-2 text-[12px] text-amber-700">{c.overnightHint}</p> : null}
        <label className="mt-3 block space-y-1 text-[12px] text-subtle">
          {c.reason}
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
        </label>
        <label className="mt-2 flex items-center gap-2 text-[12.5px] text-text">
          <input type="checkbox" checked={ackAvail} onChange={(e) => setAckAvail(e.target.checked)} />
          {c.ackAvailability}
        </label>
        <label className="mt-1 flex items-center gap-2 text-[12.5px] text-text">
          <input type="checkbox" checked={ackLeave} onChange={(e) => setAckLeave(e.target.checked)} />
          {c.ackLeave}
        </label>
        {error ? <p className="mt-3 text-[13px] text-rose-600">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
            {c.close}
          </Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !ready}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
            {c.save}
          </Button>
        </div>
      </div>
    </div>
  )
}

function HistoryDrawer({
  access,
  shiftId,
  locale,
  onClose,
  onAccessIssue,
}: {
  access: DashboardAccess
  shiftId: string
  locale: ShiftsLocale
  onClose: () => void
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const c = shiftsCopy(locale)
  const [data, setData] = useState<PosthireShiftHistoryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const next = await getPosthireShiftHistory(access, shiftId)
        if (!cancelled) setData(next)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue?.(issue)
        else if (!cancelled) setError(friendlyError(err, c.retry, locale))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [access, shiftId, locale, onAccessIssue, c.retry])

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div className="flex h-full w-full max-w-lg flex-col border-line/60 bg-panel/98 shadow-xl sm:border-l">
        <div className="flex items-center justify-between border-b border-line/50 px-4 py-3">
          <div>
            <p className="font-semibold text-text">{c.history}</p>
            <p className="text-[12px] text-subtle">{c.lineage}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <p className="text-[13px] text-subtle">{c.loading}</p>
            ) : error ? (
            <BlockedReason reason={error} locale={locale} />
          ) : (
            <div className="space-y-3">
              {(data?.versions || []).map((v, idx) => (
                <div key={String(v.version_id || idx)} className="rounded-[1rem] border border-line/50 bg-white/60 px-3 py-2.5 text-[13px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill tone={v.is_current ? 'success' : 'paused'}>
                      {v.is_current ? c.currentVersion : c.priorVersion} · v{String(v.version_no ?? '—')}
                    </StatusPill>
                    <span className="text-subtle">{String(v.reason_code || '')}</span>
                  </div>
                  <p className="mt-1 text-text">
                    {formatShiftWindow(String(v.shift_date || ''), String(v.start_time || ''), String(v.end_time || ''), Boolean(v.ends_next_day), locale)}
                  </p>
                  {v.previous_employee_key ? (
                    <p className="mt-1 text-[12px] text-subtle">← {String(v.previous_employee_key)}</p>
                  ) : null}
                </div>
              ))}
              {(data?.versions || []).length === 0 ? (
                <WorkflowEmpty title={c.history} hint={(data?.events || []).length ? String((data?.events || []).length) : c.emptyBoard} />
              ) : null}
              {(data?.events || []).slice(-8).map((ev, idx) => (
                <div key={String(ev.event_id || idx)} className="text-[12px] text-subtle">
                  {String(ev.event_type || '')} · {String(ev.created_at || '').slice(0, 19)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function ShiftsWorkspace({ access, permissions, role: _role, onNotice, onAccessIssue }: ShiftsWorkspaceProps) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = shiftsCopy(locale)
  const confirm = useConfirm()
  const canManage = can(permissions, 'shifts.manage')

  const [week, setWeek] = useState(0)
  const [view, setView] = useState<'day' | 'week'>('week')
  const [tab, setTab] = useState<Tab>('board')
  const [filters, setFilters] = useState({ employee: '', branch_key: '', site_key: '', team_key: '', role: '' })
  const filterKey = useMemo(() => ({ ...filters }), [filters])

  const { data, loading, refreshing, error, reload } = useShiftsData(access, week, view, filterKey, onAccessIssue)
  const [extraShifts, setExtraShifts] = useState<PosthireShiftRow[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  const [rowBusy, setRowBusy] = useState<string | null>(null)
  const [editShift, setEditShift] = useState<PosthireShiftRow | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState<string | null>(null)

  useEffect(() => {
    setExtraShifts([])
  }, [data])

  const baseShifts = data?.shifts ?? []
  const shifts = [...baseShifts, ...extraShifts]
  const totalShifts = data?.total_count ?? baseShifts.length
  const swaps = data?.swaps ?? []
  const availability = data?.availability ?? []
  const recon = data?.reconciliation_flags ?? []
  const reminders = data?.terminal_reminders ?? []
  const wave3 = data?.wave3
  // Real mutations need reason when gate on; synthetic subjects still work without allowlist.
  const needsAuditReason = Boolean(wave3?.enabled && wave3?.real_mutation_gate)

  const [form, setForm] = useState({
    employee_name: '',
    shift_date: '',
    start_time: '',
    end_time: '',
    site_key: '',
    branch_key: '',
    team_key: '',
    role: '',
    reason: '',
    ack_availability: false,
    ack_leave: false,
  })
  const formOvernight = Boolean(form.start_time && form.end_time && form.end_time <= form.start_time)
  const formReady = Boolean(form.employee_name.trim() && form.shift_date && form.start_time && form.end_time)

  const weekLabel =
    data?.start_date && data?.end_date
      ? view === 'day'
        ? String(data.start_date)
        : `${data.start_date} – ${data.end_date}`
      : c.thisWeek

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await getPosthireShifts(access, week, { offset: shifts.length, view, ...filters })
      setExtraShifts((prev) => [...prev, ...(res.shifts ?? [])])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setLoadingMore(false)
    }
  }

  const runAction = async (actionType: string, args: Record<string, unknown>, key: string) => {
    setActionBusy(key)
    try {
      const result = await runPosthireAction(access, actionType, args)
      const code = actionErrorCode(result)
      const surface = mapActionSurface(code, locale)
      if (code && (result.status === 'failed' || result.status === 'permission_denied' || result.result?.ok === false)) {
        onNotice(surface || String(result.result?.message || code), 'error')
        return
      }
      if (result.result?.needs_confirmation) {
        onNotice(String(result.result?.message || c.ackAvailability), 'info')
        return
      }
      onNotice(String(result.result?.message || result.message || 'OK'), 'success')
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setActionBusy(null)
    }
  }

  const submitShift = () => {
    if (!formReady || !canManage) return
    void runAction(
      'create_shift_assignment',
      {
        employee_name: form.employee_name.trim(),
        shift_date: form.shift_date,
        start_time: form.start_time,
        end_time: form.end_time,
        site_key: form.site_key || undefined,
        branch_key: form.branch_key || undefined,
        team_key: form.team_key || undefined,
        role: form.role || undefined,
        reason: form.reason || undefined,
        ack_availability_conflict: form.ack_availability,
        allow_leave_conflicts: form.ack_leave,
      },
      'create-shift',
    ).then(() => {
      setForm((f) => ({ ...f, employee_name: '', shift_date: '', start_time: '', end_time: '', reason: '' }))
    })
  }

  const runCancel = async (shift: PosthireShiftRow) => {
    if (!shift.shift_id) return
    const reason = needsAuditReason ? window.prompt(c.reason) || '' : 'soft-cancel'
    if (needsAuditReason && reason.trim().length < 3) {
      onNotice(c.reasonRequired, 'error')
      return
    }
    if (
      !(await confirm({
        title: c.softCancel,
        body: formatShiftWindow(shift.shift_date, shift.start_time, shift.end_time, Boolean(shift.ends_next_day), locale),
        confirmLabel: c.softCancel,
        destructive: true,
      }))
    )
      return
    setRowBusy(shift.shift_id)
    try {
      const res = await cancelShift(access, shift.shift_id, {
        expected_updated_at: shift.updated_at ? String(shift.updated_at) : undefined,
        reason,
        reason_code: 'cancelled',
      })
      onNotice(res.message || c.softCancel, 'success')
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setRowBusy(null)
    }
  }

  const resolveRecon = async (flagId: string, action: 'acknowledge' | 'cancel') => {
    const reason = action === 'cancel' ? window.prompt(c.reason) || '' : undefined
    if (action === 'cancel' && needsAuditReason && (reason || '').trim().length < 3) {
      onNotice(c.reasonRequired, 'error')
      return
    }
    setActionBusy(`recon:${flagId}`)
    try {
      await resolveShiftReconciliation(access, flagId, { action, reason })
      onNotice(action === 'acknowledge' ? c.acknowledge : c.resolveCancel, 'success')
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setActionBusy(null)
    }
  }

  // Group same-day windows (split) without duplicating overnight authority rows.
  const boardByDate = useMemo(() => {
    const map = new Map<string, PosthireShiftRow[]>()
    for (const s of shifts) {
      const d = String(s.shift_date || '').slice(0, 10) || '—'
      const list = map.get(d) || []
      list.push(s)
      map.set(d, list)
      if (s.ends_next_day || s.is_overnight) {
        // Visual span marker only — do not clone the authority row into the next day bucket as a second assignment.
        const nextKey = `${d}+1`
        const ghost = map.get(nextKey) || []
        if (!ghost.some((g) => g.shift_id === s.shift_id)) {
          ghost.push({ ...s, ui_state: s.ui_state, _overnight_span: true } as PosthireShiftRow)
          map.set(nextKey, ghost)
        }
      }
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [shifts])

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'board', label: c.board, count: totalShifts },
    { id: 'swaps', label: c.swaps, count: swaps.length },
    { id: 'availability', label: c.availability, count: availability.length },
    { id: 'reconciliation', label: c.reconciliation, count: recon.length },
    { id: 'reminders', label: c.reminders, count: reminders.length },
  ]

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="shifts-workspace">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-text">{c.title}</h2>
          <p className="mt-1 max-w-2xl text-[13.5px] leading-6 text-subtle/95">{c.subtitle}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void reload()} disabled={refreshing}>
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {c.refresh}
        </Button>
      </div>

      <HonestyBanner locale={locale} wave3={wave3} />

      {loading ? (
        <Card>
          <CardContent className="py-10 text-center text-[13px] text-subtle">{c.loading}</CardContent>
        </Card>
      ) : error ? (
        <div className="space-y-2">
          <BlockedReason reason={error} locale={locale} />
          <Button size="sm" onClick={() => void reload()}>
            {c.retry}
          </Button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2" role="tablist" aria-label={c.title}>
            {tabs.map((t) => (
              <Button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                variant={tab === t.id ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {typeof t.count === 'number' ? <span className="ms-1 text-subtle">({t.count})</span> : null}
              </Button>
            ))}
          </div>

          {tab === 'board' ? (
            <>
              {canManage ? (
                <Card data-testid="shifts-create-card">
                  <CardHeader>
                    <CardTitle>{c.schedule}</CardTitle>
                    <CardDescription>{c.scheduleHint}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <Input
                        placeholder={c.employee}
                        value={form.employee_name}
                        onChange={(e) => setForm((f) => ({ ...f, employee_name: e.target.value }))}
                      />
                      <Input type="date" value={form.shift_date} onChange={(e) => setForm((f) => ({ ...f, shift_date: e.target.value }))} />
                      <Input type="time" value={form.start_time} onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))} />
                      <Input type="time" value={form.end_time} onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))} />
                      <Input placeholder={c.site} value={form.site_key} onChange={(e) => setForm((f) => ({ ...f, site_key: e.target.value }))} />
                      <Input placeholder={c.branch} value={form.branch_key} onChange={(e) => setForm((f) => ({ ...f, branch_key: e.target.value }))} />
                      <Input placeholder={c.team} value={form.team_key} onChange={(e) => setForm((f) => ({ ...f, team_key: e.target.value }))} />
                      <Input placeholder={c.role} value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} />
                    </div>
                    {formOvernight ? (
                      <p className="text-[12.5px] text-amber-800">
                        {c.overnight} — {c.overnightHint}
                      </p>
                    ) : null}
                    <Textarea
                      placeholder={c.reason}
                      value={form.reason}
                      onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
                      rows={2}
                    />
                    <div className="flex flex-wrap gap-4 text-[12.5px]">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={form.ack_availability}
                          onChange={(e) => setForm((f) => ({ ...f, ack_availability: e.target.checked }))}
                        />
                        {c.ackAvailability}
                      </label>
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={form.ack_leave} onChange={(e) => setForm((f) => ({ ...f, ack_leave: e.target.checked }))} />
                        {c.ackLeave}
                      </label>
                    </div>
                    <div className="flex justify-end">
                      <Button size="sm" disabled={!formReady || actionBusy === 'create-shift'} onClick={submitShift}>
                        {actionBusy === 'create-shift' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                        {c.create}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : null}

              <Card>
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                  <div>
                    <CardTitle>{c.board}</CardTitle>
                    <CardDescription>
                      {weekLabel} · {totalShifts}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Button variant={view === 'day' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('day')}>
                      {c.day}
                    </Button>
                    <Button variant={view === 'week' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('week')}>
                      {c.week}
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setWeek((w) => w - 1)} aria-label="prev">
                      <ArrowRight className={cn('h-4 w-4', isAr ? '' : 'rotate-180')} />
                    </Button>
                    <Button variant={week === 0 ? 'secondary' : 'ghost'} size="sm" disabled={week === 0} onClick={() => setWeek(0)}>
                      {c.thisWeek}
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setWeek((w) => w + 1)} aria-label="next">
                      <ArrowRight className={cn('h-4 w-4', isAr ? 'rotate-180' : '')} />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" data-testid="shifts-filters">
                    <Input
                      placeholder={c.employee}
                      value={filters.employee}
                      onChange={(e) => setFilters((f) => ({ ...f, employee: e.target.value }))}
                    />
                    <Input placeholder={c.branch} value={filters.branch_key} onChange={(e) => setFilters((f) => ({ ...f, branch_key: e.target.value }))} />
                    <Input placeholder={c.site} value={filters.site_key} onChange={(e) => setFilters((f) => ({ ...f, site_key: e.target.value }))} />
                    <Input placeholder={c.team} value={filters.team_key} onChange={(e) => setFilters((f) => ({ ...f, team_key: e.target.value }))} />
                    <Input placeholder={c.role} value={filters.role} onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))} />
                  </div>

                  {shifts.length === 0 ? (
                    <WorkflowEmpty icon={<CalendarDays className="h-5 w-5" />} title={c.emptyBoard} hint={c.scheduleHint} />
                  ) : (
                    <div className="space-y-4" data-testid="shifts-board">
                      {boardByDate.map(([dateKey, rows]) => (
                        <div key={dateKey}>
                          <p className="mb-2 text-[11.5px] font-medium uppercase tracking-[0.08em] text-subtle/80">
                            {dateKey.endsWith('+1') ? `${dateKey.slice(0, -2)} (+1)` : dateKey}
                            {rows.some((r) => !(r as { _overnight_span?: boolean })._overnight_span) &&
                            rows.filter((r) => !(r as { _overnight_span?: boolean })._overnight_span).length > 1 ? (
                              <span className="ms-2 normal-case tracking-normal text-subtle/70">· {c.splitHint}</span>
                            ) : null}
                          </p>
                          <div className="overflow-x-auto rounded-[1.1rem] border border-line/50">
                            <table className="w-full min-w-[720px] text-left text-[13px]">
                              <thead className="bg-panel-muted/60 text-[11.5px] uppercase tracking-[0.06em] text-subtle/80">
                                <tr>
                                  <th className="px-3 py-2.5 font-medium">{c.employee}</th>
                                  <th className="px-3 py-2.5 font-medium">{c.start}–{c.end}</th>
                                  <th className="px-3 py-2.5 font-medium">{c.site}</th>
                                  <th className="px-3 py-2.5 font-medium">Status</th>
                                  <th className="px-3 py-2.5 text-end font-medium"> </th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-line/45">
                                {rows.map((shift, idx) => {
                                  const span = Boolean((shift as { _overnight_span?: boolean })._overnight_span)
                                  const ui = shift.ui_state || shift.status || 'scheduled'
                                  return (
                                    <tr
                                      key={`${shift.shift_id || idx}-${span ? 'span' : 'row'}`}
                                      className={cn('hover:bg-white/45', span && 'bg-amber-50/40')}
                                    >
                                      <td className="px-3 py-2.5 font-semibold text-text">
                                        {shift.employee_name || '—'}
                                        {span ? <span className="ms-2 text-[11px] font-normal text-amber-800">{c.overnight}</span> : null}
                                      </td>
                                      <td className="px-3 py-2.5 text-subtle/90">
                                        {formatShiftWindow(shift.shift_date, shift.start_time, shift.end_time, Boolean(shift.ends_next_day), locale)}
                                      </td>
                                      <td className="px-3 py-2.5 text-subtle/90">{shift.site_key || shift.location || '—'}</td>
                                      <td className="px-3 py-2.5">
                                        <StatusPill tone={shiftStatusTone(ui)}>{shiftStatusLabel(ui, locale)}</StatusPill>
                                      </td>
                                      <td className="px-3 py-2.5">
                                        <div className="flex flex-wrap items-center justify-end gap-1">
                                          {shift.shift_id && !span ? (
                                            <Button variant="ghost" size="sm" onClick={() => setHistoryId(shift.shift_id || null)}>
                                              <History className="h-3.5 w-3.5" />
                                              {c.history}
                                            </Button>
                                          ) : null}
                                          {canManage && shift.shift_id && !span && String(shift.status) === 'scheduled' ? (
                                            <>
                                              <Button variant="ghost" size="sm" disabled={rowBusy === shift.shift_id} onClick={() => setEditShift(shift)}>
                                                {c.edit}
                                              </Button>
                                              <Button
                                                variant="ghost"
                                                size="sm"
                                                className="text-rose-600"
                                                disabled={rowBusy === shift.shift_id}
                                                onClick={() => void runCancel(shift)}
                                              >
                                                {rowBusy === shift.shift_id ? <Loader2 className="h-4 w-4 animate-spin" /> : c.softCancel}
                                              </Button>
                                            </>
                                          ) : null}
                                          {!canManage && !span ? <span className="text-[12px] text-subtle">{c.noActions}</span> : null}
                                        </div>
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ))}
                      <LoadMoreBar loaded={shifts.length} total={totalShifts} loading={loadingMore} onLoadMore={() => void loadMore()} noun="shift" />
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          ) : null}

          {tab === 'swaps' ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Repeat className="h-4 w-4" /> {c.swaps}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {swaps.length === 0 ? (
                  <WorkflowEmpty title={c.emptySwaps} />
                ) : (
                  <div className="space-y-2.5">
                    {swaps.map((swap: PosthireSwapRow, idx: number) => (
                      <div key={swap.swap_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] border border-line/50 bg-panel/70 px-4 py-3">
                        <div>
                          <p className="font-semibold text-text">{swap.employee_name || swap.requester_employee_key || '—'}</p>
                          <p className="text-[12px] text-subtle">{String(swap.shift_date || '')}</p>
                        </div>
                        {canManage ? (
                          <div className="flex gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={Boolean(actionBusy)}
                              onClick={() => void runAction('reject_shift_swap', { swap_id: swap.swap_id }, `rej:${swap.swap_id}`)}
                            >
                              {c.decline}
                            </Button>
                            <Button size="sm" disabled={Boolean(actionBusy)} onClick={() => void runAction('approve_shift_swap', { swap_id: swap.swap_id }, `apr:${swap.swap_id}`)}>
                              {c.approve}
                            </Button>
                          </div>
                        ) : (
                          <StatusPill tone="review">{String(swap.status || 'requested')}</StatusPill>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}

          {tab === 'availability' ? (
            <Card>
              <CardHeader>
                <CardTitle>{c.availability}</CardTitle>
              </CardHeader>
              <CardContent>
                {availability.length === 0 ? (
                  <WorkflowEmpty title={c.emptyAvailability} />
                ) : (
                  <div className="space-y-2.5">
                    {availability.map((row, idx) => (
                      <div key={String(row.availability_id || idx)} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] border border-line/50 px-4 py-3">
                        <div>
                          <p className="font-semibold text-text">{String(row.employee_name || row.employee_key || '—')}</p>
                          <p className="text-[12px] text-subtle">
                            {String(row.start_date || '')} – {String(row.end_date || '')}
                          </p>
                        </div>
                        {canManage ? (
                          <div className="flex gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                void runAction('reject_availability', { availability_id: row.availability_id }, `av-rej:${row.availability_id}`)
                              }
                            >
                              {c.decline}
                            </Button>
                            <Button
                              size="sm"
                              onClick={() =>
                                void runAction('approve_availability', { availability_id: row.availability_id }, `av-apr:${row.availability_id}`)
                              }
                            >
                              {c.approve}
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}

          {tab === 'reconciliation' ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4" /> {c.reconciliation}
                </CardTitle>
                <CardDescription>{c.honesty}</CardDescription>
              </CardHeader>
              <CardContent>
                {recon.length === 0 ? (
                  <WorkflowEmpty title={c.emptyRecon} />
                ) : (
                  <div className="space-y-2.5">
                    {recon.map((flag, idx) => (
                      <div key={String(flag.flag_id || idx)} className="rounded-[1.1rem] border border-amber-200/80 bg-amber-50/40 px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <StatusPill tone="review">{String(flag.flag_type || '')}</StatusPill>
                            <p className="mt-1 font-semibold text-text">{String(flag.employee_key || '—')}</p>
                            <p className="text-[12px] text-subtle">{String(flag.shift_id || '')}</p>
                          </div>
                          {canManage ? (
                            <div className="flex gap-2">
                              <Button size="sm" variant="secondary" disabled={Boolean(actionBusy)} onClick={() => void resolveRecon(String(flag.flag_id), 'acknowledge')}>
                                {c.acknowledge}
                              </Button>
                              <Button size="sm" variant="ghost" className="text-rose-600" disabled={Boolean(actionBusy)} onClick={() => void resolveRecon(String(flag.flag_id), 'cancel')}>
                                {c.resolveCancel}
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}

          {tab === 'reminders' ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" /> {c.reminders}
                </CardTitle>
                <CardDescription>{c.remindersSynthetic}</CardDescription>
              </CardHeader>
              <CardContent>
                {reminders.length === 0 ? (
                  <WorkflowEmpty title={c.emptyReminders} />
                ) : (
                  <div className="space-y-2">
                    {reminders.map((r, idx) => (
                      <div key={String(r.reminder_id || idx)} className="rounded-[1rem] border border-line/50 px-3 py-2 text-[13px]">
                        <p className="font-medium text-text">{String(r.employee_key || r.shift_id || '—')}</p>
                        <p className="text-[12px] text-rose-700">{String(r.last_error || r.status || '')}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}
        </>
      )}

      {editShift ? (
        <RescheduleModal
          access={access}
          shift={editShift}
          locale={locale}
          onClose={() => setEditShift(null)}
          onNotice={onNotice}
          onDone={() => void reload()}
          onAccessIssue={onAccessIssue}
          requireReason={needsAuditReason}
        />
      ) : null}
      {historyId ? (
        <HistoryDrawer access={access} shiftId={historyId} locale={locale} onClose={() => setHistoryId(null)} onAccessIssue={onAccessIssue} />
      ) : null}
    </div>
  )
}

export default ShiftsWorkspace
