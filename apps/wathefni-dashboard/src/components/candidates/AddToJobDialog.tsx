import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'

import type { ApplicationSummary, CandidatePersonProfileResponse, DashboardAccess, PositionSummary } from '@/types'
import { addCandidateToJobViaPersonProfile, DashboardApiError } from '@/lib/api'
import { accessIssueFromError, type AccessIssue } from '@/lib/access'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import {
  hasDuplicateJobApplication,
  openAssignableJobs,
  overviewFromProfile,
  profileCopy,
} from '@/lib/candidateProfilePresentation'
import { Button } from '@/components/ui/button'

type Step = 'select' | 'confirm'

export function AddToJobDialog({
  access,
  application,
  related,
  positions,
  personProfile,
  locale,
  onClose,
  onAccessIssue,
  onSuccess,
}: {
  access: DashboardAccess
  application: ApplicationSummary
  related: ApplicationSummary[]
  positions: PositionSummary[]
  personProfile: CandidatePersonProfileResponse | null
  locale: RecruitingLocale
  onClose: () => void
  onAccessIssue?: (issue: AccessIssue) => void
  onSuccess: (message: string) => void
}) {
  const t = profileCopy(locale)
  const overview = overviewFromProfile(application, personProfile, locale)
  const blocked = new Set(personProfile?.add_to_job?.blocked_position_codes || [])
  const jobs = useMemo(() => {
    const open = openAssignableJobs(positions, related)
    return open.filter((job) => !blocked.has(String(job.position_code || '').trim()))
  }, [positions, related, blocked])
  const [step, setStep] = useState<Step>('select')
  const [positionCode, setPositionCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const selectedJob = jobs.find((job) => job.position_code === positionCode) || null
  const cvLabel = application.cv?.received
    ? (application.cv.filename || t.cvOnFile)
    : t.cvMissing

  const goConfirm = () => {
    setError('')
    if (!positionCode) {
      setError(locale === 'ar' ? 'اختر وظيفة مفتوحة.' : 'Select an open job.')
      return
    }
    if (hasDuplicateJobApplication(related, positionCode) || blocked.has(positionCode)) {
      setError(t.duplicateJob)
      return
    }
    setStep('confirm')
  }

  const submit = async () => {
    if (!selectedJob) return
    if (hasDuplicateJobApplication(related, selectedJob.position_code) || blocked.has(selectedJob.position_code)) {
      setError(t.duplicateJob)
      return
    }
    setBusy(true)
    setError('')
    try {
      await addCandidateToJobViaPersonProfile(access, application.app_key, {
        position_code: selectedJob.position_code,
        position_title: selectedJob.title || selectedJob.position_title || selectedJob.position_code,
        confirm: true,
      })
      onSuccess(t.added)
      onClose()
    } catch (err) {
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      if (err instanceof DashboardApiError) {
        const detail = err.detail as { error?: string; message?: string } | string | undefined
        const code = typeof detail === 'object' && detail ? String(detail.error || '') : ''
        if (err.status === 403 || code.includes('entitlement') || code.includes('permission')) {
          setError(t.permissionDenied)
          return
        }
        if (code === 'duplicate_active_application' || code.includes('duplicate') || code === 'not_in_import_review') {
          setError(t.duplicateJob)
          return
        }
        if (typeof detail === 'object' && detail?.message) {
          setError(String(detail.message))
          return
        }
      }
      setError(err instanceof Error ? err.message : t.permissionDenied)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-ink/30 p-3 backdrop-blur-[2px] sm:items-center"
      onClick={() => {
        if (!busy) onClose()
      }}
    >
      <div
        className="w-full max-w-lg rounded-[1.6rem] border border-white/70 bg-panel/95 p-5 shadow-[0_28px_90px_rgba(24,20,15,0.18)]"
        dir={locale === 'ar' ? 'rtl' : 'ltr'}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-xl font-semibold tracking-tight text-text">{step === 'confirm' ? t.confirmTitle : t.addToJob}</h2>
        <p className="mt-1 text-sm text-subtle">{step === 'confirm' ? t.confirmBody : t.selectJob}</p>

        {step === 'select' ? (
          <div className="mt-4 space-y-3">
            <label className="block text-sm font-medium text-text">
              {t.job}
              <select
                className="mt-1.5 w-full rounded-xl border border-line bg-white px-3 py-2.5 text-sm"
                onChange={(event) => setPositionCode(event.target.value)}
                value={positionCode}
              >
                <option value="">{t.selectJob}</option>
                {jobs.map((job) => (
                  <option key={job.position_code} value={job.position_code}>
                    {job.title || job.position_title || job.position_code}
                    {job.department ? ` · ${job.department}` : ''}
                  </option>
                ))}
              </select>
            </label>
            {!jobs.length ? (
              <p className="text-sm text-subtle">
                {locale === 'ar' ? 'لا توجد وظائف مفتوحة متاحة لهذا المرشح.' : 'No open jobs are available for this candidate.'}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="mt-4 space-y-3 rounded-2xl border border-line/60 bg-white/45 p-4 text-sm">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{t.candidate}</div>
              <div className="mt-1 font-medium text-text">{overview.name}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{t.job}</div>
              <div className="mt-1 font-medium text-text">{selectedJob?.title || selectedJob?.position_title || selectedJob?.position_code}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle">{t.cv}</div>
              <div className="mt-1 font-medium text-text">{cvLabel}</div>
            </div>
          </div>
        )}

        {error ? <p className="mt-3 text-sm font-medium text-red-700">{error}</p> : null}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {step === 'confirm' ? (
            <Button disabled={busy} onClick={() => setStep('select')} type="button" variant="secondary">
              {t.back}
            </Button>
          ) : (
            <Button disabled={busy} onClick={onClose} type="button" variant="secondary">
              {t.cancel}
            </Button>
          )}
          {step === 'select' ? (
            <Button disabled={!jobs.length || busy} onClick={goConfirm} type="button">
              {t.confirmAdd}
            </Button>
          ) : (
            <Button disabled={busy} onClick={() => void submit()} type="button">
              {busy ? <Loader2 className="animate-spin" size={16} /> : null}
              {busy ? t.adding : t.confirmAdd}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
