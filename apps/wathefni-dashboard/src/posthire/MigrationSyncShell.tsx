import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowLeft, Download, Eye, History, Link2, Loader2, Upload, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  applyEmployeeImportApprovedNameChange,
  approveEmployeeImportNameChange,
  createMigrationConnection,
  downloadEmployeeImportExceptions,
  getEmployeeImportBatch,
  importEmployees,
  listEmployeeImportBatches,
  listEmployeeImportReview,
  listMigrationConnections,
  listMigrationConnectorKinds,
  listMigrationLifecycleReview,
  listMigrationSyncRuns,
  approveMigrationLifecycleEvent,
  rejectMigrationLifecycleEvent,
  rollbackEmployeeImportBatch,
  runMigrationConnectionSync,
  saveEmployeeImportMapping,
  setMigrationConnectionStatus,
  type EmployeeImportResult,
  type EmployeeImportRow,
  type MigrationConnection,
  type MigrationSyncRun,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  emitMigrationSyncLive,
  MIGRATION_SYNC_SOFT_POLL_MS,
  useMigrationSyncLiveRefresh,
} from '@/lib/migrationSyncLive'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

type Section = 'import' | 'connected' | 'review' | 'history'

function friendlyError(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'message' in err && typeof (err as { message: unknown }).message === 'string') {
    const message = (err as { message: string }).message.trim()
    // Never surface raw internal error codes to HR.
    if (message && !/^[a-z][a-z0-9_]+$/.test(message)) return message
  }
  if (err && typeof err === 'object' && 'code' in err && typeof (err as { code: unknown }).code === 'string') {
    const code = (err as { code: string }).code
    if (code === 'review_state_stale' || code === 'row_not_approved_pending_apply') {
      return 'This review item changed. Refresh Needs review and try again.'
    }
    if (code === 'batch_not_applyable' || code === 'batch_not_approvable') {
      return 'This approval is on an older import. Refresh Needs review and continue from the current item.'
    }
    if (code === 'apply_conflict') {
      return 'This person changed after approval. Refresh Needs review and review again.'
    }
    if (code === 'row_not_found' || code === 'batch_not_found') {
      return 'That review item is no longer available. Refresh Needs review and try again.'
    }
  }
  return fallback
}

function changeLines(row: EmployeeImportRow): string[] {
  const changes = row.changes || {}
  return Object.keys(changes)
    .sort()
    .map((field) => {
      const ch = changes[field]
      const before = ch?.before ?? '—'
      const after = ch?.after ?? '—'
      const label =
        field === 'position_title'
          ? 'Job title'
          : field === 'start_date'
            ? 'Start date'
            : field === 'manager_employee_key'
              ? 'Manager'
              : field.charAt(0).toUpperCase() + field.slice(1)
      return `${label}: ${before} → ${after}`
    })
}

function OutcomeList({
  title,
  rows,
  tone,
  showChanges,
  onApproveName,
  onApplyApproved,
  approveBusyId,
  applyBusyId,
}: {
  title: string
  rows: EmployeeImportRow[]
  tone: 'success' | 'warning' | 'danger' | 'muted' | 'info'
  showChanges?: boolean
  onApproveName?: (row: EmployeeImportRow) => void
  onApplyApproved?: (row: EmployeeImportRow) => void
  approveBusyId?: string | null
  applyBusyId?: string | null
}) {
  if (!rows.length) return null
  const toneClass =
    tone === 'success'
      ? 'text-emerald-700'
      : tone === 'danger'
        ? 'text-rose-600'
        : tone === 'warning'
          ? 'text-[#8a5a16]'
          : tone === 'info'
            ? 'text-[#3d5a40]'
            : 'text-subtle/85'
  return (
    <div className="rounded-2xl border border-line/50 bg-white/55 p-3">
      <p className={cn('text-[13px] font-semibold', toneClass)}>
        {title} · {rows.length}
      </p>
      <ul className="mt-1 space-y-2 text-[12px] leading-5 text-subtle/85">
        {rows.slice(0, 12).map((r) => {
          const lines = showChanges ? changeLines(r) : []
          const canApprove = Boolean(onApproveName && r.approvable && r.name_identity_review && r.row_id)
          const canApply = Boolean(
            onApplyApproved && r.applyable && (r.canonical_row_id || r.row_id) && (r.canonical_batch_id || r.batch_id),
          )
          const approved = Boolean(r.applyable || (r.name_change_approved && !r.name_change_applied && r.status === 'will_update'))
          const applied = Boolean(r.name_change_applied)
          return (
            <li key={`${title}-${r.row}-${r.row_id || r.employee_key || r.phone || ''}`} className="space-y-0.5">
              <p>
                <span className="font-medium text-text">{r.name}</span>
                {r.phone ? <span className="text-subtle/70"> · {r.phone}</span> : null}
                {approved && !applied ? (
                  <span className="ms-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-medium text-emerald-700">
                    Approved
                  </span>
                ) : null}
                {applied ? (
                  <span className="ms-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-medium text-emerald-700">
                    Applied
                  </span>
                ) : null}
              </p>
              {r.reason ? <p>{r.reason}</p> : null}
              {(() => {
                const ob = (r.detail as { onboarding_migration?: { preview_label?: string; disposition?: string } } | undefined)
                  ?.onboarding_migration
                if (!ob?.preview_label) return null
                return (
                  <p className="text-[11.5px] text-[#3d5a40]">
                    Onboarding · {ob.preview_label}
                  </p>
                )
              })()}
              {(() => {
                const lines = (
                  r.detail as {
                    opening_balances?: Array<{
                      preview_label?: string
                      disposition?: string
                      import_value?: string
                      existing_value?: string
                      cutover_date?: string | null
                      source?: string | null
                      masked?: boolean
                    }>
                  } | undefined
                )?.opening_balances
                if (!lines?.length) return null
                return (
                  <div className="mt-0.5 space-y-0.5">
                    {lines.slice(0, 6).map((line, idx) => {
                      const disp = String(line.disposition || '')
                      const tone =
                        disp === 'needs_review'
                          ? 'text-amber-800'
                          : disp === 'will_apply'
                            ? 'text-[#3d5a40]'
                            : 'text-subtle/75'
                      const dispLabel =
                        disp === 'will_apply'
                          ? 'Will apply'
                          : disp === 'unchanged'
                            ? 'Unchanged'
                            : disp === 'needs_review'
                              ? 'Needs review'
                              : disp === 'not_supplied'
                                ? 'Not supplied'
                                : disp
                      return (
                        <p key={`${line.preview_label}-${idx}`} className={cn('text-[11.5px]', tone)}>
                          {line.preview_label}: {line.import_value}
                          {line.existing_value && line.existing_value !== 'Not supplied'
                            ? ` · existing ${line.existing_value}`
                            : ''}
                          {line.cutover_date ? ` · as of ${line.cutover_date}` : ''}
                          {line.source ? ` · ${line.source}` : ''}
                          {dispLabel ? ` · ${dispLabel}` : ''}
                        </p>
                      )
                    })}
                  </div>
                )
              })()}
              {lines.map((line) => (
                <p key={line} className="text-[11.5px] text-subtle/75">
                  {line}
                </p>
              ))}
              {approved && r.name_change_approved_at ? (
                <p className="text-[11px] text-subtle/60">
                  Approved{r.name_change_approved_by ? ` by ${r.name_change_approved_by}` : ''} ·{' '}
                  {r.name_change_approved_at}
                </p>
              ) : null}
              {applied && r.name_change_applied_at ? (
                <p className="text-[11px] text-subtle/60">
                  Applied{r.name_change_applied_by ? ` by ${r.name_change_applied_by}` : ''} ·{' '}
                  {r.name_change_applied_at}
                </p>
              ) : null}
              {canApprove ? (
                <button
                  type="button"
                  disabled={approveBusyId === r.row_id}
                  onClick={() => onApproveName?.(r)}
                  className="mt-1 inline-flex items-center rounded-full bg-[#fff7e8] px-2.5 py-1 text-[11.5px] font-medium text-[#8a5a16] hover:bg-[#fdeecb] disabled:opacity-60"
                >
                  {approveBusyId === r.row_id ? 'Approving…' : 'Approve name change'}
                </button>
              ) : null}
              {canApply ? (
                <button
                  type="button"
                  disabled={applyBusyId === r.row_id}
                  onClick={() => onApplyApproved?.(r)}
                  className="mt-1 ms-2 inline-flex items-center rounded-full bg-[#eef5ee] px-2.5 py-1 text-[11.5px] font-medium text-[#3d5a40] hover:bg-[#e2eee3] disabled:opacity-60"
                >
                  {applyBusyId === r.row_id ? 'Applying…' : 'Apply approved change'}
                </button>
              ) : null}
            </li>
          )
        })}
        {rows.length > 12 ? <li className="text-subtle/70">+{rows.length - 12} more</li> : null}
      </ul>
    </div>
  )
}

function SectionNav({
  section,
  setSection,
  reviewCount,
}: {
  section: Section
  setSection: (s: Section) => void
  reviewCount: number
}) {
  const items: { id: Section; label: string }[] = [
    { id: 'import', label: 'Import employees' },
    { id: 'connected', label: 'Connected systems' },
    { id: 'review', label: `Needs review${reviewCount ? ` (${reviewCount})` : ''}` },
    { id: 'history', label: 'History' },
  ]
  return (
    <nav className="flex flex-wrap gap-2 border-b border-line/50 pb-3">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => setSection(item.id)}
          className={cn(
            'rounded-full px-3.5 py-1.5 text-[13px] font-medium transition',
            section === item.id ? 'bg-[#eee5d4] text-text' : 'bg-white/50 text-subtle/85 hover:bg-white/80',
          )}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}

function ImportSection({
  access,
  onNotice,
  onApplied,
}: {
  access: DashboardAccess
  onNotice: NoticeFn
  onApplied: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [preview, setPreview] = useState<EmployeeImportResult | null>(null)
  const [result, setResult] = useState<EmployeeImportResult | null>(null)
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [sourceSystem, setSourceSystem] = useState('')
  const [approveBusyId, setApproveBusyId] = useState<string | null>(null)
  const [applyBusyId, setApplyBusyId] = useState<string | null>(null)
  const [lastApprovedName, setLastApprovedName] = useState<string | null>(null)
  const [mappingRules, setMappingRules] = useState<Array<Record<string, unknown>>>([])
  const [mappingBusy, setMappingBusy] = useState(false)
  const previewSeq = useRef(0)

  const runPreview = useCallback(
    async (nextFile: File, opts?: { refresh?: boolean; source?: string }) => {
      const seq = ++previewSeq.current
      setChecking(true)
      setBusy(true)
      setError(null)
      setStatus(null)
      setResult(null)
      try {
        const res = await importEmployees(access, {
          file: nextFile,
          dryRun: true,
          sourceSystem: (opts?.source ?? sourceSystem).trim() || undefined,
          // Refresh must create a fresh preview for the same file content when needed —
          // pass no batchId so server classifies from file again (idempotency may replay).
        })
        if (seq !== previewSeq.current) return
        setPreview(res)
        setStep('preview')
        const mapping = (res as EmployeeImportResult & { mapping?: { mappings?: Array<Record<string, unknown>> } }).mapping
        if (mapping?.mappings) setMappingRules(mapping.mappings)
        const totals = res.totals
        const review = totals?.review ?? totals?.conflict ?? 0
        const unmapped = Number((mapping as { summary?: { unmapped_count?: number } } | undefined)?.summary?.unmapped_count || 0)
        setStatus(
          opts?.refresh
            ? `Preview refreshed · ${res.total_rows} row${res.total_rows === 1 ? '' : 's'}.`
            : `Preview ready · ${res.total_rows} row${res.total_rows === 1 ? '' : 's'}` +
                (review ? ` · ${review} need review` : '') +
                (unmapped ? ` · ${unmapped} source-only / unmapped fields retained` : '') +
                '.',
        )
        onNotice(
          opts?.refresh ? 'Preview refreshed.' : 'Preview complete. Review the results, then confirm to apply.',
          'success',
        )
      } catch (err) {
        if (seq !== previewSeq.current) return
        setPreview(null)
        setStep('upload')
        setError(friendlyError(err, 'We couldn’t check this file. Please try again.'))
        onNotice('We couldn’t check this file.', 'error')
      } finally {
        if (seq === previewSeq.current) {
          setChecking(false)
          setBusy(false)
        }
      }
    },
    [access, onNotice, sourceSystem],
  )

  const pickFile = (next: File | null) => {
    previewSeq.current += 1
    setFile(next)
    setPreview(null)
    setResult(null)
    setError(null)
    setStatus(null)
    setLastApprovedName(null)
    setStep('upload')
    if (next) {
      setStatus(`Selected ${next.name}. Checking your file…`)
      onNotice(`Selected ${next.name}.`, 'info')
      void runPreview(next)
    }
  }

  const runConfirm = async () => {
    if (!file) {
      setError('Choose a CSV or XLSX file first.')
      return
    }
    if (!preview?.batch_id) {
      setError('Wait for the preview to finish before confirming.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await importEmployees(access, {
        file,
        dryRun: false,
        sourceSystem: sourceSystem.trim() || undefined,
        batchId: preview.batch_id,
      })
      setResult(res)
      setPreview(res)
      setStep('done')
      const added = res.counts?.created || 0
      const updated = res.counts?.updated || 0
      const msg =
        added + updated > 0
          ? `Import confirmed · ${added} added, ${updated} updated.`
          : 'Import confirmed · no employees were added or updated.'
      setStatus(msg)
      onNotice(msg, 'success')
      onApplied()
      emitMigrationSyncLive({ reason: 'import_applied', batch_id: res.batch_id || preview.batch_id })
    } catch (err) {
      setError(friendlyError(err, 'We couldn’t confirm this import. Please try again.'))
      onNotice('We couldn’t confirm this import.', 'error')
    } finally {
      setBusy(false)
    }
  }

  const downloadExceptions = async () => {
    const batchId = (result ?? preview)?.batch_id
    if (!batchId) return
    setBusy(true)
    try {
      const blob = await downloadEmployeeImportExceptions(access, batchId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `employee-import-exceptions-${batchId}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(friendlyError(err, 'Could not download exceptions.'))
    } finally {
      setBusy(false)
    }
  }

  const approveName = async (row: EmployeeImportRow) => {
    const batchId = preview?.batch_id
    if (!batchId || !row.row_id) return
    setApproveBusyId(row.row_id)
    setError(null)
    try {
      const res = await approveEmployeeImportNameChange(access, batchId, row.row_id)
      // Keep the same batch context; server returns updated totals/buckets.
      setPreview(res)
      setStep('preview')
      setLastApprovedName(row.name)
      const msg =
        (res as EmployeeImportResult & { message?: string }).message ||
        `Approved name change for ${row.name}. Apply approved change, or Confirm import on this same file.`
      setStatus(msg)
      onNotice(msg, 'success')
      onApplied()
      emitMigrationSyncLive({ reason: 'review_resolved', batch_id: batchId })
    } catch (err) {
      // Never surface employee-profile 404s as the approval outcome.
      const raw = friendlyError(err, 'Could not approve name change.')
      const safe =
        /couldn'?t find that employee/i.test(raw)
          ? 'Could not approve name change. Please refresh the preview and try again.'
          : raw
      setError(safe)
      onNotice(safe, 'error')
    } finally {
      setApproveBusyId(null)
    }
  }

  const applyApproved = async (row: EmployeeImportRow) => {
    const batchId = row.canonical_batch_id || row.batch_id || preview?.batch_id
    const rowId = row.canonical_row_id || row.row_id
    if (!batchId || !rowId) return
    setApplyBusyId(row.row_id || rowId)
    setError(null)
    try {
      const res = await applyEmployeeImportApprovedNameChange(access, batchId, rowId)
      setPreview(res)
      const remainingReview = Number(res.totals?.review ?? res.totals?.conflict ?? res.counts?.needs_review ?? 0)
      const remainingUpdate = (res.results?.updated || []).filter((r) => r.applyable).length
      if (remainingReview === 0 && remainingUpdate === 0 && !res.dry_run) {
        setResult(res)
        setStep('done')
      } else {
        setStep('preview')
      }
      const msg =
        (res as EmployeeImportResult & { message?: string }).message ||
        `Applied approved change for ${row.name}.`
      setStatus(msg)
      setLastApprovedName(null)
      onNotice(msg, 'success')
      onApplied()
      emitMigrationSyncLive({
        reason: 'review_resolved',
        batch_id: batchId,
        employee_keys: row.employee_key ? [String(row.employee_key)] : undefined,
      })
    } catch (err) {
      const safe = friendlyError(err, 'Could not apply approved change. Refresh and try again.')
      setError(safe)
      onNotice(safe, 'error')
      // Stale/superseded — reload preview context calmly when possible.
      if (file) void runPreview(file, { refresh: true })
    } finally {
      setApplyBusyId(null)
    }
  }

  const summary = result ?? preview
  const totals = summary?.totals
  const createdRows = summary?.results?.created || []
  const updatedRows = summary?.results?.updated || []
  const skippedRows = summary?.results?.skipped || []
  const reviewRows = summary?.results?.needs_review || []
  const failedRows = summary?.results?.failed || []
  const previewReady = Boolean(preview && !checking && !result)
  const confirmStillRequired = previewReady

  return (
    <div className="space-y-4">
      <div>
        <p className="text-[15px] font-semibold text-text">Import employees</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Upload a file of your existing team. We check it automatically, then you confirm. We never send invitations or messages, and we never start onboarding from import.
        </p>
      </div>
      <ol className="flex flex-wrap gap-2 text-[11.5px] font-medium uppercase tracking-[0.06em] text-subtle/70">
        <li className={cn('rounded-full px-2.5 py-1', step === 'upload' && !checking ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>1 · Upload</li>
        <li className={cn('rounded-full px-2.5 py-1', step === 'preview' || checking ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>2 · Preview</li>
        <li className={cn('rounded-full px-2.5 py-1', step === 'done' ? 'bg-[#eee5d4] text-text' : 'bg-white/50')}>3 · Confirm</li>
      </ol>
      <div className="rounded-2xl border border-line/50 bg-white/55 p-3 text-[12px] leading-5 text-subtle/85">
        <p>
          Required: <span className="font-semibold text-text">name</span>, <span className="font-semibold text-text">phone</span>
        </p>
        <p className="mt-0.5">
          Optional roster: email, job title, department, start date, external_employee_id, payroll_id, source_system, manager_phone.
          Deep fields (Civil ID, nationality, contacts, bank, documents, compliance) and onboarding migration state map via field mapping.
        </p>
        <p className="mt-1.5 text-subtle/75">
          Matching: external ID when supplied, otherwise phone. Unknown source columns are retained. Existing employees can be marked already onboarded externally, history imported, not applicable, or requiring OctoHR onboarding — never faked from “active” alone.
        </p>
      </div>
      <input
        type="file"
        accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
        disabled={busy || Boolean(result)}
        className="block w-full text-[13px] text-subtle/90 file:me-3 file:rounded-full file:border-0 file:bg-[#fff7e8] file:px-4 file:py-2 file:text-[13px] file:font-medium file:text-[#8a5a16] hover:file:bg-[#fdeecb]"
      />
      {file ? <p className="text-[12px] text-subtle/80">{file.name}</p> : null}
      <button
        type="button"
        className="text-[12px] font-medium text-[#8a5a16] hover:underline"
        onClick={() => setShowAdvanced((v) => !v)}
      >
        {showAdvanced ? 'Hide advanced' : 'Advanced'}
      </button>
      {showAdvanced ? (
        <label className="block max-w-sm space-y-1">
          <span className="text-[12px] text-subtle/85">Source system (optional)</span>
          <input
            value={sourceSystem}
            onChange={(e) => setSourceSystem(e.target.value)}
            disabled={busy || Boolean(result)}
            placeholder="e.g. bayan"
            className="w-full rounded-xl border border-line/60 bg-white/80 px-3 py-2 text-[13px]"
          />
        </label>
      ) : null}
      {checking ? (
        <p className="flex items-center gap-2 text-[13px] text-subtle/85">
          <Loader2 className="h-4 w-4 animate-spin" /> Checking your file…
        </p>
      ) : null}
      {status && !error ? (
        <p className="rounded-2xl border border-emerald-200/80 bg-emerald-50/70 px-3 py-2 text-[12.5px] leading-5 text-emerald-800">
          {status}
          {confirmStillRequired && lastApprovedName ? (
            <span className="mt-1 block text-emerald-700/90">
              {lastApprovedName} is approved on this import. Apply approved change, or Confirm import — no re-upload needed.
            </span>
          ) : null}
          {confirmStillRequired && !lastApprovedName && preview ? (
            <span className="mt-1 block text-emerald-700/90">Confirm import is required to apply these changes.</span>
          ) : null}
        </p>
      ) : null}
      {error ? <p className="rounded-2xl border border-rose-200/80 bg-rose-50/70 px-3 py-2 text-[12.5px] text-rose-700">{error}</p> : null}
      {previewReady && mappingRules.length > 0 ? (
        <div className="space-y-2 rounded-2xl border border-line/50 bg-white/70 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-text">Field mapping</p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={mappingBusy || busy}
              onClick={async () => {
                setMappingBusy(true)
                setError(null)
                try {
                  await saveEmployeeImportMapping(access, {
                    sourceSystem: sourceSystem.trim() || 'csv',
                    mappings: mappingRules,
                    activate: true,
                  })
                  onNotice('Mapping profile saved for this source. Future imports will reuse it.', 'success')
                  if (file) await runPreview(file, { refresh: true })
                } catch (err) {
                  setError(friendlyError(err, 'Could not save mapping profile.'))
                } finally {
                  setMappingBusy(false)
                }
              }}
            >
              {mappingBusy ? 'Saving…' : 'Save mapping profile'}
            </Button>
          </div>
          <p className="text-[12px] leading-5 text-subtle/85">
            Every source column maps to an OctoHR field, a company custom field, or source-only retention. Unmapped fields never fail the batch.
          </p>
          <div className="max-h-56 space-y-1.5 overflow-y-auto">
            {mappingRules.map((rule, idx) => {
              const header = String(rule.source_header || '')
              const disposition = String(rule.disposition || 'source_only')
              const unmapped = disposition === 'source_only' || disposition === 'ignore'
              return (
                <div
                  key={`${header}-${idx}`}
                  className={cn(
                    'grid grid-cols-1 gap-2 rounded-xl border px-2.5 py-2 text-[12px] sm:grid-cols-[1.2fr_1fr_1fr]',
                    unmapped ? 'border-amber-200/80 bg-amber-50/40' : 'border-line/40 bg-white/60',
                  )}
                >
                  <div>
                    <p className="font-medium text-text">{header}</p>
                    {unmapped ? <p className="text-amber-800/80">Unmapped · retained as source data</p> : null}
                  </div>
                  <label className="block space-y-0.5">
                    <span className="text-subtle/70">Disposition</span>
                    <select
                      className="w-full rounded-lg border border-line/60 bg-white px-2 py-1.5"
                      value={disposition}
                      disabled={busy || mappingBusy}
                      onChange={(e) => {
                        const next = [...mappingRules]
                        next[idx] = {
                          ...rule,
                          disposition: e.target.value,
                          confirmed: true,
                          canonical_field: e.target.value === 'canonical' ? rule.canonical_field || null : null,
                          custom_field_key:
                            e.target.value === 'custom' || e.target.value === 'create_custom'
                              ? rule.custom_field_key || String(rule.source_header_normalized || '')
                              : null,
                        }
                        setMappingRules(next)
                      }}
                    >
                      <option value="canonical">Canonical OctoHR field</option>
                      <option value="custom">Company custom field</option>
                      <option value="create_custom">Create custom field</option>
                      <option value="source_only">Source-only (retain)</option>
                      <option value="ignore">Ignore operationally (retain)</option>
                    </select>
                  </label>
                  {disposition === 'canonical' ? (
                    <label className="block space-y-0.5">
                      <span className="text-subtle/70">Canonical field</span>
                      <input
                        className="w-full rounded-lg border border-line/60 bg-white px-2 py-1.5"
                        value={String(rule.canonical_field || '')}
                        placeholder="e.g. civil_id, bank_iban, department"
                        disabled={busy || mappingBusy}
                        onChange={(e) => {
                          const next = [...mappingRules]
                          next[idx] = { ...rule, canonical_field: e.target.value.trim(), confirmed: true }
                          setMappingRules(next)
                        }}
                      />
                    </label>
                  ) : disposition === 'custom' || disposition === 'create_custom' ? (
                    <label className="block space-y-0.5">
                      <span className="text-subtle/70">Custom field key</span>
                      <input
                        className="w-full rounded-lg border border-line/60 bg-white px-2 py-1.5"
                        value={String(rule.custom_field_key || '')}
                        placeholder="e.g. cost_center"
                        disabled={busy || mappingBusy}
                        onChange={(e) => {
                          const next = [...mappingRules]
                          next[idx] = { ...rule, custom_field_key: e.target.value.trim(), confirmed: true }
                          setMappingRules(next)
                        }}
                      />
                    </label>
                  ) : (
                    <p className="self-center text-subtle/70">Kept in raw source payload</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
      {summary && !checking ? (
        <div className="space-y-2">
          <p className="text-[12px] font-medium text-subtle/90">
            {result ? 'Import complete' : `Preview · ${summary.total_rows} row${summary.total_rows === 1 ? '' : 's'}`}
            {summary.batch_id ? (
              <span className="ms-2 font-normal text-subtle/65">batch {String(summary.batch_id).slice(0, 8)}…</span>
            ) : null}
          </p>
          {totals ? (
            <p className="text-[12px] text-subtle/80">
              Will be added {totals.create} · Will be updated {totals.update ?? 0} · Will be skipped {totals.skip} · Needs
              review {totals.review ?? totals.conflict ?? 0} · Invalid {totals.invalid}
              {typeof totals.warnings === 'number' ? ` · Warnings ${totals.warnings}` : ''}
            </p>
          ) : null}
          <OutcomeList title={result ? 'Added' : 'Will be added'} rows={createdRows} tone="success" />
          <OutcomeList
            title={result ? 'Updated' : 'Will be updated'}
            rows={updatedRows}
            tone="info"
            showChanges
            onApplyApproved={!result || updatedRows.some((r) => r.applyable) ? applyApproved : undefined}
            applyBusyId={applyBusyId}
          />
          <OutcomeList title="Will be skipped" rows={skippedRows} tone="muted" />
          <OutcomeList
            title="Needs review"
            rows={reviewRows}
            tone="warning"
            showChanges
            onApproveName={!result ? approveName : undefined}
            approveBusyId={approveBusyId}
          />
          <OutcomeList title="Will be skipped (invalid)" rows={failedRows} tone="danger" />
          {summary.batch_id &&
          ((summary.counts?.needs_review || 0) + (summary.counts?.failed || 0) > 0 || (totals?.warnings || 0) > 0) ? (
            <button
              type="button"
              onClick={() => void downloadExceptions()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[#8a5a16] hover:underline"
            >
              <Download className="h-3.5 w-3.5" /> Download exception report
            </button>
          ) : null}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {!result ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => file && void runPreview(file, { refresh: true })}
              disabled={busy || !file || checking}
            >
              {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
              {preview ? 'Refresh preview' : 'Preview'}
            </Button>
            <Button size="sm" onClick={() => void runConfirm()} disabled={busy || checking || !previewReady}>
              {busy && !checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Confirm import
            </Button>
          </>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              pickFile(null)
              setResult(null)
            }}
          >
            Import another file
          </Button>
        )}
      </div>
    </div>
  )
}

function ConnectedSection({
  access,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  onNotice?: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [connections, setConnections] = useState<MigrationConnection[]>([])
  const [runs, setRuns] = useState<MigrationSyncRun[]>([])
  const [canaryAvailable, setCanaryAvailable] = useState(false)
  const [name, setName] = useState('OctoHR canary connector')
  const [error, setError] = useState<string | null>(null)
  const nameBaseline = useRef('OctoHR canary connector')

  const refresh = useCallback(async (opts?: { soft?: boolean }) => {
    // Soft refresh keeps painted rows (no loading blank / filter reset).
    if (!opts?.soft) setLoading(true)
    setError(null)
    try {
      const [connRes, runRes, kindsRes] = await Promise.all([
        listMigrationConnections(access),
        listMigrationSyncRuns(access, undefined, 12),
        listMigrationConnectorKinds(access).catch(() => ({ kinds: [] as Array<Record<string, unknown>> })),
      ])
      setConnections(connRes.connections || [])
      setRuns(runRes.runs || [])
      const canary = (kindsRes.kinds || []).find((row) => row.kind === 'deterministic_canary')
      setCanaryAvailable(canary?.available === true)
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      else setError(friendlyError(err, 'Could not load connected systems.'))
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useMigrationSyncLiveRefresh(
    async () => {
      await refresh({ soft: true })
    },
    {
      // Do not clobber an in-progress Add connection name draft or Sync/Pause action.
      isDirty: () => busy || name.trim() !== nameBaseline.current.trim(),
      pollMs: MIGRATION_SYNC_SOFT_POLL_MS,
      debounceMs: 450,
    },
  )

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[15px] font-semibold text-text">Connected systems</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Connect a source, map fields, run sync, then review accepted changes. Lifecycle terminations follow connection policy (default: review).
        </p>
      </div>

      {error ? (
        <p className="rounded-2xl border border-rose-200/80 bg-rose-50/70 px-3 py-2 text-[12.5px] text-rose-700">{error}</p>
      ) : null}

      {canaryAvailable ? (
      <Card className="border-line/50 bg-white/55 shadow-none">
        <CardContent className="space-y-3 p-4">
          <p className="text-[13px] font-medium text-text">Add connection</p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-[220px] flex-1 space-y-1 text-[12px]">
              <span className="text-subtle/70">Name</span>
              <input
                className="w-full rounded-xl border border-line/60 bg-white px-3 py-2 text-[13px]"
                value={name}
                disabled={busy || (loading && connections.length === 0)}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. HRIS production"
              />
            </label>
            <Button
              type="button"
              size="sm"
              disabled={busy || (loading && connections.length === 0) || !name.trim()}
              onClick={async () => {
                setBusy(true)
                setError(null)
                try {
                  const tag = Math.random().toString(16).slice(2, 8)
                  await createMigrationConnection(access, {
                    name: name.trim(),
                    connector_kind: 'deterministic_canary',
                    source_system: `canary:deterministic:${tag}`,
                    config: { fixture_tag: tag, fixture_version: 1 },
                    schedule_enabled: false,
                  })
                  onNotice?.('Connection added. Run a sync to preview changes.', 'success')
                  setName('OctoHR canary connector')
                  nameBaseline.current = 'OctoHR canary connector'
                  await refresh({ soft: true })
                  emitMigrationSyncLive({ reason: 'connection_changed' })
                } catch (err) {
                  const issue = accessIssueFromError(err)
                  if (issue) onAccessIssue?.(issue)
                  else setError(friendlyError(err, 'Could not add connection.'))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {busy ? 'Working…' : 'Connect canary source'}
            </Button>
          </div>
          <p className="text-[11.5px] leading-5 text-subtle/75">
            Isolated test capability. Synthetic fixture sources are not available to production workspaces.
          </p>
        </CardContent>
      </Card>
      ) : null}

      {loading && connections.length === 0 ? (
        <p className="flex items-center gap-2 text-[13px] text-subtle/80">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading connections…
        </p>
      ) : connections.length === 0 ? (
        <Card className="border-line/50 bg-white/55 shadow-none">
          <CardContent className="flex items-start gap-3 p-4">
            <Link2 className="mt-0.5 h-5 w-5 text-subtle/70" />
            <div>
              <p className="text-[13px] font-medium text-text">No systems connected</p>
              <p className="mt-1 text-[12px] leading-5 text-subtle/80">
                Add a connection to sync from an external source into the same preview → review path as file import.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {connections.map((c) => (
            <Card key={c.connection_id} className="border-line/50 bg-white/55 shadow-none">
              <CardContent className="space-y-2 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-[13px] font-semibold text-text">{c.name}</p>
                    <p className="mt-0.5 text-[12px] text-subtle/80">
                      {c.connector_kind.replace(/_/g, ' ')} · {c.source_system}
                    </p>
                    <p className="mt-1 text-[11.5px] text-subtle/70">
                      Status {c.status}
                      {c.schedule_enabled ? ' · schedule on' : ''}
                      {c.last_success_at ? ` · last success ${c.last_success_at}` : c.last_sync_at ? ` · last sync ${c.last_sync_at}` : ''}
                      {c.next_sync_at ? ` · next ${c.next_sync_at}` : ''}
                    </p>
                    {c.last_error_summary ? (
                      <p className="mt-1 text-[11.5px] text-rose-700">{c.last_error_summary}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy || c.status === 'paused'}
                      onClick={async () => {
                        setBusy(true)
                        setError(null)
                        try {
                          const res = await runMigrationConnectionSync(access, c.connection_id, {
                            force_full: true,
                            auto_commit: false,
                          })
                          if (!res.ok) {
                            setError(res.message || 'Sync failed.')
                          } else {
                            onNotice?.(
                              `Sync preview ready${res.batch_id ? ` · batch ${res.batch_id.slice(0, 8)}` : ''}. Review in Import / Needs review.`,
                              'success',
                            )
                          }
                          await refresh({ soft: true })
                          emitMigrationSyncLive({
                            reason: 'sync_completed',
                            connection_id: c.connection_id,
                            batch_id: res.batch_id || null,
                          })
                        } catch (err) {
                          const issue = accessIssueFromError(err)
                          if (issue) onAccessIssue?.(issue)
                          else setError(friendlyError(err, 'Could not run sync.'))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Sync now
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await setMigrationConnectionStatus(
                            access,
                            c.connection_id,
                            c.status === 'paused' ? 'active' : 'paused',
                          )
                          onNotice?.(c.status === 'paused' ? 'Connection resumed.' : 'Connection paused.', 'info')
                          await refresh({ soft: true })
                          emitMigrationSyncLive({
                            reason: 'connection_changed',
                            connection_id: c.connection_id,
                          })
                        } catch (err) {
                          setError(friendlyError(err, 'Could not update status.'))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      {c.status === 'paused' ? 'Resume' : 'Pause'}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await setMigrationConnectionStatus(access, c.connection_id, 'disconnected')
                          onNotice?.('Connection disconnected.', 'info')
                          await refresh({ soft: true })
                          emitMigrationSyncLive({
                            reason: 'connection_changed',
                            connection_id: c.connection_id,
                          })
                        } catch (err) {
                          setError(friendlyError(err, 'Could not disconnect.'))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Disconnect
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <p className="text-[13px] font-semibold text-text">Sync history</p>
        {runs.length === 0 ? (
          <p className="text-[12px] text-subtle/75">No sync runs yet.</p>
        ) : (
          <ul className="space-y-1.5 text-[12px] text-subtle/85">
            {runs.map((r) => (
              <li key={r.sync_run_id} className="rounded-xl border border-line/40 bg-white/50 px-3 py-2">
                <span className="font-medium text-text">{r.status}</span>
                <span className="text-subtle/70"> · {r.trigger}</span>
                {r.started_at ? <span className="text-subtle/70"> · {r.started_at}</span> : null}
                <span className="text-subtle/70">
                  {' '}
                  · fetched {r.records_fetched ?? 0} · create {r.created_count ?? 0} · update {r.updated_count ?? 0} ·
                  review {r.review_count ?? 0}
                </span>
                {r.error_summary ? <p className="mt-0.5 text-rose-700">{r.error_summary}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function ReviewSection({
  access,
  onAccessIssue,
  onNotice,
}: {
  access: DashboardAccess
  onAccessIssue?: (issue: AccessIssue) => void
  onNotice?: NoticeFn
}) {
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<EmployeeImportRow[]>([])
  const [lifecycleItems, setLifecycleItems] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState<string | null>(null)
  const [approveBusyId, setApproveBusyId] = useState<string | null>(null)
  const [applyBusyId, setApplyBusyId] = useState<string | null>(null)
  const [lifecycleBusyId, setLifecycleBusyId] = useState<string | null>(null)

  const load = useCallback(async (opts?: { soft?: boolean }) => {
    if (!opts?.soft) setLoading(true)
    setError(null)
    try {
      const [res, life] = await Promise.all([
        listEmployeeImportReview(access, 100),
        listMigrationLifecycleReview(access, 50).catch(() => ({ ok: true, events: [] as Array<Record<string, unknown>> })),
      ])
      setItems(res.items || [])
      setLifecycleItems(life.events || [])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setError(friendlyError(err, 'Could not load review items.'))
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  useMigrationSyncLiveRefresh(
    async () => {
      await load({ soft: true })
    },
    {
      isDirty: () => Boolean(approveBusyId || applyBusyId || lifecycleBusyId),
      pollMs: MIGRATION_SYNC_SOFT_POLL_MS,
      debounceMs: 450,
    },
  )

  const approveName = async (item: EmployeeImportRow) => {
    if (!item.batch_id || !item.row_id) return
    setApproveBusyId(item.row_id)
    setError(null)
    try {
      const res = await approveEmployeeImportNameChange(access, item.batch_id, item.row_id)
      const msg =
        (res as EmployeeImportResult & { message?: string }).message ||
        `Approved name change for ${item.name}. Apply approved change on this same import.`
      onNotice?.(msg, 'success')
      await load({ soft: true })
      emitMigrationSyncLive({ reason: 'review_resolved', batch_id: item.batch_id })
    } catch (err) {
      const raw = friendlyError(err, 'Could not approve name change.')
      const safe =
        /couldn'?t find that employee/i.test(raw)
          ? 'Could not approve name change. Please refresh and try again.'
          : raw
      setError(safe)
      onNotice?.(safe, 'error')
    } finally {
      setApproveBusyId(null)
    }
  }

  const applyApproved = async (item: EmployeeImportRow) => {
    const batchId = item.canonical_batch_id || item.batch_id
    const rowId = item.canonical_row_id || item.row_id
    if (!batchId || !rowId) return
    setApplyBusyId(item.row_id || rowId)
    setError(null)
    try {
      const res = await applyEmployeeImportApprovedNameChange(access, batchId, rowId)
      const msg =
        (res as EmployeeImportResult & { message?: string }).message ||
        `Applied approved change for ${item.name}.`
      onNotice?.(msg, 'success')
      await load({ soft: true })
      emitMigrationSyncLive({
        reason: 'review_resolved',
        batch_id: batchId,
        employee_keys: item.employee_key ? [String(item.employee_key)] : undefined,
      })
    } catch (err) {
      const safe = friendlyError(err, 'Could not apply approved change. Refresh and try again.')
      setError(safe)
      onNotice?.(safe, 'error')
      await load({ soft: true })
    } finally {
      setApplyBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[15px] font-semibold text-text">Needs review</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Decide on each person, then apply on the same import. Lifecycle changes from connected systems appear here too.
        </p>
      </div>
      {loading && items.length === 0 && lifecycleItems.length === 0 ? (
        <p className="flex items-center gap-2 text-[13px] text-subtle/80">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      ) : null}
      {error ? <p className="text-[13px] text-rose-600">{error}</p> : null}
      {!loading && !items.length && !lifecycleItems.length ? (
        <p className="text-[13px] text-subtle/80">Nothing needs review right now.</p>
      ) : null}
      {lifecycleItems.length ? (
        <ul className="space-y-2">
          {lifecycleItems.map((ev) => {
            const id = String(ev.event_id || '')
            const disposition = String(ev.disposition || 'needs_review').replace(/_/g, ' ')
            const source = String(ev.source_system || '')
            const effective = ev.effective_date ? String(ev.effective_date) : null
            const why = String(ev.review_reason || ev.authority_note || '').replace(/_/g, ' ')
            const employeeKey = ev.employee_key ? String(ev.employee_key) : null
            return (
              <li key={id} className="rounded-2xl border border-line/50 bg-white/55 px-4 py-3 text-[13px]">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#8a5a16]" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-text capitalize">{disposition}</p>
                    <p className="mt-0.5 text-[12px] text-subtle/80">
                      {String(ev.normalized_state || '')}
                      {ev.source_status ? ` · source “${String(ev.source_status)}”` : ''}
                      {source ? ` · ${source}` : ''}
                      {effective ? ` · effective ${effective}` : ''}
                    </p>
                    {why ? <p className="mt-1 text-[12px] text-subtle/75">Review: {why}</p> : null}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button
                        type="button"
                        size="sm"
                        disabled={Boolean(lifecycleBusyId)}
                        onClick={async () => {
                          setLifecycleBusyId(id)
                          try {
                            await approveMigrationLifecycleEvent(access, id)
                            onNotice?.('Lifecycle change applied.', 'success')
                            await load({ soft: true })
                            emitMigrationSyncLive({
                              reason: 'lifecycle_resolved',
                              employee_keys: employeeKey ? [employeeKey] : undefined,
                            })
                          } catch (err) {
                            setError(friendlyError(err, 'Could not approve lifecycle change.'))
                          } finally {
                            setLifecycleBusyId(null)
                          }
                        }}
                      >
                        {lifecycleBusyId === id ? 'Working…' : 'Approve'}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={Boolean(lifecycleBusyId)}
                        onClick={async () => {
                          setLifecycleBusyId(id)
                          try {
                            await rejectMigrationLifecycleEvent(access, id, 'rejected_by_hr')
                            onNotice?.('Lifecycle change ignored.', 'info')
                            await load({ soft: true })
                            emitMigrationSyncLive({
                              reason: 'lifecycle_resolved',
                              employee_keys: employeeKey ? [employeeKey] : undefined,
                            })
                          } catch (err) {
                            setError(friendlyError(err, 'Could not reject lifecycle change.'))
                          } finally {
                            setLifecycleBusyId(null)
                          }
                        }}
                      >
                        Ignore
                      </Button>
                    </div>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      ) : null}
      <ul className="space-y-2">
        {items.map((item) => {
          const quietSource = item.filename
            ? String(item.filename).replace(/^.*[\\/]/, '')
            : null
          // Apply only when backend marks this exact canonical row applyable.
          const pendingApply = Boolean(item.applyable)
          const canApprove =
            Boolean(item.approvable && item.name_identity_review && item.batch_id && item.row_id) &&
            ['previewed', 'partial'].includes(String(item.batch_status || ''))
          const lines = changeLines(item)
          return (
            <li
              key={item.review_identity_key || `${item.canonical_batch_id || item.batch_id}-${item.canonical_row_id || item.row_id || item.row}`}
              className="rounded-2xl border border-line/50 bg-white/55 px-4 py-3 text-[13px]"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle className={cn('mt-0.5 h-4 w-4 shrink-0', pendingApply ? 'text-emerald-700' : 'text-[#8a5a16]')} />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-text">
                    {item.name}
                    {pendingApply ? (
                      <span className="ms-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-medium text-emerald-700">
                        Approved
                      </span>
                    ) : null}
                  </p>
                  <p className="text-[12px] text-subtle/85">{item.reason}</p>
                  {lines.map((line) => (
                    <p key={line} className="text-[11.5px] text-subtle/75">
                      {line}
                    </p>
                  ))}
                  {item.name_change_approved_at ? (
                    <p className="mt-1 text-[11px] text-subtle/60">
                      Approved{item.name_change_approved_by ? ` by ${item.name_change_approved_by}` : ''} ·{' '}
                      {item.name_change_approved_at}
                    </p>
                  ) : null}
                  {quietSource ? (
                    <p className="mt-1 text-[11.5px] text-subtle/55">From {quietSource}</p>
                  ) : null}
                  {canApprove ? (
                    <button
                      type="button"
                      disabled={approveBusyId === item.row_id}
                      onClick={() => void approveName(item)}
                      className="mt-2 inline-flex items-center rounded-full bg-[#fff7e8] px-2.5 py-1 text-[11.5px] font-medium text-[#8a5a16] hover:bg-[#fdeecb] disabled:opacity-60"
                    >
                      {approveBusyId === item.row_id ? 'Approving…' : 'Approve name change'}
                    </button>
                  ) : null}
                  {pendingApply ? (
                    <button
                      type="button"
                      disabled={applyBusyId === (item.row_id || item.canonical_row_id)}
                      onClick={() => void applyApproved(item)}
                      className="mt-2 ms-2 inline-flex items-center rounded-full bg-[#eef5ee] px-2.5 py-1 text-[11.5px] font-medium text-[#3d5a40] hover:bg-[#e2eee3] disabled:opacity-60"
                    >
                      {applyBusyId === (item.row_id || item.canonical_row_id) ? 'Applying…' : 'Apply approved change'}
                    </button>
                  ) : null}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function HistorySection({
  access,
  onNotice,
  onAccessIssue,
}: {
  access: DashboardAccess
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
}) {
  const [loading, setLoading] = useState(true)
  const [batches, setBatches] = useState<Array<Record<string, unknown>>>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<EmployeeImportResult | null>(null)
  const expandedIdRef = useRef<string | null>(null)
  expandedIdRef.current = expanded?.batch_id || null

  const load = useCallback(async (opts?: { soft?: boolean }) => {
    if (!opts?.soft) setLoading(true)
    setError(null)
    try {
      const res = await listEmployeeImportBatches(access, 40)
      setBatches(res.batches || [])
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue?.(issue)
      setError(friendlyError(err, 'Could not load history.'))
    } finally {
      setLoading(false)
    }
  }, [access, onAccessIssue])

  useEffect(() => {
    void load()
  }, [load])

  useMigrationSyncLiveRefresh(
    async () => {
      await load({ soft: true })
      // Keep open batch detail in sync without collapsing the drawer.
      const openId = expandedIdRef.current
      if (openId) {
        try {
          const res = await getEmployeeImportBatch(access, openId)
          setExpanded(res)
        } catch {
          /* leave prior expanded detail painted */
        }
      }
    },
    {
      isDirty: () => Boolean(busyId),
      pollMs: MIGRATION_SYNC_SOFT_POLL_MS,
      debounceMs: 450,
    },
  )

  const openBatch = async (batchId: string) => {
    setBusyId(batchId)
    try {
      const res = await getEmployeeImportBatch(access, batchId)
      setExpanded(res)
    } catch (err) {
      onNotice(friendlyError(err, 'Could not open batch.'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const undo = async (batchId: string) => {
    const key = `undo-${batchId}-${Date.now()}`
    setBusyId(batchId)
    try {
      const res = await rollbackEmployeeImportBatch(access, batchId, key)
      const reverted = (res as { reverted?: number }).reverted || 0
      const msg = `Undo completed · ${res.removed} added people removed, ${reverted} updates reversed (fields changed later were left alone).`
      onNotice(msg, 'success')
      setExpanded(null)
      await load({ soft: true })
      emitMigrationSyncLive({ reason: 'import_applied', batch_id: batchId })
    } catch (err) {
      onNotice(friendlyError(err, 'Could not undo this batch.'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[15px] font-semibold text-text">History</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Past imports and sync runs. Undo reverses this batch only — if someone edited a field again after the import, that field stays as it is now.
        </p>
      </div>
      {loading && batches.length === 0 ? (
        <p className="flex items-center gap-2 text-[13px] text-subtle/80">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      ) : null}
      {error ? <p className="text-[13px] text-rose-600">{error}</p> : null}
      {!loading && !batches.length ? <p className="text-[13px] text-subtle/80">No import history yet.</p> : null}
      <ul className="space-y-2">
        {batches.map((b) => {
          const id = String(b.batch_id || '')
          const totals = (b.totals || {}) as Record<string, number>
          const status = String(b.status || '')
          const canUndo = status === 'committed' || status === 'partial' || status === 'failed'
          return (
            <li key={id} className="rounded-2xl border border-line/50 bg-white/55 px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-[13px] font-medium text-text">{String(b.filename || 'Import')}</p>
                  <p className="text-[12px] text-subtle/80">
                    {status} · {Number(b.total_rows || 0)} rows · added {Number(totals.create || 0)} · updated{' '}
                    {Number(totals.update || 0)} · review {Number(totals.review ?? totals.conflict ?? 0)}
                  </p>
                  <p className="text-[11.5px] text-subtle/65">{String(b.created_at || '')}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" size="sm" disabled={busyId === id} onClick={() => void openBatch(id)}>
                    {busyId === id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <History className="h-3.5 w-3.5" />}
                    Open
                  </Button>
                  {canUndo ? (
                    <Button variant="secondary" size="sm" disabled={busyId === id} onClick={() => void undo(id)}>
                      Undo
                    </Button>
                  ) : null}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
      {expanded ? (
        <div className="space-y-2 rounded-2xl border border-line/60 bg-[#fffaf0]/70 p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-text">Batch detail</p>
            <button type="button" className="text-[12px] text-subtle/80 hover:underline" onClick={() => setExpanded(null)}>
              Close
            </button>
          </div>
          <OutcomeList title="Added" rows={expanded.results?.created || []} tone="success" />
          <OutcomeList title="Updated" rows={expanded.results?.updated || []} tone="info" showChanges />
          <OutcomeList title="Skipped" rows={expanded.results?.skipped || []} tone="muted" />
          <OutcomeList title="Needs review" rows={expanded.results?.needs_review || []} tone="warning" />
          <OutcomeList title="Failed / invalid" rows={expanded.results?.failed || []} tone="danger" />
        </div>
      ) : null}
    </div>
  )
}

export function MigrationSyncShell({
  access,
  onNotice,
  onAccessIssue,
  onBack,
}: {
  access: DashboardAccess
  onNotice: NoticeFn
  onAccessIssue?: (issue: AccessIssue) => void
  onBack: () => void
}) {
  const [section, setSection] = useState<Section>('import')
  const [reviewCount, setReviewCount] = useState(0)

  const refreshReviewCount = useCallback(async () => {
    try {
      const [res, life] = await Promise.all([
        listEmployeeImportReview(access, 100),
        listMigrationLifecycleReview(access, 50).catch(() => ({ events: [] as Array<Record<string, unknown>> })),
      ])
      const importCount = res.count || (res.items || []).length
      const lifeCount = (life.events || []).length
      setReviewCount(importCount + lifeCount)
    } catch {
      /* ignore for badge */
    }
  }, [access])

  useEffect(() => {
    void refreshReviewCount()
  }, [refreshReviewCount])

  // Keep nav badge live while shell is open (sync / scheduler / other tab).
  useMigrationSyncLiveRefresh(
    async () => {
      await refreshReviewCount()
    },
    {
      pollMs: MIGRATION_SYNC_SOFT_POLL_MS,
      debounceMs: 400,
    },
  )

  const body: ReactNode = useMemo(() => {
    if (section === 'import') {
      return (
        <ImportSection
          access={access}
          onNotice={onNotice}
          onApplied={() => {
            void refreshReviewCount()
            emitMigrationSyncLive({ reason: 'import_applied' })
          }}
        />
      )
    }
    if (section === 'connected') {
      return <ConnectedSection access={access} onNotice={onNotice} onAccessIssue={onAccessIssue} />
    }
    if (section === 'review') return <ReviewSection access={access} onAccessIssue={onAccessIssue} onNotice={onNotice} />
    return <HistorySection access={access} onNotice={onNotice} onAccessIssue={onAccessIssue} />
  }, [section, access, onNotice, onAccessIssue, refreshReviewCount])

  return (
    <div className="space-y-5" dir="ltr">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button
            type="button"
            onClick={onBack}
            className="mb-2 inline-flex items-center gap-1.5 text-[12px] font-medium text-subtle/80 hover:text-text"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to employees
          </button>
          <h1 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-text">Migration & Sync</h1>
          <p className="mt-1 max-w-2xl text-[13px] leading-6 text-subtle/90">
            Bring your existing team in safely. Preview who will be added or updated, resolve anything that needs review, then confirm.
          </p>
        </div>
      </div>
      <SectionNav section={section} setSection={setSection} reviewCount={reviewCount} />
      <Card className="border-line/50 bg-panel/40 shadow-none">
        <CardContent className="p-5 sm:p-6">{body}</CardContent>
      </Card>
    </div>
  )
}
