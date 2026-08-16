/**
 * Payroll Wave 3 — payslip workspace (display only).
 * Native preview payslips are non-authoritative; external mirrors keep external authority.
 */
import { useCallback, useEffect, useState } from 'react'

import {
  DashboardApiError,
  getPayrollPayslipDetail,
  getPayrollPayslipWorkspace,
  postPayrollPayslipExternal,
  postPayrollPayslipNative,
  postPayrollPayslipRelease,
  postPayrollPayslipReplace,
  postPayrollPayslipRevoke,
  postPayrollPayslipUnrelease,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { FRESHNESS_MS } from '@/lib/query/freshness'
import { useVisibilitySoftPoll } from '@/lib/query/useVisibilitySoftPoll'
import { BlockedReason, useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import {
  payrollPayslipCopy,
  payslipEmployeeVisibilityLabel,
  payslipStatusTone,
} from '@/posthire/payrollPayslipUx'
import type { DashboardAccess } from '@/types'
type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type PayslipWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

type PayslipRow = {
  payslip_id: string
  source_kind: string
  employee_key: string
  period_start: string
  period_end: string
  version_number: number
  status: string
  employee_visibility?: string
  employee_facing_state?: string
  employee_visible?: boolean
  money_authority: string
  totals_net?: number
  currency?: string
}

type Workspace = {
  payslips?: PayslipRow[]
  preview_runs?: Array<Record<string, unknown>>
  import_runs?: Array<Record<string, unknown>>
  manager_scoped?: boolean
  can_manage?: boolean
}

export function PayslipWorkspace({ access, permissions, onNotice, onAccessIssue }: PayslipWorkspaceProps) {
  const locale = useEmployees360Locale()
  const c = payrollPayslipCopy(locale)
  const isAr = locale === 'ar'
  const canManage = can(permissions, 'payroll.manage')
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'list' | 'history'>('list')
  const [reason, setReason] = useState('')
  const [previewRunId, setPreviewRunId] = useState('')
  const [importRunId, setImportRunId] = useState('')
  const [employeeKey, setEmployeeKey] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)
  const [honestyOpen, setHonestyOpen] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const ws = (await getPayrollPayslipWorkspace(access)) as Workspace
      setData(ws)
      const firstPreview = String((ws.preview_runs || [])[0]?.preview_run_id || '')
      const firstImport = String((ws.import_runs || [])[0]?.import_run_id || '')
      setPreviewRunId((prev) => prev || firstPreview)
      setImportRunId((prev) => prev || firstImport)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        setError('permission')
        return
      }
      if (err instanceof DashboardApiError && err.status === 404) {
        setError('disabled')
        return
      }
      setError('load')
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  useVisibilitySoftPoll(reload, FRESHNESS_MS.inboundQueue, !busy)

  const openDetail = async (id: string) => {
    setSelectedId(id)
    try {
      const payload = await getPayrollPayslipDetail(access, id)
      setDetail(payload)
    } catch (err) {
      onNotice(err instanceof DashboardApiError ? err.message : c.permissionDenied, 'error')
    }
  }

  if (loading && !data) {
    return (
      <div className="rounded-[var(--radius-wf-panel)] border border-line/70 bg-white/70 px-5 py-8 text-center text-[13px] text-subtle" dir={isAr ? 'rtl' : 'ltr'}>
        {c.loading}
      </div>
    )
  }

  if (error === 'disabled') {
    return (
      <div className="space-y-2 rounded-[var(--radius-wf-panel)] border border-line/70 bg-white/80 px-5 py-8 text-center" dir={isAr ? 'rtl' : 'ltr'}>
        <p className="text-[15px] font-medium text-text">{c.disabled}</p>
        <p className="text-[13px] text-subtle">{c.disabledHint}</p>
      </div>
    )
  }

  if (error === 'permission') {
    return <BlockedReason reason={c.permissionDenied} />
  }

  const payslips = data?.payslips || []
  const toneClass = (status: string) => {
    const t = payslipStatusTone(status)
    if (t === 'success') return 'text-emerald-700'
    if (t === 'warning') return 'text-amber-700'
    if (t === 'danger') return 'text-rose-700'
    return 'text-subtle'
  }

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} data-testid="payslip-workspace">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-subtle/90">{c.subtitle}</p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="text-[12px] font-medium text-subtle underline"
            onClick={() => setHonestyOpen((v) => !v)}
            data-payroll-honesty-toggle
          >
            {honestyOpen ? (isAr ? 'إخفاء تفاصيل السلطة' : 'Hide authority details') : isAr ? 'إظهار تفاصيل السلطة' : 'Show authority details'}
          </button>
          <button
            type="button"
            className="text-[12px] font-medium text-subtle underline"
            onClick={() => void reload()}
            aria-label={c.refresh}
          >
            {c.refresh}
          </button>
        </div>
      </div>

      {honestyOpen ? (
        <div className="rounded-xl border border-dashed border-amber-200/80 bg-amber-50/70 px-4 py-3 text-[13px] text-amber-950" data-payroll-honesty>
          <p>{c.honesty}</p>
          <p className="mt-1">
            {c.paymentDisabled} · {c.notMoney}
          </p>
          <p className="mt-1 text-amber-900/80">{c.historyRetained}</p>
          {data?.manager_scoped ? <p className="mt-1">{c.managerScoped}</p> : null}
        </div>
      ) : null}
      <p className="text-[12px] text-subtle md:hidden">{c.mobileHint}</p>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`rounded-full px-3 py-1.5 text-[13px] font-medium ${tab === 'list' ? 'bg-wf-ink text-white' : 'bg-[#f3ebe0] text-subtle'}`}
          onClick={() => setTab('list')}
        >
          {c.tabList}
        </button>
        <button
          type="button"
          className={`rounded-full px-3 py-1.5 text-[13px] font-medium ${tab === 'history' ? 'bg-wf-ink text-white' : 'bg-[#f3ebe0] text-subtle'}`}
          onClick={() => setTab('history')}
        >
          {c.tabHistory}
        </button>
      </div>

      {canManage ? (
        <div className="grid gap-3 rounded-xl border border-line/70 bg-white/80 p-4 md:grid-cols-2">
          <label className="block text-[12px] text-subtle">
            {c.employee}
            <input
              className="mt-1 w-full rounded-lg border border-line/80 bg-white px-3 py-2 text-[13px] text-text"
              value={employeeKey}
              onChange={(e) => setEmployeeKey(e.target.value)}
              placeholder="WATHEFNI-PYW1-…"
            />
          </label>
          <label className="block text-[12px] text-subtle">
            {c.reasonRequired}
            <input
              className="mt-1 w-full rounded-lg border border-line/80 bg-white px-3 py-2 text-[13px] text-text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={c.reasonPlaceholder}
            />
          </label>
          <label className="block text-[12px] text-subtle">
            {isAr ? 'تشغيل المعاينة' : 'Native preview run'}
            <select
              className="mt-1 w-full rounded-lg border border-line/80 bg-white px-3 py-2 text-[13px] text-text"
              value={previewRunId}
              onChange={(e) => setPreviewRunId(e.target.value)}
              data-testid="payslip-preview-run-picker"
            >
              <option value="">{isAr ? 'اختر تشغيل المعاينة' : 'Choose preview run'}</option>
              {(data?.preview_runs || []).map((row) => {
                const id = String(row.preview_run_id || '')
                const start = String(row.period_start || '').slice(0, 10)
                const end = String(row.period_end || '').slice(0, 10)
                const status = String(row.status || '')
                return (
                  <option key={id} value={id}>
                    {start && end ? `${start} → ${end}` : id.slice(0, 8)} · {status}
                  </option>
                )
              })}
            </select>
          </label>
          <label className="block text-[12px] text-subtle">
            {isAr ? 'رفع المورّد' : 'Vendor upload (external)'}
            <select
              className="mt-1 w-full rounded-lg border border-line/80 bg-white px-3 py-2 text-[13px] text-text"
              value={importRunId}
              onChange={(e) => setImportRunId(e.target.value)}
              data-testid="payslip-import-run-picker"
            >
              <option value="">{isAr ? 'اختر رفع المورّد' : 'Choose vendor upload'}</option>
              {(data?.import_runs || []).map((row) => {
                const id = String(row.import_run_id || '')
                const start = String(row.period_start || row.created_at || '').slice(0, 10)
                const status = String(row.status || '')
                const matched = row.matched_count != null ? String(row.matched_count) : '—'
                return (
                  <option key={id} value={id}>
                    {start || 'upload'} · {status} · matched {matched}
                  </option>
                )
              })}
            </select>
          </label>
          <div className="flex flex-wrap gap-2 md:col-span-2">
            <button
              type="button"
              disabled={busy || !employeeKey || !previewRunId || !reason.trim()}
              className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] font-medium text-white disabled:opacity-50"
              onClick={async () => {
                setBusy(true)
                try {
                  const payload = await postPayrollPayslipNative(access, {
                    preview_run_id: previewRunId,
                    employee_key: employeeKey,
                    reason,
                  })
                  onNotice(payload.idempotent ? 'Idempotent replay' : 'Native payslip generated', 'success')
                  await reload()
                } catch (err) {
                  onNotice(err instanceof DashboardApiError ? err.message : c.permissionDenied, 'error')
                } finally {
                  setBusy(false)
                }
              }}
            >
              {c.generateNative}
            </button>
            <button
              type="button"
              disabled={busy || !employeeKey || !importRunId || !reason.trim()}
              className="rounded-lg border border-line/80 bg-white px-3 py-2 text-[13px] font-medium text-text disabled:opacity-50"
              onClick={async () => {
                setBusy(true)
                try {
                  const payload = await postPayrollPayslipExternal(access, {
                    import_run_id: importRunId,
                    employee_key: employeeKey,
                    reason,
                  })
                  onNotice(payload.idempotent ? 'Idempotent replay' : 'External payslip generated', 'success')
                  await reload()
                } catch (err) {
                  onNotice(err instanceof DashboardApiError ? err.message : c.permissionDenied, 'error')
                } finally {
                  setBusy(false)
                }
              }}
            >
              {c.generateExternal}
            </button>
          </div>
          <p className="text-[12px] text-subtle md:col-span-2">
            {c.nativeLabel} · {c.externalLabel}
          </p>
        </div>
      ) : null}

      {payslips.length === 0 ? (
        <WorkflowEmpty title={c.empty} hint={c.emptyHint} />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line/70 bg-white/80">
          <table className="min-w-full text-start text-[13px]">
            <thead className="border-b border-line/60 text-subtle">
              <tr>
                <th className="px-3 py-2 font-medium">{c.employee}</th>
                <th className="px-3 py-2 font-medium">{c.period}</th>
                <th className="px-3 py-2 font-medium">{c.status}</th>
                <th className="px-3 py-2 font-medium">{c.employeeVisibility}</th>
                <th className="px-3 py-2 font-medium">{c.version}</th>
                <th className="px-3 py-2 font-medium">{c.net}</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {payslips
                .filter((p) => (tab === 'list' ? p.status === 'active' : true))
                .map((p) => (
                  <tr key={p.payslip_id} className="border-b border-line/40 last:border-0">
                    <td className="px-3 py-2 text-text">{p.employee_key}</td>
                    <td className="px-3 py-2 text-subtle">
                      {p.period_start} → {p.period_end}
                      <div className="text-[11px]">{p.source_kind === 'native_preview' ? c.nativeLabel : c.externalLabel}</div>
                    </td>
                    <td className={`px-3 py-2 ${toneClass(p.status)}`}>{p.status}</td>
                    <td className={`px-3 py-2 ${toneClass(String(p.employee_facing_state || p.employee_visibility || ''))}`}>
                      {payslipEmployeeVisibilityLabel(p, c)}
                    </td>
                    <td className="px-3 py-2 text-subtle">v{p.version_number}</td>
                    <td className="px-3 py-2 text-text">
                      {p.totals_net} {p.currency || 'KWD'}
                    </td>
                    <td className="px-3 py-2">
                      <button type="button" className="text-[12px] font-medium text-wf-ink" onClick={() => void openDetail(p.payslip_id)}>
                        {c.audit}
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && detail ? (
        <div className="space-y-3 rounded-xl border border-line/70 bg-white/90 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-text">{c.audit}</h3>
            <a
              className="rounded-lg border border-line/80 px-2 py-1 text-[12px]"
              href={`/dashboard/posthire/payroll/payslips/${encodeURIComponent(selectedId)}/download?locale=${locale}`}
            >
              {c.download}
            </a>
            {canManage && String((detail.payslip as PayslipRow | undefined)?.status) === 'active' ? (
              <>
                {String((detail.payslip as PayslipRow | undefined)?.employee_visibility || '') !== 'released' ? (
                  <button
                    type="button"
                    className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-[12px] text-emerald-900"
                    disabled={busy || !reason.trim()}
                    onClick={async () => {
                      setBusy(true)
                      try {
                        const payload = await postPayrollPayslipRelease(access, selectedId, { reason })
                        onNotice(payload.idempotent ? (isAr ? 'كان مُصدَراً مسبقاً' : 'Already released') : c.release, 'success')
                        await reload()
                        await openDetail(selectedId)
                      } catch (err) {
                        onNotice(err instanceof Error ? err.message : c.permissionDenied, 'error')
                      } finally {
                        setBusy(false)
                      }
                    }}
                  >
                    {c.release}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="rounded-lg border border-amber-200 px-2 py-1 text-[12px] text-amber-900"
                    disabled={busy || !reason.trim()}
                    onClick={async () => {
                      setBusy(true)
                      try {
                        await postPayrollPayslipUnrelease(access, selectedId, { reason })
                        onNotice(c.unrelease, 'info')
                        await reload()
                        await openDetail(selectedId)
                      } catch (err) {
                        onNotice(err instanceof Error ? err.message : c.permissionDenied, 'error')
                      } finally {
                        setBusy(false)
                      }
                    }}
                  >
                    {c.unrelease}
                  </button>
                )}
                <button
                  type="button"
                  className="rounded-lg border border-line/80 px-2 py-1 text-[12px]"
                  disabled={busy || !reason.trim()}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      const payload = await postPayrollPayslipReplace(access, selectedId, { reason })
                      onNotice('Replaced — re-release required for employee app', 'success')
                      await reload()
                      const nextId = String((payload.payslip as PayslipRow | undefined)?.payslip_id || selectedId)
                      await openDetail(nextId)
                    } catch (err) {
                      onNotice(err instanceof Error ? err.message : c.permissionDenied, 'error')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {c.replace}
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-rose-200 px-2 py-1 text-[12px] text-rose-700"
                  disabled={busy || !reason.trim()}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      await postPayrollPayslipRevoke(access, selectedId, { reason })
                      onNotice('Revoked (history retained)', 'success')
                      await reload()
                      await openDetail(selectedId)
                    } catch (err) {
                      onNotice(err instanceof Error ? err.message : c.permissionDenied, 'error')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {c.revoke}
                </button>
              </>
            ) : null}
          </div>
          <p className="text-[12px] text-subtle">{c.releaseHint}</p>
          <pre className="overflow-x-auto rounded-lg bg-black/[0.03] p-3 text-[11px] leading-relaxed text-text">
            {JSON.stringify({ payslip: detail.payslip, lines: detail.lines, history: detail.history }, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  )
}

export default PayslipWorkspace
