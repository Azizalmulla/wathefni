/**
 * Shifts workspace — Visual & Interaction Redesign Wave 3B.
 * Interaction Quality Wave 2 (IQ-12) behaviors preserved.
 * Does not import PostHire.tsx. No scheduling authority reopen.
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
  createSchedulePeriod,
  createOpenShift,
  createPamExport,
  createScheduleDraftFromPublished,
  DashboardApiError,
  generateDraftFromRotation,
  getPosthireShiftHistory,
  getPosthireShifts,
  getEmployeeOrgUnits,
  listShiftRecurrences,
  listShiftTemplates,
  listSchedulePeriods,
  listScheduleVersions,
  listOpenShifts,
  listCoverageRules,
  listRotationPatterns,
  listRotationAssignments,
  listPamExports,
  materializeShiftRecurrence,
  previewRotation,
  previewShiftRecurrence,
  publishScheduleVersion,
  rescheduleShift,
  resolveShiftReconciliation,
  runPosthireAction,
  transitionScheduleVersion,
  upsertCoverageRule,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import {
  formatShiftWindow,
  shiftStatusLabel,
  shiftsCopy,
  type ShiftsLocale,
} from '@/posthire/shiftsUx'
import { ShiftsRosterBoard } from '@/posthire/ShiftsRosterBoard'
import { shiftStateSurfaceClass } from '@/posthire/visualBaseline'
import type {
  DashboardAccess,
  OrgUnitRow,
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

type SurfaceTab = 'schedule' | 'requests' | 'planning'
type QueueTab = 'board' | 'swaps' | 'availability' | 'reconciliation' | 'reminders' | 'templates' | 'publish' | 'rotations' | 'advanced'
type RequestPanel = 'swaps' | 'availability' | 'reconciliation'
type PlanningPanel = 'templates' | 'publish' | 'rotations' | 'advanced'
type ViewMode = 'day' | 'week'

const ORG_UNMAPPED = '__unmapped__'

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

/** Merge ack flags for executor needs_confirmation without changing authority contracts. */
function ackArgsForConflict(errorCode: string | null | undefined): Record<string, unknown> {
  const k = String(errorCode || '').toLowerCase()
  const next: Record<string, unknown> = {}
  if (k.includes('availability')) {
    next.ack_availability_conflict = true
    next.acknowledge_availability = true
    next.allow_availability_conflicts = true
  }
  if (k.includes('leave')) {
    next.allow_leave_conflicts = true
    next.ack_leave_conflict = true
  }
  if (k.includes('seasonal')) {
    next.acknowledge_seasonal = true
    next.ack_seasonal = true
  }
  if (k.includes('beyond') || k.includes('lifecycle')) {
    next.ack_beyond_employment_end = true
    next.acknowledge_beyond_end = true
  }
  if (Object.keys(next).length === 0) {
    // Safe default for require-ack conflicts when the code is unspecific.
    next.ack_availability_conflict = true
    next.allow_leave_conflicts = true
  }
  return next
}

function resultNeedsConfirmation(result: PosthireActionResult): boolean {
  return Boolean(
    result.confirmation ||
      result.status === 'needs_confirmation' ||
      result.result?.needs_confirmation,
  )
}

/** Calendar-aligned semantic surfaces — shared post-hire baseline tokens. */
function shiftSurfaceClass(shift: PosthireShiftRow) {
  return shiftStateSurfaceClass(shift)
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

export function ShiftsWorkspace({ access, permissions, role: _role, onNotice, onAccessIssue }: ShiftsWorkspaceProps) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const c = shiftsCopy(locale)
  const confirm = useConfirm()
  const canManage = can(permissions, 'shifts.manage')
  const canSeeAdvanced = can(permissions, 'settings.manage') || can(permissions, 'users.manage')

  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(max-width: 900px)').matches : false,
  )
  const [view, setView] = useState<ViewMode>(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches ? 'day' : 'week',
  )
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()))
  const [surface, setSurface] = useState<SurfaceTab>('schedule')
  const [requestPanel, setRequestPanel] = useState<RequestPanel>('swaps')
  const [planningPanel, setPlanningPanel] = useState<PlanningPanel>('templates')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [rotationsLoaded, setRotationsLoaded] = useState(false)
  const [orgUnits, setOrgUnits] = useState<OrgUnitRow[]>([])
  const [filters, setFilters] = useState({ employee: '', branch_key: '', site_key: '', team_key: '', role: '', status: '' })
  const [debouncedEmployee, setDebouncedEmployee] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedSnapshot, setSelectedSnapshot] = useState<PosthireShiftRow | null>(null)
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
    location: '',
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
  const [rotationPatterns, setRotationPatterns] = useState<Record<string, unknown>[]>([])
  const [rotationAssignments, setRotationAssignments] = useState<Record<string, unknown>[]>([])
  const [pamExports, setPamExports] = useState<Record<string, unknown>[]>([])
  const [wave6Busy, setWave6Busy] = useState<string | null>(null)
  const [enterpriseInfo, setEnterpriseInfo] = useState<string>('')
  const [selectedPeriodId, setSelectedPeriodId] = useState<string>('')
  const [selectedVersionId, setSelectedVersionId] = useState<string>('')
  const [periodName, setPeriodName] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [openShiftDate, setOpenShiftDate] = useState('')
  const [coverageName, setCoverageName] = useState('')

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
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedEmployee(filters.employee.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [filters.employee])

  // Debounce text search only — selects apply immediately. Never wipe week/filters on reload.
  const filterKey = useMemo(
    () => ({
      employee: debouncedEmployee,
      branch_key: filters.branch_key,
      site_key: filters.site_key,
      team_key: filters.team_key,
      role: filters.role,
    }),
    [debouncedEmployee, filters.branch_key, filters.site_key, filters.team_key, filters.role],
  )
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
  const wave6 = data?.wave6
  const needsAuditReason = Boolean(wave3?.enabled && wave3?.real_mutation_gate)
  const rotationsUsed =
    Boolean(wave6?.enabled) &&
    rotationsLoaded &&
    (rotationPatterns.length > 0 || rotationAssignments.length > 0)

  useEffect(() => {
    if (surface !== 'planning' || !wave6?.enabled || rotationsLoaded) return
    let cancelled = false
    void (async () => {
      try {
        const [pat, asg, pam] = await Promise.all([
          listRotationPatterns(access),
          listRotationAssignments(access),
          canSeeAdvanced ? listPamExports(access) : Promise.resolve({ exports: [] as Record<string, unknown>[] }),
        ])
        if (cancelled) return
        setRotationPatterns(pat.patterns || [])
        setRotationAssignments(asg.assignments || [])
        if (canSeeAdvanced) setPamExports(pam.exports || [])
        setRotationsLoaded(true)
      } catch {
        if (!cancelled) setRotationsLoaded(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [surface, wave6?.enabled, rotationsLoaded, access, canSeeAdvanced])

  const queue: QueueTab = useMemo(() => {
    if (surface === 'schedule') return 'board'
    if (surface === 'requests') return requestPanel
    if (planningPanel === 'templates' && !wave4?.enabled) {
      if (wave5?.enabled) return 'publish'
      if (rotationsUsed) return 'rotations'
      if (canSeeAdvanced && advancedOpen) return 'advanced'
      return 'templates'
    }
    if (planningPanel === 'publish' && !wave5?.enabled) {
      if (wave4?.enabled) return 'templates'
      if (rotationsUsed) return 'rotations'
      if (canSeeAdvanced && advancedOpen) return 'advanced'
      return 'publish'
    }
    if (planningPanel === 'rotations' && !rotationsUsed) {
      if (wave5?.enabled) return 'publish'
      if (wave4?.enabled) return 'templates'
      if (canSeeAdvanced && advancedOpen) return 'advanced'
      return 'templates'
    }
    if (planningPanel === 'advanced' && !(canSeeAdvanced && advancedOpen)) {
      if (wave4?.enabled) return 'templates'
      if (wave5?.enabled) return 'publish'
      if (rotationsUsed) return 'rotations'
      return 'templates'
    }
    return planningPanel
  }, [
    surface,
    requestPanel,
    planningPanel,
    wave4?.enabled,
    wave5?.enabled,
    rotationsUsed,
    canSeeAdvanced,
    advancedOpen,
  ])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await getEmployeeOrgUnits(access)
        if (!cancelled) setOrgUnits(Array.isArray(res.units) ? res.units : [])
      } catch {
        if (!cancelled) setOrgUnits([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [access])

  const branchUnits = useMemo(
    () => orgUnits.filter((u) => String(u.unit_type || '').toLowerCase() === 'branch'),
    [orgUnits],
  )
  const siteOnlyUnits = useMemo(
    () => orgUnits.filter((u) => String(u.unit_type || '').toLowerCase() === 'site'),
    [orgUnits],
  )
  const locationUnits = useMemo(
    () => orgUnits.filter((u) => String(u.unit_type || '').toLowerCase() === 'location'),
    [orgUnits],
  )
  const siteUnits = useMemo(() => [...siteOnlyUnits, ...locationUnits], [siteOnlyUnits, locationUnits])
  const teamUnits = useMemo(
    () => orgUnits.filter((u) => String(u.unit_type || '').toLowerCase() === 'team'),
    [orgUnits],
  )

  const findOrgUnit = useCallback((units: OrgUnitRow[], key: string | null | undefined) => {
    const k = String(key || '').trim()
    if (!k) return null
    return units.find((u) => String(u.unit_key || '') === k || u.org_unit_id === k || u.name === k) || null
  }, [])

  const orgUnitValue = useCallback((u: OrgUnitRow) => String(u.unit_key || u.org_unit_id), [])

  const childrenOfParent = useCallback((units: OrgUnitRow[], parent: OrgUnitRow | null) => {
    if (!parent) return units
    const filtered = units.filter((u) => String(u.parent_org_unit_id || '') === parent.org_unit_id)
    // If hierarchy is not wired for this company, keep full type list so creation stays possible.
    return filtered.length > 0 ? filtered : units
  }, [])

  const unitSelectValue = (units: OrgUnitRow[], key: string) => {
    if (!key) return ''
    const hit = findOrgUnit(units, key)
    return hit ? orgUnitValue(hit) : ''
  }

  const composerSelectValue = (units: OrgUnitRow[], key: string) => {
    if (!key) return ''
    const hit = findOrgUnit(units, key)
    if (hit) return orgUnitValue(hit)
    return ORG_UNMAPPED
  }

  const selectedBranchUnit = findOrgUnit(branchUnits, form.branch_key)
  const composerSiteOptions = childrenOfParent(siteOnlyUnits, selectedBranchUnit)
  const composerLocationOptions = childrenOfParent(
    locationUnits.length ? locationUnits : siteOnlyUnits,
    findOrgUnit(siteOnlyUnits, form.site_key) || selectedBranchUnit,
  )
  const composerTeamOptions = childrenOfParent(
    teamUnits,
    findOrgUnit([...siteOnlyUnits, ...locationUnits, ...branchUnits], form.site_key) || selectedBranchUnit,
  )

  const applyComposerOrg = (
    field: 'branch_key' | 'site_key' | 'team_key' | 'location',
    next: string,
  ) => {
    setForm((f) => {
      if (next === ORG_UNMAPPED) return f
      if (field === 'branch_key') {
        const branch = findOrgUnit(branchUnits, next)
        const sites = childrenOfParent(siteOnlyUnits, branch)
        const siteStillValid = Boolean(findOrgUnit(sites, f.site_key))
        const site = siteStillValid ? f.site_key : ''
        const siteUnit = findOrgUnit([...siteOnlyUnits, ...locationUnits], site)
        const teams = childrenOfParent(teamUnits, siteUnit || branch)
        const teamStillValid = Boolean(findOrgUnit(teams, f.team_key))
        const locs = childrenOfParent(locationUnits.length ? locationUnits : siteOnlyUnits, siteUnit || branch)
        const locStillValid = Boolean(findOrgUnit(locs, f.location))
        return {
          ...f,
          branch_key: next,
          site_key: site,
          team_key: teamStillValid ? f.team_key : '',
          location: locStillValid ? f.location : '',
        }
      }
      if (field === 'site_key') {
        const siteUnit = findOrgUnit(siteOnlyUnits, next)
        const teams = childrenOfParent(teamUnits, siteUnit || selectedBranchUnit)
        const teamStillValid = Boolean(findOrgUnit(teams, f.team_key))
        const locs = childrenOfParent(locationUnits.length ? locationUnits : siteOnlyUnits, siteUnit || selectedBranchUnit)
        const locStillValid = Boolean(findOrgUnit(locs, f.location))
        return {
          ...f,
          site_key: next,
          team_key: teamStillValid ? f.team_key : '',
          location: locStillValid ? f.location : '',
        }
      }
      return { ...f, [field]: next }
    })
  }

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

  const selectedFromList = useMemo(
    () => (selectedId ? shifts.find((s) => s.shift_id === selectedId) || null : null),
    [selectedId, shifts],
  )
  const selected =
    selectedFromList ||
    (selectedSnapshot && selectedSnapshot.shift_id === selectedId ? selectedSnapshot : null)

  useEffect(() => {
    if (selectedFromList) setSelectedSnapshot(selectedFromList)
  }, [selectedFromList])

  const selectShift = useCallback((shift: PosthireShiftRow) => {
    const id = shift.shift_id || null
    setComposerOpen(false)
    setEditMode(false)
    setSelectedId(id)
    setSelectedSnapshot(shift)
  }, [])

  const clearSelection = useCallback(() => {
    setSelectedId(null)
    setSelectedSnapshot(null)
    setEditMode(false)
    setComposerOpen(false)
  }, [])

  const navigate = (dir: -1 | 1) => {
    const step = view === 'day' ? 1 : 7
    setAnchor((a) => addDays(a, dir * step))
  }

  const openCreate = (day?: Date) => {
    setComposerOpen(true)
    setSelectedId(null)
    setSelectedSnapshot(null)
    setEditMode(false)
    setForm((f) => ({
      ...f,
      shift_date: day ? isoDate(day) : f.shift_date || isoDate(anchor),
    }))
  }

  const loadHistory = async (shiftId: string) => {
    setHistoryLoading(true)
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
    // Soft-keep prior history while the same shift refreshes; clear only when closed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  const runAction = async (actionType: string, args: Record<string, unknown>, key: string) => {
    if (actionBusy) return
    setActionBusy(key)
    try {
      let result = await runPosthireAction(access, { action_type: actionType, args })

      // Complete needs_confirmation instead of idle info toast (IQ-12).
      if (resultNeedsConfirmation(result)) {
        const body = String(
          result.confirmation?.text || result.result?.message || result.message || c.confirmRequired,
        )
        const proceed = await confirm({
          title: c.ackAvailability,
          body,
          confirmLabel: c.continueLabel,
          cancelLabel: c.close,
          dir: isAr ? 'rtl' : 'ltr',
        })
        if (!proceed) {
          onNotice(c.cancelled, 'info')
          return
        }
        const errCode = actionErrorCode(result)
        const confirmType = result.confirmation?.action_type || actionType
        const merged = {
          ...args,
          ...(result.confirmation?.args || {}),
          ...ackArgsForConflict(errCode),
        }
        result = await runPosthireAction(access, { action_type: confirmType, args: merged })
      }

      const code = actionErrorCode(result)
      const surface = mapActionSurface(code, locale)
      if (resultNeedsConfirmation(result)) {
        // Second ack still required — stop with clear failure rather than silent idle.
        onNotice(String(result.result?.message || result.message || c.confirmRequired), 'error')
        return
      }
      if (
        code &&
        (result.status === 'failed' ||
          result.status === 'permission_denied' ||
          result.result?.ok === false ||
          result.ok === false)
      ) {
        onNotice(surface || String(result.result?.message || result.message || code), 'error')
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
        location: form.location || undefined,
        role: form.role || undefined,
        reason: form.reason || undefined,
        acknowledge_availability: form.ack_availability,
        ack_availability_conflict: form.ack_availability,
        allow_leave_conflicts: form.ack_leave,
      })
      onNotice(res.message || c.create, 'success')
      setForm((f) => ({
        ...f,
        employee_name: '',
        start_time: '',
        end_time: '',
        site_key: '',
        branch_key: '',
        team_key: '',
        location: '',
        role: '',
        reason: '',
        ack_availability: false,
        ack_leave: false,
      }))
      setComposerOpen(false)
      if (res.shift?.shift_id) {
        setSelectedId(String(res.shift.shift_id))
        if (res.shift) setSelectedSnapshot(res.shift as PosthireShiftRow)
      }
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
    if (!shift.shift_id || rowBusy) return
    const windowLabel = formatShiftWindow(
      shift.shift_date,
      shift.start_time,
      shift.end_time,
      Boolean(shift.ends_next_day),
      locale,
    )
    const who = String(shift.employee_name || shift.employee_key || '—')
    const impact = (
      <div className="space-y-2">
        <p>
          <span className="font-medium text-ink">{who}</span>
          <span className="text-muted"> · {windowLabel}</span>
        </p>
        <p>{c.cancelImpact}</p>
      </div>
    )
    const doCancel = async (reason: string) => {
      setRowBusy(shift.shift_id!)
      try {
        const res = await cancelShift(access, shift.shift_id!, {
          expected_updated_at: shift.updated_at ? String(shift.updated_at) : undefined,
          reason,
          reason_code: 'cancelled',
        })
        onNotice(res.message || c.softCancel, 'success')
        clearSelection()
        await reload()
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue?.(issue)
        else onNotice(friendlyError(err, c.retry, locale), 'error')
        throw err instanceof Error ? err : new Error(friendlyError(err, c.retry, locale))
      } finally {
        setRowBusy(null)
      }
    }
    if (needsAuditReason) {
      const entered = await confirm.withReason({
        title: c.softCancel,
        body: impact,
        confirmLabel: c.softCancel,
        cancelLabel: c.close,
        destructive: true,
        reasonLabel: c.reason,
        reasonPlaceholder: c.reasonPlaceholder,
        minReasonLength: 3,
        dir: isAr ? 'rtl' : 'ltr',
        run: async ({ reason }) => {
          await doCancel(String(reason || '').trim() || 'soft-cancel')
        },
      })
      if (!entered) return
      return
    }
    await confirm({
      title: c.softCancel,
      body: impact,
      confirmLabel: c.softCancel,
      cancelLabel: c.close,
      destructive: true,
      dir: isAr ? 'rtl' : 'ltr',
      run: async () => {
        await doCancel('soft-cancel')
      },
    })
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
    if (actionBusy) return
    let reason: string | undefined
    if (action === 'cancel') {
      const flag = recon.find((r) => String(r.flag_id) === flagId)
      const label = String(flag?.employee_key || flag?.shift_id || flagId)
      const entered = await confirm.withReason({
        title: c.resolveCancel,
        body: (
          <div className="space-y-2">
            <p>
              <span className="font-medium text-ink">{label}</span>
            </p>
            <p>{c.reconCancelImpact}</p>
          </div>
        ),
        confirmLabel: c.resolveCancel,
        cancelLabel: c.close,
        destructive: true,
        reasonLabel: c.reason,
        reasonPlaceholder: c.reasonPlaceholder,
        minReasonLength: needsAuditReason ? 3 : 1,
        dir: isAr ? 'rtl' : 'ltr',
        run: async ({ reason: enteredReason }) => {
          setActionBusy(`recon:${flagId}`)
          try {
            await resolveShiftReconciliation(access, flagId, {
              action,
              reason: String(enteredReason || '').trim() || undefined,
            })
            onNotice(c.resolveCancel, 'success')
            await reload()
          } catch (err) {
            const issue = accessIssueFromError(err)
            if (issue) onAccessIssue?.(issue)
            else onNotice(friendlyError(err, c.retry, locale), 'error')
            throw err instanceof Error ? err : new Error(friendlyError(err, c.retry, locale))
          } finally {
            setActionBusy(null)
          }
        },
      })
      if (!entered) return
      return
    }
    setActionBusy(`recon:${flagId}`)
    try {
      await resolveShiftReconciliation(access, flagId, { action, reason })
      onNotice(c.acknowledge, 'success')
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

  const requestCount = swaps.length + availability.length + recon.length
  const queueCounts: Record<QueueTab, number> = {
    board: shifts.length,
    swaps: swaps.length,
    availability: availability.length,
    reconciliation: recon.length,
    reminders: reminders.length,
    templates: recurrences.length || templates.length,
    publish: periods.length || openShifts.length || coverageRules.length,
    rotations: rotationPatterns.length || rotationAssignments.length,
    advanced: reminders.length || pamExports.length,
  }

  return (
    <section
      className="space-y-3"
      dir={isAr ? 'rtl' : 'ltr'}
      lang={locale}
      data-testid="shifts-workspace"
      data-shifts-queue
      data-shifts-iq-wave2
      data-shifts-visual-wave3
      data-shifts-visual-wave3b
    >
      {/* Quiet toolbar — Schedule primary only */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-[13px] text-subtle/90">{c.subtitle}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => void reload()} disabled={refreshing} aria-label={c.refresh}>
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
          {canManage ? (
            <Button onClick={() => openCreate()} data-testid="shifts-add" data-primary-action="schedule">
              <Plus className="h-4 w-4" />
              {c.schedule}
            </Button>
          ) : null}
        </div>
      </div>

      {/* Surface IA — Schedule / Requests / Planning */}
      <div className="inline-flex w-fit items-center gap-0.5 rounded-[0.75rem] bg-wf-ink/[0.05] p-0.5" data-shifts-surfaces role="tablist" aria-label={c.title}>
        {(
          [
            ['schedule', c.surfaceSchedule, shifts.length],
            ['requests', c.surfaceRequests, requestCount],
            ['planning', c.surfacePlanning, 0],
          ] as [SurfaceTab, string, number][]
        ).map(([id, label, count]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={surface === id}
            data-surface={id}
            className={cn(
              'rounded-[0.6rem] px-3.5 py-1.5 text-[12px] font-semibold transition',
              surface === id ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink',
            )}
            onClick={() => setSurface(id)}
          >
            {label}
            {id !== 'planning' && count ? <span className="ms-1 opacity-80">({count})</span> : null}
          </button>
        ))}
      </div>

      {/* Schedule chrome: compact day/week + date nav */}
      {surface === 'schedule' ? (
        <div className="flex flex-wrap items-center gap-2" data-shifts-date-chrome>
          <div className="inline-flex rounded-[0.7rem] bg-wf-ink/[0.05] p-0.5">
            {(['day', 'week'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                className={cn(
                  'rounded-[0.55rem] px-3 py-1 text-[12px] font-semibold transition',
                  view === mode ? 'bg-wf-ink text-white' : 'text-muted hover:text-ink',
                  isMobile && mode !== 'day' ? 'hidden sm:inline' : '',
                )}
                onClick={() => setView(mode)}
              >
                {mode === 'day' ? c.day : c.week}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center gap-0.5">
            <button type="button" className="rounded-[0.55rem] p-1.5 text-muted hover:bg-wf-canvas/80 hover:text-ink" onClick={() => navigate(-1)} aria-label="prev">
              {isAr ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </button>
            <button type="button" className="rounded-[0.55rem] px-2.5 py-1 text-[12px] font-semibold text-ink hover:bg-wf-canvas/80" onClick={() => setAnchor(startOfDay(new Date()))}>
              {isAr ? 'اليوم' : 'Today'}
            </button>
            <button type="button" className="rounded-[0.55rem] p-1.5 text-muted hover:bg-wf-canvas/80 hover:text-ink" onClick={() => navigate(1)} aria-label="next">
              {isAr ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          </div>
          <span className="px-1 text-[13px] font-semibold tracking-[-0.01em] text-ink">{rangeLabel}</span>
        </div>
      ) : null}

      {/* Compact attention on Schedule — review soft when waiting */}
      {surface === 'schedule' && requestCount > 0 ? (
        <div
          className="flex gap-3 rounded-[0.85rem] bg-wf-accent-review-soft/55 px-3.5 py-2.5 text-wf-accent-review-ink"
          data-shifts-attention
        >
          <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-wf-accent-review-ink" />
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-semibold text-wf-accent-review-ink">{c.attentionWaiting(requestCount)}</p>
            <button
              type="button"
              className="mt-1 text-[12px] font-medium underline opacity-85"
              onClick={() => {
                setSurface('requests')
                if (swaps.length) setRequestPanel('swaps')
                else if (availability.length) setRequestPanel('availability')
                else setRequestPanel('reconciliation')
              }}
            >
              {c.surfaceRequests}
            </button>
          </div>
        </div>
      ) : null}

      {/* Requests sub-nav */}
      {surface === 'requests' ? (
        <div className="flex flex-wrap gap-2" data-shifts-request-panels role="tablist">
          {(
            [
              ['swaps', c.swaps, swaps.length],
              ['availability', c.availability, availability.length],
              ['reconciliation', c.reconciliation, recon.length],
            ] as [RequestPanel, string, number][]
          ).map(([id, label, count]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={requestPanel === id}
              className={cn(
                'rounded-full px-3 py-1.5 text-sm font-medium transition',
                requestPanel === id ? 'bg-wf-ink text-white' : 'bg-wf-surface text-muted hover:text-ink',
              )}
              onClick={() => setRequestPanel(id)}
            >
              {label}
              {count ? <span className="ms-1 opacity-80">({count})</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      {/* Planning sub-nav — HR-facing panels; advanced ops for admins */}
      {surface === 'planning' ? (
        <div className="space-y-3" data-shifts-planning>
          <div className="flex flex-wrap gap-2" role="tablist" data-shifts-planning-hr>
            {(
              [
                ...(wave4?.enabled ? ([['templates', c.templates]] as [PlanningPanel, string][]) : []),
                ...(wave5?.enabled ? ([['publish', c.publish]] as [PlanningPanel, string][]) : []),
                ...(rotationsUsed ? ([['rotations', c.rotations]] as [PlanningPanel, string][]) : []),
              ] as [PlanningPanel, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={planningPanel === id}
                className={cn(
                  'rounded-full px-3 py-1.5 text-sm font-medium transition',
                  planningPanel === id ? 'bg-wf-ink text-white' : 'bg-wf-surface text-muted hover:text-ink',
                )}
                onClick={() => {
                  setAdvancedOpen(false)
                  setPlanningPanel(id)
                }}
              >
                {label}
                {queueCounts[id] ? <span className="ms-1 opacity-80">({queueCounts[id]})</span> : null}
              </button>
            ))}
          </div>
          {canSeeAdvanced ? (
            <div data-shifts-operations data-shifts-advanced>
              <button
                type="button"
                className="text-[12px] font-medium text-subtle underline"
                data-testid="shifts-advanced-toggle"
                onClick={() => {
                  setAdvancedOpen((v) => {
                    const next = !v
                    if (next) setPlanningPanel('advanced')
                    else if (planningPanel === 'advanced') {
                      setPlanningPanel(
                        wave4?.enabled ? 'templates' : wave5?.enabled ? 'publish' : rotationsUsed ? 'rotations' : 'templates',
                      )
                    }
                    return next
                  })
                }}
              >
                {advancedOpen ? c.hideOperations : c.showOperations}
              </button>
              {advancedOpen ? <p className="mt-1 text-[12px] text-muted">{c.advancedOpsHint}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Compact filter chrome — advanced fields stay governed, status is client-only. */}
      {surface === 'schedule' ? (
        <div className="relative" data-testid="shifts-filters" data-shifts-filters>
          <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-[0.8rem] bg-wf-surface-raised px-2 py-1.5 ring-1 ring-wf-ink/[0.06]">
            <input
              className="h-7 min-w-[8rem] flex-1 border-0 bg-transparent px-2 text-[12px] text-ink outline-none placeholder:text-muted sm:min-w-[11rem]"
              placeholder={c.employee}
              value={filters.employee}
              onChange={(e) => setFilters((f) => ({ ...f, employee: e.target.value }))}
            />
            <select
              className="hidden h-7 max-w-[10rem] border-0 border-s border-wf-ink/10 bg-transparent px-2 text-[11px] text-ink outline-none sm:block"
              value={unitSelectValue(teamUnits, filters.team_key)}
              onChange={(e) => setFilters((f) => ({ ...f, team_key: e.target.value }))}
            >
              <option value="">{c.allTeams}</option>
              {teamUnits.map((u) => (
                <option key={u.org_unit_id} value={u.unit_key || u.org_unit_id}>
                  {u.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="h-7 rounded-[0.55rem] px-2.5 text-[11px] font-semibold text-muted hover:bg-wf-canvas/65 hover:text-ink"
              onClick={() => setFiltersOpen((open) => !open)}
              aria-expanded={filtersOpen}
            >
              {c.filters}
              {[filters.branch_key, filters.site_key, filters.team_key, filters.status].filter(Boolean).length
                ? ` · ${[filters.branch_key, filters.site_key, filters.team_key, filters.status].filter(Boolean).length}`
                : ''}
            </button>
          </div>

          {[filters.branch_key, filters.site_key, filters.team_key, filters.status].some(Boolean) ? (
            <div className="mt-1.5 flex flex-wrap gap-1.5" data-shifts-active-filters>
              {[
                ['branch_key', filters.branch_key],
                ['site_key', filters.site_key],
                ['team_key', filters.team_key],
                ['status', filters.status],
              ].map(([field, value]) =>
                value ? (
                  <button
                    key={field}
                    type="button"
                    className="rounded-[0.55rem] bg-wf-accent-review-soft/70 px-2 py-1 text-[10px] font-semibold text-wf-accent-review-ink"
                    onClick={() => setFilters((current) => ({ ...current, [field]: '' }))}
                  >
                    {value} ×
                  </button>
                ) : null,
              )}
              <button
                type="button"
                className="px-1 text-[10px] font-semibold text-muted underline"
                onClick={() => setFilters((current) => ({ ...current, branch_key: '', site_key: '', team_key: '', status: '' }))}
              >
                {c.clearFilters}
              </button>
            </div>
          ) : null}

          {filtersOpen ? (
            <div
              className="absolute end-0 top-11 z-20 grid w-full max-w-xl grid-cols-1 gap-2 rounded-[1rem] bg-wf-surface-raised p-3 shadow-[0_18px_45px_rgba(35,33,29,0.14)] ring-1 ring-wf-ink/[0.08] sm:grid-cols-2"
              data-shifts-advanced-filters
            >
              <select
                className="h-9 rounded-[0.65rem] border border-wf-ink/10 bg-wf-surface px-3 text-[12px] text-ink"
                value={unitSelectValue(branchUnits, filters.branch_key)}
                onChange={(e) => setFilters((f) => ({ ...f, branch_key: e.target.value }))}
              >
                <option value="">{c.allBranches}</option>
                {branchUnits.map((u) => (
                  <option key={u.org_unit_id} value={u.unit_key || u.org_unit_id}>
                    {u.name}
                  </option>
                ))}
              </select>
              <select
                className="h-9 rounded-[0.65rem] border border-wf-ink/10 bg-wf-surface px-3 text-[12px] text-ink"
                value={unitSelectValue(siteUnits, filters.site_key)}
                onChange={(e) => setFilters((f) => ({ ...f, site_key: e.target.value }))}
              >
                <option value="">{c.allSites}</option>
                {siteUnits.map((u) => (
                  <option key={u.org_unit_id} value={u.unit_key || u.org_unit_id}>
                    {u.name}
                  </option>
                ))}
              </select>
              <select
                className="h-9 rounded-[0.65rem] border border-wf-ink/10 bg-wf-surface px-3 text-[12px] text-ink sm:hidden"
                value={unitSelectValue(teamUnits, filters.team_key)}
                onChange={(e) => setFilters((f) => ({ ...f, team_key: e.target.value }))}
              >
                <option value="">{c.allTeams}</option>
                {teamUnits.map((u) => (
                  <option key={u.org_unit_id} value={u.unit_key || u.org_unit_id}>
                    {u.name}
                  </option>
                ))}
              </select>
              <select
                className="h-9 rounded-[0.65rem] border border-wf-ink/10 bg-wf-surface px-3 text-[12px] text-ink"
                value={filters.status}
                onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
              >
                <option value="">{c.allStatuses}</option>
                <option value="scheduled">{c.statusScheduled}</option>
                <option value="conflicted">{c.statusConflicted}</option>
                <option value="reconciliation_required">{c.statusRecon}</option>
                <option value="cancelled">{c.statusCancelled}</option>
              </select>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-[1.1rem] bg-wf-accent-review-soft/70 px-4 py-3 text-sm text-wf-accent-review-ink">
          <p className="font-semibold">{c.denied}</p>
          <p className="mt-1 opacity-90">{error}</p>
          <button type="button" className="mt-2 text-xs font-semibold underline" onClick={() => void reload()}>
            {c.retry}
          </button>
        </div>
      ) : null}

      <div className="grid gap-4">
        {/* Main canvas */}
        <div>
          {queue === 'board' ? (
            <div
              className="relative -mt-1 overflow-hidden rounded-[1.2rem] bg-wf-surface-raised shadow-[0_16px_38px_rgba(35,33,29,0.06)] ring-1 ring-wf-ink/[0.05]"
              data-testid="shifts-board"
              data-shifts-board-hero
              data-shifts-roster-board
            >
              {refreshing && !coldLoading ? (
                <div
                  className="pointer-events-none absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-wf-canvas"
                  data-shifts-updating
                  aria-live="polite"
                  aria-label={c.updating}
                >
                  <span className="block h-full w-1/3 animate-pulse rounded-full bg-wf-accent-follow" />
                </div>
              ) : null}
              <ShiftsRosterBoard
                shifts={shifts}
                days={range.days}
                anchor={anchor}
                locale={locale}
                isMobile={isMobile || view === 'day'}
                coldLoading={coldLoading}
                canManage={canManage}
                selectedId={selectedId}
                onSelect={selectShift}
                onCreate={openCreate}
                onSelectDay={(day) => {
                  setAnchor(startOfDay(day))
                  setView('day')
                }}
              />
            </div>
          ) : null}

          {queue === 'swaps' ? (
            <QueueCanvas
              title={c.swaps}
              icon={<Repeat className="h-4 w-4" />}
              empty={c.emptySwaps}
              hint={c.emptyRequestsHint}
              refreshing={refreshing}
            >
              {swaps.map((swap: PosthireSwapRow, idx: number) => (
                <div key={swap.swap_id || idx} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] bg-white/55 px-4 py-3">
                  <div>
                    <p className="font-semibold text-ink">{swap.employee_name || swap.requester_employee_key || '—'}</p>
                    <p className="text-xs text-muted">{String(swap.shift_date || '')}</p>
                  </div>
                  {canManage ? (
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={Boolean(actionBusy)}
                        pending={actionBusy === `rej:${swap.swap_id}`}
                        onClick={() => void runAction('reject_shift_swap', { swap_id: swap.swap_id }, `rej:${swap.swap_id}`)}
                      >
                        {c.decline}
                      </Button>
                      <Button
                        size="sm"
                        disabled={Boolean(actionBusy)}
                        pending={actionBusy === `apr:${swap.swap_id}`}
                        onClick={() => void runAction('approve_shift_swap', { swap_id: swap.swap_id }, `apr:${swap.swap_id}`)}
                      >
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
            <QueueCanvas title={c.availability} empty={c.emptyAvailability} hint={c.emptyRequestsHint} refreshing={refreshing}>
              {availability.map((row, idx) => (
                <div key={String(row.availability_id || idx)} className="flex flex-wrap items-center justify-between gap-3 rounded-[1.1rem] bg-white/55 px-4 py-3">
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
            <QueueCanvas title={c.reconciliation} icon={<ShieldAlert className="h-4 w-4" />} empty={c.emptyRecon} hint={c.emptyRequestsHint} refreshing={refreshing}>
              {recon.map((flag, idx) => (
                <div key={String(flag.flag_id || idx)} className="rounded-[1.1rem] bg-wf-accent-assess-soft/70 px-4 py-3 text-wf-accent-assess-ink">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <span className="rounded-full bg-white/50 px-1.5 py-0.5 text-[11px] font-medium">{String(flag.flag_type || '')}</span>
                      <p className="mt-1 font-semibold">{String(flag.employee_key || '—')}</p>
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

          {queue === 'templates' && wave4?.enabled ? (
            <div className="space-y-4 rounded-[1.55rem] bg-wf-surface-raised/90 p-4 shadow-[0_10px_28px_rgba(35,33,29,0.05)] ring-1 ring-wf-ink/[0.05]" data-testid="shifts-templates-panel">
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
                  <p className="text-xs uppercase tracking-wide text-muted">{c.recurring}</p>
                  {recurrences.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا تكرار بعد' : 'No recurrences yet'}</p>
                  ) : (
                    recurrences.map((r) => {
                      const rid = String(r.recurrence_id || '')
                      const cycle = String(r.cycle_type || '').replace(/_/g, ' ')
                      const status = String(r.status || '').replace(/_/g, ' ')
                      return (
                        <div key={rid} className="space-y-2 rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                          <p className="font-medium text-ink">{String(r.name || '')}</p>
                          <p className="text-xs text-muted">
                            {[cycle, status].filter(Boolean).join(' · ') || '—'}
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
                                    setPreviewInfo(c.previewSummary(counts))
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
                                    await confirm({
                                      title: c.materialize,
                                      body: c.previewHint,
                                      confirmLabel: c.materialize,
                                      dir: isAr ? 'rtl' : 'ltr',
                                      run: async () => {
                                        setWave4Busy(`mat:${rid}`)
                                        try {
                                          const mat = await materializeShiftRecurrence(access, rid)
                                          const res = mat.results || {}
                                          setPreviewInfo(c.generateSummary(res))
                                          onNotice(c.materialize, 'success')
                                          await reload()
                                        } catch (err) {
                                          const msg = err instanceof Error ? err.message : 'Materialize failed'
                                          onNotice?.(msg, 'error')
                                          throw err instanceof Error ? err : new Error(msg)
                                        } finally {
                                          setWave4Busy(null)
                                        }
                                      },
                                    })
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
            <div className="space-y-4 rounded-[1.55rem] bg-wf-surface-raised/90 p-4 shadow-[0_10px_28px_rgba(35,33,29,0.05)] ring-1 ring-wf-ink/[0.05]" data-testid="shifts-publish-panel">
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

              <div className="grid gap-3 md:grid-cols-2" data-testid="shifts-publish-actions">
                <div className="space-y-2 rounded-xl border border-[#e8dfd0] p-3">
                  <p className="text-xs uppercase tracking-wide text-muted">{c.createPeriod}</p>
                  <Input placeholder={isAr ? 'اسم الفترة' : 'Period name'} value={periodName} onChange={(e) => setPeriodName(e.target.value)} />
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
                    <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
                  </div>
                  <Button
                    size="sm"
                    disabled={Boolean(wave5Busy) || !periodName || !periodStart || !periodEnd}
                    onClick={() => {
                      void (async () => {
                        setWave5Busy('period')
                        try {
                          const res = await createSchedulePeriod(access, {
                            name: periodName,
                            start_date: periodStart,
                            end_date: periodEnd,
                          })
                          setSelectedPeriodId(String(res.period?.period_id || ''))
                          setSelectedVersionId(String(res.version?.version_id || ''))
                          setPublishInfo(`${c.createPeriod}: ${String(res.period?.name || periodName)}`)
                          const p = await listSchedulePeriods(access)
                          setPeriods(p.periods || [])
                        } catch (err) {
                          onNotice?.(err instanceof Error ? err.message : 'Create period failed')
                        } finally {
                          setWave5Busy(null)
                        }
                      })()
                    }}
                  >
                    <Plus className="me-1 h-3.5 w-3.5" />
                    {c.createPeriod}
                  </Button>
                </div>
                <div className="space-y-2 rounded-xl border border-[#e8dfd0] p-3">
                  <p className="text-xs uppercase tracking-wide text-muted">{c.createOpenShift} / {c.createCoverage}</p>
                  <Input type="date" value={openShiftDate} onChange={(e) => setOpenShiftDate(e.target.value)} />
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={Boolean(wave5Busy) || !openShiftDate}
                    onClick={() => {
                      void (async () => {
                        setWave5Busy('open')
                        try {
                          await createOpenShift(access, {
                            shift_date: openShiftDate,
                            start_time: '09:00',
                            end_time: '17:00',
                            notes: 'UI open shift',
                          })
                          const o = await listOpenShifts(access)
                          setOpenShifts(o.open_shifts || [])
                          setPublishInfo(c.createOpenShift)
                        } catch (err) {
                          onNotice?.(err instanceof Error ? err.message : 'Open shift failed')
                        } finally {
                          setWave5Busy(null)
                        }
                      })()
                    }}
                  >
                    {c.createOpenShift}
                  </Button>
                  <Input placeholder={c.coverage} value={coverageName} onChange={(e) => setCoverageName(e.target.value)} />
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={Boolean(wave5Busy) || !coverageName || !periodStart}
                    onClick={() => {
                      void (async () => {
                        setWave5Busy('cov')
                        try {
                          await upsertCoverageRule(access, {
                            name: coverageName,
                            min_staff: 1,
                            window_start: '09:00',
                            window_end: '17:00',
                            enforcement_mode: 'warn',
                            effective_start: periodStart || openShiftDate,
                          })
                          const r = await listCoverageRules(access)
                          setCoverageRules(r.rules || [])
                          setPublishInfo(c.createCoverage)
                        } catch (err) {
                          onNotice?.(err instanceof Error ? err.message : 'Coverage rule failed')
                        } finally {
                          setWave5Busy(null)
                        }
                      })()
                    }}
                  >
                    {c.createCoverage}
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={Boolean(wave5Busy) || !selectedVersionId}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('review')
                      try {
                        await transitionScheduleVersion(access, selectedVersionId, { to_state: 'in_review' })
                        setPublishInfo(c.submitReview)
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Submit failed')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  {c.submitReview}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={Boolean(wave5Busy) || !selectedVersionId}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('draft')
                      try {
                        await transitionScheduleVersion(access, selectedVersionId, { to_state: 'draft', note: 'ui return' })
                        setPublishInfo(c.returnToDraft)
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Return failed')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  {c.returnToDraft}
                </Button>
                <Button
                  size="sm"
                  disabled={Boolean(wave5Busy) || !selectedVersionId}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('approve')
                      try {
                        await transitionScheduleVersion(access, selectedVersionId, { to_state: 'approved' })
                        setPublishInfo(c.approve)
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Approve failed')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  {c.approve}
                </Button>
                <Button
                  size="sm"
                  disabled={Boolean(wave5Busy) || !selectedVersionId}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('publish')
                      try {
                        const res = await publishScheduleVersion(access, selectedVersionId)
                        setPublishInfo(`${c.publishAction}${res.idempotent ? ` · ${c.alreadyPublished}` : ''}`)
                        const p = await listSchedulePeriods(access)
                        setPeriods(p.periods || [])
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Publish failed')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  {c.publishAction}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={Boolean(wave5Busy) || !selectedPeriodId}
                  onClick={() => {
                    void (async () => {
                      setWave5Busy('rollback')
                      try {
                        const vers = await listScheduleVersions(access, selectedPeriodId)
                        const published = (vers.versions || []).find((v) => String(v.state) === 'published' || String(v.state) === 'superseded')
                        if (!published) {
                          const nd = await createScheduleDraftFromPublished(access, selectedPeriodId)
                          setSelectedVersionId(String(nd.version?.version_id || ''))
                          setPublishInfo(c.rollbackDraft)
                          return
                        }
                        setPublishInfo(c.rollbackDraft)
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : 'Rollback draft failed')
                      } finally {
                        setWave5Busy(null)
                      }
                    })()
                  }}
                >
                  {c.rollbackDraft}
                </Button>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'فترات الجدول' : 'Schedule periods'}</p>
                  {periods.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا فترات بعد' : 'No periods yet'}</p>
                  ) : (
                    periods.map((p) => (
                      <button
                        type="button"
                        key={String(p.period_id)}
                        className={`w-full rounded-xl border px-3 py-2 text-start text-sm ${selectedPeriodId === String(p.period_id) ? 'border-wf-ink bg-[#fbf7ee]' : 'border-[#e8dfd0]'}`}
                        onClick={() => {
                          setSelectedPeriodId(String(p.period_id))
                          void (async () => {
                            try {
                              const vers = await listScheduleVersions(access, String(p.period_id))
                              const editable = (vers.versions || []).find((v) => ['draft', 'in_review', 'approved'].includes(String(v.state)))
                                || (vers.versions || [])[0]
                              setSelectedVersionId(String(editable?.version_id || ''))
                            } catch {
                              /* ignore */
                            }
                          })()
                        }}
                      >
                        <p className="font-medium text-ink">{String(p.name || '')}</p>
                        <p className="text-xs text-muted">
                          {String(p.status || '')} · {String(p.start_date || '').slice(0, 10)} → {String(p.end_date || '').slice(0, 10)}
                          {p.require_publish ? ` · ${c.publishAction}` : ''}
                        </p>
                      </button>
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
                          {c.coverageMin(String(r.min_staff ?? '—'))}
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

          {queue === 'rotations' && rotationsUsed ? (
            <div className="space-y-4 rounded-[1.55rem] bg-wf-surface-raised/90 p-4 shadow-[0_10px_28px_rgba(35,33,29,0.05)] ring-1 ring-wf-ink/[0.05]" data-testid="shifts-rotations-panel">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-ink">{c.rotations}</h2>
                  <p className="text-sm text-muted">{c.honestyEnterprise}</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={Boolean(wave6Busy)}
                  onClick={() => {
                    void (async () => {
                      setWave6Busy('load')
                      try {
                        const [pat, asg] = await Promise.all([listRotationPatterns(access), listRotationAssignments(access)])
                        setRotationPatterns(pat.patterns || [])
                        setRotationAssignments(asg.assignments || [])
                        setRotationsLoaded(true)
                        setEnterpriseInfo('')
                      } catch (err) {
                        onNotice?.(err instanceof Error ? err.message : c.retry)
                      } finally {
                        setWave6Busy(null)
                      }
                    })()
                  }}
                >
                  <RefreshCw className={`me-1 h-3.5 w-3.5 ${wave6Busy === 'load' ? 'animate-spin' : ''}`} />
                  {c.retry}
                </Button>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'أنماط الدورات' : 'Rotation patterns'}</p>
                  {rotationPatterns.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا أنماط بعد' : 'No patterns yet'}</p>
                  ) : (
                    rotationPatterns.slice(0, 8).map((p) => (
                      <div key={String(p.pattern_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(p.name || '')}</p>
                        <p className="text-xs text-muted">{String(p.pattern_kind || '').replace(/_/g, ' ')}</p>
                      </div>
                    ))
                  )}
                </div>
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-muted">{isAr ? 'تعيينات الدورة' : 'Team assignments'}</p>
                  {rotationAssignments.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا تعيينات بعد' : 'No assignments yet'}</p>
                  ) : (
                    rotationAssignments.slice(0, 8).map((a) => (
                      <div key={String(a.assignment_id)} className="space-y-1 rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(a.name || a.target_key || '')}</p>
                        <div className="flex flex-wrap gap-1">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={Boolean(wave6Busy)}
                            onClick={() => {
                              void (async () => {
                                setWave6Busy('preview')
                                try {
                                  const prev = await previewRotation(access, String(a.assignment_id))
                                  setEnterpriseInfo(
                                    `${c.rotationPreview}: ${c.rotationCounts(prev.counts?.work ?? 0, prev.counts?.rest ?? 0, prev.counts?.travel ?? 0)}`,
                                  )
                                } catch (err) {
                                  onNotice?.(err instanceof Error ? err.message : c.retry)
                                } finally {
                                  setWave6Busy(null)
                                }
                              })()
                            }}
                          >
                            {c.rotationPreview}
                          </Button>
                          <Button
                            size="sm"
                            disabled={Boolean(wave6Busy) || !selectedPeriodId}
                            onClick={() => {
                              void (async () => {
                                setWave6Busy('draft')
                                try {
                                  const res = await generateDraftFromRotation(access, selectedPeriodId, {
                                    assignment_id: String(a.assignment_id),
                                    acknowledge_availability: true,
                                    allow_leave_conflicts: true,
                                  })
                                  setEnterpriseInfo(
                                    `${c.generateFromRotation}: ${res.draft_rows ?? 0} ${isAr ? 'صف' : 'rows'}`,
                                  )
                                } catch (err) {
                                  onNotice?.(err instanceof Error ? err.message : c.retry)
                                } finally {
                                  setWave6Busy(null)
                                }
                              })()
                            }}
                          >
                            {c.generateFromRotation}
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              {enterpriseInfo ? <p className="rounded-xl bg-[#fbf7ee] px-3 py-2 text-xs text-muted" data-testid="shifts-rotations-info">{enterpriseInfo}</p> : null}
            </div>
          ) : null}

          {queue === 'advanced' && canSeeAdvanced && advancedOpen ? (
            <div className="space-y-4 rounded-[1.55rem] border border-dashed border-[#e8dfd0] bg-[#fffaf0]/50 p-4" data-testid="shifts-advanced-panel" data-shifts-advanced-panel>
              <div>
                <h2 className="text-lg font-semibold text-ink">{c.advancedOps}</h2>
                <p className="text-sm text-muted">{c.advancedOpsHint}</p>
              </div>

              {wave3?.enabled ? (
                <div className="space-y-2 rounded-[1rem] border border-dashed border-[#e8dfd0] bg-white/70 px-3.5 py-3 text-[12px] text-muted" data-testid="shifts-honesty-banner">
                  <p>
                    {wave6?.enabled
                      ? c.honestyEnterprise
                      : wave5?.enabled
                        ? c.honestyPublish
                        : wave4?.enabled
                          ? c.honesty
                          : c.honestyNoTemplates}
                  </p>
                  <div className="flex flex-wrap gap-2 text-[11px]">
                    {wave3.real_mutation_gate ? <span className="rounded-full bg-white/70 px-2 py-1 text-[#7a5a20]">{c.realGateOn}</span> : null}
                    <span className="rounded-full bg-white/70 px-2 py-1">{c.timersDisabled}</span>
                    <span className="rounded-full bg-white/70 px-2 py-1">{c.remindersSynthetic}</span>
                    <span className="rounded-full bg-white/70 px-2 py-1">{c.talalReadOnly}</span>
                  </div>
                </div>
              ) : null}

              <QueueCanvas title={c.reminders} icon={<ShieldAlert className="h-4 w-4" />} empty={c.emptyReminders} refreshing={refreshing}>
                {reminders.map((rem: Record<string, unknown>, idx: number) => (
                  <div key={String(rem.reminder_id || idx)} className="rounded-2xl border border-[#e8dfd0] bg-white/70 px-4 py-3 text-sm">
                    <p className="font-semibold text-ink">{String(rem.employee_key || rem.shift_id || '—')}</p>
                    <p className="text-xs text-muted">{String(rem.last_error || rem.status || '')}</p>
                  </div>
                ))}
              </QueueCanvas>

              {wave6?.enabled ? (
                <div className="space-y-2 rounded-xl border border-[#e8dfd0] bg-white px-3 py-3">
                  <p className="text-sm font-semibold text-ink">{c.pamExport}</p>
                  <p className="text-xs text-muted">{c.pamExportHint}</p>
                  <Button
                    size="sm"
                    disabled={Boolean(wave6Busy) || !selectedVersionId}
                    onClick={() => {
                      void (async () => {
                        setWave6Busy('pam')
                        try {
                          const res = await createPamExport(access, selectedVersionId, 'both')
                          setEnterpriseInfo(`${c.pamExport}: ${String(res.fingerprint || '').slice(0, 16)}…`)
                          const pam = await listPamExports(access)
                          setPamExports(pam.exports || [])
                        } catch (err) {
                          onNotice?.(err instanceof Error ? err.message : c.retry)
                        } finally {
                          setWave6Busy(null)
                        }
                      })()
                    }}
                  >
                    {c.pamExport}
                  </Button>
                  {pamExports.length === 0 ? (
                    <p className="text-sm text-muted">{isAr ? 'لا صادرات بعد' : 'No exports yet'}</p>
                  ) : (
                    pamExports.slice(0, 6).map((e) => (
                      <div key={String(e.export_id)} className="rounded-xl border border-[#e8dfd0] px-3 py-2 text-sm">
                        <p className="font-medium text-ink">{String(e.status || '').replace(/_/g, ' ')}</p>
                        <p className="text-xs text-muted">{String(e.created_at || '').slice(0, 19)}</p>
                      </div>
                    ))
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Fixed end sheet — never resizes, pushes, or blanks the roster board. */}
        {asideOpen ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-50 bg-wf-ink/25"
              onClick={() => clearSelection()}
              aria-label={c.close}
              data-shifts-aside-scrim
            />
            <aside
              className="fixed inset-y-0 end-0 z-[51] grid w-full grid-rows-[auto_minmax(0,1fr)] bg-wf-surface-raised shadow-[-20px_0_50px_rgba(35,33,29,0.16)] sm:max-w-[420px] rtl:shadow-[20px_0_50px_rgba(35,33,29,0.16)]"
              data-testid="shifts-aside"
              data-shifts-aside-sheet
              role="dialog"
              aria-modal="true"
              aria-label={composerOpen ? c.schedule : selected?.employee_name || c.history}
            >
            <header className="flex items-start justify-between gap-3 border-b border-wf-ink/[0.07] px-5 py-4">
              <div className="min-w-0">
                <p className="text-[9px] font-semibold uppercase tracking-[0.11em] text-muted">
                  {composerOpen ? c.schedule : editMode ? c.reschedule : shiftStatusLabel(selected?.ui_state || selected?.status, locale)}
                </p>
                <p className="mt-1 truncate text-[20px] font-semibold tracking-[-0.035em] text-ink">
                  {composerOpen ? c.schedule : editMode ? c.reschedule : selected?.employee_name || c.history}
                </p>
                {!composerOpen && selected ? (
                  <p className="mt-1 truncate text-[10px] text-muted">
                    {formatShiftWindow(selected.shift_date, selected.start_time, selected.end_time, Boolean(selected.ends_next_day), locale)}
                  </p>
                ) : (
                  <p className="mt-1 text-[10px] text-muted">{c.scheduleHint}</p>
                )}
              </div>
              <button
                type="button"
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-wf-ink/[0.045] text-muted hover:bg-wf-ink/[0.08] hover:text-ink"
                onClick={() => clearSelection()}
                aria-label={c.close}
              >
                <X className="h-4 w-4" />
              </button>
            </header>
            <div className="min-h-0 overflow-y-auto px-5 pb-6" data-shifts-aside-scroll>

            {composerOpen ? (
              <div className="space-y-0" data-testid="shifts-create-card" data-shifts-composer-org>
                <section className="border-b border-wf-ink/[0.07] py-4" data-shifts-drawer-section="shift">
                  <div className="mb-3 flex items-baseline justify-between">
                    <h3 className="text-[12px] font-semibold text-ink">{isAr ? 'الوردية' : 'Shift'}</h3>
                    <span className="text-[9px] text-muted">{isAr ? 'مطلوب' : 'Required'}</span>
                  </div>
                  <label className="block space-y-1 text-[10px] font-medium text-muted">
                    <span>{c.employee}</span>
                    <Input className="h-10 w-full" placeholder={c.employee} value={form.employee_name} onChange={(e) => setForm((f) => ({ ...f, employee_name: e.target.value }))} />
                  </label>
                  <div className="mt-3 grid grid-cols-2 gap-2.5">
                    <label className="block space-y-1 text-[10px] font-medium text-muted">
                      <span>{c.date}</span>
                      <Input className="h-10 w-full" type="date" value={form.shift_date} onChange={(e) => setForm((f) => ({ ...f, shift_date: e.target.value }))} />
                    </label>
                    <label className="block space-y-1 text-[10px] font-medium text-muted">
                      <span>{c.role}</span>
                      <Input className="h-10 w-full" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} />
                    </label>
                    <label className="block space-y-1 text-[10px] font-medium text-muted">
                      <span>{c.start}</span>
                      <Input className="h-10 w-full" type="time" value={form.start_time} onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))} />
                    </label>
                    <label className="block space-y-1 text-[10px] font-medium text-muted">
                      <span>{c.end}</span>
                      <Input className="h-10 w-full" type="time" value={form.end_time} onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))} />
                    </label>
                  </div>
                  {formOvernight ? <p className="mt-2 text-[10px] text-wf-accent-follow-ink">{c.overnight} — {c.overnightHint}</p> : null}
                </section>
                <section className="border-b border-wf-ink/[0.07] py-4" data-shifts-drawer-section="organization">
                  <div className="mb-3 flex items-baseline justify-between">
                    <h3 className="text-[12px] font-semibold text-ink">{isAr ? 'الهيكل التنظيمي' : 'Organization'}</h3>
                    <span className="text-[9px] text-muted">{isAr ? 'محكوم' : 'Governed'}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                <label className="block space-y-1 text-[11px] font-medium text-muted">
                  <span>{c.branch}</span>
                  <select
                    className="h-10 w-full rounded-xl border border-[#e8dfd0] bg-white px-3 text-sm text-ink"
                    value={composerSelectValue(branchUnits, form.branch_key)}
                    onChange={(e) => applyComposerOrg('branch_key', e.target.value)}
                    data-org-field="branch_key"
                  >
                    <option value="">{c.noneOrg}</option>
                    {branchUnits.map((u) => (
                      <option key={u.org_unit_id} value={orgUnitValue(u)}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1 text-[11px] font-medium text-muted">
                  <span>{c.site}</span>
                  <select
                    className="h-10 w-full rounded-xl border border-[#e8dfd0] bg-white px-3 text-sm text-ink"
                    value={composerSelectValue(composerSiteOptions, form.site_key)}
                    onChange={(e) => applyComposerOrg('site_key', e.target.value)}
                    data-org-field="site_key"
                  >
                    <option value="">{c.noneOrg}</option>
                    {composerSiteOptions.map((u) => (
                      <option key={u.org_unit_id} value={orgUnitValue(u)}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1 text-[11px] font-medium text-muted">
                  <span>{c.team}</span>
                  <select
                    className="h-10 w-full rounded-xl border border-[#e8dfd0] bg-white px-3 text-sm text-ink"
                    value={composerSelectValue(composerTeamOptions, form.team_key)}
                    onChange={(e) => applyComposerOrg('team_key', e.target.value)}
                    data-org-field="team_key"
                  >
                    <option value="">{c.noneOrg}</option>
                    {composerTeamOptions.map((u) => (
                      <option key={u.org_unit_id} value={orgUnitValue(u)}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1 text-[11px] font-medium text-muted">
                  <span>{c.location}</span>
                  <select
                    className="h-10 w-full rounded-xl border border-[#e8dfd0] bg-white px-3 text-sm text-ink"
                    value={composerSelectValue(composerLocationOptions, form.location)}
                    onChange={(e) => applyComposerOrg('location', e.target.value)}
                    data-org-field="location"
                  >
                    <option value="">{c.noneOrg}</option>
                    {composerLocationOptions.map((u) => (
                      <option key={u.org_unit_id} value={orgUnitValue(u)}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </label>
                  </div>
                </section>
                <section className="py-4" data-shifts-drawer-section="controls">
                  <div className="mb-3 flex items-baseline justify-between">
                    <h3 className="text-[12px] font-semibold text-ink">{isAr ? 'الضوابط' : 'Controls'}</h3>
                    <span className="text-[9px] text-muted">{isAr ? 'حالة محلية' : 'Local pending'}</span>
                  </div>
                  <label className="block space-y-1 text-[10px] font-medium text-muted">
                    <span>{c.reason}</span>
                    <Textarea className="w-full" value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} rows={2} />
                  </label>
                  <div className="mt-3 grid gap-2 rounded-[0.75rem] bg-wf-accent-follow-soft/70 p-3 text-[11px] text-wf-accent-follow-ink">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={form.ack_availability} onChange={(e) => setForm((f) => ({ ...f, ack_availability: e.target.checked }))} />
                      {c.ackAvailability}
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={form.ack_leave} onChange={(e) => setForm((f) => ({ ...f, ack_leave: e.target.checked }))} />
                      {c.ackLeave}
                    </label>
                  </div>
                </section>
                <div className="sticky bottom-0 -mx-5 mt-4 flex items-center justify-end border-t border-wf-ink/[0.07] bg-wf-surface-raised/95 px-5 py-3 backdrop-blur-sm">
                  <Button
                    pending={actionBusy === 'create-shift'}
                    disabled={actionBusy === 'create-shift'}
                    onClick={() => void submitCreate()}
                    data-testid="shifts-create-submit"
                  >
                    <Plus className="h-4 w-4" />
                    {c.create}
                  </Button>
                </div>
              </div>
            ) : selected ? (
              <div className="space-y-0">
                <div className={cn('-mx-1 mt-4 rounded-[0.9rem] border-0 px-3 py-3', shiftSurfaceClass(selected))}>
                  <p className="text-[15px] font-semibold tracking-[-0.02em]">{selected.employee_name}</p>
                  <p className="mt-1 text-[11px] opacity-85">
                    {formatShiftWindow(selected.shift_date, selected.start_time, selected.end_time, Boolean(selected.ends_next_day), locale)}
                  </p>
                  <p className="mt-1.5 text-[9px] font-semibold uppercase tracking-[0.06em]">
                    {shiftStatusLabel(selected.ui_state || selected.status, locale)}
                  </p>
                </div>

                <section className="border-b border-wf-ink/[0.07] py-4" data-shifts-edit-org>
                  <div className="mb-3 flex items-baseline justify-between">
                    <h3 className="text-[12px] font-semibold text-ink">{isAr ? 'الهيكل التنظيمي' : 'Organization'}</h3>
                    <span className="text-[9px] text-muted">{isAr ? 'محفوظ' : 'Preserved'}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                  {(
                    [
                      ['branch_key', c.branch, branchUnits, selected.branch_key],
                      ['site_key', c.site, siteOnlyUnits, selected.site_key],
                      ['team_key', c.team, teamUnits, selected.team_key],
                      ['location', c.location, locationUnits.length ? locationUnits : siteOnlyUnits, selected.location],
                    ] as [string, string, OrgUnitRow[], string | null | undefined][]
                  ).map(([field, label, units, raw]) => {
                    const mapped = findOrgUnit(units, raw)
                    const hasLegacy = Boolean(String(raw || '').trim()) && !mapped
                    return (
                      <label key={field} className="block min-w-0 space-y-1 text-[10px] font-medium text-muted">
                        <span>{label}</span>
                        <select
                          className="h-9 w-full rounded-[0.65rem] border border-wf-ink/10 bg-wf-surface px-2.5 text-[11px] text-ink disabled:opacity-80"
                          value={mapped ? orgUnitValue(mapped) : hasLegacy ? ORG_UNMAPPED : ''}
                          disabled
                          data-org-field={field}
                          data-org-unmapped={hasLegacy ? 'true' : 'false'}
                        >
                          <option value="">{c.noneOrg}</option>
                          {hasLegacy ? (
                            <option value={ORG_UNMAPPED}>
                              {c.unmappedOrg}: {String(raw)}
                            </option>
                          ) : null}
                          {units.map((u) => (
                            <option key={u.org_unit_id} value={orgUnitValue(u)}>
                              {u.name}
                            </option>
                          ))}
                        </select>
                        {hasLegacy ? <p className="text-[10px] font-normal text-[#7a5a20]">{c.unmappedOrgHint}</p> : null}
                      </label>
                    )
                  })}
                  </div>
                </section>

                {canManage && String(selected.status) === 'scheduled' && !editMode ? (
                  <div className="flex items-center gap-2 border-b border-wf-ink/[0.07] py-4" data-shifts-drawer-actions>
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
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-wf-accent-active-ink"
                      pending={rowBusy === selected.shift_id}
                      disabled={rowBusy === selected.shift_id}
                      onClick={() => void runCancel(selected)}
                    >
                      {c.softCancel}
                    </Button>
                  </div>
                ) : null}

                {editMode ? (
                  <section className="space-y-3 border-b border-wf-ink/[0.07] py-4" data-shifts-drawer-section="edit">
                    <div className="grid grid-cols-2 gap-2.5">
                      <label className="col-span-2 block space-y-1 text-[10px] font-medium text-muted">
                        <span>{c.date}</span>
                        <Input className="h-10 w-full" type="date" value={editDraft.shift_date} onChange={(e) => setEditDraft((d) => ({ ...d, shift_date: e.target.value }))} />
                      </label>
                      <label className="block space-y-1 text-[10px] font-medium text-muted">
                        <span>{c.start}</span>
                        <Input className="h-10 w-full" type="time" value={editDraft.start_time} onChange={(e) => setEditDraft((d) => ({ ...d, start_time: e.target.value }))} />
                      </label>
                      <label className="block space-y-1 text-[10px] font-medium text-muted">
                        <span>{c.end}</span>
                        <Input className="h-10 w-full" type="time" value={editDraft.end_time} onChange={(e) => setEditDraft((d) => ({ ...d, end_time: e.target.value }))} />
                      </label>
                    </div>
                    <label className="block space-y-1 text-[10px] font-medium text-muted">
                      <span>{c.reason}</span>
                      <Textarea className="w-full" value={editDraft.reason} onChange={(e) => setEditDraft((d) => ({ ...d, reason: e.target.value }))} rows={2} />
                    </label>
                    <label className="flex items-center gap-2 text-[11px]">
                      <input type="checkbox" checked={editDraft.ackAvail} onChange={(e) => setEditDraft((d) => ({ ...d, ackAvail: e.target.checked }))} />
                      {c.ackAvailability}
                    </label>
                    <label className="flex items-center gap-2 text-[11px]">
                      <input type="checkbox" checked={editDraft.ackLeave} onChange={(e) => setEditDraft((d) => ({ ...d, ackLeave: e.target.checked }))} />
                      {c.ackLeave}
                    </label>
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setEditMode(false)}>
                        {c.close}
                      </Button>
                      <Button
                        size="sm"
                        pending={rowBusy === selected.shift_id}
                        disabled={Boolean(rowBusy)}
                        onClick={() => void submitReschedule()}
                      >
                        {c.save}
                      </Button>
                    </div>
                  </section>
                ) : null}

                <div className="py-4" aria-busy={historyLoading} data-shifts-history-soft-keep>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                      <History className="h-3.5 w-3.5" /> {c.lineage}
                    </p>
                    {historyLoading ? (
                      <span className="inline-flex items-center gap-1 text-[9px] text-muted">
                        <Loader2 className="h-3 w-3 animate-spin" /> {c.updating}
                      </span>
                    ) : null}
                  </div>
                  <div className={cn('space-y-2 transition-opacity', historyLoading && 'opacity-70')}>
                    {(history?.versions || []).map((v, idx) => (
                      <div key={String(v.version_id || idx)} className="rounded-[0.7rem] bg-wf-surface px-2.5 py-2 text-[11px]">
                        <p className="font-medium text-ink">
                          {v.is_current ? c.currentVersion : c.priorVersion} · v{String(v.version_no ?? '—')}
                        </p>
                        <p className="text-muted">{String(v.reason_code || '')}</p>
                        <p className="mt-0.5 text-ink">
                          {formatShiftWindow(String(v.shift_date || ''), String(v.start_time || ''), String(v.end_time || ''), Boolean(v.ends_next_day), locale)}
                        </p>
                      </div>
                    ))}
                    {(history?.versions || []).length === 0 && !historyLoading ? (
                      <p className="text-[11px] text-muted">{c.history}</p>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
            </div>
          </aside>
          </>
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
    <div
      className="relative -mt-1 overflow-hidden rounded-[1.55rem] bg-wf-surface/90 shadow-[0_10px_28px_rgba(35,33,29,0.045)] ring-1 ring-wf-ink/[0.05]"
      data-shifts-queue-canvas
    >
      {refreshing ? (
        <div
          className="pointer-events-none absolute inset-x-0 top-0 z-10 flex h-7 items-center gap-2 bg-wf-surface/92 px-4 text-xs text-muted backdrop-blur-[1px]"
          data-shifts-updating
          aria-live="polite"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> …
        </div>
      ) : null}
      <div className="border-b border-wf-ink/[0.05] px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          {icon} {title}
        </p>
        {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
      </div>
      <div className="space-y-2 p-4">
        {childArray.length === 0 ? (
          <div className="py-6 text-center">
            <p className="text-[14px] font-semibold text-ink">{empty}</p>
            {hint ? <p className="mt-1 text-[12px] text-muted">{hint}</p> : null}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  )
}

export default ShiftsWorkspace
