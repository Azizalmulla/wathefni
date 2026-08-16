import { useState } from 'react'
import { Copy, Download, ExternalLink, Pencil, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { normalizedJobStatus } from '@/pages/shared/format'
import type { PositionSummary } from '@/types'

type JobWorkspaceTab = 'overview' | 'sharing' | 'applicants' | 'activity'

type JobWorkspaceProps = {
  job: PositionSummary
  locale: RecruitingLocale
  canCloseJobs: boolean
  canEditJobs: boolean
  canPublishJobs: boolean
  statusBusy: boolean
  qrDataUrl: string
  onClose: () => void
  onCopy: (value: string | undefined, label: string) => void
  onDownloadQr: () => void
  onEdit: () => void
  onSetStatus: (status: 'open' | 'paused' | 'closed') => void
  onViewCandidates: () => void
}

function hasValue(value: unknown) {
  if (value == null) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (typeof value === 'number') return Number.isFinite(value)
  return true
}

function PanelSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-[1.4rem] border border-line/60 bg-panel/85 p-5 shadow-[0_10px_32px_rgba(24,20,15,0.045)] ring-1 ring-white/50">
      <div className="border-b border-line/45 pb-4">
        <h3 className="text-[15px] font-semibold tracking-[-0.015em] text-text">{title}</h3>
        {description ? <p className="mt-1 text-[13px] leading-6 text-subtle/90">{description}</p> : null}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Fact({ label, value, wide = false }: { label: string; value?: React.ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? 'md:col-span-2' : ''}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle/85">{label}</div>
      <div className="mt-1 text-sm font-medium text-text">{value ?? '—'}</div>
    </div>
  )
}

export function JobWorkspace({
  job,
  locale,
  canCloseJobs,
  canEditJobs,
  canPublishJobs,
  statusBusy,
  qrDataUrl,
  onClose,
  onCopy,
  onDownloadQr,
  onEdit,
  onSetStatus,
  onViewCandidates,
}: JobWorkspaceProps) {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  const [tab, setTab] = useState<JobWorkspaceTab>('overview')

  const status = normalizedJobStatus(job)
  const title = jobDisplayTitle(job, locale)
  const shareable = jobIsExternallyShareable(job)
  const applicantCount = Number(job.active_count || 0)
  const activityCount = Number(job.notifications?.length || 0)
  const stageRows = (job.stage_counts?.length ? job.stage_counts : fallbackStatusCounts()).filter((item) => Number(item.count || 0) > 0)

  const description = (locale === 'ar' ? job.description_ar : job.description_en) || job.description || ''

  const tabs: Array<{ id: JobWorkspaceTab; label: string; count?: number }> = [
    { id: 'overview', label: t('jobsWsTabOverview') },
    { id: 'sharing', label: t('jobsWsTabSharing') },
    { id: 'applicants', label: t('jobsWsTabApplicants'), count: applicantCount },
    { id: 'activity', label: t('jobsWsTabActivity'), count: activityCount },
  ]

  const intakeValue = shareable ? t('jobsIntakeOpen') : jobEligibilityReasonLabel(locale, job.eligibility_reason)

  const lifecycleActions: Array<{ label: string; show: boolean; variant?: 'default' | 'secondary'; action: () => void }> = [
    { label: t('jobsPause'), show: status === 'open' && canCloseJobs, variant: 'secondary' as const, action: () => onSetStatus('paused') },
    { label: t('jobsResume'), show: status === 'paused' && canPublishJobs, variant: 'secondary' as const, action: () => onSetStatus('open') },
    { label: t('jobsPublish'), show: status === 'draft' && canPublishJobs, variant: 'default' as const, action: () => onSetStatus('open') },
    { label: t('jobsClose'), show: (status === 'open' || status === 'paused' || status === 'draft') && canCloseJobs, variant: 'secondary' as const, action: () => onSetStatus('closed') },
    { label: t('jobsReopen'), show: status === 'closed' && canPublishJobs, variant: 'default' as const, action: () => onSetStatus('open') },
  ].filter((item) => item.show)

  return (
    <div className="fixed inset-0 z-30 bg-ink/35 backdrop-blur-sm" onClick={onClose} dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div
        aria-label={title}
        className="mx-auto flex h-full w-full max-w-5xl flex-col overflow-y-auto bg-[#fbf8f2] p-4 shadow-[0_30px_80px_rgba(24,20,15,0.22)] sm:p-6 lg:p-8"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="rounded-[1.6rem] border border-line/60 bg-panel/90 p-5 shadow-[0_14px_40px_rgba(24,20,15,0.06)] ring-1 ring-white/55 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={jobStatusTone(status)}>{jobStatusLabel(status, locale)}</Badge>
                <span className="text-xs font-medium uppercase tracking-[0.16em] text-subtle/80">{job.position_code}</span>
              </div>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-text sm:text-3xl">{title}</h2>
              {description ? <p className="mt-2 max-w-2xl text-sm leading-6 text-subtle/95 line-clamp-3">{description}</p> : null}
            </div>
            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              {canEditJobs ? (
                <Button disabled={statusBusy} onClick={onEdit} variant="secondary">
                  <Pencil size={15} /> {t('jobsEdit')}
                </Button>
              ) : null}
              {lifecycleActions.map((item) => (
                <Button disabled={statusBusy} key={item.label} onClick={item.action} variant={item.variant || 'secondary'}>
                  {item.label}
                </Button>
              ))}
              <Button aria-label={t('jobsCloseWorkspace')} onClick={onClose} variant="ghost">
                <X size={18} />
              </Button>
            </div>
          </div>

          <nav aria-label={t('jobsWsTabs')} className="mt-5 flex gap-1 overflow-x-auto rounded-full border border-line/55 bg-white/35 p-1">
            {tabs.map((item) => (
              <button
                aria-current={tab === item.id ? 'page' : undefined}
                className={`flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold transition ${
                  tab === item.id
                    ? 'bg-[linear-gradient(180deg,#24211d_0%,#11100e_100%)] text-white shadow-[0_10px_22px_rgba(24,20,15,0.16)]'
                    : 'text-subtle hover:bg-white/70 hover:text-text'
                }`}
                key={item.id}
                onClick={() => setTab(item.id)}
                type="button"
              >
                {item.label}
                {item.count != null ? <span className={tab === item.id ? 'text-white/85' : 'text-subtle/80'}>{item.count}</span> : null}
              </button>
            ))}
          </nav>
        </header>

        <div className="mt-5 space-y-5 pb-6">
          {tab === 'overview' ? (
            <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
              <PanelSection description={t('jobsWsOverviewFactsHint')} title={t('jobsWsKeyFacts')}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Fact label={t('jobsColStatus')} value={jobStatusLabel(status, locale)} />
                  <Fact label={t('jobsColApps')} value={String(applicantCount)} />
                  <Fact label={t('jobsEligibilityReason')} value={intakeValue} wide />
                  {hasValue(job.department) ? <Fact label={t('jobsFieldDepartment')} value={job.department} /> : null}
                  {hasValue(job.location) ? <Fact label={t('jobsFieldLocation')} value={job.location} /> : null}
                  {job.vacancies != null ? (
                    <Fact label={t('jobsColVacancies')} value={t('jobsRemaining', { remaining: job.remaining_vacancies ?? 0, total: job.vacancies })} />
                  ) : null}
                  {hasValue(job.application_deadline) ? (
                    <Fact label={t('jobsFieldDeadline')} value={formatDateTime(job.application_deadline)} />
                  ) : null}
                  {jobAgeDays(job) != null ? <Fact label={t('jobsColAge')} value={t('jobsAgeDays', { days: jobAgeDays(job)! })} /> : null}
                  {job.salary_visibility !== 'public' && (job.salary_min != null || job.salary_max != null) ? (
                    <Fact label={t('jobsFieldSalaryMin')} value={`${job.salary_min ?? '—'} – ${job.salary_max ?? '—'} ${job.currency || 'KD'}`} />
                  ) : null}
                  {hasValue(job.recruiter_name || job.recruiter_user_id) ? <Fact label={t('jobsFieldRecruiter')} value={job.recruiter_name || (locale === 'ar' ? 'مسند' : 'Assigned')} /> : null}
                </div>
              </PanelSection>

              <PanelSection description={t('jobsWsOverviewDescHint')} title={t('jobsWsCandidateFacing')}>
                <div className="space-y-4">
                  {description ? (
                    <div className="text-sm leading-6 text-subtle whitespace-pre-wrap">{description}</div>
                  ) : (
                    <EmptyBlock text={t('jobsPreviewNoDescription')} />
                  )}
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle/85">{t('jobsWsRequirements')}</div>
                    <div className="mt-2 text-sm leading-6 text-subtle whitespace-pre-wrap">
                      {formatRequirements(locale === 'ar' ? job.requirements_ar || job.requirements : job.requirements_en || job.requirements)}
                    </div>
                  </div>
                </div>
              </PanelSection>
            </div>
          ) : null}

          {tab === 'sharing' ? (
            <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
              <PanelSection description={t('jobsWsSharingHint')} title={t('jobsWsShareCard')}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Fact label={t('jobsColCode')} value={shareable ? job.apply_code || '—' : job.apply_code ? t('jobsApplyCodeInternal') : '—'} />
                  <Fact label={t('jobsWsApplyLink')} value={shareable && job.application_link ? job.application_link : t('jobsApplicationLinkUnavailable')} wide />
                  <Fact label={t('jobsEligibilityReason')} value={intakeValue} />
                </div>
                {!shareable ? <p className="mt-3 text-sm text-subtle">{t('jobsShareUnavailable')}</p> : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button disabled={!shareable || !job.apply_code} onClick={() => onCopy(job.apply_code, 'Application code')} size="sm" variant="secondary">
                    <Copy size={14} /> {t('jobsWsCopyCode')}
                  </Button>
                  <Button disabled={!shareable || !job.application_link} onClick={() => onCopy(job.application_link || undefined, 'Application link')} size="sm" variant="secondary">
                    <Copy size={14} /> {t('jobsWsCopyLink')}
                  </Button>
                  <Button disabled={!shareable || !job.application_link} onClick={() => onCopy(job.application_link || undefined, 'Application link')} size="sm" variant="ghost">
                    <ExternalLink size={14} /> {t('jobsWsOpenLink')}
                  </Button>
                </div>
              </PanelSection>

              <PanelSection description={t('jobsWsQrHint')} title={t('jobsWsQr')}>
                {shareable && qrDataUrl ? (
                  <img alt={`QR code for ${title}`} className="mx-auto w-full max-w-[220px] rounded-xl border border-line bg-white p-3" src={qrDataUrl} />
                ) : (
                  <EmptyBlock text={shareable ? t('jobsWsQrNotReady') : t('jobsShareUnavailable')} />
                )}
                <Button className="mt-4 w-full" disabled={!shareable || !qrDataUrl} onClick={onDownloadQr} size="sm" variant="secondary">
                  <Download size={14} /> {t('jobsWsDownloadQr')}
                </Button>
              </PanelSection>
            </div>
          ) : null}

          {tab === 'applicants' ? (
            <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
              <PanelSection description={t('jobsWsFunnelHint')} title={t('jobsWsFunnel')}>
                <div className="space-y-3">
                  {stageRows.length ? (
                    stageRows.map((item) => <PipelineRow count={item.count} key={item.status} label={stageLabel(item.status)} />)
                  ) : (
                    <EmptyBlock text={t('jobsWsNoStageActivity')} />
                  )}
                </div>
                <Button className="mt-4 w-full" onClick={onViewCandidates} variant="secondary">
                  {t('jobsWsViewCandidates')}
                </Button>
              </PanelSection>

              <PanelSection description={t('jobsWsRecentHint')} title={t('jobsWsRecentApplicants')}>
                <div className="space-y-2">
                  {(job.recent_applicants || []).map((applicant) => (
                    <div className="rounded-xl border border-line/60 bg-white/45 p-3" key={applicant.app_key}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-text">{applicant.candidate_name || applicant.phone || 'Unknown applicant'}</div>
                        <Badge tone={statusTone(applicant.status)}>{stageLabel(applicant.status)}</Badge>
                      </div>
                      <div className="mt-1 text-xs text-subtle">{formatDateTime(applicant.ingested_at || applicant.updated_at)}</div>
                    </div>
                  ))}
                  {!job.recent_applicants?.length ? <EmptyBlock text={t('jobsWsNoApplicants')} /> : null}
                </div>
              </PanelSection>
            </div>
          ) : null}

          {tab === 'activity' ? (
            <PanelSection description={t('jobsWsActivityHint')} title={t('jobsWsCandidateActivity')}>
              <div className="space-y-2">
                {(job.notifications || []).map((item) => (
                  <div className="rounded-xl border border-line/60 bg-white/45 p-3" key={item.delivery_id}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium text-text">{item.target_phone || t('jobsWsCandidateContact')}</div>
                      <Badge tone={statusTone(item.status)}>{stageLabel(item.status)}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-subtle">{jobNotificationLabel(item)}</div>
                  </div>
                ))}
                {!job.notifications?.length ? <EmptyBlock text={t('jobsWsNoActivity')} /> : null}
              </div>
            </PanelSection>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line/75 bg-white/28 p-4 text-sm text-subtle">
      {text}
    </div>
  )
}

// ---- Shared job helpers (unchanged authority; presentation only) ----

function jobDisplayTitle(job: PositionSummary, locale: RecruitingLocale) {
  if (locale === 'ar') return job.title_ar || job.position_title || job.title || job.position_code
  return job.title_en || job.title || job.position_title || job.position_code
}

function jobIsExternallyShareable(job: PositionSummary) {
  return Boolean(job.shareable ?? job.accepts_applications)
}

function jobStatusTone(status: string) {
  if (status === 'open') return 'success' as const
  if (status === 'draft' || status === 'paused') return 'warning' as const
  return 'muted' as const
}

function jobStatusLabel(status: string, locale: RecruitingLocale) {
  if (status === 'open') return recruitingCopy(locale, 'jobsOpen')
  if (status === 'draft') return recruitingCopy(locale, 'jobsDraft')
  if (status === 'paused') return recruitingCopy(locale, 'jobsPaused')
  if (status === 'closed') return recruitingCopy(locale, 'jobsClosed')
  return status
}

function jobAgeDays(job: PositionSummary) {
  const raw = job.created_at || job.published_at
  if (!raw) return null
  const ms = Date.now() - new Date(raw).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)))
}

function jobEligibilityReasonLabel(locale: RecruitingLocale, reason?: string | null) {
  if (!reason) return recruitingCopy(locale, 'jobsIntakeClosed')
  const key = `jobsEligibility_${reason}` as Parameters<typeof recruitingCopy>[1]
  return recruitingCopy(locale, key)
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function formatRequirements(requirements: unknown) {
  if (Array.isArray(requirements) && requirements.length) {
    return requirements.map((item) => `- ${String(item)}`).join('\n')
  }
  if (requirements && typeof requirements === 'object') {
    return Object.entries(requirements as Record<string, unknown>)
      .map(([key, value]) => `${stageLabel(key)}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
      .join('\n')
  }
  if (typeof requirements === 'string' && requirements.trim()) return requirements
  return recruitingCopy('en', 'jobsWsNoRequirements')
}

function stageLabel(value?: string | null) {
  if (!value) return '—'
  return String(value).replace(/_/g, ' ')
}

function statusTone(_status?: string) {
  return 'muted' as const
}

function PipelineRow({ count, label }: { count: number; label: string }) {
  const width = Math.max(6, Math.min(100, Number(count || 0) * 14))
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-sm">
        <span className="font-medium text-text">{label}</span>
        <span className="text-subtle">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-panel-muted">
        <div className="h-2 rounded-full bg-ink" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function fallbackStatusCounts() {
  return [
    { status: 'screening', count: 0 },
    { status: 'review_pending', count: 0 },
    { status: 'shortlisted', count: 0 },
    { status: 'hired', count: 0 },
  ]
}

function jobNotificationLabel(item: { status?: string; last_error?: string; created_at?: string }) {
  const normalized = String(item.status || '').toLowerCase()
  const lastError = String(item.last_error || '').toLowerCase()
  if (normalized === 'sent') return `Candidate contacted ${formatDateTime(item.created_at)}`
  if (lastError) return lastError
  if (normalized === 'failed') return 'Candidate was not reached. Try another contact method.'
  return formatDateTime(item.created_at)
}
