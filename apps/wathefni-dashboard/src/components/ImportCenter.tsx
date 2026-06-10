import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Archive, AlertTriangle, Check, CheckCheck, CheckCircle2, ChevronDown, ChevronUp, Download, FileText, Loader2, UploadCloud, X } from 'lucide-react'

import {
  bulkImportAction,
  DashboardApiError,
  downloadImportReport,
  getImportIntake,
  uploadBulkCvImport,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useConfirm } from '@/components/ConfirmDialog'
import { Select } from '@/components/ui/field'
import type {
  DashboardAccess,
  ImportIntakeGroup,
  ImportItemResult,
  ImportUploadResponse,
  PositionSummary,
} from '@/types'

// Keep raw backend/API text out of the import UI. Maps known error codes to calm
// copy and suppresses anything that looks like an identifier/stack/backend string,
// falling back to a friendly default. Raw errors are still available in the console.
const IMPORT_ERROR_MESSAGES: Record<string, string> = {
  permission_denied: 'You don’t have permission to do this.',
  module_disabled: 'CV import isn’t enabled for your company yet.',
  dashboard_auth_failed: 'Your session needs to be verified again. Please sign in.',
}
function friendlyImportError(error: unknown, fallback: string): string {
  const technical = /(_|[{}[\]"<>]|backend|traceback|exception|psycopg|sql|stack|null|undefined|tool_|registry)/i
  if (error instanceof DashboardApiError) {
    const mapped = IMPORT_ERROR_MESSAGES[error.code]
    if (mapped) return mapped
    return error.message && !technical.test(error.message) ? error.message : fallback
  }
  if (error instanceof Error && error.message && !technical.test(error.message)) return error.message
  return fallback
}

const CV_ACCEPT = '.pdf,.doc,.docx,.rtf,.txt,.png,.jpg,.jpeg,.webp,.zip'
const META_ACCEPT = '.csv,.xlsx'
// Kept in sync with the backend (IMPORT_MAX_FILES / IMPORT_MAX_TOTAL_BYTES). The
// server is the source of truth; these only drive friendly client-side hints.
const MAX_FILES = 300
const MAX_TOTAL_BYTES = 250 * 1024 * 1024
// Lead with the formats HR actually recognises; the rest live under "More supported formats".
const PRIMARY_FORMATS = ['PDF', 'DOC', 'DOCX', 'ZIP']
const MORE_FORMATS = ['RTF', 'TXT', 'PNG', 'JPG', 'WEBP']
// Provenance labels only — generic CSV/Excel + CVs are the universal bridge.
const IMPORT_SOURCE_OPTIONS: { value: string; label: string }[] = [
  { value: 'bulk_upload', label: 'Bulk upload' },
  { value: 'linkedin_export', label: 'LinkedIn' },
  { value: 'oracle_taleo_export', label: 'Oracle / Taleo' },
  { value: 'workday_export', label: 'Workday' },
  { value: 'sap_successfactors_export', label: 'SAP SuccessFactors' },
  { value: 'email', label: 'Email' },
  { value: 'other_ats_export', label: 'Other ATS' },
]
const SUGGESTION_SOURCE_LABELS: Record<string, string> = {
  metadata_position_code: 'matched from your sheet',
  metadata_applied_role: 'matched from your sheet',
  metadata_unmatched_code: 'role in sheet not recognized',
  zip_folder_path: 'from ZIP folder',
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`
}

function fileSignature(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`
}

// Maps backend item error codes to short, human-readable reasons for the result list.
function skipReason(item: ImportItemResult): string {
  const error = item.error || ''
  if (item.status === 'duplicate') {
    if (error === 'duplicate_in_batch') return 'Duplicate within this upload'
    if (error === 'duplicate_existing_cv') return 'Already imported earlier'
    return 'Duplicate CV'
  }
  if (error.startsWith('unsupported_file_type')) {
    const ext = error.split(':')[1]
    return `Unsupported file type${ext && ext !== 'unknown' ? ` (${ext})` : ''}`
  }
  if (error === 'unreadable_or_unsupported_file') return 'Unreadable or unsupported file'
  if (error.startsWith('storage_failed') || error === 'storage_failed') return 'Could not store file'
  if (error.startsWith('import_failed')) return 'Import failed'
  return 'Skipped'
}

// Small header button that opens the bulk-import modal. Import is an admin/onboarding
// action, so it lives behind a button rather than dominating the Candidates page.
export function ImportCvButton({
  access,
  positions,
  onImported,
}: {
  access: DashboardAccess
  positions: PositionSummary[]
  onImported: () => void
}) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [metadataFile, setMetadataFile] = useState<File | null>(null)
  const [destination, setDestination] = useState<'review' | 'role'>('review')
  const [defaultPosition, setDefaultPosition] = useState('')
  const [source, setSource] = useState('bulk_upload')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<ImportUploadResponse | null>(null)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [showMoreFormats, setShowMoreFormats] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const confirm = useConfirm()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const metaInputRef = useRef<HTMLInputElement>(null)

  const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
  const overFileLimit = files.length > MAX_FILES
  const overSizeLimit = totalBytes > MAX_TOTAL_BYTES
  const positionTitleFor = (code: string) => positions.find((p) => p.position_code === code)?.position_title || code
  // Safety: "Add directly to a role" needs a chosen role, otherwise the candidate
  // would enter the pipeline with no explicit role (which must never happen).
  const roleRequired = destination === 'role' && !defaultPosition
  const canSubmit = files.length > 0 && !overFileLimit && !overSizeLimit && !roleRequired

  function openModal() {
    setOpen(true)
    setError('')
  }

  // Additive selection: merge new picks into the existing set and de-dupe by
  // name+size+lastModified so picking files across multiple clicks accumulates
  // instead of replacing the previous selection.
  function addFiles(incoming: FileList | null) {
    if (!incoming?.length) return
    // Snapshot the File refs NOW: the setFiles updater runs after we clear the
    // input below, which would otherwise empty the live FileList before it reads.
    const picked = Array.from(incoming)
    setError('')
    setFiles((current) => {
      const seen = new Set(current.map(fileSignature))
      const merged = [...current]
      for (const file of picked) {
        const signature = fileSignature(file)
        if (!seen.has(signature)) {
          seen.add(signature)
          merged.push(file)
        }
      }
      return merged
    })
    // Reset the input so re-picking the same file fires onChange again.
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function removeFile(signature: string) {
    setFiles((current) => current.filter((file) => fileSignature(file) !== signature))
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    addFiles(event.dataTransfer?.files || null)
  }

  function resetForm() {
    setFiles([])
    setMetadataFile(null)
    setDestination('review')
    setDefaultPosition('')
    setSource('bulk_upload')
    setShowAdvanced(false)
    setShowMoreFormats(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (metaInputRef.current) metaInputRef.current.value = ''
  }

  function closeModal() {
    setOpen(false)
    setResult(null)
    resetForm()
  }

  async function runImport() {
    if (!files.length) {
      setError('Add at least one CV file or a ZIP archive.')
      return
    }
    if (overFileLimit) {
      setError(`Import up to ${MAX_FILES} files at a time. For larger migrations, use an enterprise import.`)
      return
    }
    if (overSizeLimit) {
      setError(`Total upload exceeds ${formatBytes(MAX_TOTAL_BYTES)}. Split into smaller batches or use a ZIP.`)
      return
    }
    if (roleRequired) {
      setError('Choose a role, or switch to “Review before adding”.')
      return
    }
    // Only pass a role when HR explicitly chose "Add directly to a role".
    const positionCode = destination === 'role' ? defaultPosition : ''
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const response = await uploadBulkCvImport(access, {
        files,
        metadataFile,
        positionCode: positionCode || undefined,
        positionTitle: positionCode ? positionTitleFor(positionCode) : undefined,
        source,
      })
      setResult(response)
      resetForm()
      onImported()
    } catch (err) {
      setError(friendlyImportError(err, 'We couldn’t import these files. Please check the format and try again.'))
    } finally {
      setUploading(false)
    }
  }

  const skippedItems = (result?.items || []).filter((item) => item.status === 'duplicate' || item.status === 'failed')

  return (
    <>
      <Button onClick={openModal} type="button" variant="secondary">
        <UploadCloud size={16} /> Import CVs
      </Button>

      {open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-ink/20 p-4 backdrop-blur-[2px]" onClick={closeModal}>
          <div
            className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-[1.75rem] border border-white/70 bg-panel/95 p-6 shadow-[0_24px_80px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-lg font-semibold tracking-tight">Import CVs</div>
                <p className="mt-1 text-sm leading-6 text-subtle">
                  Upload CVs or a ZIP file. Wathefni will prepare them for review before they’re added to your candidates.
                </p>
              </div>
              <button className="rounded-full p-1.5 text-subtle hover:bg-panel-muted" onClick={closeModal} type="button">
                <X size={18} />
              </button>
            </div>

            {error ? (
              <div className="mt-4 flex items-start gap-2 rounded-2xl border border-rose-200/70 bg-rose-50/70 px-4 py-3 text-sm text-rose-700">
                <AlertTriangle className="mt-0.5 shrink-0" size={16} /> <span>{error}</span>
              </div>
            ) : null}

            {result ? (
              <div className="mt-4 space-y-4">
                <div className="rounded-2xl border border-emerald-200/70 bg-emerald-50/60 p-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-emerald-800">
                    <CheckCircle2 size={16} /> Imported {result.counts.imported} of {result.total_files} file{result.total_files === 1 ? '' : 's'}.
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <Badge tone="success">{result.counts.imported} imported</Badge>
                    {result.counts.auto_admitted ? <Badge tone="success">{result.counts.auto_admitted} added to Candidates</Badge> : null}
                    {result.counts.needs_role ? <Badge tone="warning">{result.counts.needs_role} to review</Badge> : null}
                    {result.counts.duplicate ? <Badge tone="muted">{result.counts.duplicate} duplicate</Badge> : null}
                    {result.counts.failed ? <Badge tone="danger">{result.counts.failed} skipped</Badge> : null}
                  </div>
                  {result.counts.auto_admitted ? (
                    <p className="mt-1.5 text-xs text-emerald-800/80">
                      Candidates with a clear role were added to Candidates automatically. They are labelled, and never
                      messaged or ranked without your review.
                    </p>
                  ) : (
                    <p className="mt-1.5 text-xs text-emerald-800/80">
                      You can sort and confirm these in Intake review on the Candidates page.
                    </p>
                  )}
                  {skippedItems.length ? (
                    <div className="mt-3 space-y-1 rounded-2xl border border-white/60 bg-white/55 p-2.5">
                      <div className="px-1 text-[11px] font-medium uppercase tracking-wide text-subtle">
                        Skipped files ({skippedItems.length})
                      </div>
                      <div className="max-h-32 space-y-0.5 overflow-y-auto">
                        {skippedItems.map((item, index) => (
                          <div key={`${item.original_filename}-${index}`} className="flex items-center justify-between gap-2 px-1 text-xs">
                            <span className="truncate text-text">{item.original_filename}</span>
                            <span className={`shrink-0 ${item.status === 'failed' ? 'text-rose-600' : 'text-amber-700'}`}>{skipReason(item)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <button
                    className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-emerald-800 underline-offset-2 hover:underline"
                    onClick={async () => {
                      if (!(await confirm({ title: 'Download import report?', body: 'This report contains candidate data and will download to this device as a file. Continue?', confirmLabel: 'Download' }))) return
                      setError('')
                      try {
                        await downloadImportReport(access, result.batch_id)
                      } catch (err) {
                        console.error('Import report download failed', err)
                        setError(friendlyImportError(err, 'We couldn’t download the import report. Please try again.'))
                      }
                    }}
                    type="button"
                  >
                    <Download size={14} /> Download import report
                  </button>
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <Button onClick={() => setResult(null)} type="button" variant="secondary">Import more</Button>
                  <Button onClick={closeModal} type="button">Done</Button>
                </div>
              </div>
            ) : (
              <div className="mt-5 space-y-6">
                {/* Step 1 — Upload files */}
                <section className="space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-text">Upload files</div>
                    {files.length ? (
                      <button
                        className="text-xs font-medium text-subtle underline-offset-2 hover:text-text hover:underline"
                        onClick={() => setFiles([])}
                        type="button"
                      >
                        Clear all
                      </button>
                    ) : null}
                  </div>
                  <input
                    ref={fileInputRef}
                    accept={CV_ACCEPT}
                    className="hidden"
                    multiple
                    onChange={(event) => addFiles(event.target.files)}
                    type="file"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(event) => {
                      event.preventDefault()
                      setDragging(true)
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={onDrop}
                    className={cnLocal(
                      'flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-9 text-center transition-colors',
                      dragging ? 'border-ink bg-ink/[0.04]' : 'border-subtle/30 bg-white/40 hover:border-ink/40 hover:bg-white/60',
                    )}
                  >
                    <span className="grid h-11 w-11 place-items-center rounded-full bg-ink/[0.06] text-ink">
                      <UploadCloud size={20} />
                    </span>
                    <span className="text-sm font-medium text-text">Drag &amp; drop, or click to browse</span>
                    <span className="text-xs text-subtle">
                      Accepted: {PRIMARY_FORMATS.join(', ')}
                    </span>
                  </button>
                  <div className="flex items-center justify-between">
                    <button
                      className="text-xs font-medium text-subtle underline-offset-2 hover:text-text hover:underline"
                      onClick={() => setShowMoreFormats((value) => !value)}
                      type="button"
                    >
                      {showMoreFormats ? 'Hide other formats' : 'More supported formats'}
                    </button>
                    {files.length ? (
                      <span className={`text-xs ${overSizeLimit ? 'text-rose-600' : 'text-subtle'}`}>
                        {files.length} file{files.length === 1 ? '' : 's'} · {formatBytes(totalBytes)}
                      </span>
                    ) : null}
                  </div>
                  {showMoreFormats ? (
                    <p className="text-xs leading-5 text-subtle">
                      Also accepted: {MORE_FORMATS.join(', ')}. ZIPs expand nested folders automatically; unsupported files are skipped.
                    </p>
                  ) : null}
                  {files.length ? (
                    <div className="max-h-40 space-y-1 overflow-y-auto rounded-2xl border border-white/60 bg-white/40 p-2">
                      {files.map((file) => {
                        const signature = fileSignature(file)
                        return (
                          <div key={signature} className="flex items-center justify-between gap-2 rounded-xl px-2 py-1 text-xs hover:bg-white/60">
                            <span className="flex min-w-0 items-center gap-1.5">
                              <FileText className="shrink-0 text-subtle" size={13} />
                              <span className="truncate text-text">{file.name}</span>
                            </span>
                            <span className="flex shrink-0 items-center gap-2 text-subtle">
                              <span>{formatBytes(file.size)}</span>
                              <button
                                aria-label={`Remove ${file.name}`}
                                className="rounded-full p-0.5 hover:bg-rose-100 hover:text-rose-600"
                                onClick={() => removeFile(signature)}
                                type="button"
                              >
                                <X size={13} />
                              </button>
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                  {overFileLimit ? (
                    <p className="text-xs text-rose-600">Over the {MAX_FILES}-file limit — remove some or use an enterprise import.</p>
                  ) : null}
                </section>

                {/* Step 2 — Choose destination */}
                <section className="space-y-2.5">
                  <div className="text-sm font-semibold text-text">Choose destination</div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <DestinationOption
                      active={destination === 'review'}
                      title="Review before adding"
                      description="Sort and confirm in Intake review first."
                      onClick={() => setDestination('review')}
                    />
                    <DestinationOption
                      active={destination === 'role'}
                      title="Add directly to a role"
                      description="Place these candidates straight into one role."
                      onClick={() => setDestination('role')}
                    />
                  </div>
                  {destination === 'role' ? (
                    <div className="space-y-1.5">
                      <Select onChange={(event) => setDefaultPosition(event.target.value)} value={defaultPosition}>
                        <option value="">Select a role…</option>
                        {positions.map((position) => (
                          <option key={position.position_code} value={position.position_code}>
                            {position.position_title || position.position_code}
                          </option>
                        ))}
                      </Select>
                      <p className="text-xs text-subtle">Candidates only enter ranking once they have a confirmed role.</p>
                    </div>
                  ) : null}
                </section>

                {/* Step 3 — Source */}
                <section className="space-y-2.5">
                  <div className="text-sm font-semibold text-text">Source</div>
                  <Select onChange={(event) => setSource(event.target.value)} value={source}>
                    {IMPORT_SOURCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </section>

                {/* Advanced — collapsed */}
                <section className="rounded-2xl border border-white/60 bg-white/35">
                  <button
                    className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-text"
                    onClick={() => setShowAdvanced((value) => !value)}
                    type="button"
                  >
                    Advanced options
                    {showAdvanced ? <ChevronUp size={16} className="text-subtle" /> : <ChevronDown size={16} className="text-subtle" />}
                  </button>
                  {showAdvanced ? (
                    <div className="space-y-2 border-t border-white/60 px-4 py-3">
                      <div className="text-xs font-medium text-text">Role mapping sheet (optional)</div>
                      <input
                        ref={metaInputRef}
                        accept={META_ACCEPT}
                        className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-panel-muted file:px-4 file:py-2 file:text-sm file:font-medium file:text-text hover:file:opacity-90"
                        onChange={(event) => setMetadataFile(event.target.files?.[0] || null)}
                        type="file"
                      />
                      <p className="text-xs leading-5 text-subtle">
                        Use this if you have a CSV/Excel file with candidate names, emails, or role codes. Clear role
                        matches are assigned automatically; the rest go to review.
                      </p>
                    </div>
                  ) : null}
                </section>

                <div className="flex justify-end gap-2 pt-1">
                  <Button onClick={closeModal} type="button" variant="secondary">Cancel</Button>
                  <Button disabled={uploading || !canSubmit} onClick={runImport} type="button">
                    {uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
                    {uploading
                      ? 'Importing…'
                      : !files.length
                        ? 'Choose files first'
                        : destination === 'role'
                          ? `Add ${files.length} to role`
                          : `Import ${files.length} to review`}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  )
}

function DestinationOption({
  active,
  title,
  description,
  onClick,
}: {
  active: boolean
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cnLocal(
        'flex items-start gap-2.5 rounded-2xl border px-3.5 py-3 text-left transition-colors',
        active ? 'border-ink bg-ink/[0.04]' : 'border-subtle/25 bg-white/40 hover:border-ink/30',
      )}
    >
      <span
        className={cnLocal(
          'mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border',
          active ? 'border-ink' : 'border-subtle/50',
        )}
      >
        {active ? <span className="h-2 w-2 rounded-full bg-ink" /> : null}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-text">{title}</span>
        <span className="block text-xs leading-5 text-subtle">{description}</span>
      </span>
    </button>
  )
}

// Local class merge to avoid coupling this component to the app-wide cn helper.
function cnLocal(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

const CONFIDENCE_LABELS: Record<string, string> = { high: 'High match', medium: 'Likely match', low: 'Low match', none: 'No role' }
const CONFIDENCE_TONES: Record<string, 'success' | 'warning' | 'muted'> = { high: 'success', medium: 'warning', low: 'muted', none: 'muted' }
const IMPORT_SOURCE_CHIPS: Record<string, string> = {
  bulk_upload: 'Upload',
  email: 'Email',
  email_inbound: 'Email',
  linkedin_export: 'LinkedIn',
  oracle_taleo_export: 'Taleo',
  workday_export: 'Workday',
  sap_successfactors_export: 'SuccessFactors',
  other_ats_export: 'ATS',
}

function groupTitle(group: ImportIntakeGroup): string {
  if (group.kind === 'unclear') return 'Needs a role'
  return group.role_title || group.role_code || 'Suggested role'
}

// Intake workspace: only the imports that still need a human decision, grouped by the
// role we inferred. Explicit-role imports auto-admit into Candidates and never appear here.
// HR confirms a whole group, assigns a different role, or archives noise — in bulk.
export function ImportReviewQueue({
  access,
  positions,
  reloadKey,
  onChanged,
}: {
  access: DashboardAccess
  positions: PositionSummary[]
  reloadKey: number
  onChanged: () => void
}) {
  const [groups, setGroups] = useState<ImportIntakeGroup[]>([])
  const [total, setTotal] = useState(0)
  const [autoAdmittedTotal, setAutoAdmittedTotal] = useState(0)
  const [collapsed, setCollapsed] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [assignDraft, setAssignDraft] = useState<Record<string, string>>({})
  const [busyGroup, setBusyGroup] = useState<string>('')
  const confirm = useConfirm()

  const positionTitleFor = (code: string) => positions.find((p) => p.position_code === code)?.position_title || code

  const refresh = useCallback(async () => {
    try {
      const response = await getImportIntake(access, 500)
      setGroups(response.groups)
      setTotal(response.total)
      setAutoAdmittedTotal(response.auto_admitted_total)
      setSelected((current) => {
        const live = new Set(response.groups.flatMap((g) => g.app_keys))
        return new Set([...current].filter((key) => live.has(key)))
      })
    } catch (err) {
      setError(friendlyImportError(err, 'We couldn’t load the intake queue right now. Please try again.'))
    } finally {
      setLoading(false)
    }
  }, [access])

  useEffect(() => {
    void refresh()
  }, [refresh, reloadKey])

  // Items the action applies to: the selected ones in a group, or all of them if none picked.
  function targetKeys(group: ImportIntakeGroup): string[] {
    const picked = group.app_keys.filter((key) => selected.has(key))
    return picked.length ? picked : group.app_keys
  }

  function toggleItem(appKey: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(appKey)) next.delete(appKey)
      else next.add(appKey)
      return next
    })
  }

  function toggleGroup(group: ImportIntakeGroup) {
    setSelected((current) => {
      const next = new Set(current)
      const allSelected = group.app_keys.every((key) => next.has(key))
      for (const key of group.app_keys) {
        if (allSelected) next.delete(key)
        else next.add(key)
      }
      return next
    })
  }

  async function runAction(group: ImportIntakeGroup, action: 'confirm' | 'assign' | 'archive') {
    const appKeys = targetKeys(group)
    if (!appKeys.length) return
    const body: { action: 'confirm' | 'assign' | 'archive'; app_keys: string[]; position_code?: string; position_title?: string } = {
      action,
      app_keys: appKeys,
    }
    if (action === 'assign') {
      const code = assignDraft[group.key]
      if (!code) {
        setSuccess('')
        setError('Pick a role to assign before confirming this group.')
        return
      }
      body.position_code = code
      body.position_title = positionTitleFor(code)
    }
    const n = appKeys.length
    const noun = `${n} candidate${n === 1 ? '' : 's'}`
    const prompt =
      action === 'archive'
        ? { title: 'Archive these imports?', body: `${noun} will be archived and removed from review. This is hard to undo.`, confirmLabel: 'Archive', destructive: true }
        : action === 'assign'
          ? { title: 'Assign this group?', body: `${noun} will be assigned to ${body.position_title || 'the selected role'} and added to your pipeline.`, confirmLabel: 'Assign' }
          : { title: 'Confirm this group?', body: `${noun} will be added to your pipeline with their detected role.`, confirmLabel: 'Confirm group' }
    if (!(await confirm(prompt))) return
    setBusyGroup(`${group.key}:${action}`)
    setError('')
    setSuccess('')
    try {
      const res = await bulkImportAction(access, body)
      await refresh()
      onChanged()
      const parts: string[] = []
      if (res.promoted) parts.push(`${res.promoted} added to your pipeline`)
      if (res.updated) parts.push(`${res.updated} updated`)
      if (res.archived) parts.push(`${res.archived} archived`)
      if (res.skipped) parts.push(`${res.skipped} skipped`)
      setSuccess(parts.length ? `Done · ${parts.join(' · ')}.` : 'Done.')
    } catch (err) {
      setSuccess('')
      setError(friendlyImportError(err, 'We couldn’t update these candidates right now. Please try again.'))
    } finally {
      setBusyGroup('')
    }
  }

  if (loading && !groups.length && !error) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-subtle">
          <Loader2 className="animate-spin" size={16} /> Loading candidates to review…
        </CardContent>
      </Card>
    )
  }

  if (!groups.length && !error) {
    // Nothing to review — but if explicit imports were auto-admitted, reassure HR quietly.
    if (!autoAdmittedTotal) return null
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-subtle">
          <CheckCircle2 className="text-emerald-600" size={16} />
          {autoAdmittedTotal} imported candidate{autoAdmittedTotal === 1 ? '' : 's'} with a clear declared role
          {autoAdmittedTotal === 1 ? ' was' : ' were'} added straight to Candidates. Nothing needs review.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              Intake review
              {total ? <Badge tone="warning">{total}</Badge> : null}
            </CardTitle>
            <CardDescription>
              Imports we could not place with certainty. Confirm a group, assign a different role, or archive noise.
              {autoAdmittedTotal ? ` ${autoAdmittedTotal} with a clear role went straight to Candidates.` : ''}
            </CardDescription>
          </div>
          {groups.length ? (
            <Button onClick={() => setCollapsed((value) => !value)} size="sm" type="button" variant="ghost">
              {collapsed ? 'Show' : 'Hide'}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      {!collapsed ? (
        <CardContent className="space-y-3">
          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-200/70 bg-rose-50/70 px-4 py-2.5 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 shrink-0" size={16} /> <span>{error}</span>
            </div>
          ) : null}
          {success ? (
            <div className="flex items-start gap-2 rounded-2xl border border-emerald-200/70 bg-emerald-50/70 px-4 py-2.5 text-sm text-emerald-800">
              <CheckCircle2 className="mt-0.5 shrink-0" size={16} /> <span>{success}</span>
            </div>
          ) : null}
          {groups.map((group) => {
            const allSelected = group.app_keys.every((key) => selected.has(key))
            const selectedCount = group.app_keys.filter((key) => selected.has(key)).length
            const actionCount = selectedCount || group.count
            const canConfirm = Boolean(group.role_code)
            return (
              <div key={group.key} className="rounded-2xl border border-white/70 bg-white/55">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/60 px-3 py-2.5">
                  <label className="flex min-w-0 items-center gap-2">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={() => toggleGroup(group)}
                      className="h-4 w-4 rounded border-subtle/40 accent-ink"
                    />
                    <span className="truncate text-sm font-semibold text-text">{groupTitle(group)}</span>
                    <Badge tone={CONFIDENCE_TONES[group.confidence]}>{CONFIDENCE_LABELS[group.confidence]}</Badge>
                    <span className="text-xs text-subtle">{group.count}</span>
                  </label>
                  <div className="flex flex-wrap items-center gap-2">
                    {canConfirm ? (
                      <Button
                        disabled={busyGroup.startsWith(`${group.key}:`)}
                        onClick={() => void runAction(group, 'confirm')}
                        size="sm"
                        type="button"
                      >
                        {busyGroup === `${group.key}:confirm` ? <Loader2 className="animate-spin" size={14} /> : <CheckCheck size={14} />}
                        Confirm {actionCount} as {groupTitle(group)}
                      </Button>
                    ) : null}
                    <Select
                      className="w-40"
                      onChange={(event) => setAssignDraft((current) => ({ ...current, [group.key]: event.target.value }))}
                      value={assignDraft[group.key] ?? ''}
                    >
                      <option value="">Assign role…</option>
                      {positions.map((position) => (
                        <option key={position.position_code} value={position.position_code}>
                          {position.position_title || position.position_code}
                        </option>
                      ))}
                    </Select>
                    <Button
                      disabled={!assignDraft[group.key] || busyGroup.startsWith(`${group.key}:`)}
                      onClick={() => void runAction(group, 'assign')}
                      size="sm"
                      type="button"
                      variant="secondary"
                    >
                      {busyGroup === `${group.key}:assign` ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                      Assign
                    </Button>
                    <Button
                      disabled={busyGroup.startsWith(`${group.key}:`)}
                      onClick={() => void runAction(group, 'archive')}
                      size="sm"
                      type="button"
                      variant="ghost"
                    >
                      {busyGroup === `${group.key}:archive` ? <Loader2 className="animate-spin" size={14} /> : <Archive size={14} />}
                      Archive
                    </Button>
                  </div>
                </div>
                <div className="divide-y divide-white/50">
                  {group.items.map((item) => (
                    <label key={item.app_key} className="flex cursor-pointer items-center gap-2.5 px-3 py-2 hover:bg-white/40">
                      <input
                        type="checkbox"
                        checked={selected.has(item.app_key)}
                        onChange={() => toggleItem(item.app_key)}
                        className="h-4 w-4 rounded border-subtle/40 accent-ink"
                      />
                      <FileText className="shrink-0 text-subtle" size={15} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-text">
                          {item.candidate_name || item.original_filename || item.app_key}
                        </span>
                        <span className="block truncate text-xs text-subtle">
                          {[item.candidate_email, item.original_filename].filter(Boolean).join(' · ') || 'Imported CV'}
                          {item.suggestion_source && group.kind === 'suggested'
                            ? ` · ${SUGGESTION_SOURCE_LABELS[item.suggestion_source] || 'from your file'}`
                            : ''}
                        </span>
                      </span>
                      {item.import_source ? (
                        <span className="shrink-0 rounded-full bg-panel-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-subtle">
                          {IMPORT_SOURCE_CHIPS[item.import_source] || item.import_source}
                        </span>
                      ) : null}
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </CardContent>
      ) : null}
    </Card>
  )
}
