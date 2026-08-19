/**
 * Attendance operations — exception queue, corrections, disputes (customer UX).
 * Uses ops APIs. No real punch ingest / devices.
 */
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, RotateCcw, UserRound } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { useConfirm } from '@/components/ConfirmDialog'
import {
  applyAttendanceOpsCase,
  assignAttendanceOpsException,
  DashboardApiError,
  listAttendanceOpsExceptions,
  reopenAttendanceOpsException,
  requestAttendanceOpsCorrection,
  resolveAttendanceOpsDispute,
  reviewAttendanceOpsCase,
  raiseAttendanceOpsDispute,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import type { DashboardAccess } from '@/types'
import {
  ApprovalStrip,
  BlockedReason,
  ConflictBanner,
  QuietStat,
  useEmployees360Locale,
  WorkflowEmpty,
  type Locale,
} from '@/posthire/employees360/chrome'
import {
  caseStatusLabel,
  exceptionKindLabel,
  formatMinutes,
  payrollExclusionReason,
} from '@/posthire/attendanceUx'
import { cn } from '@/lib/utils'
import { ResourceState } from '@/pages/shared/dataState'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

type OpsException = {
  exception_id: string
  employee_key?: string
  employee_name?: string
  employee_phone?: string
  work_date?: string
  kind: string
  status: string
  priority?: string
  owner_phone?: string | null
  due_at?: string | null
  payroll_excluded?: boolean
  row_version: number
  before_values?: Record<string, unknown>
  after_values?: Record<string, unknown>
  dual_pending?: boolean
}

type OpsCase = {
  case_id: string
  exception_id?: string | null
  employee_key?: string
  work_date?: string
  status: string
  kind?: string
  dual_approval_required?: boolean
  high_risk?: boolean
  first_approver_phone?: string
  second_approver_phone?: string
  requested_by_phone?: string
  requested_changes?: Record<string, unknown>
  before_snapshot?: Record<string, unknown>
  after_snapshot?: Record<string, unknown>
  decision_note?: string | null
  row_version: number
}

type OpsDispute = {
  dispute_id: string
  exception_id?: string | null
  case_id?: string | null
  employee_key?: string
  work_date?: string
  status: string
  reason?: string
  raised_by_phone?: string
  row_version: number
}

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof DashboardApiError) {
    const detail = error.detail as { error?: string } | string | undefined
    const code = typeof detail === 'object' ? String(detail?.error || '') : ''
    if (code === 'stale_row_version') {
      return 'stale'
    }
    if ([
      'employee_outside_manager_scope',
      'manager_self_correction_denied',
      'payroll_period_locked',
    ].includes(code)) {
      return code
    }
    return error.message || fallback
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

const copy = {
  en: {
    title: 'Exceptions',
    subtitle: 'One governed path: request → dual review → apply. Approve does not write until Apply.',
    fullTitle: 'Attendance operations',
    fullSubtitle: 'Exceptions, corrections, and disputes — ready for HR and managers.',
    refresh: 'Refresh',
    queue: 'Needs action',
    corrections: 'Corrections',
    disputes: 'Disputes',
    locked: 'Locked / excluded',
    emptyQueue: 'No open exceptions.',
    emptyHint: 'Exceptions appear when check-in or check-out is missing, ambiguous, late, early, or absent.',
    owner: 'Owner',
    due: 'Due',
    next: 'Next action',
    assignMe: 'Assign to me',
    requestFix: 'Request correction',
    approve: 'Approve',
    reject: 'Reject',
    apply: 'Apply',
    dualNeeded: 'Second approval required',
    dualPending: 'Waiting for a different approver',
    reopen: 'Reopen with evidence',
    evidence: 'Evidence note',
    before: 'Before',
    after: 'After',
    payrollWhy: 'Payroll',
    loading: 'Loading exceptions…',
    permission: 'You need attendance manage permission to work this queue.',
    disabled: 'Attendance operations are not enabled for this company yet.',
    stale: 'Someone else updated this item. Refresh and try again.',
    scopeDenied: 'This employee is outside your team scope.',
    selfDenied: 'You cannot correct or approve your own attendance.',
    lockedDenied: 'This day is locked in Payroll.',
    open: 'Open',
    assigned: 'Assigned',
    inReview: 'In review',
    resolved: 'Resolved',
    checkIn: 'Check-in',
    checkOut: 'Check-out',
    note: 'Note',
    applyHint: 'Approve confirms the decision. Apply writes the new attendance version.',
    impact: 'Impact',
    impactPayroll: 'Held out of Payroll until resolved',
    impactReview: 'Needs HR follow-up',
    more: 'Details',
    hide: 'Hide',
  },
  ar: {
    title: 'الاستثناءات',
    subtitle: 'مسار واحد محكوم: طلب ← اعتماد مزدوج ← تطبيق. الاعتماد لا يكتب حتى التطبيق.',
    fullTitle: 'عمليات الحضور',
    fullSubtitle: 'الاستثناءات والتصحيحات والنزاعات — جاهزة للموارد البشرية والمديرين.',
    refresh: 'تحديث',
    queue: 'يحتاج إجراء',
    corrections: 'التصحيحات',
    disputes: 'النزاعات',
    locked: 'مقفل / مستبعد',
    emptyQueue: 'لا توجد استثناءات مفتوحة.',
    emptyHint: 'تظهر الاستثناءات عند نقص الدخول أو الخروج أو الغموض أو التأخير أو الانصراف المبكر أو الغياب.',
    owner: 'المسؤول',
    due: 'الاستحقاق',
    next: 'الإجراء التالي',
    assignMe: 'تعييني',
    requestFix: 'طلب تصحيح',
    approve: 'اعتماد',
    reject: 'رفض',
    apply: 'تطبيق',
    dualNeeded: 'يلزم موافقة ثانية',
    dualPending: 'بانتظار معتمد مختلف',
    reopen: 'إعادة فتح مع دليل',
    evidence: 'ملاحظة الدليل',
    before: 'قبل',
    after: 'بعد',
    payrollWhy: 'الرواتب',
    loading: 'جاري تحميل الاستثناءات…',
    permission: 'تحتاج صلاحية إدارة الحضور للعمل على هذا الطابور.',
    disabled: 'عمليات الحضور غير مفعّلة لهذه الشركة بعد.',
    stale: 'حدّث شخص آخر هذا العنصر. حدّث وحاول مجدداً.',
    scopeDenied: 'هذا الموظف خارج نطاق فريقك.',
    selfDenied: 'لا يمكنك تصحيح أو اعتماد حضورك بنفسك.',
    lockedDenied: 'هذا اليوم مقفل في كشف الرواتب.',
    open: 'مفتوح',
    assigned: 'معيَّن',
    inReview: 'قيد المراجعة',
    resolved: 'محلول',
    checkIn: 'دخول',
    checkOut: 'خروج',
    note: 'ملاحظة',
    applyHint: 'الاعتماد يؤكد القرار. التطبيق يكتب نسخة الحضور الجديدة.',
    impact: 'الأثر',
    impactPayroll: 'موقوف عن الرواتب حتى الحل',
    impactReview: 'يحتاج متابعة الموارد البشرية',
    more: 'التفاصيل',
    hide: 'إخفاء',
  },
} as const

function formatDue(iso: string | null | undefined, locale: Locale): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(locale === 'ar' ? 'ar-KW' : 'en-GB', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return String(iso)
  }
}

function snapLine(snap: Record<string, unknown> | undefined, locale: Locale): string {
  if (!snap || !Object.keys(snap).length) return '—'
  const parts: string[] = []
  if (snap.check_in_at) parts.push(`${locale === 'ar' ? 'دخول' : 'In'} ${String(snap.check_in_at).slice(11, 16) || snap.check_in_at}`)
  if (snap.check_out_at) parts.push(`${locale === 'ar' ? 'خروج' : 'Out'} ${String(snap.check_out_at).slice(11, 16) || snap.check_out_at}`)
  if (snap.status) parts.push(String(snap.status))
  if (snap.worked_minutes != null) parts.push(formatMinutes(Number(snap.worked_minutes), locale))
  return parts.join(' · ') || '—'
}

function nextActionFor(exc: OpsException, locale: Locale): string {
  const t = copy[locale]
  if (exc.status === 'open') return t.assignMe
  if (exc.status === 'assigned') return t.requestFix
  if (exc.status === 'pending_dual_approval') return t.dualPending
  if (exc.status === 'in_review') return t.approve
  if (exc.status === 'reopened') return t.requestFix
  if (exc.status === 'resolved') return t.resolved
  return exc.status.replace(/_/g, ' ')
}

export function AttendanceOpsPanel({
  access,
  canManage,
  onNotice,
  onAccessIssue,
  compact = true,
  focusEmployeeKey = null,
  focusWorkDate = null,
  onOpenCount,
}: {
  access: DashboardAccess
  canManage: boolean
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  /** Wave 1 default: queue-first exception cards without ops lab chrome. */
  compact?: boolean
  focusEmployeeKey?: string | null
  focusWorkDate?: string | null
  onOpenCount?: (count: number) => void
}) {
  const locale = useEmployees360Locale()
  const t = copy[locale]
  const isAr = locale === 'ar'
  const confirm = useConfirm()
  const actorPhone = (access.hrPhone || '').replace(/\D/g, '')
  const [tab, setTab] = useState('queue')
  const [exceptions, setExceptions] = useState<OpsException[]>([])
  const [cases, setCases] = useState<OpsCase[]>([])
  const [disputes, setDisputes] = useState<OpsDispute[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [disabled, setDisabled] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkIn, setCheckIn] = useState('09:00')
  const [checkOut, setCheckOut] = useState('17:00')
  const [evidence, setEvidence] = useState('')
  const [disputeReason, setDisputeReason] = useState('')
  const [stale, setStale] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(
    async (soft = false) => {
      if (!canManage) {
        setLoading(false)
        return
      }
      if (soft) setRefreshing(true)
      else setLoading(true)
      setError(null)
      setStale(false)
      try {
        const res = await listAttendanceOpsExceptions(access)
        if (res && (res as { error?: string }).error === 'attendance_ops_disabled') {
          setDisabled(true)
          setExceptions([])
          setCases([])
          setDisputes([])
          return
        }
        setDisabled(false)
        setExceptions(((res as { exceptions?: OpsException[] }).exceptions || []) as OpsException[])
        setCases(((res as { cases?: OpsCase[] }).cases || []) as OpsCase[])
        setDisputes(((res as { disputes?: OpsDispute[] }).disputes || []) as OpsDispute[])
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          setError(friendlyError(err, t.loading))
          return
        }
        if (err instanceof DashboardApiError && (err.status === 404 || err.status === 403)) {
          setDisabled(true)
          setExceptions([])
          setCases([])
          setDisputes([])
          setError(null)
          return
        }
        setError(friendlyError(err, t.loading))
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [access, canManage, onAccessIssue, t.loading],
  )

  useEffect(() => {
    void load()
  }, [load])

  const openish = useMemo(
    () => exceptions.filter((e) => ['open', 'assigned', 'in_review', 'pending_dual_approval', 'reopened'].includes(e.status)),
    [exceptions],
  )
  const activeCases = useMemo(
    () => cases.filter((c) => !['applied', 'rejected'].includes(c.status)),
    [cases],
  )
  const openDisputes = useMemo(() => disputes.filter((d) => d.status === 'open' || d.status === 'under_review'), [disputes])
  const lockedish = useMemo(() => exceptions.filter((e) => e.payroll_excluded === true), [exceptions])

  useEffect(() => {
    onOpenCount?.(openish.length + activeCases.length)
  }, [openish.length, activeCases.length, onOpenCount])

  useEffect(() => {
    if (!focusEmployeeKey) return
    const match =
      openish.find(
        (e) =>
          String(e.employee_key || '') === focusEmployeeKey &&
          (!focusWorkDate || String(e.work_date || '').slice(0, 10) === String(focusWorkDate).slice(0, 10)),
      ) ||
      openish.find((e) => String(e.employee_key || '') === focusEmployeeKey) ||
      exceptions.find((e) => String(e.employee_key || '') === focusEmployeeKey)
    if (match) {
      setSelectedId(match.exception_id)
      setTab('queue')
      requestAnimationFrame(() => {
        rootRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    }
  }, [focusEmployeeKey, focusWorkDate, openish, exceptions])

  const selected = selectedId ? exceptions.find((e) => e.exception_id === selectedId) || null : null

  const handleError = (err: unknown, fallback: string) => {
    const issue = accessIssueFromError(err)
    if (issue) {
      onAccessIssue?.(issue)
      return
    }
    const msg = friendlyError(err, fallback)
    if (msg === 'stale' || msg === 'stale_row_version') {
      setStale(true)
      onNotice(t.stale, 'error')
      void load(true)
      return
    }
    if (msg === 'employee_outside_manager_scope') {
      onNotice(t.scopeDenied, 'error')
      return
    }
    if (msg === 'manager_self_correction_denied') {
      onNotice(t.selfDenied, 'error')
      return
    }
    if (msg === 'payroll_period_locked') {
      onNotice(t.lockedDenied, 'error')
      return
    }
    onNotice(msg, 'error')
  }

  const runAssign = async (exc: OpsException) => {
    if (!actorPhone) {
      onNotice(t.permission, 'error')
      return
    }
    setBusyId(exc.exception_id)
    try {
      await assignAttendanceOpsException(access, exc.exception_id, {
        owner_phone: actorPhone,
        expected_row_version: exc.row_version,
      })
      onNotice(locale === 'ar' ? 'تم التعيين' : 'Assigned', 'success')
      await load(true)
    } catch (err) {
      handleError(err, t.assignMe)
    } finally {
      setBusyId(null)
    }
  }

  const runRequest = async (exc: OpsException) => {
    setBusyId(exc.exception_id)
    try {
      const workDate = String(exc.work_date || '').slice(0, 10)
      const changes: Record<string, unknown> = {}
      if (checkIn) changes.check_in_at = `${workDate}T${checkIn}:00`
      if (checkOut) changes.check_out_at = `${workDate}T${checkOut}:00`
      if (exc.kind === 'absence') changes.status = 'completed'
      const res = await requestAttendanceOpsCorrection(access, {
        employee_key: String(exc.employee_key),
        work_date: workDate,
        changes,
        exception_id: exc.exception_id,
        kind: exc.kind,
      })
      const caseRow = (res as { case?: OpsCase }).case
      if (caseRow) setCases((prev) => [caseRow, ...prev.filter((c) => c.case_id !== caseRow.case_id)])
      onNotice(locale === 'ar' ? 'تم طلب التصحيح — بانتظار المراجعة' : 'Correction requested — awaiting review', 'success')
      setTab('corrections')
      await load(true)
    } catch (err) {
      handleError(err, t.requestFix)
    } finally {
      setBusyId(null)
    }
  }

  const runReview = async (caseRow: OpsCase, decision: 'approved' | 'rejected') => {
    const ok = await confirm({
      title: decision === 'approved' ? t.approve : t.reject,
      body: t.applyHint,
      confirmLabel: decision === 'approved' ? t.approve : t.reject,
      destructive: decision === 'rejected',
    })
    if (!ok) return
    setBusyId(caseRow.case_id)
    try {
      const res = await reviewAttendanceOpsCase(access, caseRow.case_id, {
        decision,
        expected_row_version: caseRow.row_version,
      })
      const updated = (res as { case?: OpsCase }).case || caseRow
      setCases((prev) => prev.map((c) => (c.case_id === caseRow.case_id ? { ...c, ...updated } : c)))
      if ((res as { dual_pending?: boolean }).dual_pending) {
        onNotice(t.dualPending, 'info')
      } else {
        onNotice(decision === 'approved' ? (locale === 'ar' ? 'تم الاعتماد — طبّق الآن' : 'Approved — apply next') : (locale === 'ar' ? 'مرفوض' : 'Rejected'), decision === 'approved' ? 'success' : 'info')
      }
      await load(true)
    } catch (err) {
      handleError(err, decision)
    } finally {
      setBusyId(null)
    }
  }

  const runApply = async (caseRow: OpsCase) => {
    const ok = await confirm({
      title: t.apply,
      body: t.applyHint,
      confirmLabel: t.apply,
    })
    if (!ok) return
    setBusyId(caseRow.case_id)
    try {
      const res = await applyAttendanceOpsCase(access, caseRow.case_id, {
        expected_row_version: caseRow.row_version,
        idempotency_key: `ui-apply-${caseRow.case_id}`,
      })
      const updated = (res as { case?: OpsCase }).case
      if (updated) setCases((prev) => prev.map((c) => (c.case_id === caseRow.case_id ? { ...c, ...updated } : c)))
      onNotice(locale === 'ar' ? 'تم تطبيق التصحيح' : 'Correction applied', 'success')
      await load(true)
    } catch (err) {
      handleError(err, t.apply)
    } finally {
      setBusyId(null)
    }
  }

  const runReopen = async (exc: OpsException) => {
    if (!evidence.trim()) {
      onNotice(t.evidence, 'error')
      return
    }
    setBusyId(exc.exception_id)
    try {
      await reopenAttendanceOpsException(access, exc.exception_id, {
        expected_row_version: exc.row_version,
        evidence_note: evidence.trim(),
      })
      onNotice(locale === 'ar' ? 'أُعيد فتح الاستثناء' : 'Exception reopened', 'success')
      setEvidence('')
      await load(true)
    } catch (err) {
      handleError(err, t.reopen)
    } finally {
      setBusyId(null)
    }
  }

  const runDispute = async (exc: OpsException) => {
    if (!disputeReason.trim()) {
      onNotice(locale === 'ar' ? 'أدخل سبب النزاع' : 'Enter a dispute reason', 'error')
      return
    }
    setBusyId(exc.exception_id)
    try {
      await raiseAttendanceOpsDispute(access, {
        employee_key: String(exc.employee_key),
        work_date: String(exc.work_date || '').slice(0, 10),
        reason: disputeReason.trim(),
        exception_id: exc.exception_id,
      })
      onNotice(locale === 'ar' ? 'تم فتح النزاع' : 'Dispute opened', 'success')
      setDisputeReason('')
      setTab('disputes')
      await load(true)
    } catch (err) {
      handleError(err, t.disputes)
    } finally {
      setBusyId(null)
    }
  }

  const runResolveDispute = async (d: OpsDispute, resolution: 'upheld' | 'overturned') => {
    setBusyId(d.dispute_id)
    try {
      await resolveAttendanceOpsDispute(access, d.dispute_id, {
        resolution,
        expected_row_version: d.row_version,
      })
      onNotice(locale === 'ar' ? 'تم حل النزاع' : 'Dispute resolved', 'success')
      await load(true)
    } catch (err) {
      handleError(err, t.disputes)
    } finally {
      setBusyId(null)
    }
  }

  if (!canManage) {
    return (
      <div data-testid="attendance-ops" dir={isAr ? 'rtl' : 'ltr'}>
        <ResourceState kind="forbidden" locale={isAr ? 'ar' : 'en'} title={t.permission} testId="attendance-ops-state" />
      </div>
    )
  }

  if (disabled) {
    return (
      <div data-testid="attendance-ops" dir={isAr ? 'rtl' : 'ltr'}>
        <ResourceState kind="unavailable" locale={isAr ? 'ar' : 'en'} title={t.disabled} testId="attendance-ops-state" />
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="attendance-ops" data-compact={compact ? '1' : '0'} dir={isAr ? 'rtl' : 'ltr'} ref={rootRef}>
      <Card className="border-[#e8dfd0] bg-[#fffdf8]" tone="board">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="text-[17px] tracking-[-0.02em]">{compact ? t.title : t.fullTitle}</CardTitle>
            <CardDescription>{compact ? t.subtitle : t.fullSubtitle}</CardDescription>
          </div>
          <Button variant="ghost" size="sm" disabled={refreshing} onClick={() => void load(true)} aria-label={t.refresh}>
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            <span className="sr-only sm:not-sr-only sm:ms-1">{t.refresh}</span>
          </Button>
        </CardHeader>
        <div className="space-y-4 px-5 pb-5">
          {stale ? <ConflictBanner detail={t.stale} locale={locale} action={<Button size="sm" variant="secondary" onClick={() => void load(true)}>{t.refresh}</Button>} /> : null}
          {loading ? (
            <ResourceState kind="loading" locale={isAr ? 'ar' : 'en'} testId="attendance-ops-state" />
          ) : error ? (
            <ResourceState
              kind="error"
              locale={isAr ? 'ar' : 'en'}
              title={error}
              onRetry={() => void load()}
              retrying={loading || refreshing}
              testId="attendance-ops-state"
            />
          ) : (
            <>
              {!compact ? (
                <div className="grid gap-2 sm:grid-cols-4">
                  <QuietStat label={t.queue} value={openish.length} />
                  <QuietStat label={t.corrections} value={activeCases.length} />
                  <QuietStat label={t.disputes} value={openDisputes.length} />
                  <QuietStat label={t.locked} value={lockedish.length} />
                </div>
              ) : null}
              <div className="flex flex-wrap gap-1.5" data-testid="attendance-exception-filters" role="tablist">
                {(
                  [
                    ['queue', t.queue, openish.length],
                    ['corrections', t.corrections, activeCases.length],
                    ['disputes', t.disputes, openDisputes.length],
                    ['locked', t.locked, lockedish.length],
                  ] as const
                ).map(([id, label, count]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTab(id)}
                    className={cn(
                      'rounded-full px-3 py-1.5 text-[12.5px] font-semibold transition',
                      tab === id ? 'bg-[#23211d] text-white' : 'bg-[#eee5d4]/80 text-[#5c554a] hover:bg-[#eee5d4]',
                    )}
                  >
                    {label}
                    <span className="ms-1.5 tabular-nums opacity-80">{count}</span>
                  </button>
                ))}
              </div>

              {tab === 'queue' ? (
                openish.length === 0 ? (
                  <WorkflowEmpty title={t.emptyQueue} hint={t.emptyHint} icon={<CheckCircle2 className="h-5 w-5" />} />
                ) : (
                  <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className="space-y-2">
                      {openish.map((exc) => {
                        const active = (selected?.exception_id || '') === exc.exception_id
                        const linkedCase = activeCases.find((c) => c.exception_id === exc.exception_id)
                        const primaryLabel = linkedCase
                          ? linkedCase.status === 'approved'
                            ? t.apply
                            : ['requested', 'under_review', 'reopened', 'pending_dual_approval'].includes(linkedCase.status)
                              ? t.approve
                              : nextActionFor(exc, locale)
                          : nextActionFor(exc, locale)
                        const impact =
                          exc.payroll_excluded === true
                            ? t.impactPayroll
                            : t.impactReview
                        return (
                          <div
                            key={exc.exception_id}
                            data-testid="attendance-exception-row"
                            data-exception-id={exc.exception_id}
                            className={cn(
                              'rounded-[1.1rem] border px-3.5 py-3 transition',
                              active ? 'border-[#23211d]/35 bg-white shadow-[0_1px_0_rgba(35,33,29,0.06)]' : 'border-[#e8dfd0] bg-[#fffdf8]/60',
                            )}
                          >
                            <button
                              type="button"
                              onClick={() => setSelectedId(exc.exception_id === selectedId ? null : exc.exception_id)}
                              className="w-full text-start"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusPill tone="review">{exceptionKindLabel(exc.kind, locale)}</StatusPill>
                                <Badge tone="muted" className="text-[11px]">{exc.status.replace(/_/g, ' ')}</Badge>
                                {exc.payroll_excluded === true ? (
                                  <Badge tone="warning" className="text-[11px]">{locale === 'ar' ? 'مستبعد من الرواتب' : 'Payroll excluded'}</Badge>
                                ) : null}
                              </div>
                              <p className="mt-2 text-[14px] font-semibold text-text">{exc.employee_name || exc.employee_key}</p>
                              <p className="mt-1 text-[12.5px] text-subtle/90">
                                {String(exc.work_date || '').slice(0, 10)}
                                {exc.due_at ? ` · ${t.due}: ${formatDue(exc.due_at, locale)}` : ''}
                              </p>
                              <p className="mt-1 text-[12px] text-subtle/80">
                                {t.impact}: {impact}
                              </p>
                              <p className="mt-1 text-[12px] font-medium text-text">
                                {t.next}: {primaryLabel}
                              </p>
                            </button>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {exc.status === 'open' || !exc.owner_phone ? (
                                <Button size="sm" disabled={busyId === exc.exception_id} onClick={() => void runAssign(exc)}>
                                  {busyId === exc.exception_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                                  {t.assignMe}
                                </Button>
                              ) : linkedCase && linkedCase.status === 'approved' ? (
                                <Button size="sm" disabled={busyId === linkedCase.case_id} onClick={() => void runApply(linkedCase)}>
                                  {busyId === linkedCase.case_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                                  {t.apply}
                                </Button>
                              ) : linkedCase && ['requested', 'under_review', 'reopened', 'pending_dual_approval'].includes(linkedCase.status) ? (
                                <Button size="sm" disabled={busyId === linkedCase.case_id} onClick={() => void runReview(linkedCase, 'approved')}>
                                  {t.approve}
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  disabled={busyId === exc.exception_id}
                                  onClick={() => {
                                    setSelectedId(exc.exception_id)
                                    void runRequest(exc)
                                  }}
                                >
                                  {t.requestFix}
                                </Button>
                              )}
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setSelectedId(exc.exception_id === selectedId ? null : exc.exception_id)}
                              >
                                {active ? t.hide : t.more}
                              </Button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    {selected && selectedId === selected.exception_id ? (
                      <div className="space-y-3 rounded-[1.2rem] border border-[#e8dfd0] bg-white p-4 lg:sticky lg:top-4">
                        <div className="flex items-start gap-2">
                          <UserRound className="mt-0.5 h-4 w-4 text-mist" />
                          <div>
                            <p className="font-semibold text-text">{selected.employee_name || selected.employee_key}</p>
                            <p className="text-[12px] text-subtle">{exceptionKindLabel(selected.kind, locale)} · {String(selected.work_date || '').slice(0, 10)}</p>
                          </div>
                        </div>
                        <BlockedReason
                          locale={locale}
                          reason={
                            payrollExclusionReason(
                              {
                                exception_state: selected.kind,
                                payroll_eligible: false,
                                payroll_excluded: selected.payroll_excluded,
                              } as never,
                              locale,
                            ) || (locale === 'ar' ? 'يحتاج مراجعة قبل الرواتب' : 'Needs review before Payroll')
                          }
                        />
                        <div className="grid gap-2 sm:grid-cols-2">
                          <label className="text-[12px] font-medium text-subtle">
                            {t.checkIn}
                            <Input type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} className="mt-1 h-10" />
                          </label>
                          <label className="text-[12px] font-medium text-subtle">
                            {t.checkOut}
                            <Input type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)} className="mt-1 h-10" />
                          </label>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {selected.status === 'open' || !selected.owner_phone ? (
                            <Button size="sm" disabled={busyId === selected.exception_id} onClick={() => void runAssign(selected)}>
                              {busyId === selected.exception_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                              {t.assignMe}
                            </Button>
                          ) : null}
                          <Button size="sm" variant="secondary" disabled={busyId === selected.exception_id} onClick={() => void runRequest(selected)}>
                            {t.requestFix}
                          </Button>
                        </div>
                        <div className="space-y-2 border-t border-[#e8dfd0] pt-3">
                          <label className="text-[12px] font-medium text-subtle">
                            {locale === 'ar' ? 'سبب النزاع' : 'Dispute reason'}
                            <Input value={disputeReason} onChange={(e) => setDisputeReason(e.target.value)} className="mt-1 h-10" />
                          </label>
                          <Button size="sm" variant="ghost" disabled={busyId === selected.exception_id} onClick={() => void runDispute(selected)}>
                            {t.disputes}
                          </Button>
                        </div>
                        {['resolved', 'rejected', 'closed'].includes(selected.status) ? (
                          <div className="space-y-2 border-t border-[#e8dfd0] pt-3">
                            <label className="text-[12px] font-medium text-subtle">
                              {t.evidence}
                              <Input value={evidence} onChange={(e) => setEvidence(e.target.value)} className="mt-1 h-10" placeholder={t.evidence} />
                            </label>
                            <Button size="sm" variant="ghost" disabled={busyId === selected.exception_id} onClick={() => void runReopen(selected)}>
                              <RotateCcw className="h-4 w-4" /> {t.reopen}
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                )
              ) : null}

              {tab === 'corrections' ? (
                cases.length === 0 ? (
                  <WorkflowEmpty title={locale === 'ar' ? 'لا توجد تصحيحات بعد' : 'No corrections yet'} hint={t.applyHint} />
                ) : (
                  <div className="space-y-3">
                    <p className="text-[12px] text-subtle/90">{t.applyHint}</p>
                    {cases.slice(0, 40).map((c) => (
                      <div key={c.case_id} className="rounded-[1.1rem] border border-[#e8dfd0] bg-white p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusPill tone={c.status === 'applied' ? 'success' : c.status === 'rejected' ? 'danger' : 'review'}>
                            {caseStatusLabel(c.status, locale)}
                          </StatusPill>
                          {c.dual_approval_required ? <Badge tone="review">{t.dualNeeded}</Badge> : null}
                          {c.kind ? <span className="text-[12px] text-subtle">{exceptionKindLabel(c.kind, locale)}</span> : null}
                        </div>
                        <p className="mt-2 text-[13px] text-text">
                          {c.employee_key} · {String(c.work_date || '').slice(0, 10)} · {t.owner}: {c.requested_by_phone || '—'}
                        </p>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          <div className="rounded-[0.9rem] border border-[#e8dfd0]/80 bg-[#fffdf8] px-3 py-2 text-[12px]">
                            <div className="font-semibold text-mist">{t.before}</div>
                            <div className="mt-1 text-text">{snapLine(c.before_snapshot, locale)}</div>
                          </div>
                          <div className="rounded-[0.9rem] border border-[#e8dfd0]/80 bg-[#fffdf8] px-3 py-2 text-[12px]">
                            <div className="font-semibold text-mist">{t.after}</div>
                            <div className="mt-1 text-text">{snapLine(c.after_snapshot, locale)}</div>
                          </div>
                        </div>
                        {c.status === 'pending_dual_approval' ? (
                          <div className="mt-3">
                            <ApprovalStrip state={t.dualPending} nextApprover={locale === 'ar' ? 'معتمد ثانٍ مختلف' : 'A different second approver'} locale={locale} />
                          </div>
                        ) : null}
                        <div className="mt-3 flex flex-wrap gap-2">
                          {['requested', 'under_review', 'reopened', 'pending_dual_approval'].includes(c.status) ? (
                            <>
                              <Button size="sm" disabled={busyId === c.case_id} onClick={() => void runReview(c, 'approved')}>
                                {t.approve}
                              </Button>
                              <Button size="sm" variant="ghost" disabled={busyId === c.case_id} onClick={() => void runReview(c, 'rejected')}>
                                {t.reject}
                              </Button>
                            </>
                          ) : null}
                          {c.status === 'approved' ? (
                            <Button size="sm" disabled={busyId === c.case_id} onClick={() => void runApply(c)}>
                              {busyId === c.case_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                              {t.apply}
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : null}

              {tab === 'disputes' ? (
                openDisputes.length === 0 ? (
                  <WorkflowEmpty
                    title={locale === 'ar' ? 'لا توجد نزاعات مفتوحة' : 'No open disputes'}
                    hint={
                      locale === 'ar'
                        ? 'عند وجود نزاع، يظهر السجل كـ «متنازع عليه» ويُستبعد من الرواتب حتى الحل أو إعادة الفتح بدليل جديد.'
                        : 'When disputed, the day shows as Disputed and stays out of Payroll until resolved or reopened with new evidence.'
                    }
                    icon={<AlertTriangle className="h-5 w-5" />}
                  />
                ) : (
                  <div className="space-y-3">
                    {openDisputes.map((d) => (
                      <div key={d.dispute_id} className="rounded-[1.1rem] border border-[#e8dfd0] bg-white p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusPill tone="danger">{locale === 'ar' ? 'نزاع' : 'Dispute'}</StatusPill>
                          <span className="text-[13px] font-medium text-text">{d.employee_key}</span>
                          <span className="text-[12px] text-subtle">{String(d.work_date || '').slice(0, 10)}</span>
                        </div>
                        <p className="mt-2 text-[13px] text-text">{d.reason || '—'}</p>
                        <p className="mt-1 text-[12px] text-subtle">
                          {t.owner}: {d.raised_by_phone || '—'} · {t.next}: {locale === 'ar' ? 'حل النزاع' : 'Resolve dispute'}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Button size="sm" disabled={busyId === d.dispute_id} onClick={() => void runResolveDispute(d, 'overturned')}>
                            {locale === 'ar' ? 'قبول النزاع' : 'Uphold employee'}
                          </Button>
                          <Button size="sm" variant="ghost" disabled={busyId === d.dispute_id} onClick={() => void runResolveDispute(d, 'upheld')}>
                            {locale === 'ar' ? 'تأكيد السجل' : 'Keep record'}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : null}

              {tab === 'locked' ? (
                lockedish.length === 0 ? (
                  <WorkflowEmpty title={locale === 'ar' ? 'لا توجد أيام مستبعدة ظاهرة' : 'No excluded days in view'} />
                ) : (
                  <div className="space-y-2">
                    {lockedish.slice(0, 20).map((exc) => (
                      <div key={exc.exception_id} className="rounded-[1rem] border border-[#e8dfd0] bg-white px-3 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusPill tone="warning">{exceptionKindLabel(exc.kind, locale)}</StatusPill>
                          <span className="text-[13px] font-medium text-text">{exc.employee_name || exc.employee_key}</span>
                          <span className="text-[12px] text-subtle">{String(exc.work_date || '').slice(0, 10)}</span>
                        </div>
                        <p className="mt-2 text-[12px] text-subtle/90">
                          {payrollExclusionReason({ exception_state: exc.kind, payroll_eligible: false }, locale)}
                        </p>
                      </div>
                    ))}
                  </div>
                )
              ) : null}
            </>
          )}
        </div>
      </Card>
    </div>
  )
}
