/**
 * Loads compliance journey OCR for one document type and renders DocumentExtractionSummary.
 */
import { useEffect, useState } from 'react'

import { getEmployeeComplianceJourney } from '@/lib/api'
import type { DashboardAccess } from '@/types'
import {
  DocumentExtractionSummary,
  type OcrProposal,
  type VerifiedDocumentFields,
} from '@/posthire/DocumentExtractionSummary'

function matchesDocType(rowType: string, wanted: string): boolean {
  const a = String(rowType || '').trim().toLowerCase()
  const b = String(wanted || '').trim().toLowerCase()
  if (!a || !b) return false
  if (a === b) return true
  // Disposable canary lanes validate as their alias target but store isolated types.
  if (a.startsWith('docs_qual_') && (a === `docs_qual_${b}` || a.endsWith(`_${b}`))) return true
  if (b.startsWith('docs_qual_') && (b === `docs_qual_${a}` || b.endsWith(`_${a}`))) return true
  if (a === 'civil_id_dual_side_canary' && b === 'civil_id') return true
  if (b === 'civil_id_dual_side_canary' && a === 'civil_id') return true
  return false
}

export function DocumentExtractionSummaryLoader({
  access,
  employeeKey,
  documentType,
  locale = 'en',
  canRevealSensitive = false,
  className,
}: {
  access: DashboardAccess
  employeeKey: string
  documentType: string
  locale?: 'en' | 'ar'
  canRevealSensitive?: boolean
  className?: string
}) {
  const isAr = locale === 'ar'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [ocr, setOcr] = useState<OcrProposal | null>(null)
  const [verified, setVerified] = useState<VerifiedDocumentFields | null>(null)
  const [authoritative, setAuthoritative] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    void getEmployeeComplianceJourney(access, employeeKey)
      .then((res) => {
        if (cancelled) return
        const docs = Array.isArray(res?.documents) ? res.documents : []
        const hit =
          docs.find((d) => matchesDocType(String(d.document_type || ''), documentType)) ||
          docs.find((d) =>
            matchesDocType(String((d as { legacy_document_type?: string }).legacy_document_type || ''), documentType),
          )
        const proposal = (hit?.ocr_proposal || null) as OcrProposal | null
        setOcr(proposal)
        setAuthoritative(Boolean(hit?.ocr_authoritative))
        const vf = (hit as { verified_fields?: VerifiedDocumentFields | null } | undefined)?.verified_fields
        if (vf && typeof vf === 'object') {
          setVerified({
            document_number: vf.document_number ?? null,
            issue_date: vf.issue_date ?? null,
            expiry_date: vf.expiry_date ?? null,
            review_status: vf.review_status ?? hit?.review_status_label ?? hit?.review_status ?? null,
          })
        } else {
          setVerified({
            document_number: null,
            issue_date: null,
            expiry_date: null,
            review_status: hit?.review_status_label || hit?.review_status || null,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [access, employeeKey, documentType])

  if (loading) {
    return (
      <div className={className} data-document-extraction-summary="loading">
        <p className="text-[12px] text-subtle/80">{isAr ? 'جارٍ تحميل ملخص الاستخراج…' : 'Loading extraction summary…'}</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className={className} data-document-extraction-summary="error">
        <p className="text-[12px] text-rose-700">
          {isAr ? 'تعذر تحميل ملخص الاستخراج.' : 'Could not load extraction summary.'}
        </p>
      </div>
    )
  }

  return (
    <DocumentExtractionSummary
      ocrProposal={ocr}
      verified={verified}
      ocrAuthoritative={authoritative}
      locale={locale}
      canRevealSensitive={canRevealSensitive}
      className={className}
    />
  )
}
