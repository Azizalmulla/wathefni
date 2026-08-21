/**
 * Payroll Wave 4 — close + finance export workspace (staging).
 * Journal drafts + bank-export contract validation only. Payment disabled.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  DashboardApiError,
  getPayrollCloseExportWorkspace,
  postPayrollCloseApprove,
  postPayrollCloseBankContract,
  postPayrollCloseCreate,
  postPayrollCloseJournal,
  postPayrollCloseReopenConfirm,
  postPayrollCloseReopenInitiate,
  postPayrollCloseSeal,
  postPayrollCloseSubmit,
  postPayrollFinanceExportRecord,
} from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { BlockedReason, useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'
import { closeRunStatusTone, payrollCloseExportCopy } from '@/posthire/payrollCloseExportUx'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type CloseExportWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

type CloseRun = {
  close_run_id: string
  source_kind: string
  status: string
  period_start?: string
  period_end?: string
  money_authority?: string
  totals_net?: number
  snapshot_immutable?: boolean
  row_version?: number
}

type Workspace = {
  close_runs?: CloseRun[]
  account_mappings?: Array<Record<string, unknown>>
  finance_exports?: Array<Record<string, unknown>>
  preview_runs?: Array<Record<string, unknown>>
  import_runs?: Array<Record<string, unknown>>
  can_manage?: boolean
  can_approve?: boolean
  can_export?: boolean
}

export function CloseExportWorkspace({
  access,
  permissions,
  onNotice,
  onAccessIssue,
}: CloseExportWorkspaceProps) {
  const locale = useEmployees360Locale()
  const c = payrollCloseExportCopy(locale)
  const isAr = locale === 'ar'
  const canManage = can(permissions, 'payroll.manage')
  const canApprove = can(permissions, 'payroll.approve')
  const canExport = can(permissions, 'payroll.export')
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)
  const paintedRef = useRef(false)
  const [tab, setTab] = useState<'close' | 'mappings' | 'exports'>('close')
  const [reason, setReason] = useState('')
  const [previewRunId, setPreviewRunId] = useState('')
  const [importRunId, setImportRunId] = useState('')
  const [selected, setSelected] = useState<CloseRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [honestyOpen, setHonestyOpen] = useState(false)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    const cold = !paintedRef.current
    if (cold) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const ws = (await getPayrollCloseExportWorkspace(access)) as Workspace
      if (requestId !== requestIdRef.current) return
      setData(ws)
      paintedRef.current = true
      const firstPreview = String((ws.preview_runs || [])[0]?.preview_run_id || '')
      const firstImport = String((ws.import_runs || [])[0]?.import_run_id || '')
      if (firstPreview) setPreviewRunId((v) => v || firstPreview)
      if (firstImport) setImportRunId((v) => v || firstImport)
      setSelected((prev) => {
        if (!prev) return prev
        const next = (ws.close_runs || []).find((r) => r.close_run_id === prev.close_run_id)
        return next || prev
      })
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      if (err instanceof DashboardApiError && err.status === 404) {
        setError('disabled')
      } else {
        const issue = accessIssueFromError(err)
        if (issue && onAccessIssue) onAccessIssue(issue)
        setError(
          err instanceof DashboardApiError
            ? err.message
            : isAr
              ? 'تعذر تحميل مساحة الإقفال والتصدير.'
              : 'We couldn’t load the close and export workspace.',
        )
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [access, isAr, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(fn: () => Promise<unknown>, okMsg: string) {
    if (!reason.trim()) {
      onNotice(c.reasonRequired, 'error')
      return
    }
    setBusy(true)
    try {
      await fn()
      onNotice(okMsg, 'success')
      setReason('')
      await reload()
    } catch (err) {
      onNotice(
        err instanceof DashboardApiError
          ? err.message
          : isAr
            ? 'تعذر إكمال هذا الإجراء.'
            : 'We couldn’t complete this action.',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) {
    return <p className="text-sm text-subtle">{c.loading}</p>
  }
  if (error === 'disabled') {
    return <BlockedReason reason={`${c.disabled} — ${c.disabledHint}`} locale={isAr ? 'ar' : 'en'} />
  }
  if (error && !data) {
    return <BlockedReason reason={error} locale={isAr ? 'ar' : 'en'} />
  }

  const runs = data?.close_runs || []

  return (
    <div
      className="space-y-4"
      data-testid="close-export-workspace"
      data-rendering-soft-keep
      data-rendering-updating={refreshing ? 'true' : undefined}
      dir={isAr ? 'rtl' : 'ltr'}
    >
      {refreshing ? (
        <p className="text-[11px] text-subtle" data-rendering-soft-status>
          {isAr ? 'جاري التحديث…' : 'Updating…'}
        </p>
      ) : null}
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
          <button type="button" className="text-[12px] font-medium text-subtle underline" onClick={() => void reload()} aria-label={c.refresh}>
            {c.refresh}
          </button>
        </div>
      </div>

      {honestyOpen ? (
        <div className="space-y-1 rounded-md border border-dashed border-line/70 bg-black/[0.02] px-3 py-2 text-[13px] text-text" data-payroll-honesty>
          <p>{c.honesty}</p>
          <p className="text-[12px] text-subtle">
            {c.paymentDisabled} · {c.nativeNonAuth} · {c.externalAuthority}
          </p>
          <p className="text-[12px] text-subtle">{c.sodHint}</p>
        </div>
      ) : null}
      <p className="text-[12px] text-subtle md:hidden">{c.mobileHint}</p>

      <HrSurfaceTabs
        value={tab}
        onChange={setTab}
        items={[
          { id: 'close', label: c.tabClose },
          { id: 'mappings', label: c.tabMappings },
          { id: 'exports', label: c.tabExports },
        ]}
      />

      <label className="block text-[13px] text-subtle">
        {c.reasonPlaceholder}
        <input
          className="mt-1 w-full rounded-md border border-black/10 bg-white px-3 py-2 text-sm"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>

      {tab === 'close' ? (
        <div className="space-y-3">
          {canManage ? (
            <div className="flex flex-wrap gap-2">
              <select
                className="min-w-[12rem] flex-1 rounded-md border border-black/10 px-3 py-2 text-sm"
                value={previewRunId}
                onChange={(e) => setPreviewRunId(e.target.value)}
                data-testid="close-preview-run-picker"
                aria-label={isAr ? 'تشغيل المعاينة' : 'Native preview run'}
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
              <button
                type="button"
                disabled={busy || !previewRunId}
                className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
                onClick={() =>
                  void runAction(
                    () =>
                      postPayrollCloseCreate(access, {
                        source_kind: 'native_preview',
                        source_run_id: previewRunId,
                        reason,
                      }),
                    c.createFromPreview,
                  )
                }
              >
                {c.createFromPreview}
              </button>
              <select
                className="min-w-[12rem] flex-1 rounded-md border border-black/10 px-3 py-2 text-sm"
                value={importRunId}
                onChange={(e) => setImportRunId(e.target.value)}
                data-testid="close-import-run-picker"
                aria-label={isAr ? 'رفع المورّد' : 'Vendor upload'}
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
              <button
                type="button"
                disabled={busy || !importRunId}
                className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
                onClick={() =>
                  void runAction(
                    () =>
                      postPayrollCloseCreate(access, {
                        source_kind: 'external_import',
                        source_run_id: importRunId,
                        reason,
                      }),
                    c.createFromImport,
                  )
                }
              >
                {c.createFromImport}
              </button>
            </div>
          ) : null}

          {runs.length === 0 ? (
            <WorkflowEmpty title={c.empty} hint={c.emptyHint} />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-[13px]">
                <thead className="text-subtle">
                  <tr>
                    <th className="px-2 py-1">{c.period}</th>
                    <th className="px-2 py-1">{c.status}</th>
                    <th className="px-2 py-1">{c.totals}</th>
                    <th className="px-2 py-1">ID</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr
                      key={r.close_run_id}
                      className={`cursor-pointer border-t border-black/5 ${selected?.close_run_id === r.close_run_id ? 'bg-wf-ink/5' : ''}`}
                      onClick={() => setSelected(r)}
                    >
                      <td className="px-2 py-2">
                        {r.period_start} → {r.period_end}
                        <div className="text-[11px] text-subtle">{r.source_kind}</div>
                      </td>
                      <td className={`px-2 py-2 ${closeRunStatusTone(r.status)}`}>
                        {r.status}
                        {r.snapshot_immutable ? ` · ${c.immutable}` : ''}
                      </td>
                      <td className="px-2 py-2">{r.totals_net ?? '—'}</td>
                      <td className="px-2 py-2 font-mono text-[11px]">{r.close_run_id.slice(0, 8)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {selected ? (
            <div className="flex flex-wrap gap-2 rounded-md border border-black/10 p-3">
              {canManage && selected.status === 'draft' ? (
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-lg bg-wf-ink/90 px-3 py-2 text-[13px] text-white disabled:opacity-40"
                  onClick={() =>
                    void runAction(
                      () =>
                        postPayrollCloseSubmit(access, selected.close_run_id, {
                          reason,
                          expected_row_version: selected.row_version ?? 1,
                        }),
                      c.submitReview,
                    )
                  }
                >
                  {c.submitReview}
                </button>
              ) : null}
              {canApprove && selected.status === 'in_review' ? (
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-lg bg-wf-ink/90 px-3 py-2 text-[13px] text-white disabled:opacity-40"
                  onClick={() =>
                    void runAction(
                      () =>
                        postPayrollCloseApprove(access, selected.close_run_id, {
                          reason,
                          expected_row_version: selected.row_version ?? 1,
                        }),
                      c.approve,
                    )
                  }
                >
                  {c.approve}
                </button>
              ) : null}
              {canApprove && selected.status === 'approved' ? (
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-lg bg-wf-ink px-3 py-2 text-[13px] text-white disabled:opacity-40"
                  onClick={() =>
                    void runAction(
                      () =>
                        postPayrollCloseSeal(access, selected.close_run_id, {
                          reason,
                          expected_row_version: selected.row_version ?? 1,
                        }),
                      c.close,
                    )
                  }
                >
                  {c.close}
                </button>
              ) : null}
              {canManage && selected.status === 'closed' ? (
                <>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                    onClick={() =>
                      void runAction(
                        () => postPayrollCloseJournal(access, selected.close_run_id, { reason }),
                        c.generateJournal,
                      )
                    }
                  >
                    {c.generateJournal}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                    onClick={() =>
                      void runAction(
                        () => postPayrollCloseBankContract(access, selected.close_run_id, { reason }),
                        c.generateBankContract,
                      )
                    }
                  >
                    {c.generateBankContract}
                  </button>
                  {canApprove ? (
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                      onClick={() =>
                        void runAction(
                          () => postPayrollCloseReopenInitiate(access, selected.close_run_id, { reason }),
                          c.reopen,
                        )
                      }
                    >
                      {c.reopen}
                    </button>
                  ) : null}
                  {canApprove ? (
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                      onClick={() =>
                        void runAction(
                          () => postPayrollCloseReopenConfirm(access, selected.close_run_id, { reason }),
                          c.confirmReopen,
                        )
                      }
                    >
                      {c.confirmReopen}
                    </button>
                  ) : null}
                </>
              ) : null}
              {canExport && selected.status === 'closed' ? (
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-lg border border-black/10 px-3 py-2 text-[13px] disabled:opacity-40"
                  onClick={() =>
                    void runAction(
                      () =>
                        postPayrollFinanceExportRecord(access, {
                          close_run_id: selected.close_run_id,
                          export_kind: 'journal_draft',
                          artifact_id: '',
                          reason,
                        }),
                      c.recordExport,
                    )
                  }
                >
                  {c.recordExport}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'mappings' ? (
        <div className="overflow-x-auto">
          {(data?.account_mappings || []).length === 0 ? (
            <WorkflowEmpty title={c.empty} hint={c.balanced} />
          ) : (
            <table className="min-w-full text-left text-[13px]">
              <thead className="text-subtle">
                <tr>
                  <th className="px-2 py-1">Code</th>
                  <th className="px-2 py-1">Account</th>
                  <th className="px-2 py-1">Side</th>
                  <th className="px-2 py-1">Cost centre</th>
                </tr>
              </thead>
              <tbody>
                {(data?.account_mappings || []).map((m) => (
                  <tr key={String(m.mapping_id)} className="border-t border-black/5">
                    <td className="px-2 py-2">{String(m.component_code)}</td>
                    <td className="px-2 py-2">{String(m.account_code)}</td>
                    <td className="px-2 py-2">{String(m.journal_side)}</td>
                    <td className="px-2 py-2">{String(m.cost_centre || '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}

      {tab === 'exports' ? (
        <div className="overflow-x-auto">
          {(data?.finance_exports || []).length === 0 ? (
            <WorkflowEmpty title={c.empty} hint={c.validationOnly} />
          ) : (
            <table className="min-w-full text-left text-[13px]">
              <thead className="text-subtle">
                <tr>
                  <th className="px-2 py-1">Kind</th>
                  <th className="px-2 py-1">{c.status}</th>
                  <th className="px-2 py-1">Recon</th>
                  <th className="px-2 py-1">Fingerprint</th>
                </tr>
              </thead>
              <tbody>
                {(data?.finance_exports || []).map((e) => (
                  <tr key={String(e.finance_export_id)} className="border-t border-black/5">
                    <td className="px-2 py-2">{String(e.export_kind)}</td>
                    <td className="px-2 py-2">{String(e.status)}</td>
                    <td className="px-2 py-2">{String(e.reconciliation_status)}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">
                      {String(e.content_fingerprint || '').slice(0, 12)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </div>
  )
}
