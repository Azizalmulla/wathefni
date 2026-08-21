import { memo } from 'react'
import type { ApplicationSummary, CandidateSavedViewId } from '@/types'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import { recruitingCopy } from '@/lib/recruitingLifecycle'
import {
  aggregateCandidatesForList,
  candidateExpertiseLabel,
  candidateInitials,
  candidateListJobPresentation,
  candidateListReceivedLabel,
  candidateListStageLabel,
  candidateListStageTone,
  formatCandidateDisplayName,
  identityReviewWarningLabel,
  isGeneralCandidate,
  isHeldCandidate,
  type CandidateListPerson,
} from '@/lib/candidatesListPresentation'
import { Badge } from '@/components/ui/badge'
import { HrSurfaceTabs } from '@/components/hr/HrSurfaceTabs'

export { isHeldCandidate, isGeneralCandidate }
export type { CandidateListPerson }

export const CANDIDATE_VIEW_PILLS: Array<{ id: CandidateSavedViewId; labelEn: string; labelAr: string }> = [
  { id: 'all', labelEn: 'All', labelAr: 'الكل' },
  { id: 'active', labelEn: 'With a job', labelAr: 'مرتبط بوظيفة' },
  { id: 'talent_pool', labelEn: 'No job assigned', labelAr: 'بدون وظيفة' },
  { id: 'hired', labelEn: 'Hired', labelAr: 'تم التعيين' },
  { id: 'archived', labelEn: 'Archived', labelAr: 'مؤرشف' },
  { id: 'restricted', labelEn: 'Restricted', labelAr: 'مقيّد' },
]

/** Elevated privacy/governance access — Restricted view is hidden from ordinary recruiters. */
export function canViewRestrictedCandidates(access: {
  role?: string | null
  permissions?: string[] | null
} | null | undefined) {
  const permissions = access?.permissions || []
  return permissions.includes('users.manage')
    || permissions.includes('settings.manage')
}

export function candidateDisplayName(application: ApplicationSummary, locale: RecruitingLocale = 'en') {
  return formatCandidateDisplayName(application.candidate?.name, locale)
}

export function candidateDisplayContact(application: ApplicationSummary) {
  const grounded = application.grounded_contacts
  const email = grounded?.email || application.candidate?.email
  const phone = grounded?.phone
  const value = email || phone || ''
  if (/^imp-/i.test(value)) return ''
  if (/^imp-/i.test(application.phone || '') && !email && !phone) return ''
  return value
}

/** @deprecated Prefer candidateListJobPresentation for the simplified list. */
export function candidateJobLabel(application: ApplicationSummary, locale: RecruitingLocale = 'en') {
  return candidateListJobPresentation(application, locale, 0).title
}

/** @deprecated Prefer candidateListStageLabel for the simplified list. */
export function candidateStatusLabel(application: ApplicationSummary, locale: RecruitingLocale) {
  return candidateListStageLabel(application, locale)
}

export function candidateAssessmentLabel(application: ApplicationSummary, assessmentEnabled: boolean) {
  if (!assessmentEnabled) return null
  if (application.assessment_display) return application.assessment_display
  if (isHeldCandidate(application) && application.record_state !== 'hired') return '—'
  const status = application.assessment?.status
  if (!status) return '—'
  return status
}

export function candidateCommunicationLabel(application: ApplicationSummary, locale: RecruitingLocale) {
  if (application.communication_display) return application.communication_display
  if (isGeneralCandidate(application)) return locale === 'ar' ? 'لا تواصل' : 'No outreach'
  const status = application.communication?.status
  if (!status) return recruitingCopy(locale, 'communication')
  return status
}

export function candidateCvProcessingLabel(application: ApplicationSummary) {
  return application.cv_processing?.label
    || application.cv_processing?.status
    || (application.cv?.received ? 'Received' : 'Not received')
}

export function candidateRecruiterLabel(application: ApplicationSummary) {
  return application.recruiter_owner?.label || 'Unassigned'
}

export function CandidateViewPills({
  value,
  onChange,
  locale = 'en',
  showRestricted = false,
}: {
  value: CandidateSavedViewId
  onChange: (value: CandidateSavedViewId) => void
  locale?: RecruitingLocale
  showRestricted?: boolean
}) {
  const pills = CANDIDATE_VIEW_PILLS.filter((pill) => pill.id !== 'restricted' || showRestricted)
  return (
    <HrSurfaceTabs
      ariaLabel={locale === 'ar' ? 'عرض المرشحين' : 'Candidate views'}
      items={pills.map((pill) => ({
        id: pill.id,
        label: locale === 'ar' ? pill.labelAr : pill.labelEn,
      }))}
      onChange={onChange}
      testId="candidate-view-pills"
      value={value}
    />
  )
}

function CandidateAvatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-semantic-accent-soft text-[11px] font-semibold tracking-wide text-semantic-ink"
    >
      {candidateInitials(name)}
    </span>
  )
}

export const CandidateTableRow = memo(function CandidateTableRow({
  application,
  locale,
  onSelect,
  person,
}: {
  locale: RecruitingLocale
  onSelect: (application: ApplicationSummary) => void
  person?: CandidateListPerson
  application?: ApplicationSummary
  /** Ignored — assessments are no longer a default list column. */
  assessmentEnabled?: boolean
}) {
  const row = person || (application ? aggregateCandidatesForList([application])[0] : null)
  if (!row) return null
  const primary = row.primary
  const name = candidateDisplayName(primary, locale)
  const job = candidateListJobPresentation(primary, locale, row.additionalActiveJobs)

  return (
    <tr
      className="cursor-pointer transition duration-150 hover:bg-semantic-surface-raised/90"
      data-record-state={primary.record_state || (isGeneralCandidate(primary) ? 'talent_pool' : 'active_application')}
      data-testid="candidate-list-row"
      onClick={() => onSelect(primary)}
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <CandidateAvatar name={name} />
          <div className="min-w-0">
            <div className="truncate font-semibold text-text">{name}</div>
            {row.identityReviewWarning ? (
              <div className="mt-1 flex items-center gap-1.5 text-xs font-medium text-semantic-warning-ink" data-testid="identity-review-warning">
                <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-wf-accent-review" />
                {identityReviewWarningLabel(locale)}
              </div>
            ) : null}
          </div>
        </div>
      </td>
      <td className="px-4 py-3 text-subtle">{candidateExpertiseLabel(primary, locale)}</td>
      <td className="px-4 py-3 text-subtle">
        <span className="truncate" data-testid="candidate-job-label">{job.title}</span>
      </td>
      <td className="px-4 py-3">
        <Badge tone={candidateListStageTone(primary)}>{candidateListStageLabel(primary, locale)}</Badge>
      </td>
      <td className="px-4 py-3 text-subtle">{candidateListReceivedLabel(primary, locale)}</td>
    </tr>
  )
})

CandidateTableRow.displayName = 'CandidateTableRow'
