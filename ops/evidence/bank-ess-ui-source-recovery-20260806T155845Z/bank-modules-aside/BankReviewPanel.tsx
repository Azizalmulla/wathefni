import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, History, Loader2, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill } from '@/components/ui/page-chrome'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import {
  applyEmployeeEssRequest,
  DashboardApiError,
  decideEmployeeEssRequest,
  getEmployeeBankReview,
  openBankEvidence,
} from '@/lib/api'
import { qk } from '@/lib/query/keys'
import type { BankEvidenceRow, BankReviewResponse, DashboardAccess } from '@/types'

import { bankFieldLabel, bankReadableFields, bankStateLabel, bankStateTone } from './bankReview'
import { ConflictBanner, useEmployees360Locale, WorkflowEmpty } from './chrome'

function isBankUnavailable(err: unknown): boolean {
  if (!(err instanceof DashboardApiError)) return false
  return err.code === 'bank_ess_disabled' || err.code === 'ess_v5_disabled' || err.status === 404
}

/**
 * HR review surface for employee-submitted bank details. Employee input is a
 * change request: nothing here mutates verified or payroll-effective values
 * until an HR decision is recorded, and applying it is a separate step.
 */
export function BankReviewPanel({
  access,
  employeeKey,
  canDecide,
  onAccessIssue,
  onDecided,
}: {
  access: DashboardAccess
  employeeKey: string
  /** Approve/reject/apply are hidden without the ESS HR approval permission. */
  canDecide: boolean
  onAccessIssue: (issue: AccessIssue) => void
  /** A bank decision moves the onboarding bank item, so the host refetches. */
  onDecided?: () => void
}) {
  const locale = useEmployees360Locale()
  const isAr = locale === 'ar'
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState<'approve' | 'reject' | 'apply' | null>(null)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [conflict, setConflict] = useState<string | null>(null)
  const [openingEvidence, setOpeningEvidence] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const bankKey = useMemo(
    () => qk.employeeBankReview(access, employeeKey, locale),
    [access, employeeKey, locale],
  )
  const reviewQuery = useQuery({
    queryKey: bankKey,
    queryFn: () => getEmployeeBankReview(access, employeeKey, locale),
    retry: false,
  })
  const data = reviewQuery.data ?? null
  const unavailable = isBankUnavailable(reviewQuery.error)
  const loading = reviewQuery.isPending && !data
  const load = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: bankKey })
  }, [bankKey, queryClient])

  useEffect(() => {
    if (!reviewQuery.error || unavailable) return
    const issue = accessIssueFromError(reviewQuery.error)
    if (issue) onAccessIssue(issue)
  }, [onAccessIssue, reviewQuery.error, unavailable])

  const submission = data?.submission || null
  const submissionState = String(data?.submission_state || 'none')
  const comparison = data?.comparison
  const changed = useMemo(() => new Set(comparison?.changed_fields || []), [comparison])
  const awaitingReview = submissionState === 'pending_review'
  const approvedNotApplied = submissionState === 'approved' && String(submission?.state || '') === 'approved'
  const evidence = submission?.evidence || []
  const payrollLocked = Boolean(data?.payroll_lock?.locked)

  const decide = useCallback(
    async (action: 'approve' | 'reject') => {
      if (!submission?.request_id) return
      if (action === 'reject' && !reason.trim()) {
        setNotice(isAr ? 'سبب الرفض مطلوب.' : 'A reason is required to reject.')
        return
      }
      setBusy(action)
      setNotice(null)
      setConflict(null)
      try {
        await decideEmployeeEssRequest(access, submission.request_id, {
          action,
          comment: action === 'reject' ? reason.trim() : undefined,
        })
        setReason('')
        setRejectOpen(false)
        setNotice(
          action === 'approve'
            ? isAr
              ? 'تمت الموافقة. طبّق التغيير ليصبح ساري المفعول للرواتب.'
              : 'Approved. Apply the change to make it payroll-effective.'
            : isAr
              ? 'أُعيد الطلب للموظف مع السبب.'
              : 'Returned to the employee with your reason.',
        )
        await load()
        onDecided?.()
      } catch (err) {
        const code = err instanceof DashboardApiError ? err.code : ''
        const status = err instanceof DashboardApiError ? err.status : 0
        if (code === 'stale_concurrency_version' || status === 409) {
          setConflict(
            isAr
              ? 'راجع شخص آخر هذا الطلب للتو. تم تحديث العرض.'
              : 'Someone else reviewed this request. The view has been refreshed.',
          )
          await load()
          return
        }
        if (code === 'decision_reason_required') {
          setNotice(isAr ? 'سبب الرفض مطلوب.' : 'A reason is required to reject.')
          return
        }
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue(issue)
        else setNotice(err instanceof Error ? err.message : isAr ? 'تعذّر تنفيذ الإجراء.' : 'Could not complete that action.')
      } finally {
        setBusy(null)
      }
    },
    [access, isAr, load, onAccessIssue, onDecided, reason, submission],
  )

  const apply = useCallback(async () => {
    if (!submission?.request_id) return
    setBusy('apply')
    setNotice(null)
    try {
      await applyEmployeeEssRequest(access, submission.request_id, {
        // Stable key so a retry after a network error cannot double-apply.
        idempotency_key: `apply-${submission.request_id}`,
      })
      setNotice(isAr ? 'أصبح التغيير ساري المفعول للرواتب.' : 'The change is now payroll-effective.')
      await load()
      onDecided?.()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) onAccessIssue(issue)
      else setNotice(isAr ? 'تعذّر تطبيق التغيير.' : 'Could not apply the change.')
    } finally {
      setBusy(null)
    }
  }, [access, isAr, load, onAccessIssue, onDecided, submission])

  const openEvidence = useCallback(
    async (row: BankEvidenceRow) => {
      setOpeningEvidence(row.evidence_id)
      try {
        await openBankEvidence(access, employeeKey, row)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) onAccessIssue(issue)
        else setNotice(isAr ? 'تعذّر فتح المستند.' : 'Could not open this document.')
      } finally {
        setOpeningEvidence(null)
      }
    },
    [access, employeeKey, isAr, onAccessIssue],
  )

  if (unavailable) return null

  if (loading && !data) {
    return (
      <Card tone="board" className="p-5" data-testid="bank-review-loading">
        <CardContent className="flex items-center gap-2 text-[13px] text-subtle">
          <Loader2 className="h-4 w-4 animate-spin" />
          {isAr ? 'جارٍ التحميل…' : 'Loading…'}
        </CardContent>
      </Card>
    )
  }

  const verifiedFields = bankReadableFields(comparison?.current_verified || data?.verified?.display)
  const proposedFields = bankReadableFields(comparison?.proposed || submission?.proposed?.display)

  return (
    <Card tone="board" className="p-5" data-testid="bank-review" dir={isAr ? 'rtl' : 'ltr'}>
      <CardHeader className="mb-3 border-0 pb-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-[15px]">{isAr ? 'البيانات البنكية' : 'Bank details'}</CardTitle>
          <StatusPill tone={bankStateTone(submissionState)}>{bankStateLabel(submissionState, isAr)}</StatusPill>
        </div>
        <CardDescription>
          {data?.next_step?.message ||
            (isAr
              ? 'مقنّعة افتراضياً — الكشف يتطلب صلاحية ويُسجّل في التدقيق.'
              : 'Masked by default — unmasking requires permission and is audited.')}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {conflict ? <ConflictBanner detail={conflict} locale={locale} /> : null}

        {/* Verified vs proposed, side by side, with changes marked. */}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-[1.1rem] border border-[#e8dfd0]/80 bg-wf-surface px-4 py-3">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">
              <ShieldCheck className="h-3.5 w-3.5" />
              {isAr ? 'الموثقة حالياً' : 'Currently verified'}
            </div>
            {verifiedFields.length ? (
              <dl className="mt-2 space-y-1.5">
                {verifiedFields.map((row) => (
                  <div key={row.field}>
                    <dt className="text-[11px] text-subtle/85">{bankFieldLabel(row.field, isAr)}</dt>
                    <dd className="font-mono text-[13px] text-text">{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-[13px] text-subtle/90">
                {isAr ? 'لا توجد بيانات موثقة بعد.' : 'Nothing verified yet.'}
              </p>
            )}
            {data?.payroll_effective?.effective_from ? (
              <p className="mt-2 text-[12px] text-subtle/85">
                {isAr ? 'مستخدمة للرواتب من ' : 'Payroll-effective from '}
                {String(data.payroll_effective.effective_from).slice(0, 10)}
              </p>
            ) : null}
          </div>

          <div className="rounded-[1.1rem] border border-[#e8dfd0]/80 bg-panel-muted/40 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">
              {comparison?.is_first_submission
                ? isAr
                  ? 'أول إرسال من الموظف'
                  : 'First submission'
                : isAr
                  ? 'المقترحة من الموظف'
                  : 'Proposed by employee'}
            </div>
            {proposedFields.length ? (
              <dl className="mt-2 space-y-1.5">
                {proposedFields.map((row) => (
                  <div key={row.field}>
                    <dt className="text-[11px] text-subtle/85">
                      {bankFieldLabel(row.field, isAr)}
                      {changed.has(row.field) ? (
                        <span className="ms-1.5 rounded-full bg-wf-accent-review-soft px-1.5 py-0.5 text-[10px] font-semibold text-wf-accent-review-ink">
                          {isAr ? 'تغيير' : 'changed'}
                        </span>
                      ) : null}
                    </dt>
                    <dd className="font-mono text-[13px] text-text">{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-[13px] text-subtle/90">
                {isAr ? 'لا يوجد طلب معلّق.' : 'No pending submission.'}
              </p>
            )}
            {submission?.submitted_at ? (
              <p className="mt-2 text-[12px] text-subtle/85">
                {isAr ? 'أُرسل في ' : 'Submitted '}
                {String(submission.submitted_at).slice(0, 10)}
              </p>
            ) : null}
            {submission?.rejection_reason ? (
              <p className="mt-2 text-[12px] text-wf-accent-active-ink">
                {isAr ? 'سبب الإرجاع: ' : 'Return reason: '}
                {submission.rejection_reason}
              </p>
            ) : null}
          </div>
        </div>

        {evidence.length ? (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">
              {isAr ? 'المستندات المؤيدة' : 'Supporting evidence'}
            </div>
            <ul className="mt-2 space-y-1">
              {evidence.map((row) => (
                <li key={row.evidence_id}>
                  <button
                    type="button"
                    onClick={() => void openEvidence(row)}
                    disabled={openingEvidence === row.evidence_id}
                    className="inline-flex items-center gap-1.5 text-[13px] font-medium text-wf-ink underline-offset-2 hover:underline disabled:opacity-60"
                  >
                    {openingEvidence === row.evidence_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <FileText className="h-3.5 w-3.5" />
                    )}
                    {row.filename || row.evidence_id}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {payrollLocked ? (
          <ConflictBanner
            title={isAr ? 'الرواتب قيد المعالجة' : 'Payroll is processing'}
            detail={
              isAr
                ? 'سيسري التغيير من الفترة التالية حتى لا تتأثر دورة الرواتب الحالية.'
                : 'The change will take effect from the next period so the current payroll run is unaffected.'
            }
            locale={locale}
          />
        ) : null}

        {notice ? <p className="text-[13px] text-subtle">{notice}</p> : null}

        {canDecide && (awaitingReview || approvedNotApplied) ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {awaitingReview ? (
                <>
                  <Button size="sm" onClick={() => void decide('approve')} disabled={busy !== null}>
                    {busy === 'approve' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                    {isAr ? 'موافقة' : 'Approve'}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setRejectOpen((prev) => !prev)}
                    disabled={busy !== null}
                  >
                    {isAr ? 'رفض / طلب تصحيح' : 'Reject / request correction'}
                  </Button>
                </>
              ) : null}
              {approvedNotApplied ? (
                <Button size="sm" onClick={() => void apply()} disabled={busy !== null}>
                  {busy === 'apply' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {isAr ? 'تطبيق على الرواتب' : 'Apply to payroll'}
                </Button>
              ) : null}
            </div>
            {rejectOpen ? (
              <div className="space-y-2 rounded-[1rem] border border-line/60 bg-panel-muted/40 p-3">
                <label className="block text-[12px] font-medium text-text" htmlFor="bank-reject-reason">
                  {isAr
                    ? 'السبب (يظهر للموظف ويُسجّل في التدقيق)'
                    : 'Reason (shown to the employee and recorded in the audit trail)'}
                </label>
                <textarea
                  id="bank-reject-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  rows={3}
                  className="w-full rounded-[0.75rem] border border-line/70 bg-wf-surface px-3 py-2 text-[13px] text-text"
                  placeholder={
                    isAr ? 'مثال: الآيبان لا يطابق اسم صاحب الحساب.' : 'e.g. IBAN does not match the account holder name.'
                  }
                />
                <Button
                  size="sm"
                  onClick={() => void decide('reject')}
                  disabled={busy !== null || !reason.trim()}
                >
                  {busy === 'reject' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {isAr ? 'إرجاع للموظف' : 'Return to employee'}
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}

        <div>
          <button
            type="button"
            onClick={() => setShowHistory((prev) => !prev)}
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-wf-ink underline-offset-2 hover:underline"
          >
            <History className="h-3.5 w-3.5" />
            {isAr ? 'سجل المراجعة والتوثيق' : 'Submission and decision history'}
          </button>
          {showHistory ? <BankHistory data={data} isAr={isAr} /> : null}
        </div>
      </CardContent>
    </Card>
  )
}

/** Who submitted, who reviewed, who approved, and what payroll used when. */
function BankHistory({ data, isAr }: { data: BankReviewResponse | null; isAr: boolean }) {
  const decisions = data?.decision_history || []
  const verified = data?.verified_history || []
  const effective = data?.effective_history || []
  if (!decisions.length && !verified.length && !effective.length) {
    return (
      <WorkflowEmpty
        className="mt-2"
        title={isAr ? 'لا يوجد سجل بعد' : 'No history yet'}
        hint={isAr ? 'سيظهر كل إرسال وقرار هنا.' : 'Every submission and decision will appear here.'}
      />
    )
  }
  return (
    <div className="mt-2 space-y-3">
      {decisions.length ? (
        <ol className="space-y-1.5">
          {decisions.map((row, index) => (
            <li
              key={`${row.request_id || 'req'}-${row.created_at || index}`}
              className="rounded-[0.75rem] border border-line/50 bg-wf-surface px-3 py-2 text-[12.5px]"
            >
              <span className="font-semibold text-text">{String(row.action || '').replace(/_/g, ' ')}</span>
              {row.from_state || row.to_state ? (
                <span className="text-subtle/85">
                  {' '}
                  {String(row.from_state || '—')} → {String(row.to_state || '—')}
                </span>
              ) : null}
              <span className="text-subtle/80">
                {' · '}
                {String(row.created_at || '').slice(0, 19).replace('T', ' ')}
              </span>
              {row.actor_user_id || row.actor_employee_key ? (
                <span className="text-subtle/80">
                  {' · '}
                  {isAr ? 'بواسطة ' : 'by '}
                  {row.actor_user_id || row.actor_employee_key}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
      {effective.length ? (
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">
            {isAr ? 'ما استخدمته الرواتب' : 'What payroll used'}
          </div>
          <ol className="mt-1 space-y-1">
            {effective.map((row, index) => (
              <li key={`${row.effective_from || index}`} className="text-[12.5px] text-subtle/90">
                {String(row.effective_from || '').slice(0, 10)}
                {row.effective_to ? ` → ${String(row.effective_to).slice(0, 10)}` : isAr ? ' → حتى الآن' : ' → current'}
                {row.bank_profile_version ? ` · v${row.bank_profile_version}` : ''}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}
