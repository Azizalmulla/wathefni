import { useRef, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SendResultPanel, type OutboundSendResult } from '@/components/SendResultPanel'
import { useBodyScrollLock, useOverlayFocus } from '@/hooks/useOverlayA11y'
import {
  assessmentActionLabel,
  assessmentCopy,
  assessmentStatusLabel,
} from '@/lib/assessmentVocabulary'
import type { AssessmentAttempt } from '@/types'
import { formatDateTime } from '@/lib/utils'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

export type AssessmentReportPresentation = {
  version?: string
  attempt_id?: string
  assessment_completed?: boolean
  scoring_complete?: boolean
  report_ready?: boolean
  review_state?: string
  review_label?: string
  reviewed?: boolean
  candidate?: { name?: string | null; email?: string | null; phone?: string | null }
  job?: { position_code?: string | null; position_title?: string | null }
  executive_summary?: string
  scores?: { overall?: number | null; job_match?: number | null; ability_fit?: number | null; competency_fit?: number | null }
  labels?: { overall_band?: string | null; job_match_band?: string | null; role_profile?: string | null }
  strengths?: string[]
  growth_areas?: string[]
  interview_probes?: Array<{ competency?: string | null; question?: string }>
  review?: { state?: string; label?: string; reviewed_at?: string | null; reviewed_by_user_id?: string | null }
  next_human_action?: string
  allowed_actions?: string[]
  report_version?: string
  norm_version?: string
  immutable?: boolean
}

function ScoreStat({ label, value }: { label: string; value?: number | null }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#716a5e]">{label}</div>
      <div className="mt-1 text-xl font-semibold text-[#23211d]">{value == null ? '—' : `${value}%`}</div>
    </div>
  )
}

export function AssessmentReportPage({
  attempt,
  presentation,
  locale,
  onClose,
  onMarkReviewed,
  busy,
  loading,
  loadError,
}: {
  attempt: AssessmentAttempt
  presentation?: AssessmentReportPresentation | null
  locale: RecruitingLocale
  onClose: () => void
  onMarkReviewed?: () => void
  busy?: boolean
  loading?: boolean
  loadError?: boolean
}) {
  const isAr = locale === 'ar'
  const panelRef = useRef<HTMLDivElement>(null)
  useBodyScrollLock(true)
  useOverlayFocus(true, onClose, panelRef)
  const reviewed = presentation?.review_state === 'reviewed'
  const reportReady = Boolean(presentation?.report_ready ?? attempt.status === 'completed')
  const scores = presentation?.scores || {}
  const partial = !loading && !loadError && !presentation

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-40 overflow-y-auto bg-ink/35 p-4 backdrop-blur-sm"
      dir={isAr ? 'rtl' : 'ltr'}
      onClick={onClose}
      role="dialog"
    >
      <div
        className="mx-auto max-w-3xl rounded-[1.6rem] border border-[#e8dfd0] bg-[#fffaf0] p-5 shadow-[0_28px_80px_rgba(24,20,15,0.22)] sm:p-7"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#716a5e]">
              {isAr ? 'تقرير التقييم' : 'Assessment report'}
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#23211d]">
              {presentation?.candidate?.name || attempt.candidate_name || attempt.phone || (isAr ? 'مرشح' : 'Candidate')}
            </h2>
            <p className="mt-1 text-sm text-[#716a5e]">
              {presentation?.job?.position_title || attempt.position_title || attempt.position_code || (isAr ? 'الوظيفة' : 'Role')}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge tone={reviewed ? 'success' : 'warning'}>
              {reviewed ? assessmentCopy(locale, 'reviewed') : assessmentCopy(locale, 'review_pending')}
            </Badge>
            <Button onClick={onClose} size="sm" variant="secondary">{isAr ? 'إغلاق' : 'Close'}</Button>
          </div>
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-[#716a5e]">{isAr ? 'جاري تحميل التقرير…' : 'Loading report…'}</p>
        ) : loadError ? (
          <p className="mt-4 text-sm text-rose-700">
            {isAr ? 'تعذّر تحميل التقرير. حاول مرة أخرى.' : 'Could not load the report. Try again.'}
          </p>
        ) : partial ? (
          <p className="mt-4 text-sm text-[#716a5e]">
            {isAr ? 'التقرير قيد التحضير.' : 'Report is being prepared.'}
          </p>
        ) : (
          <p className="mt-4 text-sm leading-6 text-[#716a5e]">
            {presentation?.executive_summary || (isAr ? 'التقرير قيد التحضير.' : 'Report is being prepared.')}
          </p>
        )}

        <div className="mt-5 grid grid-cols-2 gap-4 rounded-[1.3rem] border border-[#e8dfd0] bg-white/50 p-4 sm:grid-cols-4">
          <ScoreStat label={isAr ? 'النتيجة العامة' : 'Overall'} value={scores.overall} />
          <ScoreStat label={isAr ? 'توافق الوظيفة' : 'Job match'} value={scores.job_match} />
          <ScoreStat label={isAr ? 'القدرة' : 'Ability fit'} value={scores.ability_fit} />
          <ScoreStat label={isAr ? 'الجدارة' : 'Competency fit'} value={scores.competency_fit} />
        </div>

        {!loading && !loadError && presentation ? (
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <section>
              <h3 className="text-sm font-semibold text-[#23211d]">{isAr ? 'نقاط القوة' : 'Strengths'}</h3>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-[#716a5e]">
                {(presentation.strengths?.length ? presentation.strengths : [isAr ? 'لا يوجد دليل كافٍ بعد' : 'Not enough evidence yet']).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="text-sm font-semibold text-[#23211d]">{isAr ? 'مجالات التطوير' : 'Growth areas'}</h3>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-[#716a5e]">
                {(presentation.growth_areas?.length ? presentation.growth_areas : [isAr ? 'لا يوجد دليل كافٍ بعد' : 'Not enough evidence yet']).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          </div>
        ) : null}

        {presentation?.interview_probes?.length ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold text-[#23211d]">{isAr ? 'أسئلة مقابلة مقترحة' : 'Structured interview questions'}</h3>
            <ol className="mt-2 list-decimal space-y-2 ps-5 text-sm leading-6 text-[#716a5e]">
              {presentation.interview_probes.map((probe, index) => (
                <li key={`${probe.competency || 'probe'}-${index}`}>
                  {probe.competency ? <span className="font-medium text-[#23211d]">{probe.competency}: </span> : null}
                  {probe.question}
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-[1.3rem] border border-[#e8dfd0] bg-white/50 p-4">
          <div className="text-sm">
            <span className="text-[#716a5e]">{isAr ? 'الخطوة التالية:' : 'Next step:'}</span>{' '}
            <span className="font-medium text-[#23211d]">
              {reviewed
                ? (isAr ? 'التقرير جاهز للاطلاع.' : 'Report is ready to view.')
                : reportReady
                  ? (isAr ? 'راجع التقرير وسجّل المراجعة.' : 'Review the report and record your review.')
                  : (isAr ? 'انتظر اكتمال التقرير.' : 'Wait for the report to finish.')}
            </span>
          </div>
          {reportReady && !reviewed && onMarkReviewed ? (
            <Button disabled={busy} onClick={onMarkReviewed} size="sm">
              {assessmentCopy(locale, 'mark_reviewed')}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function AssessmentAttemptWorkspace({
  attempt,
  locale,
  sendResult,
  onClose,
  onViewReport,
}: {
  attempt: AssessmentAttempt
  locale: RecruitingLocale
  sendResult?: OutboundSendResult | null
  onClose: () => void
  onViewReport: () => void
}) {
  const isAr = locale === 'ar'
  const panelRef = useRef<HTMLElement>(null)
  useBodyScrollLock(true)
  useOverlayFocus(true, onClose, panelRef)
  const [tab, setTab] = useState<'overview' | 'delivery' | 'attempt' | 'report' | 'activity'>('overview')
  const presentation = attempt.presentation
  const state = presentation?.attempt?.state || attempt.status
  const next = presentation?.next_human_action
  const tabs = [
    { id: 'overview' as const, label: isAr ? 'نظرة عامة' : 'Overview', show: true },
    { id: 'delivery' as const, label: isAr ? 'التسليم' : 'Delivery', show: Boolean(sendResult || presentation?.invitation?.delivery_state) },
    { id: 'attempt' as const, label: isAr ? 'المحاولة' : 'Attempt', show: true },
    { id: 'report' as const, label: isAr ? 'التقرير' : 'Report', show: attempt.status === 'completed' },
    { id: 'activity' as const, label: isAr ? 'النشاط' : 'Activity', show: true },
  ].filter((t) => t.show)

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-30 bg-ink/30"
      dir={isAr ? 'rtl' : 'ltr'}
      onClick={onClose}
      role="dialog"
    >
      <aside
        className="ms-auto flex h-full w-full max-w-3xl flex-col overflow-y-auto border-s border-[#e8dfd0] bg-[#fffaf0] p-6"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#e8dfd0] pb-4">
          <div>
            <h3 className="text-lg font-semibold text-[#23211d]">{attempt.candidate_name || attempt.phone || (isAr ? 'مرشح' : 'Candidate')}</h3>
            <p className="mt-1 text-sm text-[#716a5e]">{attempt.position_title || attempt.position_code || (isAr ? 'الوظيفة' : 'Role')}</p>
            <p className="mt-2 text-sm text-[#716a5e]">
              {assessmentStatusLabel(locale, state)}
              {next ? ` · ${assessmentActionLabel(locale, next)}` : ''}
            </p>
          </div>
          <Button onClick={onClose} size="sm" variant="secondary">{isAr ? 'إغلاق' : 'Close'}</Button>
        </div>
        <nav className="mt-4 flex gap-1 overflow-x-auto rounded-full border border-[#e8dfd0] bg-white/45 p-1">
          {tabs.map((item) => (
            <button
              aria-current={tab === item.id ? 'page' : undefined}
              className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${tab === item.id ? 'bg-[#23211d] text-white' : 'text-[#716a5e] hover:bg-white/70 hover:text-[#23211d]'}`}
              key={item.id}
              onClick={() => setTab(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>

        {tab === 'overview' ? (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <span className="text-[#716a5e]">{isAr ? 'الحالة:' : 'State:'}</span>{' '}
              <span className="font-medium text-[#23211d]">
                {presentation?.display_status
                  ? assessmentStatusLabel(locale, presentation.display_status)
                  : assessmentStatusLabel(locale, state)}
              </span>
            </div>
            {presentation?.invitation?.expires_at ? (
              <div>
                <span className="text-[#716a5e]">{isAr ? 'ينتهي:' : 'Expires:'}</span>{' '}
                <span className="font-medium text-[#23211d]">{formatDateTime(presentation.invitation.expires_at)}</span>
              </div>
            ) : null}
            <div>
              <span className="text-[#716a5e]">{isAr ? 'الخطوة التالية:' : 'Next:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{next ? assessmentActionLabel(locale, next) : '—'}</span>
            </div>
          </div>
        ) : null}
        {tab === 'delivery' ? (
          <div className="mt-4 space-y-3">
            {sendResult ? <SendResultPanel locale={isAr ? 'ar' : 'en'} result={sendResult} /> : (
              <div className="text-sm text-[#716a5e]">{isAr ? 'لا يوجد سجل إرسال حديث.' : 'No recent send result.'}</div>
            )}
            <div className="text-sm text-[#716a5e]">
              {isAr ? 'حالة التسليم:' : 'Delivery state:'}{' '}
              {assessmentStatusLabel(locale, presentation?.invitation?.delivery_state || attempt.delivery_status)}
            </div>
          </div>
        ) : null}
        {tab === 'attempt' ? (
          <div className="mt-4 space-y-2 text-sm">
            <div>
              <span className="text-[#716a5e]">{isAr ? 'الحالة:' : 'Status:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{assessmentStatusLabel(locale, state)}</span>
            </div>
            <div>
              <span className="text-[#716a5e]">{isAr ? 'التقدم:' : 'Progress:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{attempt.answered_count ?? 0}/{attempt.total_items ?? 0}</span>
            </div>
            <div>
              <span className="text-[#716a5e]">{isAr ? 'بدأ:' : 'Started:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{attempt.started_at ? formatDateTime(attempt.started_at) : '—'}</span>
            </div>
            <div>
              <span className="text-[#716a5e]">{isAr ? 'اكتمل:' : 'Completed:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{attempt.completed_at ? formatDateTime(attempt.completed_at) : '—'}</span>
            </div>
          </div>
        ) : null}
        {tab === 'report' ? (
          <div className="mt-4">
            {attempt.status === 'completed' ? (
              <Button onClick={onViewReport} size="sm" variant="secondary">
                {assessmentCopy(locale, 'view_report')}
              </Button>
            ) : (
              <div className="text-sm text-[#716a5e]">{isAr ? 'التقرير غير جاهز بعد.' : 'Report is not ready yet.'}</div>
            )}
          </div>
        ) : null}
        {tab === 'activity' ? (
          <div className="mt-4 space-y-2 text-sm">
            <div>
              <span className="text-[#716a5e]">{isAr ? 'أنشئ:' : 'Created:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{attempt.created_at ? formatDateTime(attempt.created_at) : '—'}</span>
            </div>
            <div>
              <span className="text-[#716a5e]">{isAr ? 'حُدّث:' : 'Updated:'}</span>{' '}
              <span className="font-medium text-[#23211d]">{attempt.updated_at ? formatDateTime(attempt.updated_at) : '—'}</span>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
