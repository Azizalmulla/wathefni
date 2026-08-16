import { Loader2, RotateCcw, Upload, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/field'
import { useConfirm } from '@/components/ConfirmDialog'
import {
  commitAttendanceImport,
  DashboardApiError,
  listAttendanceImportBatches,
  listAttendanceImportMappings,
  previewAttendanceImport,
  reverseAttendanceImportBatch,
  saveAttendanceImportMapping,
} from '@/lib/api'
import type {
  AttendanceImportBatch,
  AttendanceImportMapping,
  AttendanceImportPreview,
  DashboardAccess,
} from '@/types'

const MAP_FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: 'external_id', label: 'Device / staff ID', required: true },
  { key: 'timestamp', label: 'Timestamp (date + time)' },
  { key: 'punch_date', label: 'Date (if separate)' },
  { key: 'punch_time', label: 'Time (if separate)' },
  { key: 'direction', label: 'Direction (in/out)' },
  { key: 'device', label: 'Device / branch' },
  { key: 'name', label: 'Name (hint only)' },
]

function errMessage(error: unknown, fallback: string): string {
  if (error instanceof DashboardApiError) return error.message || fallback
  return fallback
}

export function AttendanceImportDialog({
  access,
  onClose,
  onImported,
}: {
  access: DashboardAccess
  onClose: () => void
  onImported: () => void
}) {
  const confirm = useConfirm()
  const [file, setFile] = useState<File | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<AttendanceImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [batches, setBatches] = useState<AttendanceImportBatch[]>([])
  const [savedMappings, setSavedMappings] = useState<AttendanceImportMapping[]>([])

  const loadBatches = useCallback(async () => {
    try {
      const [b, m] = await Promise.all([listAttendanceImportBatches(access), listAttendanceImportMappings(access)])
      setBatches(b.batches || [])
      setSavedMappings(m.mappings || [])
    } catch {
      /* non-fatal */
    }
  }, [access])

  useEffect(() => {
    void loadBatches()
  }, [loadBatches])

  async function runPreview(useMapping?: Record<string, string>) {
    if (!file) {
      setNotice({ kind: 'err', text: 'Choose a CSV or XLSX file first.' })
      return
    }
    setBusy(true)
    setNotice(null)
    try {
      const result = await previewAttendanceImport(access, { file, mapping: useMapping && Object.keys(useMapping).length ? useMapping : undefined })
      setPreview(result)
      setMapping(result.applied_mapping || {})
    } catch (error) {
      setPreview(null)
      setNotice({ kind: 'err', text: errMessage(error, 'We could not read this file.') })
    } finally {
      setBusy(false)
    }
  }

  async function runCommit() {
    if (!file || !preview) return
    const counts = preview.counts || {}
    const ok = await confirm({
      title: 'Import attendance?',
      body: `This will apply ${counts.records || 0} attendance record(s). ${counts.unmatched || 0} unmatched and ${counts.errors || 0} error row(s) will be skipped. You can reverse this import afterwards.`,
      confirmLabel: 'Import',
    })
    if (!ok) return
    setBusy(true)
    setNotice(null)
    try {
      const result = await commitAttendanceImport(access, { file, mapping: Object.keys(mapping).length ? mapping : undefined })
      setNotice({ kind: 'ok', text: `Imported ${result.applied} record(s). ${result.skipped_locked} skipped (locked period).` })
      setPreview(null)
      setFile(null)
      onImported()
      await loadBatches()
    } catch (error) {
      setNotice({ kind: 'err', text: errMessage(error, 'The import could not be completed.') })
    } finally {
      setBusy(false)
    }
  }

  async function saveMapping() {
    const name = await confirm.withReason({
      title: 'Save column mapping',
      body: 'Name this mapping so you can reuse it on the next attendance import.',
      confirmLabel: 'Save mapping',
      reasonLabel: 'Mapping name',
      reasonPlaceholder: 'e.g. ZKTeco main branch',
      minReasonLength: 2,
    })
    if (!name) return
    try {
      await saveAttendanceImportMapping(access, { name, mapping })
      setNotice({ kind: 'ok', text: `Saved mapping "${name}".` })
      await loadBatches()
    } catch (error) {
      setNotice({ kind: 'err', text: errMessage(error, 'Could not save mapping.') })
    }
  }

  async function reverse(batch: AttendanceImportBatch) {
    const ok = await confirm({
      title: 'Reverse this import?',
      body: `This removes attendance created by "${batch.filename || batch.batch_id}" and restores any records it changed. Records edited after the import, or now in a locked payroll period, are left untouched.`,
      confirmLabel: 'Reverse import',
      destructive: true,
    })
    if (!ok) return
    setBusy(true)
    try {
      const result = await reverseAttendanceImportBatch(access, batch.batch_id)
      setNotice({
        kind: 'ok',
        text: `Reversed: ${result.deleted} removed, ${result.restored} restored, ${result.conflicts} skipped (changed), ${result.locked_skipped} skipped (locked).`,
      })
      onImported()
      await loadBatches()
    } catch (error) {
      setNotice({ kind: 'err', text: errMessage(error, 'Could not reverse this import.') })
    } finally {
      setBusy(false)
    }
  }

  const counts = preview?.counts || {}
  const headers = preview?.headers || []

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm">
      <div className="my-8 w-full max-w-3xl rounded-3xl border border-line/60 bg-panel p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-text">Import from fingerprint device</h2>
            <p className="text-sm text-subtle">Upload a CSV/XLSX export. Only the staff ID, time, and in/out are read — no biometric data is stored.</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>

        {notice ? (
          <div className={`mb-4 rounded-lg border p-3 text-sm ${notice.kind === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-800'}`}>{notice.text}</div>
        ) : null}

        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null) }} />
            <Button onClick={() => void runPreview()} disabled={busy || !file}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Preview
            </Button>
            {savedMappings.length ? (
              <Select onChange={(e) => { const m = savedMappings.find((x) => x.mapping_id === e.target.value); if (m) { setMapping(m.mapping); void runPreview(m.mapping) } }} value="">
                <option value="">Load saved mapping…</option>
                {savedMappings.map((m) => <option key={m.mapping_id} value={m.mapping_id}>{m.name}</option>)}
              </Select>
            ) : null}
          </div>

          {preview ? (
            <>
              {preview.dropped_biometric && preview.dropped_biometric.length ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                  Ignored biometric column(s) — never stored: {preview.dropped_biometric.join(', ')}
                </div>
              ) : null}

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Records" value={counts.records || 0} tone="success" />
                <Stat label="Unmatched" value={counts.unmatched || 0} tone={counts.unmatched ? 'warning' : 'muted'} />
                <Stat label="Duplicates" value={counts.duplicates || 0} tone="muted" />
                <Stat label="Errors" value={counts.errors || 0} tone={counts.errors ? 'danger' : 'muted'} />
                <Stat label="Incomplete" value={counts.incomplete || 0} tone={counts.incomplete ? 'warning' : 'muted'} />
                <Stat label="Locked-skip" value={counts.skipped_locked || 0} tone={counts.skipped_locked ? 'warning' : 'muted'} />
                <Stat label="Punches" value={counts.punches || 0} tone="muted" />
              </div>

              <details className="rounded-lg border border-line/60 p-3">
                <summary className="cursor-pointer text-sm font-medium text-text">Column mapping</summary>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {MAP_FIELDS.map((f) => (
                    <label key={f.key} className="text-xs text-subtle">
                      {f.label}{f.required ? ' *' : ''}
                      <Select value={mapping[f.key] || ''} onChange={(e) => setMapping((prev) => ({ ...prev, [f.key]: e.target.value }))}>
                        <option value="">—</option>
                        {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                      </Select>
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => void runPreview(mapping)} disabled={busy}>Re-analyze</Button>
                  <Button size="sm" variant="ghost" onClick={() => void saveMapping()} disabled={busy}>Save mapping</Button>
                </div>
              </details>

              {preview.unmatched && preview.unmatched.length ? (
                <details className="rounded-lg border border-amber-200/70 bg-amber-50/40 p-3">
                  <summary className="cursor-pointer text-sm font-medium text-amber-900">{preview.unmatched.length} unmatched device ID(s) — assign on the employee record, then re-import</summary>
                  <ul className="mt-2 space-y-1 text-xs text-amber-900">
                    {preview.unmatched.slice(0, 50).map((u) => (
                      <li key={u.external_id}>ID <strong>{u.external_id}</strong>{u.name_hint ? ` (${u.name_hint})` : ''} · {u.count} punch(es)</li>
                    ))}
                  </ul>
                </details>
              ) : null}

              <div className="overflow-x-auto rounded-lg border border-line/60">
                <table className="w-full text-left text-xs">
                  <thead className="bg-panel-muted/60 text-subtle">
                    <tr><th className="px-3 py-2">Employee</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">In</th><th className="px-3 py-2">Out</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Outcome</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line/40">
                    {(preview.records || []).slice(0, 100).map((r, i) => (
                      <tr key={i}>
                        <td className="px-3 py-2">{r.employee_name || r.employee_key}</td>
                        <td className="px-3 py-2">{r.attendance_date}</td>
                        <td className="px-3 py-2">{r.check_in_at ? new Date(r.check_in_at).toLocaleTimeString() : '—'}</td>
                        <td className="px-3 py-2">{r.check_out_at ? new Date(r.check_out_at).toLocaleTimeString() : '—'}</td>
                        <td className="px-3 py-2">{r.status}</td>
                        <td className="px-3 py-2"><Badge tone={r.outcome === 'applied' ? 'success' : 'warning'}>{r.outcome}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={() => { setPreview(null); setFile(null) }} disabled={busy}>Cancel</Button>
                <Button onClick={() => void runCommit()} disabled={busy || !(counts.records || 0)}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Confirm import ({counts.records || 0})
                </Button>
              </div>
            </>
          ) : null}

          {batches.length ? (
            <div className="rounded-lg border border-line/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-text">Import history</h3>
              <ul className="space-y-2">
                {batches.map((b) => (
                  <li key={b.batch_id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-subtle">
                      {b.filename || b.batch_id} · {b.period_start || '?'}→{b.period_end || '?'} · {(b.counts?.records ?? 0)} rec
                      {b.status === 'reversed' ? <Badge tone="muted" className="ml-2">reversed</Badge> : null}
                    </span>
                    {b.status !== 'reversed' ? (
                      <Button size="sm" variant="ghost" onClick={() => void reverse(b)} disabled={busy}><RotateCcw className="h-3.5 w-3.5" /> Reverse</Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'success' | 'warning' | 'danger' | 'muted' }) {
  return (
    <div className="rounded-lg border border-line/50 bg-panel-muted/40 p-2 text-center">
      <div className={`text-base font-semibold ${tone === 'danger' ? 'text-rose-700' : tone === 'warning' ? 'text-amber-700' : tone === 'success' ? 'text-emerald-700' : 'text-text'}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-subtle">{label}</div>
    </div>
  )
}
