import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowLeft, Download, Eye, History, Link2, Loader2, Upload, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  applyEmployeeImportApprovedNameChange,
  approveEmployeeImportNameChange,
  downloadEmployeeImportExceptions,
  getEmployeeImportBatch,
  importEmployees,
  listEmployeeImportBatches,
  listEmployeeImportReview,
  rollbackEmployeeImportBatch,
  type EmployeeImportResult,
  type EmployeeImportRow,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import type { DashboardAccess } from '@/types'

type NoticeFn = (message: string, tone?: 'success' | 'error' | 'info') => void

type Section = 'import' | 'connected' | 'review' | 'history'

function friendlyError(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'message' in err && typeof (err as { message: unknown }).message === 'string') {
    return (err as { message: string }).message
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
          const canApply = Boolean(onApplyApproved && r.applyable && r.row_id && r.batch_id)
          const approved = Boolean(r.name_change_approved)
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
        const totals = res.totals
        const review = totals?.review ?? totals?.conflict ?? 0
        setStatus(
          opts?.refresh
            ? `Preview refreshed · ${res.total_rows} row${res.total_rows === 1 ? '' : 's'}.`
            : `Preview ready · ${res.total_rows} row${res.total_rows === 1 ? '' : 's'}` +
                (review ? ` · ${review} need review` : '') +
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
    const batchId = row.batch_id || preview?.batch_id
    if (!batchId || !row.row_id) return
    setApplyBusyId(row.row_id)
    setError(null)
    try {
      const res = await applyEmployeeImportApprovedNameChange(access, batchId, row.row_id)
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
    } catch (err) {
      const safe = friendlyError(err, 'Could not apply approved change.')
      setError(safe)
      onNotice(safe, 'error')
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
          Optional: email, job title, department, start date, external_employee_id, payroll_id, source_system, manager_phone.
        </p>
        <p className="mt-1.5 text-subtle/75">
          Matching: external ID when supplied, otherwise phone. Never by name alone. Safe updates: name,
          email, job title, department, start date, manager — except a materially different name needs
          review (and an explicit approve) before it updates.
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

function ConnectedSection() {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-[15px] font-semibold text-text">Connected systems</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Connect an HR or payroll system later. For now, use file import. Deactivation from sync is off.
        </p>
      </div>
      <Card className="border-line/50 bg-white/55 shadow-none">
        <CardContent className="flex items-start gap-3 p-4">
          <Link2 className="mt-0.5 h-5 w-5 text-subtle/70" />
          <div>
            <p className="text-[13px] font-medium text-text">No systems connected</p>
            <p className="mt-1 text-[12px] leading-5 text-subtle/80">
              When available: connect → choose who to sync → preview → approve. Same outcome language as file import.
            </p>
          </div>
        </CardContent>
      </Card>
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
  const [error, setError] = useState<string | null>(null)
  const [approveBusyId, setApproveBusyId] = useState<string | null>(null)
  const [applyBusyId, setApplyBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listEmployeeImportReview(access, 100)
      setItems(res.items || [])
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
      await load()
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
    if (!item.batch_id || !item.row_id) return
    setApplyBusyId(item.row_id)
    setError(null)
    try {
      const res = await applyEmployeeImportApprovedNameChange(access, item.batch_id, item.row_id)
      const msg =
        (res as EmployeeImportResult & { message?: string }).message ||
        `Applied approved change for ${item.name}.`
      onNotice?.(msg, 'success')
      await load()
    } catch (err) {
      const safe = friendlyError(err, 'Could not apply approved change.')
      setError(safe)
      onNotice?.(safe, 'error')
    } finally {
      setApplyBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[15px] font-semibold text-text">Needs review</p>
        <p className="mt-1 text-[13px] leading-6 text-subtle/90">
          Decide on each person, then apply on the same import. Each person appears once. Past attempts stay in History.
        </p>
      </div>
      {loading ? (
        <p className="flex items-center gap-2 text-[13px] text-subtle/80">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      ) : null}
      {error ? <p className="text-[13px] text-rose-600">{error}</p> : null}
      {!loading && !items.length ? (
        <p className="text-[13px] text-subtle/80">Nothing needs review right now.</p>
      ) : null}
      <ul className="space-y-2">
        {items.map((item) => {
          const quietSource = item.filename
            ? String(item.filename).replace(/^.*[\\/]/, '')
            : null
          const pendingApply = Boolean(item.applyable || (item.name_change_approved && item.status === 'will_update'))
          const canApprove =
            Boolean(item.approvable && item.name_identity_review && item.batch_id && item.row_id) &&
            ['previewed', 'partial'].includes(String(item.batch_status || ''))
          const lines = changeLines(item)
          return (
            <li
              key={item.review_identity_key || `${item.batch_id}-${item.row_id || item.row}`}
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
                  {pendingApply && item.batch_id && item.row_id ? (
                    <button
                      type="button"
                      disabled={applyBusyId === item.row_id}
                      onClick={() => void applyApproved(item)}
                      className="mt-2 ms-2 inline-flex items-center rounded-full bg-[#eef5ee] px-2.5 py-1 text-[11.5px] font-medium text-[#3d5a40] hover:bg-[#e2eee3] disabled:opacity-60"
                    >
                      {applyBusyId === item.row_id ? 'Applying…' : 'Apply approved change'}
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

  const load = useCallback(async () => {
    setLoading(true)
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
      await load()
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
      {loading ? (
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
      const res = await listEmployeeImportReview(access, 100)
      setReviewCount(res.count || (res.items || []).length)
    } catch {
      /* ignore for badge */
    }
  }, [access])

  useEffect(() => {
    void refreshReviewCount()
  }, [refreshReviewCount])

  const body: ReactNode = useMemo(() => {
    if (section === 'import') {
      return (
        <ImportSection
          access={access}
          onNotice={onNotice}
          onApplied={() => {
            void refreshReviewCount()
          }}
        />
      )
    }
    if (section === 'connected') return <ConnectedSection />
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
