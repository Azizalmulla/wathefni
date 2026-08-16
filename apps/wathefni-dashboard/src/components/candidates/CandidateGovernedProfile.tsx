import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import type { ApplicationSummary, CandidateProfileResponse, DashboardAccess } from '@/types'
import { getCandidateProfile, reviewCandidateFact } from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/field'
import {
  candidateDisplayContact,
  candidateDisplayName,
  candidateJobLabel,
  candidateStatusLabel,
  isHeldCandidate,
} from '@/components/candidates/CandidatesTable'
import { CandidateClassificationSection } from '@/components/candidates/CandidateClassificationSection'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import { intakeSourceLabel } from '@/lib/recruitingLifecycle'

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="rounded-2xl border border-line/55 bg-white/32 p-3.5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle">{label}</div>
      <div className="mt-1.5 break-words text-sm font-medium text-text">{value || '—'}</div>
    </div>
  )
}

export function CandidateGovernedProfile({
  access,
  application,
  locale,
  onAccessIssue,
  onClose,
  liveActions,
  classificationEnabled = false,
}: {
  access: DashboardAccess
  application: ApplicationSummary
  locale: RecruitingLocale
  onAccessIssue?: (issue: AccessIssue) => void
  onClose: () => void
  liveActions?: React.ReactNode
  classificationEnabled?: boolean
}) {
  const [profile, setProfile] = useState<CandidateProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [factPath, setFactPath] = useState('skills')
  const [factValue, setFactValue] = useState('')
  const [busy, setBusy] = useState(false)
  const held = isHeldCandidate(application)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const payload = await getCandidateProfile(access, application.app_key)
        if (!cancelled) setProfile(payload)
      } catch (err) {
        const issue = accessIssueFromError(err)
        if (issue) {
          onAccessIssue?.(issue)
          return
        }
        if (!cancelled) setMessage('Could not load the governed candidate profile.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [access, application.app_key, onAccessIssue])

  const runFactReview = async (confirm: boolean) => {
    setBusy(true)
    setMessage('')
    try {
      const result = await reviewCandidateFact(access, application.app_key, {
        action: 'correct',
        fact_path: factPath,
        new_value: factValue.split(',').map((part) => part.trim()).filter(Boolean),
        preview: !confirm,
        confirm,
      })
      if (result.preview) {
        setMessage(result.message || 'Preview ready. Confirm to append the review event.')
      } else {
        setMessage('Fact review event appended. Extraction snapshot was not overwritten.')
        const refreshed = await getCandidateProfile(access, application.app_key)
        setProfile(refreshed)
      }
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setMessage('Could not save the fact review.')
    } finally {
      setBusy(false)
    }
  }

  const app = profile?.application || application
  const privacy = profile?.privacy || app.privacy
  const completeness = profile?.facts?.completeness || app.completeness || []

  return (
    <div className="fixed inset-0 z-30 bg-ink/25 backdrop-blur-[2px]" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl animate-[drawerIn_220ms_ease-out] flex-col overflow-y-auto border-l border-white/70 bg-panel/95 p-6 shadow-[0_28px_90px_rgba(24,20,15,0.18)] backdrop-blur-2xl"
        data-testid="candidate-governed-profile"
        dir={locale === 'ar' ? 'rtl' : 'ltr'}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={held ? 'warning' : 'success'}>{candidateStatusLabel(app, locale)}</Badge>
              {app.record_state_label ? <Badge tone="muted">{app.record_state_label}</Badge> : null}
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">{candidateDisplayName(app)}</h2>
            <p className="mt-1 text-sm text-subtle">
              Job: {candidateJobLabel(app)} · {candidateDisplayContact(app) || 'No grounded contact'}
            </p>
          </div>
          <Button onClick={onClose} variant="secondary">Close</Button>
        </div>

        {loading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-subtle">
            <Loader2 className="animate-spin" size={16} /> Loading profile…
          </div>
        ) : null}

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Info label="Source" value={intakeSourceLabel(profile?.source_channel || app.intake_source || app.data_source, locale)} />
          <Info label="Received" value={app.ingested_at || '—'} />
          <Info label="Why held" value={profile?.held_reason || (held ? 'Held in Talent Pool' : 'Live Job application')} />
          <Info label="CV contacts" value={candidateDisplayContact(app) || '—'} />
          <Info label="Sender provenance" value={profile?.sender_provenance?.sender_email || '—'} />
          <Info label="Recruiter" value={app.recruiter_owner?.label || 'Unassigned'} />
        </div>

        {profile?.sender_provenance?.note ? (
          <p className="mt-3 text-xs text-subtle">{profile.sender_provenance.note}</p>
        ) : null}
        {app.identity?.compatibility_key_hidden ? (
          <p className="mt-2 text-xs text-subtle">{app.identity.note}</p>
        ) : null}

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Extraction completeness</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {completeness.map((item) => (
              <Badge key={item.section} tone={item.state === 'grounded' ? 'success' : item.state === 'not_extracted' ? 'muted' : 'warning'}>
                {item.label}
              </Badge>
            ))}
            {!completeness.length ? <span className="text-sm text-subtle">No completeness summary yet.</span> : null}
          </div>
          <p className="mt-3 text-xs text-subtle">
            {profile?.facts?.missing_policy || 'Missing facts are Not extracted or Unknown — never negative facts.'}
          </p>
        </section>

        <section className="mt-5 grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-line/60 bg-white/45 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Held intake</div>
            <ul className="mt-2 space-y-1 text-sm">
              {(profile?.held_applications || []).map((item) => (
                <li key={String(item.app_key)}>• {String(item.app_key)} · {String(item.status)}</li>
              ))}
              {!profile?.held_applications?.length ? <li className="text-subtle">No held intake rows.</li> : null}
            </ul>
          </div>
          <div className="rounded-2xl border border-line/60 bg-white/45 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Live Job applications</div>
            <ul className="mt-2 space-y-1 text-sm">
              {(profile?.live_applications || []).map((item) => (
                <li key={String(item.app_key)}>
                  • {String(item.position_title || item.position_code || item.app_key)} · {String(item.status)}
                </li>
              ))}
              {!profile?.live_applications?.length ? <li className="text-subtle">No live Job applications.</li> : null}
            </ul>
          </div>
        </section>

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Privacy and retention</div>
          <p className="mt-2 text-sm">
            {privacy?.configured
              ? `Notice ${privacy.privacy_notice_id || '—'} / Retention ${privacy.retention_policy_id || '—'}`
              : privacy?.message || 'Privacy and retention policy not configured'}
          </p>
        </section>

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">
            {locale === 'ar' ? 'سجل المستندات' : 'Document history'}
          </div>
          <ul className="mt-2 space-y-1 text-sm">
            {(profile?.documents || []).map((document) => {
              const metadata = document.metadata && typeof document.metadata === 'object'
                ? document.metadata as Record<string, unknown>
                : {}
              const current = metadata.latest === true
              return (
                <li
                  className="flex flex-wrap items-center gap-2 rounded-xl border border-line/45 bg-white/35 px-3 py-2"
                  key={String(document.document_id || document.filename)}
                >
                  <span>• {String(document.filename || document.document_type || 'Document')}</span>
                  <Badge tone={current ? 'success' : 'muted'}>
                    {current
                      ? (locale === 'ar' ? 'الحالي' : 'Current')
                      : (locale === 'ar' ? 'سابق' : 'Previous')}
                  </Badge>
                  <span className="text-xs text-subtle">
                    {String(document.extraction_method || 'stored')}
                    {document.received_at ? ` · ${String(document.received_at)}` : ''}
                  </span>
                </li>
              )
            })}
            {!profile?.documents?.length
              ? (profile?.files || []).map((file) => (
                  <li key={String(file.file_id || file.original_filename)}>
                    • {String(file.original_filename || file.document_type || 'Document')} ({String(file.storage_status || 'stored')})
                  </li>
                ))
              : null}
            {!profile?.documents?.length && !profile?.files?.length
              ? <li className="text-subtle">{locale === 'ar' ? 'لا توجد مستندات مسجلة.' : 'No registered documents.'}</li>
              : null}
          </ul>
        </section>

        <CandidateClassificationSection
          access={access}
          appKey={application.app_key}
          enabled={classificationEnabled}
          locale={locale === 'ar' ? 'ar' : 'en'}
          onAccessIssue={onAccessIssue}
        />

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">HR fact review</div>
          <p className="mt-1 text-xs text-subtle">Append-only. Extraction snapshots stay immutable.</p>
          <div className="mt-3 grid gap-2">
            <input
              className="h-11 rounded-full border border-line/60 bg-white/70 px-4 text-sm"
              onChange={(event) => setFactPath(event.target.value)}
              placeholder="Fact path (e.g. skills)"
              value={factPath}
            />
            <Textarea
              onChange={(event) => setFactValue(event.target.value)}
              placeholder="Corrected values, comma-separated"
              rows={2}
              value={factValue}
            />
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void runFactReview(false)} size="sm" variant="secondary">Preview</Button>
              <Button disabled={busy || !factValue.trim()} onClick={() => void runFactReview(true)} size="sm">Confirm correction</Button>
            </div>
          </div>
          {message ? <p className="mt-3 text-sm text-subtle">{message}</p> : null}
        </section>

        {!held ? <div className="mt-5">{liveActions}</div> : (
          <div className="mt-5 rounded-2xl border border-line/60 bg-white/45 p-4 text-sm text-subtle">
            Talent Pool rows do not expose recruiting lifecycle, Ranking, Interviews, Offers, hiring, or outreach actions.
          </div>
        )}

        <section className="mt-5 rounded-[1.45rem] border border-white/70 bg-white/58 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">Processing timeline</div>
          <ul className="mt-2 space-y-2 text-sm">
            {(profile?.processing_timeline || []).map((item, index) => (
              <li key={`${item.label}-${index}`}>
                <div className="font-medium">{item.label}</div>
                <div className="text-xs text-subtle">{item.at || '—'}{item.actor ? ` · ${item.actor}` : ''}</div>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}
