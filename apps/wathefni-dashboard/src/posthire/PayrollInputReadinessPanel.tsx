/**
 * Payroll Authority P2 — minimal payroll input readiness panel.
 * Facts only; does not claim money authority or calculate OT/sick/PH pay.
 */
import { Loader2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  getPayrollInputDetail,
  getPayrollInputReadiness,
  postPayrollInputAssemble,
  postPayrollInputLock,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEmployees360Locale } from '@/posthire/employees360/chrome'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PayrollInputReadinessPanelProps = {
  access: DashboardAccess
  permissions: string[]
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  periodStart?: string
  periodEnd?: string
}

function canManage(permissions: string[]) {
  return permissions.includes('payroll.manage')
}

function copy(locale: 'en' | 'ar') {
  if (locale === 'ar') {
    return {
      title: 'جاهزية مدخلات الرواتب',
      hint: 'حضور وإجازات مجمّعة كوقائع فقط — بلا احتساب أجر بعد.',
      assemble: 'تجميع المدخلات',
      lock: 'قفل المدخلات',
      refresh: 'تحديث',
      status: 'الحالة',
      blockers: 'عوائق',
      employees: 'الموظفون',
      provenance: 'الأصل',
      noSnap: 'لا توجد لقطة مدخلات لهذه الفترة',
      moneyOff: 'معالجة الدفع معطّلة · بلا احتساب نظامي',
    }
  }
  return {
    title: 'Payroll input readiness',
    hint: 'Attendance + leave assembled as facts only — no pay calculation yet.',
    assemble: 'Assemble inputs',
    lock: 'Lock inputs',
    refresh: 'Refresh',
    status: 'Status',
    blockers: 'Blockers',
    employees: 'Employees',
    provenance: 'Provenance',
    noSnap: 'No input snapshot for this period',
    moneyOff: 'Payment processing disabled · no statutory money calc',
  }
}

function toneForStatus(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = String(status || '')
  if (s === 'locked' || s === 'ready') return 'success'
  if (s === 'needs_review' || s === 'assembling') return 'warning'
  if (s === 'superseded') return 'neutral'
  return 'danger'
}

export function PayrollInputReadinessPanel({
  access,
  permissions,
  onNotice,
  onAccessIssue,
  periodStart,
  periodEnd,
}: PayrollInputReadinessPanelProps) {
  const locale = useEmployees360Locale()
  const c = copy(locale)
  const isAr = locale === 'ar'
  const [start, setStart] = useState(periodStart || '')
  const [end, setEnd] = useState(periodEnd || '')
  const [busy, setBusy] = useState(false)
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [detailEmp, setDetailEmp] = useState<string | null>(null)
  const [lines, setLines] = useState<Array<Record<string, unknown>>>([])

  const reload = useCallback(async () => {
    if (!start || !end) return
    setBusy(true)
    try {
      const next = await getPayrollInputReadiness(access, { period_start: start, period_end: end })
      setData(next)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(err instanceof DashboardApiError ? err.message : c.noSnap, 'error')
    } finally {
      setBusy(false)
    }
  }, [access, start, end, onAccessIssue, onNotice, c.noSnap])

  useEffect(() => {
    if (periodStart) setStart(periodStart)
    if (periodEnd) setEnd(periodEnd)
  }, [periodStart, periodEnd])

  useEffect(() => {
    void reload()
  }, [reload])

  const snap = (data?.input_snapshot || null) as Record<string, unknown> | null
  const employees = (data?.employees as Array<Record<string, unknown>>) || []
  const blockers = (data?.blockers as Array<Record<string, unknown>>) || []
  const status = snap ? String(snap.status || data?.status || '') : null

  async function onAssemble() {
    if (!canManage(permissions)) return
    setBusy(true)
    try {
      const res = await postPayrollInputAssemble(access, {
        period_start: start,
        period_end: end,
        reason: `ui_assemble_${Date.now()}`,
      })
      onNotice(locale === 'ar' ? 'تم التجميع' : 'Inputs assembled', 'success')
      setData(res)
      await reload()
    } catch (err) {
      onNotice(err instanceof DashboardApiError ? err.message : 'Assemble failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function onLock() {
    if (!canManage(permissions) || !snap?.input_snapshot_id) return
    setBusy(true)
    try {
      await postPayrollInputLock(access, String(snap.input_snapshot_id), {
        reason: `ui_lock_${Date.now()}`,
      })
      onNotice(locale === 'ar' ? 'تم القفل' : 'Inputs locked', 'success')
      await reload()
    } catch (err) {
      onNotice(err instanceof DashboardApiError ? err.message : 'Lock failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function openProvenance(employeeKey: string) {
    if (!snap?.input_snapshot_id) return
    setDetailEmp(employeeKey)
    try {
      const detail = await getPayrollInputDetail(access, String(snap.input_snapshot_id), employeeKey)
      setLines((detail.lines as Array<Record<string, unknown>>) || [])
    } catch (err) {
      onNotice(err instanceof DashboardApiError ? err.message : 'Detail failed', 'error')
    }
  }

  return (
    <section
      className="rounded-2xl border border-[#eadfce] bg-[#fffaf3] p-4 space-y-3"
      dir={isAr ? 'rtl' : 'ltr'}
      data-testid="payroll-input-readiness"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-wf-ink">{c.title}</h3>
          <p className="text-[12.5px] text-subtle/90 mt-0.5">{c.hint}</p>
          <p className="text-[11px] text-subtle/70 mt-1">{c.moneyOff}</p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {status ? <StatusPill tone={toneForStatus(status)}>{status}</StatusPill> : null}
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => void reload()}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span className="ms-1">{c.refresh}</span>
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-end">
        <label className="text-[12px] text-subtle">
          Start
          <Input className="mt-1 w-[10.5rem]" value={start} onChange={(e) => setStart(e.target.value)} placeholder="YYYY-MM-DD" />
        </label>
        <label className="text-[12px] text-subtle">
          End
          <Input className="mt-1 w-[10.5rem]" value={end} onChange={(e) => setEnd(e.target.value)} placeholder="YYYY-MM-DD" />
        </label>
        {canManage(permissions) ? (
          <>
            <Button type="button" size="sm" disabled={busy || !start || !end} onClick={() => void onAssemble()}>
              {c.assemble}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={busy || !snap?.input_snapshot_id || status === 'locked' || status === 'needs_review'}
              onClick={() => void onLock()}
            >
              {c.lock}
            </Button>
          </>
        ) : null}
      </div>

      {!snap ? (
        <p className="text-[13px] text-subtle">{c.noSnap}</p>
      ) : (
        <div className="space-y-2">
          <div className="text-[12.5px] text-subtle">
            {c.status}: <span className="font-medium text-wf-ink">{status}</span>
            {' · '}
            mode={String(snap.attendance_payroll_mode || '')}
            {' · '}
            blockers={Number(snap.issue_blocker_count || blockers.length || 0)}
          </div>
          {blockers.length > 0 ? (
            <ul className="text-[12.5px] space-y-1" data-testid="payroll-input-blockers">
              <li className="font-medium text-wf-ink">{c.blockers}</li>
              {blockers.slice(0, 8).map((b, i) => (
                <li key={i} className="text-amber-900/90">
                  {String(b.code || '')}: {String(b.message_en || b.message_ar || '')}
                  {b.employee_key ? ` · ${String(b.employee_key)}` : ''}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="overflow-x-auto">
            <table className="min-w-full text-[12.5px]">
              <thead>
                <tr className="text-subtle text-start">
                  <th className="py-1 pe-3 font-medium">{c.employees}</th>
                  <th className="py-1 pe-3 font-medium">Attendance</th>
                  <th className="py-1 pe-3 font-medium">Leave</th>
                  <th className="py-1 pe-3 font-medium">{c.status}</th>
                  <th className="py-1 font-medium">{c.provenance}</th>
                </tr>
              </thead>
              <tbody>
                {employees.slice(0, 40).map((emp) => {
                  const att = (emp.attendance_summary || {}) as Record<string, unknown>
                  const leave = (emp.leave_summary || {}) as Record<string, unknown>
                  return (
                    <tr key={String(emp.employee_key)} className="border-t border-[#eadfce]/40">
                      <td className="py-1.5 pe-3 font-medium text-wf-ink">{String(emp.employee_key)}</td>
                      <td className="py-1.5 pe-3 text-subtle">
                        days={String(att.approved_days ?? 0)} missing={String(att.incomplete_or_missing ?? 0)}
                      </td>
                      <td className="py-1.5 pe-3 text-subtle">
                        approved={String(leave.approved_intervals ?? 0)} unpaid_dates={String(leave.unpaid_dates ?? 0)}
                      </td>
                      <td className="py-1.5 pe-3">{String(emp.readiness_status || '')}</td>
                      <td className="py-1.5">
                        <button
                          type="button"
                          className={cn('underline text-wf-ink/80')}
                          onClick={() => void openProvenance(String(emp.employee_key))}
                        >
                          {c.provenance}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {detailEmp && lines.length > 0 ? (
            <div className="rounded-xl bg-white/70 border border-[#eadfce] p-3 text-[12px] space-y-1" data-testid="payroll-input-provenance">
              <p className="font-medium text-wf-ink">
                {c.provenance}: {detailEmp}
              </p>
              {lines.slice(0, 30).map((ln, i) => (
                <div key={i} className="text-subtle">
                  {String(ln.line_kind)} · {String(ln.fact_date || '')}
                  {ln.source_table ? ` · ${String(ln.source_table)}:${String(ln.source_id || '')}` : ''}
                  {ln.suppressed ? ` · suppressed:${String(ln.suppression_reason || '')}` : ''}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}
