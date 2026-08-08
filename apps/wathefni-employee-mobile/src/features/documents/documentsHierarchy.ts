/**
 * Documents surface hierarchy over the existing compliance journey + file registry.
 *
 * Attention / Current / History are presentation sections — they do not invent
 * review status, renew authority, or OCR. A file that is already the current
 * version of a compliance type is not also listed under History.
 */
import type { ComplianceJourneyItem, EmployeeDocument } from '@/api/types'

const ATTENTION_STATUSES = new Set([
  'missing',
  'expired',
  'expiring_soon',
  'rejected_reupload',
  'pending_hr_review',
  'replacement_required',
])

export type DocumentHistoryEntry = {
  id: string
  /** Human label the API supplied, when it supplied one. Never a backend key. */
  label: string | null
  /** Backend document-type key. For i18n lookup only — the view never prints it. */
  documentType: string | null
  date: string | null
  fileId: string | null
  reviewStatus?: string
  source: 'version' | 'registry'
}

export type DocumentHistoryYear = {
  /** Calendar year, or null for entries the backend stored without a usable date. */
  year: number | null
  entries: DocumentHistoryEntry[]
}

export type DocumentsHierarchy = {
  attention: ComplianceJourneyItem[]
  current: ComplianceJourneyItem[]
  history: DocumentHistoryEntry[]
  /** True when the compliance journey returned no items but registry files exist. */
  complianceUnavailable: boolean
}

export function documentsHierarchy(
  compliance: ComplianceJourneyItem[] | null | undefined,
  documents: EmployeeDocument[] | null | undefined,
): DocumentsHierarchy {
  const journey = compliance ?? []
  const registry = documents ?? []
  const currentFileIds = new Set<string>()
  for (const item of journey) {
    if (item.current_file_id) currentFileIds.add(item.current_file_id)
    if (item.pending_version_id) {
      // pending versions are still "current attempt" — don't also dump as history
      // unless they appear as a non-current version row below.
    }
    for (const version of item.versions ?? []) {
      if (version.is_current && version.file_id) currentFileIds.add(version.file_id)
    }
  }

  const attention: ComplianceJourneyItem[] = []
  const current: ComplianceJourneyItem[] = []
  for (const item of journey) {
    const needsAttention =
      Boolean(item.renewal_required) ||
      ATTENTION_STATUSES.has(String(item.review_status || '').toLowerCase()) ||
      Boolean(item.rejection_reason)
    if (needsAttention) attention.push(item)
    else current.push(item)
  }

  const history: DocumentHistoryEntry[] = []
  const seen = new Set<string>()

  for (const item of journey) {
    for (const version of item.versions ?? []) {
      if (version.is_current) continue
      const fileId = version.file_id || null
      const id = `version:${version.version_id}`
      if (seen.has(id)) continue
      if (fileId && currentFileIds.has(fileId)) continue
      seen.add(id)
      if (fileId) seen.add(`file:${fileId}`)
      history.push({
        id,
        label: item.label || null,
        documentType: item.document_type || null,
        date: version.expiry_date || null,
        fileId,
        reviewStatus: version.review_status,
        source: 'version',
      })
    }
  }

  for (const doc of registry) {
    const fileId = doc.file_id
    if (!fileId || currentFileIds.has(fileId) || seen.has(`file:${fileId}`)) continue
    seen.add(`file:${fileId}`)
    // Deliberately no filename / file-id fallback: an employee must never be
    // shown a storage key where a document name belongs. The view resolves an
    // i18n name from `documentType`, or a generic label.
    history.push({
      id: `registry:${fileId}`,
      label: doc.label || null,
      documentType: doc.document_type || null,
      date: doc.stored_at || null,
      fileId: doc.has_file ? fileId : null,
      source: 'registry',
    })
  }

  return {
    attention,
    current,
    history,
    complianceUnavailable: journey.length === 0 && registry.length > 0,
  }
}

/**
 * Bucket superseded documents by calendar year, newest first.
 *
 * A long-tenure employee accumulates renewals indefinitely — civil ID, passport,
 * residence, work permit, every year. Laying all of them out flat means the
 * Documents screen grows without bound and buries the two sections that matter.
 * Grouping lets the view render one year and leave the rest collapsed.
 *
 * Entries whose date the backend never stored sort last under a null year rather
 * than being dropped or guessed into the current one.
 */
export function groupHistoryByYear(entries: DocumentHistoryEntry[]): DocumentHistoryYear[] {
  const buckets = new Map<number | null, DocumentHistoryEntry[]>()
  for (const entry of entries) {
    const year = parseYear(entry.date)
    const bucket = buckets.get(year)
    if (bucket) bucket.push(entry)
    else buckets.set(year, [entry])
  }
  return [...buckets.entries()]
    .map(([year, group]) => ({
      year,
      entries: group.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))),
    }))
    .sort((a, b) => {
      if (a.year === b.year) return 0
      if (a.year == null) return 1
      if (b.year == null) return -1
      return b.year - a.year
    })
}

function parseYear(value: string | null): number | null {
  if (!value) return null
  const match = /^(\d{4})/.exec(String(value).trim())
  if (match) return Number(match[1])
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.getFullYear()
}
