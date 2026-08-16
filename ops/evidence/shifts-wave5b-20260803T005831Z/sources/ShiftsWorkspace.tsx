/**
 * Shifts Wave 3 — controlled scheduling workspace.
 * UI/UX foundation: Wathefni CalendarShell (same product language).
 * Adapted for roster scheduling — not a literal calendar copy.
 * Does not import PostHire.tsx.
 */
import {
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Repeat,
  ShieldAlert,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { useConfirm } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/field'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  cancelShift,
  createShift,
  DashboardApiError,
  getPosthireShiftHistory,
  getPosthireShifts,
  listShiftRecurrences,
  listShiftTemplates,
  listSchedulePeriods,
  listOpenShifts,
  listCoverageRules,
  materializeShiftRecurrence,
  previewShiftRecurrence,
  rescheduleShift,
  resolveShiftReconciliation,
  runPosthireAction,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import {
  formatShiftWindow,
  shiftStatusLabel,
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

type QueueTab = 'board' | 'swaps' | 'availability' | 'reconciliation' | 'reminders' | 'templates' | 'publish'
type ViewMode = 'day' | 'week'

/** Visual-only overnight span into the next day — without duplicating schedule authority. */
type ShiftBoardItem = PosthireShiftRow & { spanMarker?: boolean }

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function addDays(d: Date, n: number) {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

function startOfWeek(d: Date) {
  const x = startOfDay(d)
  const day = x.getDay() // 0 Sun
  // Kuwait/work week often Sat–Fri; Calendar uses local week start — keep Sunday-based like CalendarShell
  const diff = day === 0 ? 0 : day
  return addDays(x, -diff)
}

function isoDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseIsoDate(s?: string | null): Date | null {
  const raw = String(s || '').slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null
  const [y, m, d] = raw.split('-').map(Number)
  return new Date(y, m - 1, d)
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

/** Calendar-aligned semantic surfaces adapted for shift states. */
function shiftSurfaceClass(shift: PosthireShiftRow) {
  const ui = String(shift.ui_state || shift.status || 'scheduled').toLowerCase()
  if (ui === 'cancelled' || String(shift.status).toLowerCase() === 'cancelled') {
    return 'border-transparent bg-[#ddd7cc] text-[#5b554c]'
  }
  if (ui === 'reconciliation_required') return 'border-transparent bg-[#efbdd7] text-[#482a3b]'
  if (ui === 'conflicted') return 'border-transparent bg-[#f3d85f] text-[#3b3212]'
  if (shift.ends_next_day || shift.is_overnight) return 'border-transparent bg-[#b9cde8] text-[#263247]'
  return 'border-transparent bg-[#e9e4d9] text-[#2f2c27]'
}

function weekOffsetFromAnchor(anchor: Date): number {
  const today = startOfDay(new Date())
  const a = startOfWeek(anchor)
  const t = startOfWeek(today)
  return Math.round((a.getTime() - t.getTime()) / (7 * 24 * 3600 * 1000))
}

function useShiftsData(
  access: DashboardAccess,
  week: number,
  view: ViewMode,
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
      const next = await getPosthireShifts(access, week, { view, limit: 200, ...filters })
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

  return { data, refreshing, error, reload, coldLoading: refreshing && !data }
}

function ShiftBlock({
  shift,
  locale,
  selected,
  onSelect,
  compact,
}: {
  shift: PosthireShiftRow
  locale: ShiftsLocale
  selected?: boolean
  onSelect: () => void
  compact?: boolean
}) {
  const c = shiftsCopy(locale)
  const start = String(shift.start_time || '').slice(0, 5)
  const end = String(shift.end_time || '').slice(0, 5)
  const overnight = Boolean(shift.ends_next_day || shift.is_overnight)
  const ui = shift.ui_state || shift.status || 'scheduled'
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full cursor-pointer rounded-[0.8rem] border px-2.5 py-2 text-start shadow-sm transition hover:-translate-y-px hover:brightness-[0.99] hover:shadow-md',
        shiftSurfaceClass(shift),
        selected && 'ring-2 ring-[#c89445]/55',
        compact && 'px-2 py-1.5',
      )}
      data-testid="shift-block"
    >
      <div className="flex items-start justify-between gap-2">
        <p className={cn('font-semibold leading-snug', compact ? 'text-[12px]' : 'text-[13px]')}>
          {shift.employee_name || shift.employee_key || '—'}
        </p>
        <span className="rounded bg-white/55 px-1.5 py-0.5 text-[10px] font-medium">
          {shiftStatusLabel(ui, locale)}
        </span>
      </div>
      <p className={cn('mt-0.5 opacity-90', compact ? 'text-[11px]' : 'text-[12px]')}>
        {start} – {end}
        {overnight ? (locale === 'ar' ? ' (+يوم)' : ' (+1d)') : ''}
      </p>
      {!compact && (shift.site_key || shift.role || shift.location) ? (
        <p className="mt-0.5 truncate text-[11px] opacity-80">
          {[shift.site_key, shift.role, shift.location].filter(Boolean).join(' · ')}
        </p>
      ) : null}
      {overnight && !compact ? <p className="mt-1 text-[10px] font-medium opacity-80">{c.overnightHint}</p> : null}
    </button>
  )
}

export function ShiftsWorkspace({ access, permissions, role: _role, onNotice, onAccessIssue }: ShiftsWorkspaceProps) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = shiftsCopy(locale)
  const confirm = useConfirm()
  const canManage = can(permissions, 'shifts.manage')

  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 900px)').matches : false,
  )
  const [view, setView] = useState<ViewMode>(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches ? 'day' : 'week',
  )
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()))
  const [queue, setQueue] = useState<QueueTab>('board')
  const [filters, setFilters] = useState({ employee: '', branch_key: '', site_key: '', team_key: '', role: '', status: '' })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [composerOpen, setComposerOpen] = useState(false)
  const [history, setHistory] = useState<PosthireShiftHistoryResponse | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [rowBusy, setRowBusy] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [editDraft, setEditDraft] = useState({ shift_date: '', start_time: '', end_time: '', reason: '', ackAvail: false, ackLeave: false })

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

  const [templates, setTemplates] = useState<Record<string, unknown>[]>([])
  const [recurrences, setRecurrences] = useState<Record<string, unknown>[]>([])
  const [previewInfo, setPreviewInfo] = useState<string>('')
  const [wave4Busy, setWave4Busy] = useState<string | null>(null)
  const [periods, setPeriods] = useState<Record<string, unknown>[]>([])
  const [openShifts, setOpenShifts] = useState<Record<string, unknown>[]>([])
  const [coverageRules, setCoverageRules] = useState<Record<string, unknown>[]>([])
  const [wave5Busy, setWave5Busy] = useState<string | null>(null)
  const [publishInfo, setPublishInfo] = useState<string>('')

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const apply = () => {
      const mobile = mq.matches
      setIsMobile(mobile)
      if (mobile) setView((current) => (current === 'day' ? current : 'day'))
    }
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  const week = weekOffsetFromAnchor(anchor)
  const filterKey = useMemo(() => ({ ...filters }), [filters])
  const { data, refreshing, error, reload, coldLoading } = useShiftsData(access, week, view, filterKey, onAccessIssue)

  const shifts = useMemo(() => {
    const rows = data?.shifts ?? []
    if (!filters.status) return rows
    return rows.filter((s) => String(s.ui_state || s.status || '').toLowerCase() === filters.status.toLowerCase())
  }, [data?.shifts, filters.status])

  const swaps = data?.swaps ?? []
  const availability = data?.availability ?? []
  const recon = data?.reconciliation_flags ?? []
  const reminders = data?.terminal_reminders ?? []
  const wave3 = data?.wave3
  const wave4 = data?.wave4
  const wave5 = data?.wave5
  const needsAuditReason = Boolean(wave3?.enabled && wave3?.real_mutation_gate)

  const range = useMemo(() => {
    if (view === 'day') {
      const start = startOfDay(anchor)
      return { days: [start], start, end: addDays(start, 1) }
    }
    const weekStart = startOfWeek(anchor)
    const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
    return { days, start: weekStart, end: addDays(weekStart, 7) }
  }, [anchor, view])

  const rangeLabel = useMemo(() => {
    const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }
    const loc = isAr ? 'ar' : 'en'
    if (view === 'day') return range.days[0].toLocaleDateString(loc, opts)
    return `${range.days[0].toLocaleDateString(loc, opts)} – ${range.days[6].toLocaleDateString(loc, opts)}`
  }, [isAr, range.days, view])

  const selected = useMemo(
    () => (selectedId ? shifts.find((s) => s.shift_id === selectedId) || null : null),
    [selectedId, shifts],
  )

  // Roster rows: prefer employee; fall back to site when grouping by site later
  const rosterRows = useMemo(() => {
    const map = new Map<string, { key: string; label: string; site?: string }>()
    for (const s of shifts) {
      const key = String(s.employee_key || s.employee_name || s.shift_id || '')
      if (!key || map.has(key)) continue
      map.set(key, {
        key,
        label: String(s.employee_name || s.employee_key || '—'),
        site: s.site_key || undefined,
      })
    }
    return [...map.values()].sort((a, b) => a.label.localeCompare(b.label))
  }, [shifts])

  const shiftsByEmployeeDay = useMemo(() => {
    const map = new Map<string, ShiftBoardItem[]>()
    for (const s of shifts) {
      const emp = String(s.employee_key || s.employee_name || '')
      const day = String(s.shift_date || '').slice(0, 10)
      const k = `${emp}|${day}`
      const list = map.get(k) || []
      list.push(s)
      map.set(k, list)
      // Overnight visual marker on next calendar day without cloning authority
      if (s.ends_next_day || s.is_overnight) {
        const d = parseIsoDate(day)
        if (d) {
          const next = isoDate(addDays(d, 1))
          const nk = `${emp}|${next}`
          const ghost = map.get(nk) || []
          if (!ghost.some((g) => g.shift_id === s.shift_id && g.spanMarker)) {
            ghost.push({ ...s, spanMarker: true })
            map.set(nk, ghost)
          }
        }
      }
    }
    return map
  }, [shifts])

  const navigate = (dir: -1 | 1) => {
    const step = view === 'day' ? 1 : 7
    setAnchor((a) => addDays(a, dir * step))
  }

  const openCreate = (day?: Date) => {
    setComposerOpen(true)
    setSelectedId(null)
    setEditMode(false)
    setForm((f) => ({
      ...f,
      shift_date: day ? isoDate(day) : f.shift_date || isoDate(anchor),
    }))
  }

  const loadHistory = async (shiftId: string) => {
    setHistoryLoading(true)
    setHistory(null)
    try {
      const next = await getPosthireShiftHistory(access, shiftId)
      setHistory(next)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (selectedId) void loadHistory(selectedId)
    else setHistory(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const runAction = async (actionType: string, args: Record<string, unknown>, key: string) => {
    setActionBusy(key)
    try {
      const result = await runPosthireAction(access, { action_type: actionType, args })
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

  const submitCreate = async () => {
    if (!canManage || !form.employee_name.trim() || !form.shift_date || !form.start_time || !form.end_time) return
    setActionBusy('create-shift')
    try {
      const res = await createShift(access, {
        employee_name: form.employee_name.trim(),
        shift_date: form.shift_date,
        start_time: form.start_time,
        end_time: form.end_time,
        site_key: form.site_key || undefined,
        branch_key: form.branch_key || undefined,
        team_key: form.team_key || undefined,
        role: form.role || undefined,
        reason: form.reason || undefined,
        acknowledge_availability: form.ack_availability,
        ack_availability_conflict: form.ack_availability,
        allow_leave_conflicts: form.ack_leave,
      })
      onNotice(res.message || c.create, 'success')
      setForm((f) => ({ ...f, employee_name: '', start_time: '', end_time: '', reason: '' }))
      setComposerOpen(false)
      if (res.shift?.shift_id) setSelectedId(String(res.shift.shift_id))
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      if (err instanceof DashboardApiError) {
        const detail = err.detail
        const code = String(
          (detail && typeof detail === 'object' && 'error' in detail ? (detail as { error?: string }).error : '') ||
            err.code ||
            '',
        ).toLowerCase()
        const surface = mapActionSurface(code, locale)
        if (surface) {
          onNotice(surface, 'error')
          return
        }
        const message =
          detail && typeof detail === 'object'
            ? String((detail as { message?: string }).message || (detail as { error?: string }).error || '')
            : ''
        if (message && (code.includes('ack') || code.includes('conflict') || code.includes('seasonal'))) {
          onNotice(message || c.ackAvailability, 'info')
          return
        }
      }
      onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setActionBusy(null)
    }
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
      setSelectedId(null)
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setRowBusy(null)
    }
  }

  const submitReschedule = async () => {
    if (!selected?.shift_id || !selected.updated_at) return
    if (needsAuditReason && editDraft.reason.trim().length < 3) {
      onNotice(c.reasonRequired, 'error')
      return
    }
    setRowBusy(selected.shift_id)
    try {
      const res = await rescheduleShift(access, selected.shift_id, {
        shift_date: editDraft.shift_date,
        start_time: editDraft.start_time,
        end_time: editDraft.end_time,
        expected_updated_at: String(selected.updated_at),
        acknowledge_availability: editDraft.ackAvail,
        allow_leave_conflicts: editDraft.ackLeave,
        reason: editDraft.reason || undefined,
      })
      onNotice(res.message || c.reschedule, 'success')
      setEditMode(false)
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

  const asideOpen = Boolean(selectedId || composerOpen)
  const formOvernight = Boolean(form.start_time && form.end_time && form.end_time <= form.start_time)

  const queueCounts: Record<QueueTab, number> = {
    board: shifts.length,
    swaps: swaps.length,
    availability: availability.length,
    reconciliation: recon.length,
    reminders: reminders.length,
    templates: recurrences.length || templates.length,
    publish: periods.length || openShifts.length || coverageRules.length,
  }

  return (
    <section className="space-y-4" dir={isAr ? 'rtl' : 'ltr'} lang={locale} data-testid="shifts-workspace">
      {/* Page shell — Calendar hierarchy */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-muted">{isAr ? 'الورديات' : 'Shifts'}</p>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-ink">
            <CalendarClock className="h-6 w-6" />
            {c.title}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{c.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => void reload()} disabled={refreshing}>
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {c.refresh}
          </Button>
          {canManage ? (
            <Button onClick={() => openCreate()} data-testid="shifts-add">
              <Plus className="h-4 w-4" />
              {c.schedule}
            </Button>
          ) : null}
        </div>
      </div>

      {/* Unified toolbar — Calendar pattern */}
      <div className="flex flex-wrap items-center gap-2 rounded-[1.35rem] border border-line/70 bg-panel/90 p-2 shadow-[0_8px_24px_rgba(35,33,29,0.045)]">
        <div className="inline-flex rounded-full bg-[#f3ebe0] p-1">
          {(['day', 'week'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`rounded-full px-3 py-1.5 text-sm ${view === mode ? 'bg-wf-ink text-white' : 'text-muted'} ${isMobile && mode !== 'day' ? 'hidden sm:inline' : ''}`}
              onClick={() => setView(mode)}
            >
              {mode === 'day' ? c.day : c.week}
            </button>
          ))}
        </div>

        <div className="inline-flex items-center gap-1 rounded-xl border border-line/50 bg-white/70 px-1">
          <button type="button" className="rounded-lg p-2 text-muted hover:bg-[#f3ebe0]" onClick={() => navigate(-1)} aria-label="prev">
            {isAr ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
          <button type="button" className="px-2 text-sm font-medium text-ink" onClick={() => setAnchor(startOfDay(new Date()))}>
            {isAr ? 'اليوم' : 'Today'}
          </button>
          <button type="button" className="rounded-lg p-2 text-muted hover:bg-[#f3ebe0]" onClick={() => navigate(1)} aria-label="next">
            {isAr ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>
        <span className="px-2 text-sm font-semibold text-ink">{rangeLabel}</span>

        <div className="ms-auto inline-flex max-w-full flex-wrap rounded-full bg-[#f3ebe0] p-1" role="tablist" aria-label={c.title}>
          {(
            [
              ['board', c.board],
              ['swaps', c.swaps],
              ['availability', c.availability],
              ['reconciliation', c.reconciliation],
              ['reminders', c.reminders],
              ...(wave4?.enabled ? ([['templates', c.templates]] as [QueueTab, string][]) : []),
              ...(wave5?.enabled ? ([['publish', c.publish]] as [QueueTab, string][]) : []),
            ] as [QueueTab, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={queue === id}
              className={`rounded-full px-3 py-1.5 text-sm ${queue === id ? 'bg-wf-ink text-white' : 'text-muted'}`}
              onClick={() => setQueue(id)}
            >
              {label}
              {queueCounts[id] ? <span className="ms-1 opacity-80">({queueCounts[id]})</span> : null}
            </button>
          ))}
        </div>
      </div>

      {/* Honesty / readiness — Calendar dashed guidance style */}
      {wave3?.enabled ? (
        <div className="space-y-2 rounded-2xl border border-dashed border-line/70 bg-[#fffaf0] px-4 py-3 text-sm text-muted" data-testid="shifts-honesty-banner">
          <p>{wave5?.enabled ? c.honestyPublish : wave4?.enabled ? c.honesty : c.honestyNoTemplates}</p>
          <div className="flex flex-wrap gap-2 text-xs">
            {wave3.real_mutation_gate ? <span className="rounded-full bg-white/70 px-2 py-1 text-[#7a5a20]">{c.realGateOn}</span> : null}
            <span className="rounded-full bg-white/70 px-2 py-1">{c.timersDisabled}</span>
            <span className="rounded-full bg-white/70 px-2 py-1">{c.remindersSynthetic}</span>
            <span className="rounded-full bg-white/70 px-2 py-1">{c.talalReadOnly}</span>
          </div>
        </div>
      ) : null}

      {/* Filter strip — Calendar pattern */}
      {queue === 'board' ? (
        <div className="-mt-2 flex flex-wrap gap-2 rounded-xl border border-line/45 bg-panel/55 p-2" data-testid="shifts-filters">
          <input
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            placeholder={c.employee}
            value={filters.employee}
            onChange={(e) => setFilters((f) => ({ ...f, employee: e.target.value }))}
          />
          <input
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            placeholder={c.branch}
            value={filters.branch_key}
            onChange={(e) => setFilters((f) => ({ ...f, branch_key: e.target.value }))}
          />
          <input
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            placeholder={c.site}
            value={filters.site_key}
            onChange={(e) => setFilters((f) => ({ ...f, site_key: e.target.value }))}
          />
          <input
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            placeholder={c.team}
            value={filters.team_key}
            onChange={(e) => setFilters((f) => ({ ...f, team_key: e.target.value }))}
          />
          <input
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            placeholder={c.role}
            value={filters.role}
            onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}
          />
          <select
            className="rounded-xl border border-line/60 bg-white px-3 py-2 text-sm"
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          >
            <option value="">{isAr ? 'كل الحالات' : 'All statuses'}</option>
            <option value="scheduled">{c.statusScheduled}</option>
            <option value="conflicted">{c.statusConflicted}</option>
            <option value="reconciliation_required">{c.statusRecon}</option>
            <option value="cancelled">{c.statusCancelled}</option>
          </select>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-[#e8c9a0] bg-[#fff7ea] px-4 py-3 text-sm text-[#7a5a20]">
          <p className="font-semibold">{c.denied}</p>
          <p className="mt-1">{error}</p>
          <button type="button" className="mt-2 text-xs font-semibold underline" onClick={() => void reload()}>
            {c.retry}
          </button>
        </div>
      ) : null}

      <div className={`grid gap-4 ${asideOpen && queue === 'board' ? 'xl:grid-cols-[minmax(0,1fr)_360px]' : ''}`}>
        {/* Main canvas */}
        <div>
          {queue === 'board' ? (
            <div
              className={cn(
                '-mt-1 overflow-hidden rounded-[1.55rem] border border-[#ded3c1] bg-[#fbf7ee] shadow-[0_14px_34px_rgba(35,33,29,0.055)]',
                refreshing && !coldLoading ? 'opacity-95' : '',
              )}
              data-testid="shifts-board"
            >
              {refreshing ? (
                <div className="flex items-center gap-2 border-b border-[#e8dfd0] px-4 py-2 text-xs text-muted">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> {c.loading}
                </div>
              ) : null}

              {coldLoading ? (
                <div className="flex items-center gap-2 p-6 text-sm text-muted">
                  <Loader2 className="h-4 w-4 animate-spin" /> {c.loading}
                </div>
              ) : isMobile || view === 'day' ? (
                /* Day / mobile agenda — Calendar pattern, shift blocks */
                <div className="divide-y divide-[#e2d7c6]">
                  {range.days.map((day) => {
                    const dayKey = isoDate(day)
                    const dayShifts: ShiftBoardItem[] = shifts.filter(
                      (s) => String(s.shift_date || '').slice(0, 10) === dayKey,
                    )
                    const spanning: ShiftBoardItem[] = shifts
                      .filter((s) => {
                        if (!(s.ends_next_day || s.is_overnight)) return false
                        const d = parseIsoDate(s.shift_date)
                        return d ? isoDate(addDays(d, 1)) === dayKey : false
                      })
                      .map((s) => ({ ...s, spanMarker: true }))
                    const all = [...dayShifts, ...spanning]
                    return (
                      <div key={dayKey} className="p-4">
                        <div className="mb-2 flex items-center justify-between">
                          <h3 className="text-sm font-semibold text-ink">
                            {day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'long', month: 'short', day: 'numeric' })}
                          </h3>
                          {canManage ? (
                            <button type="button" className="text-xs font-semibold text-muted underline" onClick={() => openCreate(day)}>
                              {isAr ? 'إضافة' : 'Add'}
                            </button>
                          ) : null}
                        </div>
                        {all.length === 0 ? (
                          <p className="text-sm text-muted">{c.emptyBoard}</p>
                        ) : (
                          <ul className="space-y-2">
                            {all.map((shift, idx) => (
                              <li key={`${shift.shift_id || idx}-${shift.spanMarker ? 'span' : 'row'}`}>
                                <ShiftBlock
                                  shift={shift}
                                  locale={locale}
                                  selected={selectedId === shift.shift_id}
                                  onSelect={() => {
                                    setSelectedId(shift.shift_id || null)
                                    setComposerOpen(false)
                                    setEditMode(false)
                                  }}
                                />
                                {shift.spanMarker ? (
                                  <p className="mt-1 text-[11px] text-muted">
                                    {c.overnight} · {c.overnightHint}
                                  </p>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                /* Week roster grid — employees as rows, dates as columns, shift blocks */
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[880px] border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-[#e8dfd0] bg-[#f7f1e6]/80">
                        <th className="sticky start-0 z-[1] bg-[#f7f1e6] px-3 py-2.5 text-start text-xs font-semibold uppercase tracking-[0.08em] text-muted">
                          {c.employee}
                        </th>
                        {range.days.map((day) => {
                          const today = isoDate(startOfDay(new Date())) === isoDate(day)
                          return (
                            <th
                              key={isoDate(day)}
                              className={cn(
                                'min-w-[118px] px-2 py-2.5 text-center text-xs font-semibold text-ink',
                                today && 'bg-[#fff8e8] text-[#c89445]',
                              )}
                            >
                              <div>{day.toLocaleDateString(isAr ? 'ar' : 'en', { weekday: 'short' })}</div>
                              <div className="font-normal text-muted">{day.getDate()}</div>
                            </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {rosterRows.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="px-4 py-10 text-center text-sm text-muted">
                            {c.emptyBoard}
                          </td>
                        </tr>
                      ) : (
                        rosterRows.map((row) => (
                          <tr key={row.key} className="border-b border-[#e8dfd0]/80 align-top">
                            <td className="sticky start-0 z-[1] bg-[#fbf7ee] px-3 py-2">
                              <p className="font-semibold text-ink">{row.label}</p>
                              {row.site ? <p className="text-[11px] text-muted">{row.site}</p> : null}
                            </td>
                            {range.days.map((day) => {
                              const dayKey = isoDate(day)
                              const cell = shiftsByEmployeeDay.get(`${row.key}|${dayKey}`) || []
                              const today = isoDate(startOfDay(new Date())) === dayKey
                              const split = cell.filter((s) => !s.spanMarker).length > 1
                              return (
                                <td key={dayKey} className={cn('px-1.5 py-1.5', today && 'bg-[#fff8e8]/50')}>
                                  <div className="space-y-1.5">
                                    {split ? <p className="text-[10px] font-medium text-muted">{c.splitHint}</p> : null}
                                    {cell.map((shift, idx) => (
                                      <ShiftBlock
                                        key={`${shift.shift_id}-${idx}`}
                                        shift={shift}
                                        locale={locale}
                                        compact
                                        selected={selectedId === shift.shift_id}
                                        onSelect={() => {
                                          setSelectedId(shift.shift_id || null)
                                          setComposerOpen(false)
                                          setEditMode(false)
                                        }}
                                      />
                                    ))}
                                    {canManage && cell.length === 0 ? (
                                      <button
                                        type="button"
                                        className="w-full rounded-lg border border-dashed border-[#ded3c1] px-1 py-2 text-[10px] text-muted hover:bg-white/50"
                                        onClick={() => openCreate(day)}
                                      >
                                        +
                                      </button>
                                    ) : null}
                                  </div>
                                </td>
                              )
                            })}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                  <p className="border-t border-[#e8dfd0] px-4 py-2 text-[11px] text-muted">
                    {wave4?.enabled
                      ? isAr
                        ? 'القوالب والجداول المتكررة متاحة كتعليمات تخطيط — السلطة التشغيلية تبقى في التعيينات.'
                        : 'Templates and recurring schedules are available as planning instructions — L0 assignments remain authority.'
                      : isAr
                        ? 'جاهزية الجدولة الجماعية لاحقاً — القوالب والجداول المتكررة خارج هذا الموج.'
                        : 'Bulk scheduling readiness reserved — templates and recurring schedules are out of this wave.'}
                  </p>
                </div>
              )}
            </div>
          ) : null}

          {queue === 'swaps' ? (
            <QueueCanvas
              title={c.swaps}
              icon={<Repeat className="h-4 w-4" />}
              empty={c.emptySwaps}
              refreshing={refreshing}
            >
              {swaps.map((swap: PosthireSwapRow, idx: number) => (
                <div key={swap.swap_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e8dfd0] bg-white/70 px-4 py-3">
                  <div>
                    <p className="font-semibold text-ink">{swap.employee_name || swap.requester_employee_key || '—'}</p>
                    <p className="text-xs text-muted">{String(swap.shift_date || '')}</p>
                  </div>
                  {canManage ? (
                    <div className="flex gap-2">
                      <Button variant="secondary" size="sm" disabled={Boolean(actionBusy)} onClick={() => void runAction('reject_shift_swap', { swap_id: swap.swap_id }, `rej:${swap.swap_id}`)}>
                        {c.decline}
                      </Button>
                      <Button size="sm" disabled={Boolean(actionBusy)} onClick={() => void runAction('approve_shift_swap', { swap_id: swap.swap_id }, `apr:${swap.swap_id}`)}>
                        {c.approve}
                      </Button>
                    </div>
                  ) : (
                    <span className="text-xs text-muted">{String(swap.status || 'requested')}</span>
                  )}
                </div>
              ))}
            </QueueCanvas>
          ) : null}

          {queue === 'availability' ? (
            <QueueCanvas title={c.availability} empty={c.emptyAvailability} refreshing={refreshing}>
              {availability.map((row, idx) => (
                <div key={String(row.availability_id || idx)} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e8dfd0] bg-white/70 px-4 py-3">
                  <div>
                    <p className="font-semibold text-ink">{String(row.employee_name || row.employee_key || '—')}</p>
                    <p className="text-xs text-muted">
                      {String(row.start_date || '')} – {String(row.end_date || '')}
                    </p>
                  </div>
                  {canManage ? (
                    <div className="flex gap-2">
                      <Button variant="secondary" size="sm" onClick={() => void runAction('reject_availability', { availability_id: row.availability_id }, `av-rej:${row.availability_id}`)}>
                        {c.decline}
                      </Button>
                      <Button size="sm" onClick={() => void runAction('approve_availability', { availability_id: row.availability_id }, `av-apr:${row.availability_id}`)}>
                        {c.approve}
                      </Button>
                    </div>
                  ) : null}
                </div>
              ))}
            </QueueCanvas>
          ) : null}

          {queue === 'reconciliation' ? (
            <QueueCanvas title={c.reconciliation} icon={<ShieldAlert className="h-4 w-4" />} empty={c.emptyRecon} refreshing={refreshing}>
              {recon.map((flag, idx) => (
                <div key={String(flag.flag_id || idx)} className="rounded-2xl border border-[#efbdd7]/80 bg-[#efbdd7]/25 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <span className="rounded bg-white/55 px-1.5 py-0.5 text-[11px] font-medium">{String(flag.flag_type || '')}</span>
                      <p className="mt-1 font-semibold text-ink">{String(flag.employee_key || '—')}</p>
                    </div>
                    {canManage ? (
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" disabled={Boolean(actionBusy)} onClick={() => void resolveRecon(String(flag.flag_id), 'acknowledge')}>
                          {c.acknowledge}
                        </Button>
                        <Button size="sm" variant="ghost" className="text-rose-700" disabled={Boolean(actionBusy)} onClick={() => void resolveRecon(String(flag.flag_id), 'cancel')}>
                          {c.resolveCancel}
                        </Button>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </QueueCanvas>
          ) : null}

          {queue === 'reminders' ? (
            <QueueCanvas
              title={c.reminders}
              icon={<ShieldAlert className="h-4 w-4" />}
              empty={c.emptyReminders}
              refreshing={refreshing}
            >
              {reminders.map((rem: Record<string, unknown>, idx: number) => (
                <div key={String(rem.reminder_id || idx)} className="rounded-2xl border border-[#e8dfd0] bg-white/70 px-4 py-3 text-sm">
                  <p className="font-semibold text-ink">{String(rem.employee_key || rem.shift_id || '—')}</p>
                  <p className="text-xs text-muted">{String(rem.last_error || rem.status || '')}</p>
                </div>
              ))}
            </QueueCanvas>
          ) : null}

          {queue === 'templates' && wave4?.enabled ? (
            <div className="space-y-4 rounded-[1.55rem] border border-line/55 bg-white p-4 shadow-[0_18px_40px_rgba(35,33,29,0.08)]" data-testid="shifts-templates-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-ink">{c.templates}</h2>
                  <p className="text-sm text-muted">{c.previewHint}</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={Boolean(wave4Busy)}
                  onClick={() => {
                    void (async () => {
                      setWave4Busy('load')
                      try {
                        const [t, r] = await Promise.all([listShiftTemplates(access), listShiftRecurrences(access)])
                        setTemplates(t.templates || [])
                        setRecurrences(r.recurrences || [])
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Failed to load templates')
                      } finally {
                        setWave4Busy(null)
                      }
                    })()
                  }}
                >
                  <RefreshCw className={`me-1 h-3.5 w-3.5 ${wave4Busy === 'load' ? 'animate-spin' : ''}`} />
                  {c.retry}
                </Button>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'القوالب' : 'Templates'}</p>
                  {templates.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا قوالب بعد' : 'No templates yet'}</p>
                  ) : (
                    templates.map((t) => (
                      <div key={String(t.template_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(t.name || '')}</p>
                        <p className="text-xs text-muted">
                          {String(t.start_time || '').slice(0, 5)}–{String(t.end_time || '').slice(0, 5)}
                          {t.ends_next_day ? ` · ${c.overnight}` : ''}
                        </p>
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'الجداول المتكررة' : 'Recurrences'}</p>
                  {recurrences.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا تكرار بعد' : 'No recurrences yet'}</p>
                  ) : (
                    recurrences.map((r) => {
                      const rid = String(r.recurrence_id || '')
                      return (
                        <div key={rid} className="space-y-2 rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                          <p className="font-medium text-ink">{String(r.name || '')}</p>
                          <p className="text-xs text-muted">
                            {String(r.cycle_type || '')} · {String(r.status || '')} · {String(r.target_type || '')}:{String(r.target_key || '')}
                          </p>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={Boolean(wave4Busy)}
                              onClick={() => {
                                void (async () => {
                                  setWave4Busy(`prev:${rid}`)
                                  try {
                                    const prev = await previewShiftRecurrence(access, rid)
                                    const counts = prev.counts || {}
                                    setPreviewInfo(
                                      `${c.preview}: new=${counts.newly_generated || 0} update=${counts.updated_future || 0} conflict=${counts.conflict || 0} unchanged=${counts.unchanged || 0} held=${counts.cancelled_held || 0}`,
                                    )
                                  } catch (err) {
                                    onNotice?.(err instanceof Error ? err.message : 'Preview failed')
                                  } finally {
                                    setWave4Busy(null)
                                  }
                                })()
                              }}
                            >
                              {c.preview}
                            </Button>
                            {canManage ? (
                              <Button
                                size="sm"
                                disabled={Boolean(wave4Busy)}
                                onClick={() => {
                                  void (async () => {
                                    const ok = await confirm({
                                      title: c.materialize,
                                      body: c.previewHint,
                                      confirmLabel: c.materialize,
                                    })
                                    if (!ok) return
                                    setWave4Busy(`mat:${rid}`)
                                    try {
                                      const mat = await materializeShiftRecurrence(access, rid)
                                      const res = mat.results || {}
                                      setPreviewInfo(
                                        `${c.materialize}: created=${res.newly_generated || 0} updated=${res.updated_future || 0} conflict=${res.conflict || 0}`,
                                      )
                                      await reload()
                                    } catch (err) {
                                      onNotice?.(err instanceof Error ? err.message : 'Materialize failed')
                                    } finally {
                                      setWave4Busy(null)
                                    }
                                  })()
                                }}
                              >
                                {c.materialize}
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
              {previewInfo ? <p className="rounded-xl bg-[#fbf7ee] px-3 py-2 text-xs text-muted" data-testid="shifts-wave4-preview-info">{previewInfo}</p> : null}
            </div>
          ) : null}

          {queue === 'publish' && wave5?.enabled ? (
            <div className="space-y-4 rounded-[1.55rem] border border-line/55 bg-white p-4 shadow-[0_18px_40px_rgba(35,33,29,0.08)]" data-testid="shifts-publish-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-ink">{c.publish}</h2>
                  <p className="text-sm text-muted">{c.generateDraftHint}</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={Boolean(wave5Busy)}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('load')
                      try {
                        const [p, o, r] = await Promise.all([
                          listSchedulePeriods(access),
                          listOpenShifts(access),
                          listCoverageRules(access),
                        ])
                        setPeriods(p.periods || [])
                        setOpenShifts(o.open_shifts || [])
                        setCoverageRules(r.rules || [])
                        setPublishInfo('')
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Failed to load publish surfaces')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  <RefreshCw className={`me-1 h-3.5 w-3.5 ${wave5Busy === 'load' ? 'animate-spin' : ''}`} />
                  {c.retry}
                </Button>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'فترات الجدول' : 'Schedule periods'}</p>
                  {periods.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا فترات بعد' : 'No periods yet'}</p>
                  ) : (
                    periods.map((p) => (
                      <div key={String(p.period_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(p.name || '')}</p>
                        <p className="text-xs text-muted">
                          {String(p.status || '')} · {String(p.start_date || '').slice(0, 10)} → {String(p.end_date || '').slice(0, 10)}
                          {p.require_publish ? ` · ${c.publishAction}` : ''}
                        </p>
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{c.openShifts}</p>
                  {openShifts.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا ورديات مفتوحة' : 'No open shifts'}</p>
                  ) : (
                    openShifts.slice(0, 12).map((o) => (
                      <div key={String(o.open_shift_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">
                          {String(o.shift_date || '').slice(0, 10)} · {String(o.start_time || '').slice(0, 5)}–{String(o.end_time || '').slice(0, 5)}
                        </p>
                        <p className="text-xs text-muted">
                          {String(o.status || '')}
                          {o.ends_next_day ? ` · ${c.overnight}` : ''}
                          {o.role ? ` · ${String(o.role)}` : ''}
                        </p>
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{c.coverage}</p>
                  {coverageRules.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا قواعد تغطية' : 'No coverage rules'}</p>
                  ) : (
                    coverageRules.slice(0, 12).map((r) => (
                      <div key={String(r.rule_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(r.name || '')}</p>
                        <p className="text-xs text-muted">
                          min={String(r.min_staff ?? '')} · {String(r.enforcement_mode || 'warn')}
                          {r.ends_next_day ? ` · ${c.overnight}` : ''}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
              {publishInfo ? <p className="rounded-xl bg-[#fbf7ee] px-3 py-2 text-xs text-muted">{publishInfo}</p> : null}
            </div>
          ) : null}
        </div>

        {/* Aside detail / composer — Calendar pattern */}
        {asideOpen && queue === 'board' ? (
          <aside className="rounded-[1.55rem] border border-line/55 bg-white p-4 shadow-[0_18px_40px_rgba(35,33,29,0.08)]" data-testid="shifts-aside">
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-ink">{composerOpen ? c.schedule : c.history}</p>
              <button
                type="button"
                className="rounded-lg p-1.5 text-muted hover:bg-[#f3ebe0]"
                onClick={() => {
                  setComposerOpen(false)
                  setSelectedId(null)
                  setEditMode(false)
                }}
                aria-label={c.close}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {composerOpen ? (
              <div className="space-y-3" data-testid="shifts-create-card">
                <p className="text-xs text-muted">{c.scheduleHint}</p>
                <Input placeholder={c.employee} value={form.employee_name} onChange={(e) => setForm((f) => ({ ...f, employee_name: e.target.value }))} />
                <Input type="date" value={form.shift_date} onChange={(e) => setForm((f) => ({ ...f, shift_date: e.target.value }))} />
                <div className="grid grid-cols-2 gap-2">
                  <Input type="time" value={form.start_time} onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))} />
                  <Input type="time" value={form.end_time} onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))} />
                </div>
                {formOvernight ? <p className="text-xs text-[#7a5a20]">{c.overnight} — {c.overnightHint}</p> : null}
                <Input placeholder={c.site} value={form.site_key} onChange={(e) => setForm((f) => ({ ...f, site_key: e.target.value }))} />
                <Input placeholder={c.branch} value={form.branch_key} onChange={(e) => setForm((f) => ({ ...f, branch_key: e.target.value }))} />
                <Input placeholder={c.team} value={form.team_key} onChange={(e) => setForm((f) => ({ ...f, team_key: e.target.value }))} />
                <Input placeholder={c.role} value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} />
                <Textarea placeholder={c.reason} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} rows={2} />
                <label className="flex items-center gap-2 text-xs text-ink">
                  <input type="checkbox" checked={form.ack_availability} onChange={(e) => setForm((f) => ({ ...f, ack_availability: e.target.checked }))} />
                  {c.ackAvailability}
                </label>
                <label className="flex items-center gap-2 text-xs text-ink">
                  <input type="checkbox" checked={form.ack_leave} onChange={(e) => setForm((f) => ({ ...f, ack_leave: e.target.checked }))} />
                  {c.ackLeave}
                </label>
                <Button className="w-full" disabled={actionBusy === 'create-shift'} onClick={() => void submitCreate()} data-testid="shifts-create-submit">
                  {actionBusy === 'create-shift' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  {c.create}
                </Button>
              </div>
            ) : selected ? (
              <div className="space-y-3">
                <div className={cn('rounded-2xl border px-3 py-2.5', shiftSurfaceClass(selected))}>
                  <p className="font-semibold">{selected.employee_name}</p>
                  <p className="text-xs opacity-90">
                    {formatShiftWindow(selected.shift_date, selected.start_time, selected.end_time, Boolean(selected.ends_next_day), locale)}
                  </p>
                  <p className="mt-1 text-[11px]">{shiftStatusLabel(selected.ui_state || selected.status, locale)}</p>
                </div>

                {canManage && String(selected.status) === 'scheduled' && !editMode ? (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setEditMode(true)
                        setEditDraft({
                          shift_date: String(selected.shift_date || '').slice(0, 10),
                          start_time: String(selected.start_time || '').slice(0, 5),
                          end_time: String(selected.end_time || '').slice(0, 5),
                          reason: '',
                          ackAvail: false,
                          ackLeave: false,
                        })
                      }}
                    >
                      {c.edit}
                    </Button>
                    <Button size="sm" variant="ghost" className="text-rose-700" disabled={rowBusy === selected.shift_id} onClick={() => void runCancel(selected)}>
                      {rowBusy === selected.shift_id ? <Loader2 className="h-4 w-4 animate-spin" /> : c.softCancel}
                    </Button>
                  </div>
                ) : null}

                {editMode ? (
                  <div className="space-y-2 rounded-xl border border-line/50 bg-[#fffaf0] p-3">
                    <Input type="date" value={editDraft.shift_date} onChange={(e) => setEditDraft((d) => ({ ...d, shift_date: e.target.value }))} />
                    <div className="grid grid-cols-2 gap-2">
                      <Input type="time" value={editDraft.start_time} onChange={(e) => setEditDraft((d) => ({ ...d, start_time: e.target.value }))} />
                      <Input type="time" value={editDraft.end_time} onChange={(e) => setEditDraft((d) => ({ ...d, end_time: e.target.value }))} />
                    </div>
                    <Textarea placeholder={c.reason} value={editDraft.reason} onChange={(e) => setEditDraft((d) => ({ ...d, reason: e.target.value }))} rows={2} />
                    <label className="flex items-center gap-2 text-xs">
                      <input type="checkbox" checked={editDraft.ackAvail} onChange={(e) => setEditDraft((d) => ({ ...d, ackAvail: e.target.checked }))} />
                      {c.ackAvailability}
                    </label>
                    <label className="flex items-center gap-2 text-xs">
                      <input type="checkbox" checked={editDraft.ackLeave} onChange={(e) => setEditDraft((d) => ({ ...d, ackLeave: e.target.checked }))} />
                      {c.ackLeave}
                    </label>
                    <div className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setEditMode(false)}>
                        {c.close}
                      </Button>
                      <Button size="sm" disabled={Boolean(rowBusy)} onClick={() => void submitReschedule()}>
                        {c.save}
                      </Button>
                    </div>
                  </div>
                ) : null}

                <div>
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
                    <History className="h-3.5 w-3.5" /> {c.lineage}
                  </p>
                  {historyLoading ? (
                    <p className="text-xs text-muted">{c.loading}</p>
                  ) : (
                    <div className="space-y-2">
                      {(history?.versions || []).map((v, idx) => (
                        <div key={String(v.version_id || idx)} className="rounded-xl border border-line/45 bg-[#fbf7ee] px-2.5 py-2 text-xs">
                          <p className="font-medium text-ink">
                            {v.is_current ? c.currentVersion : c.priorVersion} · v{String(v.version_no ?? '—')}
                          </p>
                          <p className="text-muted">{String(v.reason_code || '')}</p>
                          <p className="mt-0.5 text-ink">
                            {formatShiftWindow(String(v.shift_date || ''), String(v.start_time || ''), String(v.end_time || ''), Boolean(v.ends_next_day), locale)}
                          </p>
                        </div>
                      ))}
                      {(history?.versions || []).length === 0 ? <p className="text-xs text-muted">{c.history}</p> : null}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </aside>
        ) : null}
      </div>
    </section>
  )
}

function QueueCanvas({
  title,
  icon,
  empty,
  hint,
  refreshing,
  children,
}: {
  title: string
  icon?: ReactNode
  empty: string
  hint?: string
  refreshing?: boolean
  children: ReactNode
}) {
  const childArray = (Array.isArray(children) ? children : [children]).filter(Boolean)
  return (
    <div className="-mt-1 overflow-hidden rounded-[1.55rem] border border-[#ded3c1] bg-[#fbf7ee] shadow-[0_14px_34px_rgba(35,33,29,0.055)]">
      {refreshing ? (
        <div className="flex items-center gap-2 border-b border-[#e8dfd0] px-4 py-2 text-xs text-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> …
        </div>
      ) : null}
      <div className="border-b border-[#e8dfd0] px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          {icon} {title}
        </p>
        {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
      </div>
      <div className="space-y-2.5 p-4">{childArray.length === 0 ? <p className="text-sm text-muted">{empty}</p> : children}</div>
    </div>
  )
}

export default ShiftsWorkspace
