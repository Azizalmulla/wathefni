import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  assessmentActionLabel,
  assessmentCopy,
  assessmentStatusLabel,
} from '@/lib/assessmentVocabulary'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import type { AssessmentAttempt } from '@/types'
import { formatDateTime } from '@/lib/utils'

function toneFor(value?: string | null): 'default' | 'success' | 'warning' | 'danger' | 'muted' | 'assess' | 'priority' | 'review' {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'sent', 'sent pending', 'reviewed', 'ready', 'strong', 'qualified', 'جاهز', 'مكتمل', 'تمت المراجعة'].some((k) => normalized.includes(k))) {
    return 'priority'
  }
  if (['failed', 'expired', 'cancelled', 'canceled', 'فشل', 'منتهي', 'ملغى'].some((k) => normalized.includes(k))) {
    return 'danger'
  }
  if (['pending', 'in progress', 'queued', 'unreviewed', 'review pending', 'needs review', 'قيد', 'بانتظار'].some((k) => normalized.includes(k))) {
    return 'assess'
  }
  return 'muted'
}

function attemptAllowed(attempt: AssessmentAttempt): Set<string> {
  const set = new Set<string>(attempt.presentation?.allowed_actions || [])
  return set
}

export function SendRow({
  locale,
  applicationName,
  applicationContact,
  job,
  stateLabel,
  deliveryLabel,
  primaryLabel,
  disabled,
  onPrimary,
  secondaryActions,
}: {
  locale: RecruitingLocale
  applicationName: string
  applicationContact?: string
  job?: string
  stateLabel: string
  deliveryLabel?: string | null
  primaryLabel: string
  disabled?: boolean
  onPrimary: () => void
  secondaryActions?: Array<{ label: string; action: () => void; disabled?: boolean }>
}) {
  return (
    <div className="grid gap-3 border-b border-semantic-line px-4 py-3 text-sm last:border-b-0 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="truncate font-semibold text-semantic-ink">{applicationName}</div>
        <div className="truncate text-xs text-semantic-subtle">
          {[applicationContact, job].filter(Boolean).join(' · ') || '—'}
        </div>
      </div>
      <div className="min-w-0">
        <Badge tone={toneFor(stateLabel)}>{stateLabel}</Badge>
        {deliveryLabel ? <div className="mt-0.5 truncate text-xs text-semantic-subtle">{deliveryLabel}</div> : null}
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button disabled={disabled} onClick={onPrimary} size="sm">
          {primaryLabel}
        </Button>
        {secondaryActions?.length ? (
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-full border border-semantic-line bg-semantic-surface px-3 py-1.5 text-xs text-semantic-subtle">
              {locale === 'ar' ? 'المزيد' : 'More'}
            </summary>
            <div className="absolute end-0 z-10 mt-1 grid w-40 gap-1 rounded-xl border border-semantic-line bg-semantic-surface p-1.5">
              {secondaryActions.map((item) => (
                <Button disabled={item.disabled} key={item.label} onClick={item.action} size="sm" variant="ghost">
                  {item.label}
                </Button>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  )
}

export function AttemptRow({
  attempt,
  locale,
  canManage,
  busy,
  onOpen,
  onResend,
  onCancel,
  onViewReport,
  onMarkReviewed,
}: {
  attempt: AssessmentAttempt
  locale: RecruitingLocale
  canManage: boolean
  busy: boolean
  onOpen: () => void
  onResend: () => void
  onCancel: () => void
  onViewReport: () => void
  onMarkReviewed: () => void
}) {
  const presentation = attempt.presentation
  const state = presentation?.attempt?.state || attempt.status
  const review = presentation?.attempt?.review_state || attempt.review_status || 'unreviewed'
  const allowed = attemptAllowed(attempt)
  const progressLabel = assessmentStatusLabel(locale, state)
  const reviewLabel =
    review === 'reviewed'
      ? assessmentCopy(locale, 'reviewed')
      : state === 'completed'
        ? assessmentCopy(locale, 'review_pending')
        : '—'
  const nextLabel = presentation?.next_human_action
    ? assessmentActionLabel(locale, presentation.next_human_action)
    : null

  const primary =
    allowed.has('view_report')
      ? { label: assessmentCopy(locale, 'view_report'), action: onViewReport }
      : allowed.has('mark_reviewed') && canManage
        ? { label: assessmentCopy(locale, 'mark_reviewed'), action: onMarkReviewed }
        : allowed.has('resend_assessment') && canManage
          ? { label: assessmentCopy(locale, 'resend_assessment'), action: onResend }
          : { label: assessmentCopy(locale, 'open_attempt'), action: onOpen }

  const secondary: Array<{ label: string; action: () => void; disabled?: boolean }> = []
  if (allowed.has('view_report') && primary.action !== onViewReport) {
    secondary.push({ label: assessmentCopy(locale, 'view_report'), action: onViewReport })
  }
  if (allowed.has('mark_reviewed') && canManage && primary.action !== onMarkReviewed) {
    secondary.push({ label: assessmentCopy(locale, 'mark_reviewed'), action: onMarkReviewed, disabled: busy })
  }
  if (allowed.has('resend_assessment') && canManage && primary.action !== onResend) {
    secondary.push({ label: assessmentCopy(locale, 'resend_assessment'), action: onResend, disabled: busy })
  }
  if (allowed.has('cancel_assessment') && canManage) {
    secondary.push({ label: assessmentCopy(locale, 'cancel_assessment'), action: onCancel, disabled: busy })
  }
  if (primary.action !== onOpen) {
    secondary.push({ label: assessmentCopy(locale, 'open_attempt'), action: onOpen })
  }

  return (
    <div className="grid gap-3 border-b border-semantic-line px-4 py-3 text-sm last:border-b-0 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="truncate font-semibold text-semantic-ink">{attempt.candidate_name || attempt.phone || (locale === 'ar' ? 'مرشح' : 'Candidate')}</div>
        <div className="truncate text-xs text-semantic-subtle">
          {[attempt.candidate_email || attempt.phone, attempt.position_title || attempt.position_code].filter(Boolean).join(' · ')}
        </div>
        {nextLabel ? <div className="mt-1 truncate text-xs text-semantic-subtle">{nextLabel}</div> : null}
      </div>
      <div className="min-w-0 space-y-1">
        <div className="font-medium text-semantic-ink">{progressLabel}</div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-semantic-subtle">
          {attempt.percent != null ? <span>{attempt.percent}%</span> : null}
          {state === 'completed' ? <Badge tone={toneFor(reviewLabel)}>{reviewLabel}</Badge> : null}
          {attempt.completed_at ? <span>{formatDateTime(attempt.completed_at)}</span> : null}
        </div>
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button disabled={busy && primary.action !== onOpen} onClick={primary.action} size="sm">
          {primary.label}
        </Button>
        {secondary.length ? (
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-full border border-semantic-line bg-semantic-surface px-3 py-1.5 text-xs text-semantic-subtle">
              {locale === 'ar' ? 'المزيد' : 'More'}
            </summary>
            <div className="absolute end-0 z-10 mt-1 grid w-40 gap-1 rounded-xl border border-semantic-line bg-semantic-surface p-1.5">
              {secondary.map((item) => (
                <Button disabled={item.disabled} key={item.label} onClick={item.action} size="sm" variant="ghost">
                  {item.label}
                </Button>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  )
}

export function ReportRow({
  attempt,
  locale,
  onViewReport,
}: {
  attempt: AssessmentAttempt
  locale: RecruitingLocale
  onViewReport: () => void
}) {
  const presentation = attempt.presentation
  const review = presentation?.attempt?.review_state || attempt.review_status || 'unreviewed'
  const overall = attempt.percent != null ? `${attempt.percent}%` : '—'
  const reviewLabel = review === 'reviewed' ? assessmentCopy(locale, 'reviewed') : assessmentCopy(locale, 'review_pending')
  return (
    <div className="grid gap-3 border-b border-semantic-line px-4 py-3 text-sm last:border-b-0 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="truncate font-semibold text-semantic-ink">{attempt.candidate_name || attempt.phone || (locale === 'ar' ? 'مرشح' : 'Candidate')}</div>
        <div className="truncate text-xs text-semantic-subtle">
          {[attempt.candidate_email || attempt.phone, attempt.position_title || attempt.position_code].filter(Boolean).join(' · ')}
        </div>
      </div>
      <div className="min-w-0 space-y-1">
        <div className="font-medium text-semantic-ink">{overall}</div>
        <Badge tone={toneFor(reviewLabel)}>{reviewLabel}</Badge>
      </div>
      <div className="flex justify-end">
        <Button onClick={onViewReport} size="sm">
          {assessmentCopy(locale, 'view_report')}
        </Button>
      </div>
    </div>
  )
}
