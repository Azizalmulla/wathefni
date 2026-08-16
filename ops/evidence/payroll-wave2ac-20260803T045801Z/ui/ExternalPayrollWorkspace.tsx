/**
 * Payroll Wave 2A-C — HR external payroll operations workspace.
 * Wraps frozen Wave 2A adapter; never claims money authority in Wathefni.
 */
import { AlertTriangle, Download, FileUp, Loader2, RefreshCw, ShieldAlert, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/field'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  DashboardApiError,
  downloadExternalPayrollExportCsv,
  getExternalPayrollImportDetail,
  getExternalPayrollWorkspace,
  getExternalPayrollReadiness,
  postExternalPayrollExport,
  postExternalPayrollImport,
  postExternalPayrollReconcile,
  postExternalPayrollRollback,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { BlockedReason, useEmployees360Locale, WorkflowEmpty } from '@/posthire/employees360/chrome'
import { payrollExternalCopy, statusTone, type PayrollExternalLocale } from '@/posthire/payrollExternalUx'
import type { DashboardAccess, ExternalPayrollWorkspaceResponse } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

export type ExternalPayrollWorkspaceProps = {
  access: DashboardAccess
  permissions: string[]
  role?: string | null
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}

function can(permissions: string[], permission: string): boolean {
  return permissions.includes(permission)
}

function friendlyError(error: unknown, fallback: string, locale: PayrollExternalLocale): string {
  const c = payrollExternalCopy(locale)
  if (error instanceof DashboardApiError) {
    const detail = error.detail as Record<string, unknown> | string | undefined
    const code =
      typeof detail === 'object' && detail
        ? String(detail.error || detail.code || '')
        : String(error.code || '')
    const k = code.toLowerCase()
    if (k.includes('permission') || error.status === 403) return c.permissionDenied
    if (k === 'input_fingerprint_changed') return c.staleFingerprint
    if (k === 'payroll_wave2a_disabled') return c.disabled
    const message = error.message || ''
    if (message && !/(_|traceback|exception|psycopg)/i.test(message)) return message
  }
  if (error instanceof Error && error.message && !/(_|traceback|exception)/i.test(error.message)) return error.message
  return fallback
}

function useExternalPayrollData(access: DashboardAccess, onAccessIssue?: (issue: AccessIssue) => void) {
  const locale = useEmployees360Locale()
  const [data, setData] = useState<ExternalPayrollWorkspaceResponse | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setRefreshing(true)
    setError(null)
    try {
      const next = await getExternalPayrollWorkspace(access)
      if (requestId !== requestIdRef.current) return
      setData(next)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(friendlyError(err, payrollExternalCopy(locale).loading, locale))
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false)
    }
  }, [access, locale, onAccessIssue])

  useEffect(() => {
    void reload()
  }, [reload])

  return {
    data,
    loading: refreshing && data === null,
    refreshing,
    error,
    reload,
  }
}

export function ExternalPayrollWorkspace({
  access,
  permissions,
  onNotice,
  onAccessIssue,
}: ExternalPayrollWorkspaceProps) {
  const locale = useEmployees360Locale()
  const c = payrollExternalCopy(locale)
  const isAr = locale === 'ar'
  const { data, loading, refreshing, error, reload } = useExternalPayrollData(access, onAccessIssue)

  const [tab, setTab] = useState<'overview' | 'exports' | 'quarantine' | 'history'>('overview')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [periodId, setPeriodId] = useState<string | undefined>()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [readiness, setReadiness] = useState<Record<string, unknown> | null>(null)
  const [selectedExportId, setSelectedExportId] = useState<string | null>(null)
  const [importDetail, setImportDetail] = useState<Record<string, unknown> | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [replaceMode, setReplaceMode] = useState(false)

  const canExport = can(permissions, 'payroll.export') || Boolean(data?.can_export)
  const canManage = can(permissions, 'payroll.manage') || Boolean(data?.can_manage)
  const canApprove = can(permissions, 'payroll.approve') || Boolean(data?.can_approve)

  useEffect(() => {
    if (!data?.periods?.length) return
    const first = data.periods[0]
    if (!periodStart && first?.period_start) {
      setPeriodStart(String(first.period_start).slice(0, 10))
      setPeriodEnd(String(first.period_end || '').slice(0, 10))
      setPeriodId(first.period_id ? String(first.period_id) : undefined)
    }
  }, [data, periodStart])

  useEffect(() => {
    if (!periodStart || !periodEnd || !data?.enabled) {
      setReadiness(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const r = await getExternalPayrollReadiness(access, {
          period_start: periodStart,
          period_end: periodEnd,
          period_id: periodId,
        })
        if (!cancelled) setReadiness(r as Record<string, unknown>)
      } catch {
        if (!cancelled) setReadiness(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [access, data?.enabled, periodStart, periodEnd, periodId])

  const exports = data?.exports ?? []
  const quarantine = data?.quarantine ?? []
  const events = data?.events ?? []
  const selectedExport = useMemo(
    () => exports.find((e) => String(e.export_run_id) === selectedExportId) || null,
    [exports, selectedExportId],
  )

  const loadImport = useCallback(
    async (importRunId: string) => {
      try {
        const detail = await getExternalPayrollImportDetail(access, importRunId)
        setImportDetail(detail as Record<string, unknown>)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        onNotice(friendlyError(err, c.retry, locale), 'error')
      }
    },
    [access, c.retry, locale, onAccessIssue, onNotice],
  )

  const requireReason = (): boolean => {
    if (reason.trim().length < 3) {
      onNotice(c.reasonRequired, 'error')
      return false
    }
    return true
  }

  const onGenerate = async () => {
    if (!canExport || !requireReason()) return
    setBusy(true)
    try {
      const result = await postExternalPayrollExport(access, {
        period_start: periodStart,
        period_end: periodEnd,
        period_id: periodId,
        reason: reason.trim(),
      })
      if (result.fingerprint_changed) onNotice(c.fingerprintDrift, 'info')
      else onNotice(result.idempotent ? c.importIdempotent : c.generateExport, 'success')
      const id = String((result.export_run as { export_run_id?: string } | undefined)?.export_run_id || '')
      if (id) setSelectedExportId(id)
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setBusy(false)
    }
  }

  const onDownload = async (exportRunId: string) => {
    if (!canExport) return
    try {
      await downloadExternalPayrollExportCsv(access, exportRunId)
      onNotice(c.downloadExport, 'success')
    } catch (err) {
      onNotice(friendlyError(err, c.retry, locale), 'error')
    }
  }

  const onUpload = async (exportRunId: string) => {
    if (!canManage || !uploadFile || !requireReason()) return
    setBusy(true)
    try {
      const fp = selectedExport ? String(selectedExport.input_fingerprint || '') : undefined
      const result = await postExternalPayrollImport(access, exportRunId, {
        file: uploadFile,
        reason: reason.trim(),
        expected_input_fingerprint: fp || undefined,
        replace: replaceMode,
      })
      if (result.idempotent) onNotice(c.importIdempotent, 'info')
      else if (String((result.import_run as { status?: string } | undefined)?.status || '').includes('quarantine'))
        onNotice(c.importQuarantined, 'error')
      else onNotice(c.importOk, 'success')
      const iid = String((result.import_run as { import_run_id?: string } | undefined)?.import_run_id || '')
      if (iid) await loadImport(iid)
      setUploadFile(null)
      await reload()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setBusy(false)
    }
  }

  const onReconcile = async (exportRunId: string, importRunId: string) => {
    if (!canManage || !requireReason()) return
    setBusy(true)
    try {
      const result = await postExternalPayrollReconcile(access, exportRunId, {
        import_run_id: importRunId,
        reason: reason.trim(),
      })
      const status = String((result.reconciliation as { status?: string } | undefined)?.status || '')
      onNotice(status === 'ok' ? c.reconciled : c.differences, status === 'ok' ? 'success' : 'info')
      await loadImport(importRunId)
      await reload()
    } catch (err) {
      onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setBusy(false)
    }
  }

  const onRollback = async (exportRunId: string) => {
    if (!(canApprove || canManage) || !requireReason()) return
    setBusy(true)
    try {
      await postExternalPayrollRollback(access, exportRunId, { reason: reason.trim() })
      onNotice(c.rollback, 'success')
      setSelectedExportId(null)
      await reload()
    } catch (err) {
      onNotice(friendlyError(err, c.retry, locale), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div
        className="flex items-center justify-center gap-2 rounded-[var(--radius-wf-panel)] border border-dashed border-[#e8dfd0] bg-[#fffdf8]/70 px-6 py-16 text-[13px] text-subtle"
        dir={isAr ? 'rtl' : 'ltr'}
      >
        <Loader2 className="h-4 w-4 animate-spin" /> {c.loading}
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-3 rounded-[var(--radius-wf-panel)] border border-rose-200/80 bg-rose-50/50 px-6 py-10 text-center" dir={isAr ? 'rtl' : 'ltr'}>
        <p className="text-[14px] font-medium text-rose-800">{error}</p>
        <Button size="sm" variant="secondary" onClick={() => void reload()}>
          {c.retry}
        </Button>
      </div>
    )
  }

  if (data && data.enabled === false) {
    return (
      <WorkflowEmpty icon={<ShieldAlert className="h-5 w-5" />} title={c.disabled} hint={c.disabledHint} />
    )
  }

  const blockers = (readiness?.blockers as Array<{ code?: string; message?: string }> | undefined) || []
  const warnings = (readiness?.warnings as Array<{ code?: string; message?: string }> | undefined) || []
  const ready = Boolean(readiness?.ready)

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'} data-testid="external-payroll-workspace">
      <div className="space-y-2 rounded-2xl border border-dashed border-line/70 bg-[#fffaf0] px-4 py-3 text-sm text-muted">
        <p>{c.honesty}</p>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-white/70 px-2 py-1">{c.moneyAuthority}</span>
          <span className="rounded-full bg-white/70 px-2 py-1">{c.paymentDisabled}</span>
          <span className="rounded-full bg-white/70 px-2 py-1">{c.vendorUnclaimed}</span>
          <span className="rounded-full bg-amber-100/80 px-2 py-1 text-amber-900">{c.notAuthoritative}</span>
          {data?.manager_scoped ? <span className="rounded-full bg-white/70 px-2 py-1">{c.managerScoped}</span> : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">{c.title}</h2>
          <p className="text-[13px] text-subtle">{c.subtitle}</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void reload()} disabled={refreshing}>
          <RefreshCw className={cn('me-1.5 h-3.5 w-3.5', refreshing && 'animate-spin')} />
          {c.refresh}
        </Button>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-line/60 pb-1">
        {(
          [
            ['overview', c.tabOverview],
            ['exports', c.tabExports],
            ['quarantine', c.tabQuarantine],
            ['history', c.tabHistory],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={cn(
              'rounded-lg px-3 py-1.5 text-[13px] font-medium',
              tab === id ? 'bg-wf-ink/10 text-text' : 'text-subtle hover:bg-black/[0.03]',
            )}
            onClick={() => setTab(id)}
          >
            {label}
            {id === 'quarantine' && quarantine.length ? (
              <span className="ms-1.5 text-[11px] text-rose-700">{quarantine.length}</span>
            ) : null}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        <label className="text-[12px] font-semibold uppercase tracking-wide text-mist">{c.reasonPlaceholder}</label>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={c.reasonPlaceholder}
          className="min-h-[72px]"
          aria-label={c.reasonRequired}
        />
      </div>

      {tab === 'overview' ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-[12px] font-semibold uppercase tracking-wide text-mist">{c.period}</label>
              <Select
                value={periodStart && periodEnd ? `${periodStart}|${periodEnd}|${periodId || ''}` : ''}
                onChange={(e) => {
                  const [s, en, id] = e.target.value.split('|')
                  setPeriodStart(s || '')
                  setPeriodEnd(en || '')
                  setPeriodId(id || undefined)
                }}
                aria-label={c.period}
              >
                <option value="">{c.period}</option>
                {(data?.periods || []).map((p) => (
                  <option
                    key={`${p.period_start}|${p.period_end}|${p.period_id || ''}`}
                    value={`${String(p.period_start).slice(0, 10)}|${String(p.period_end).slice(0, 10)}|${p.period_id || ''}`}
                  >
                    {String(p.period_start).slice(0, 10)} → {String(p.period_end).slice(0, 10)} · {String(p.status || '')}
                  </option>
                ))}
              </Select>
              <div className="flex gap-2">
                <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} aria-label="start" />
                <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} aria-label="end" />
              </div>
            </div>
            <div className="rounded-xl border border-line/50 bg-white/60 p-3">
              <div className="mb-2 flex items-center gap-2 text-[13px] font-medium">
                {c.readiness}
                <StatusPill tone={ready ? 'success' : 'warning'}>{ready ? c.ready : c.blocked}</StatusPill>
              </div>
              {blockers.length ? (
                <ul className="space-y-1 text-[13px] text-rose-800">
                  {blockers.map((b) => (
                    <li key={b.code || b.message}>
                      <BlockedReason reason={b.message || b.code || ''} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-subtle">{c.ready}</p>
              )}
              {warnings.map((w) => (
                <p key={w.code || w.message} className="mt-2 flex items-start gap-1.5 text-[12px] text-amber-800">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {w.message}
                </p>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!canExport || !ready || busy} onClick={() => void onGenerate()}>
              <FileUp className="me-1.5 h-3.5 w-3.5" />
              {c.generateExport}
            </Button>
          </div>

          <div>
            <h3 className="mb-2 text-[13px] font-semibold text-text">{c.runHistory}</h3>
            {!exports.length ? (
              <WorkflowEmpty icon={<FileUp className="h-5 w-5" />} title={c.emptyExports} hint={c.emptyExportsHint} />
            ) : (
              <ul className="divide-y divide-line/40 rounded-xl border border-line/50 bg-white/50">
                {exports.slice(0, 8).map((row) => (
                  <li key={String(row.export_run_id)} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
                    <button
                      type="button"
                      className="text-start text-[13px] font-medium text-text underline-offset-2 hover:underline"
                      onClick={() => {
                        setSelectedExportId(String(row.export_run_id))
                        setTab('exports')
                      }}
                    >
                      {String(row.period_start).slice(0, 10)} → {String(row.period_end).slice(0, 10)}
                    </button>
                    <StatusPill tone={statusTone(String(row.status))}>{String(row.status)}</StatusPill>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {tab === 'exports' ? (
        <div className="space-y-4">
          {!exports.length ? (
            <WorkflowEmpty icon={<FileUp className="h-5 w-5" />} title={c.emptyExports} hint={c.emptyExportsHint} />
          ) : (
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
              <ul className="divide-y divide-line/40 rounded-xl border border-line/50 bg-white/50">
                {exports.map((row) => (
                  <li key={String(row.export_run_id)}>
                    <button
                      type="button"
                      className={cn(
                        'flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-start',
                        selectedExportId === String(row.export_run_id) && 'bg-wf-ink/5',
                      )}
                      onClick={() => setSelectedExportId(String(row.export_run_id))}
                    >
                      <span className="text-[13px]">
                        {String(row.period_start).slice(0, 10)} → {String(row.period_end).slice(0, 10)}
                      </span>
                      <StatusPill tone={statusTone(String(row.status))}>{String(row.status)}</StatusPill>
                    </button>
                  </li>
                ))}
              </ul>

              {selectedExport ? (
                <div className="space-y-3 rounded-xl border border-line/50 bg-white/70 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill tone={statusTone(String(selectedExport.status))}>{String(selectedExport.status)}</StatusPill>
                    <span className="font-mono text-[11px] text-subtle">
                      {c.fingerprint}: {String(selectedExport.input_fingerprint || '').slice(0, 12)}…
                    </span>
                  </div>
                  <p className="text-[12px] text-amber-900">{c.notAuthoritative}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" disabled={!canExport} onClick={() => void onDownload(String(selectedExport.export_run_id))}>
                      <Download className="me-1.5 h-3.5 w-3.5" />
                      {c.downloadExport}
                    </Button>
                    {(canApprove || canManage) && String(selectedExport.status) === 'exported' ? (
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => void onRollback(String(selectedExport.export_run_id))}>
                        {c.rollback}
                      </Button>
                    ) : null}
                  </div>

                  {canManage && String(selectedExport.status) === 'exported' ? (
                    <div className="space-y-2 rounded-lg border border-dashed border-line/60 p-3">
                      <label className="flex items-center gap-2 text-[13px]">
                        <input type="checkbox" checked={replaceMode} onChange={(e) => setReplaceMode(e.target.checked)} />
                        {c.replaceImport}
                      </label>
                      <Input
                        type="file"
                        accept=".csv,text/csv"
                        onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                        aria-label={c.selectFile}
                      />
                      <Button
                        size="sm"
                        disabled={!uploadFile || busy}
                        onClick={() => void onUpload(String(selectedExport.export_run_id))}
                      >
                        <Upload className="me-1.5 h-3.5 w-3.5" />
                        {busy ? c.uploadBusy : c.uploadResult}
                      </Button>
                    </div>
                  ) : null}

                  {(data?.imports || [])
                    .filter((i) => String(i.export_run_id) === String(selectedExport.export_run_id))
                    .map((imp) => (
                      <div key={String(imp.import_run_id)} className="rounded-lg border border-line/40 px-3 py-2 text-[13px]">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <button
                            type="button"
                            className="font-medium underline-offset-2 hover:underline"
                            onClick={() => void loadImport(String(imp.import_run_id))}
                          >
                            {String(imp.import_run_id).slice(0, 8)}…
                          </button>
                          <StatusPill tone={statusTone(String(imp.status))}>{String(imp.status)}</StatusPill>
                        </div>
                        <p className="mt-1 text-[12px] text-subtle">
                          {c.matched}: {String(imp.matched_count ?? 0)} · {c.unmatched}: {String(imp.unmatched_count ?? 0)} ·{' '}
                          {c.quarantine}: {String(imp.quarantined_count ?? 0)}
                        </p>
                        {canManage && String(imp.status) !== 'rolled_back' ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            className="mt-2"
                            disabled={busy}
                            onClick={() => void onReconcile(String(selectedExport.export_run_id), String(imp.import_run_id))}
                          >
                            {c.reconcile}
                          </Button>
                        ) : null}
                      </div>
                    ))}

                  {importDetail ? (
                    <div className="space-y-2 rounded-lg bg-[#fffdf8] p-3 text-[13px]">
                      <h4 className="font-semibold">{c.employeeDiffs}</h4>
                      {(() => {
                        const recon = importDetail.reconciliation as
                          | { status?: string; differences?: Array<{ kind?: string; items?: unknown[]; employees?: string[] }> }
                          | null
                          | undefined
                        if (!recon) return <p className="text-subtle">{c.reconcile}</p>
                        return (
                          <>
                            <StatusPill tone={statusTone(String(recon.status))}>
                              {recon.status === 'ok' ? c.reconciled : c.differences}
                            </StatusPill>
                            <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-[12px]">
                              {(recon.differences || []).map((d, idx) => (
                                <li key={idx}>
                                  {d.kind}:{' '}
                                  {Array.isArray(d.employees)
                                    ? d.employees.join(', ')
                                    : Array.isArray(d.items)
                                      ? `${d.items.length} items`
                                      : '—'}
                                </li>
                              ))}
                            </ul>
                            <p className="text-[11px] text-amber-900">{c.notAuthoritative}</p>
                          </>
                        )
                      })()}
                      <ul className="max-h-48 space-y-1 overflow-auto border-t border-line/30 pt-2 text-[12px]">
                        {((importDetail.lines as Array<Record<string, unknown>>) || []).slice(0, 40).map((line, idx) => (
                          <li key={idx} className="flex justify-between gap-2">
                            <span>
                              {String(line.employee_key)} · {String(line.component_code || '—')}
                            </span>
                            <StatusPill tone={statusTone(String(line.line_status))}>{String(line.line_status)}</StatusPill>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-[13px] text-subtle">{c.emptyExportsHint}</p>
              )}
            </div>
          )}
        </div>
      ) : null}

      {tab === 'quarantine' ? (
        !quarantine.length ? (
          <WorkflowEmpty icon={<ShieldAlert className="h-5 w-5" />} title={c.emptyQuarantine} hint={c.emptyQuarantineHint} />
        ) : (
          <ul className="divide-y divide-line/40 rounded-xl border border-rose-200/60 bg-rose-50/30">
            {quarantine.map((q) => (
              <li key={String(q.quarantine_id)} className="space-y-1 px-3 py-2.5 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill tone="danger">{String(q.source_kind || c.quarantine)}</StatusPill>
                  <span className="font-medium">{String(q.reason || '')}</span>
                </div>
                {q.artifact_excerpt ? (
                  <pre className="max-h-20 overflow-auto whitespace-pre-wrap break-all rounded bg-white/70 p-2 text-[11px] text-subtle">
                    {String(q.artifact_excerpt).slice(0, 400)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ul>
        )
      ) : null}

      {tab === 'history' ? (
        !events.length ? (
          <WorkflowEmpty icon={<RefreshCw className="h-5 w-5" />} title={c.emptyEvents} hint={c.emptyEventsHint} />
        ) : (
          <div>
            <h3 className="mb-2 text-[13px] font-semibold">{c.auditTimeline}</h3>
            <ol className="space-y-2 border-s-2 border-line/50 ps-3">
              {events.map((ev) => (
                <li key={String(ev.event_id)} className="text-[13px]">
                  <div className="font-medium text-text">{String(ev.event_type)}</div>
                  <div className="text-[11px] text-subtle">
                    {String(ev.created_at || '')} · {String(ev.created_by_phone || '—')}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )
      ) : null}
    </div>
  )
}
