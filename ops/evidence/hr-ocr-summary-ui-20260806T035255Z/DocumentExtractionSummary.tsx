/**
 * Shared HR extraction / validation summary for employee-upload documents.
 * Renders useful role-appropriate fields only — never raw OCR JSON.
 * Extracted values are proposals; they never auto-overwrite canonical employee data.
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type IdentityCheck = {
  status?: string | null
  match?: boolean | null
  reason?: string | null
  expected_name?: string | null
  document_name?: string | null
  token_score?: number | null
  sequence_score?: number | null
}

export type OcrProposal = {
  document_type?: string | null
  side?: string | null
  full_name?: string | null
  full_name_en?: string | null
  full_name_ar?: string | null
  name?: string | null
  nationality?: string | null
  date_of_birth?: string | null
  issue_date?: string | null
  issued_date?: string | null
  expiry_date?: string | null
  employer_or_sponsor?: string | null
  document_number?: string | null
  confidence?: number | null
  extraction_status?: string | null
  authoritative?: boolean | null
  hr_review_recommended?: boolean | null
  hr_warnings?: Array<string | { code?: string; message?: string; message_en?: string; message_ar?: string }> | null
  identity_check?: IdentityCheck | null
  parts_schema?: string | null
  pair_validated_at?: string | null
  parts?: {
    front?: OcrProposal | Record<string, unknown> | null
    back?: OcrProposal | Record<string, unknown> | null
  } | null
}

export type VerifiedDocumentFields = {
  document_number?: string | null
  issue_date?: string | null
  expiry_date?: string | null
  review_status?: string | null
}

function asText(value: unknown): string | null {
  if (value == null) return null
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  const s = String(value).trim()
  return s || null
}

function pickName(ocr: OcrProposal | null | undefined, isAr: boolean): string | null {
  if (!ocr) return null
  if (isAr) return asText(ocr.full_name_ar) || asText(ocr.full_name) || asText(ocr.name) || asText(ocr.full_name_en)
  return asText(ocr.full_name_en) || asText(ocr.full_name) || asText(ocr.name) || asText(ocr.full_name_ar)
}

export function maskDocumentNumber(value: string | null | undefined): string {
  const raw = asText(value)
  if (!raw) return '—'
  const compact = raw.replace(/\s+/g, '')
  if (compact.length <= 4) return '••••'
  return `${'•'.repeat(Math.min(8, Math.max(4, compact.length - 4)))}${compact.slice(-4)}`
}

function warningText(
  w: string | { code?: string; message?: string; message_en?: string; message_ar?: string },
  isAr: boolean,
): string {
  if (typeof w === 'string') return w
  if (isAr) return asText(w.message_ar) || asText(w.message) || asText(w.message_en) || asText(w.code) || '—'
  return asText(w.message_en) || asText(w.message) || asText(w.message_ar) || asText(w.code) || '—'
}

function identityLabel(check: IdentityCheck | null | undefined, isAr: boolean): { label: string; tone: 'success' | 'warning' | 'danger' | 'muted' } {
  const status = String(check?.status || '').toLowerCase()
  if (check?.match === true || status === 'matched') {
    return { label: isAr ? 'الاسم متطابق' : 'Name matched', tone: 'success' }
  }
  if (status === 'mismatch') {
    return { label: isAr ? 'الاسم غير متطابق' : 'Name mismatch', tone: 'danger' }
  }
  if (!check) {
    return { label: isAr ? 'غير مطبّق' : 'Not applicable', tone: 'muted' }
  }
  return { label: isAr ? 'غير مؤكد' : 'Unverified', tone: 'warning' }
}

function FieldRow({
  label,
  value,
  mono,
  proposal,
}: {
  label: string
  value: string | null
  mono?: boolean
  proposal?: boolean
}) {
  if (!value) return null
  return (
    <div className="grid grid-cols-[minmax(7rem,9.5rem)_1fr] gap-x-3 gap-y-0.5 text-[12.5px]">
      <dt className="text-subtle/85">{label}</dt>
      <dd className={cn('text-text', mono && 'font-mono tracking-wide', proposal && 'text-ink')}>{value}</dd>
    </div>
  )
}

function PartSummary({
  title,
  ocr,
  isAr,
  canReveal,
  revealed,
  onReveal,
}: {
  title: string
  ocr: OcrProposal | null
  isAr: boolean
  canReveal: boolean
  revealed: boolean
  onReveal: () => void
}) {
  if (!ocr || Object.keys(ocr).length === 0) {
    return (
      <div className="rounded-[0.85rem] border border-dashed border-line/60 bg-white/50 px-3 py-2 text-[12px] text-subtle/80">
        {title}: {isAr ? 'لا استخراج بعد' : 'No extraction yet'}
      </div>
    )
  }
  const number = asText(ocr.document_number)
  return (
    <div className="rounded-[0.85rem] border border-line/55 bg-white/70 px-3 py-2.5 space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle/80">{title}</p>
      <dl className="space-y-1">
        <FieldRow label={isAr ? 'الاسم' : 'Name'} value={pickName(ocr, isAr)} proposal />
        <FieldRow label={isAr ? 'الجنسية' : 'Nationality'} value={asText(ocr.nationality)} proposal />
        <FieldRow label={isAr ? 'تاريخ الميلاد' : 'Date of birth'} value={asText(ocr.date_of_birth)} proposal />
        <FieldRow
          label={isAr ? 'رقم المستند' : 'Document number'}
          value={number ? (revealed ? number : maskDocumentNumber(number)) : null}
          mono
          proposal
        />
        {number && canReveal && !revealed ? (
          <div className="ps-[9.5rem]">
            <button type="button" className="text-[11.5px] font-medium text-wf-ink underline-offset-2 hover:underline" onClick={onReveal}>
              {isAr ? 'إظهار الرقم (مصرّح)' : 'Reveal number (authorized)'}
            </button>
          </div>
        ) : null}
        <FieldRow label={isAr ? 'الجانب' : 'Side'} value={asText(ocr.side)} proposal />
      </dl>
    </div>
  )
}

export function DocumentExtractionSummary({
  ocrProposal,
  verified,
  ocrAuthoritative = false,
  locale = 'en',
  canRevealSensitive = false,
  className,
  emptyLabel,
}: {
  ocrProposal?: OcrProposal | Record<string, unknown> | null
  verified?: VerifiedDocumentFields | null
  ocrAuthoritative?: boolean
  locale?: 'en' | 'ar'
  /** Session reveal for document numbers — requires manage/unmask permission at call site. */
  canRevealSensitive?: boolean
  className?: string
  emptyLabel?: string
}) {
  const isAr = locale === 'ar'
  const [revealed, setRevealed] = useState(false)
  const ocr = (ocrProposal && typeof ocrProposal === 'object' ? ocrProposal : null) as OcrProposal | null

  const hasParts = Boolean(ocr?.parts && (ocr.parts.front || ocr.parts.back))
  const warnings = Array.isArray(ocr?.hr_warnings) ? ocr!.hr_warnings! : []
  const identity = identityLabel(ocr?.identity_check, isAr)

  const extractedName = pickName(ocr, isAr)
  const docType = asText(ocr?.document_type)
  const nationality = asText(ocr?.nationality)
  const dob = asText(ocr?.date_of_birth)
  const issue = asText(ocr?.issue_date) || asText(ocr?.issued_date)
  const expiry = asText(ocr?.expiry_date)
  const employer = asText(ocr?.employer_or_sponsor)
  const number = asText(ocr?.document_number)
  const status = asText(ocr?.extraction_status)
  const confidence =
    typeof ocr?.confidence === 'number' && Number.isFinite(ocr.confidence)
      ? `${Math.round(Math.max(0, Math.min(1, ocr.confidence)) * 100)}%`
      : null

  const verifiedIssue = asText(verified?.issue_date)
  const verifiedExpiry = asText(verified?.expiry_date)
  const verifiedNumber = asText(verified?.document_number)
  const hasVerified = Boolean(verifiedIssue || verifiedExpiry || verifiedNumber)
  const hasExtracted = Boolean(
    ocr &&
      (extractedName ||
        docType ||
        nationality ||
        dob ||
        issue ||
        expiry ||
        employer ||
        number ||
        status ||
        confidence ||
        hasParts ||
        warnings.length ||
        ocr.identity_check),
  )

  const pairStatus = useMemo(() => {
    if (!hasParts) return null
    if (ocr?.pair_validated_at) {
      return {
        tone: ocr.hr_review_recommended ? ('warning' as const) : ('success' as const),
        label: isAr ? 'الزوج مكتمل' : 'Pair complete',
      }
    }
    return { tone: 'warning' as const, label: isAr ? 'الزوج قيد المراجعة' : 'Pair under review' }
  }, [hasParts, ocr?.pair_validated_at, ocr?.hr_review_recommended, isAr])

  if (!hasExtracted && !hasVerified) {
    return (
      <div
        className={cn('rounded-[0.95rem] border border-dashed border-line/55 bg-[#fffdf8] px-3.5 py-3 text-[12.5px] text-subtle/85', className)}
        data-document-extraction-summary="empty"
      >
        {emptyLabel || (isAr ? 'لا ملخص استخراج محفوظ لهذا المستند بعد.' : 'No stored extraction summary for this document yet.')}
      </div>
    )
  }

  return (
    <section
      className={cn('space-y-3 rounded-[0.95rem] border border-line/55 bg-[#fffdf8] px-3.5 py-3', className)}
      data-document-extraction-summary="ready"
      dir={isAr ? 'rtl' : 'ltr'}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[12px] font-semibold text-ink">
          {isAr ? 'ملخص الاستخراج والمراجعة' : 'Extraction & validation summary'}
        </p>
        <Badge tone="warning">{isAr ? 'مستخرج — غير معتمد تلقائياً' : 'Extracted — not auto-verified'}</Badge>
        {ocrAuthoritative || ocr?.authoritative ? (
          <Badge tone="danger">{isAr ? 'تحذير: وُسم كمعتمد' : 'Warning: marked authoritative'}</Badge>
        ) : null}
      </div>
      <p className="text-[11.5px] leading-relaxed text-subtle/85">
        {isAr
          ? 'هذه قيم مقترحة من الملف المرفوع. لا تُستبدل بيانات الموظف الأساسية تلقائياً. الاعتماد يتم فقط بمراجعة موارد بشرية صريحة.'
          : 'These are proposals from the uploaded file. They never overwrite canonical employee data automatically. Only explicit HR review confirms evidence.'}
      </p>

      {hasExtracted ? (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle/80">
            {isAr ? 'قيم مستخرجة (اقتراح)' : 'Extracted values (proposal)'}
          </p>
          <dl className="space-y-1">
            <FieldRow label={isAr ? 'نوع المستند' : 'Document type'} value={docType} proposal />
            <FieldRow label={isAr ? 'الاسم المستخرج' : 'Extracted name'} value={extractedName} proposal />
            <FieldRow label={isAr ? 'الجنسية' : 'Nationality'} value={nationality} proposal />
            <FieldRow label={isAr ? 'تاريخ الميلاد' : 'Date of birth'} value={dob} proposal />
            <FieldRow label={isAr ? 'تاريخ الإصدار' : 'Issue date'} value={issue} proposal />
            <FieldRow label={isAr ? 'تاريخ الانتهاء' : 'Expiry date'} value={expiry} proposal />
            <FieldRow label={isAr ? 'جهة العمل / الكفيل' : 'Employer / sponsor'} value={employer} proposal />
            <FieldRow
              label={isAr ? 'رقم المستند' : 'Document number'}
              value={number ? (revealed && canRevealSensitive ? number : maskDocumentNumber(number)) : null}
              mono
              proposal
            />
            {number && canRevealSensitive && !revealed ? (
              <div className="ps-[9.5rem]">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-auto px-0 py-0 text-[11.5px] font-medium text-wf-ink"
                  onClick={() => setRevealed(true)}
                >
                  {isAr ? 'إظهار الرقم (مصرّح)' : 'Reveal number (authorized)'}
                </Button>
              </div>
            ) : null}
            <FieldRow label={isAr ? 'حالة الاستخراج' : 'Extraction status'} value={status} proposal />
            <FieldRow label={isAr ? 'الثقة' : 'Confidence'} value={confidence} proposal />
          </dl>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-[12px] text-subtle/85">{isAr ? 'مطابقة الهوية' : 'Identity match'}</span>
            <Badge tone={identity.tone}>{identity.label}</Badge>
            {ocr?.identity_check?.reason ? (
              <span className="text-[11.5px] text-subtle/80">{String(ocr.identity_check.reason)}</span>
            ) : null}
          </div>

          {warnings.length ? (
            <ul className="space-y-1 rounded-[0.75rem] border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-[12px] text-amber-950">
              {warnings.map((w, idx) => (
                <li key={idx}>• {warningText(w, isAr)}</li>
              ))}
            </ul>
          ) : null}

          {hasParts ? (
            <div className="space-y-2 pt-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle/80">
                  {isAr ? 'البطاقة المدنية — الوجهان' : 'Civil ID — both sides'}
                </p>
                {pairStatus ? <Badge tone={pairStatus.tone}>{pairStatus.label}</Badge> : null}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <PartSummary
                  title={isAr ? 'الأمامي' : 'Front'}
                  ocr={(ocr?.parts?.front || null) as OcrProposal | null}
                  isAr={isAr}
                  canReveal={canRevealSensitive}
                  revealed={revealed}
                  onReveal={() => setRevealed(true)}
                />
                <PartSummary
                  title={isAr ? 'الخلفي' : 'Back'}
                  ocr={(ocr?.parts?.back || null) as OcrProposal | null}
                  isAr={isAr}
                  canReveal={canRevealSensitive}
                  revealed={revealed}
                  onReveal={() => setRevealed(true)}
                />
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasVerified ? (
        <div className="space-y-2 border-t border-line/50 pt-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle/80">
            {isAr ? 'قيم معتمدة / محفوظة بعد المراجعة' : 'Verified / HR-saved values'}
          </p>
          <dl className="space-y-1">
            <FieldRow
              label={isAr ? 'رقم المستند' : 'Document number'}
              value={
                verifiedNumber
                  ? revealed && canRevealSensitive
                    ? verifiedNumber
                    : maskDocumentNumber(verifiedNumber)
                  : null
              }
              mono
            />
            <FieldRow label={isAr ? 'تاريخ الإصدار' : 'Issue date'} value={verifiedIssue} />
            <FieldRow label={isAr ? 'تاريخ الانتهاء' : 'Expiry date'} value={verifiedExpiry} />
            <FieldRow label={isAr ? 'حالة المراجعة' : 'Review status'} value={asText(verified?.review_status)} />
          </dl>
        </div>
      ) : (
        <p className="border-t border-line/50 pt-3 text-[11.5px] text-subtle/80">
          {isAr
            ? 'لا قيم معتمدة بعد — التواريخ/الرقم أعلاه اقتراحات فقط حتى تُراجع أو تُصحَّح.'
            : 'No verified values yet — dates/number above are proposals until HR reviews or corrects them.'}
        </p>
      )}
    </section>
  )
}
