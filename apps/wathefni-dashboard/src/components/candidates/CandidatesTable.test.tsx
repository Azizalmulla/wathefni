import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  CandidateTableRow,
  CandidateViewPills,
  candidateDisplayContact,
  candidateJobLabel,
  candidateStatusLabel,
  isHeldCandidate,
} from '@/components/candidates/CandidatesTable'
import {
  aggregateCandidatesForList,
  candidateExpertiseLabel,
  candidateListJobLabel,
  candidateListReceivedLabel,
  candidateListStageLabel,
} from '@/lib/candidatesListPresentation'
import { CandidateGovernedProfile } from '@/components/candidates/CandidateGovernedProfile'
import { ConfirmProvider } from '@/components/ConfirmDialog'
import type { ApplicationSummary } from '@/types'

function heldApp(overrides: Partial<ApplicationSummary> = {}): ApplicationSummary {
  return {
    app_key: 'imp-wathefni-noor-HELD',
    company_code: 'WATHEFNI',
    phone: 'imp-wathefni-hidden',
    status: 'needs_role',
    record_state: 'talent_pool',
    record_state_label: 'Talent Pool',
    is_held: true,
    status_display: 'Talent Pool',
    job_display: 'Not linked',
    assessment_display: '—',
    communication_display: 'No outreach',
    intake_source: 'email',
    ingested_at: new Date().toISOString(),
    grounded_contacts: { email: 'noor@cv.example', phone: '96550001111' },
    recruiter_owner: { label: 'Unassigned' },
    candidate: { name: 'Noor Tahat', email: 'noor@cv.example' },
    position: {},
    classification_chip: 'Technology · Software Engineering',
    cv: { received: true },
    cv_processing: { label: 'Ready', status: 'ready', received: true },
    allowed_actions: ['preview_cv'],
    identity: { compatibility_key_hidden: true, note: 'Compatibility identity is not shown.' },
    link_to_job: { enabled: false, label: 'Link to Job', reason: 'Reserved for future intake_admit.' },
    completeness: [
      { section: 'Skills', state: 'not_extracted', label: 'Skills not extracted' },
      { section: 'Languages', state: 'not_extracted', label: 'Languages not extracted' },
    ],
    privacy: { configured: false, message: 'Privacy and retention policy not configured' },
    ...overrides,
  }
}

function liveApp(overrides: Partial<ApplicationSummary> = {}): ApplicationSummary {
  return {
    app_key: 'APP-LIVE-1',
    company_code: 'WATHEFNI',
    phone: '96555511122',
    status: 'ready_for_review',
    canonical_stage: 'ready_for_review',
    record_state: 'active_application',
    record_state_label: 'Active application',
    is_held: false,
    intake_source: 'whatsapp',
    ingested_at: new Date().toISOString(),
    grounded_contacts: { email: 'hamad@example.com', phone: '96555511122' },
    candidate: { name: 'Hamad Almulla', email: 'hamad@example.com' },
    position: { code: 'ACCOUNTING_EXCEL', title: 'Accounting Excel' },
    classification_chip: 'Accounting',
    cv: { received: true },
    allowed_actions: ['shortlist', 'reject', 'preview_cv', 'notify'],
    ...overrides,
  }
}

describe('simplified Candidates list', () => {
  test('held rows show No job assigned and quiet Stage — without Talent Pool / New / contact / advisory chrome', () => {
    const application = heldApp()
    expect(isHeldCandidate(application)).toBe(true)
    expect(candidateListJobLabel(application, 'en')).toBe('No job assigned')
    expect(candidateListStageLabel(application, 'en')).toBe('—')
    expect(candidateListStageLabel(application, 'en')).not.toBe('New')
    expect(candidateExpertiseLabel(application, 'en')).toBe('Software Engineering')
    expect(candidateDisplayContact(application)).toBe('noor@cv.example')

    render(
      <table>
        <tbody>
          <CandidateTableRow application={application} assessmentEnabled onSelect={() => undefined} locale="en" />
        </tbody>
      </table>,
    )
    expect(screen.getByText('Noor Tahat')).toBeInTheDocument()
    expect(screen.getByText('No job assigned')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('New')).not.toBeInTheDocument()
    expect(screen.getByText('Software Engineering')).toBeInTheDocument()
    expect(screen.getByText(/Email ·/)).toBeInTheDocument()
    expect(screen.queryByText('Talent Pool')).not.toBeInTheDocument()
    expect(screen.queryByText('Not linked')).not.toBeInTheDocument()
    expect(screen.queryByText('noor@cv.example')).not.toBeInTheDocument()
    expect(screen.queryByText(/Advisory/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Unassigned/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/imp-/i)).not.toBeInTheDocument()
  })

  test('live rows keep job title and clean hiring stage', () => {
    const application = liveApp()
    render(
      <table>
        <tbody>
          <CandidateTableRow application={application} assessmentEnabled onSelect={() => undefined} locale="en" />
        </tbody>
      </table>,
    )
    expect(screen.getByText('Accounting Excel')).toBeInTheDocument()
    expect(screen.getByText('Ready for review')).toBeInTheDocument()
    expect(screen.getByText('Accounting')).toBeInTheDocument()
    expect(screen.getByText(/WhatsApp ·/)).toBeInTheDocument()
    expect(screen.queryByText('Not linked')).not.toBeInTheDocument()
  })

  test('person-first aggregation collapses confirmed same-email applications', () => {
    const people = aggregateCandidatesForList([
      liveApp({ app_key: 'APP-1', position: { code: 'FIN', title: 'Finance Manager' }, status: 'shortlisted', canonical_stage: 'shortlisted' }),
      liveApp({ app_key: 'APP-2', position: { code: 'ACC', title: 'Accountant' }, status: 'ready_for_review', canonical_stage: 'ready_for_review' }),
    ])
    expect(people).toHaveLength(1)
    expect(people[0].additionalActiveJobs).toBe(1)
    expect(candidateListJobLabel(people[0].primary, 'en', people[0].additionalActiveJobs)).toBe('2 applications')
  })

  test('uncertain same-name rows stay separate with a review warning', () => {
    const people = aggregateCandidatesForList([
      liveApp({ app_key: 'A', grounded_contacts: {}, candidate: { name: 'Sara Ali' }, phone: 'imp-a' }),
      liveApp({ app_key: 'B', grounded_contacts: {}, candidate: { name: 'Sara Ali' }, phone: 'imp-b', position: { code: 'HR', title: 'HR Officer' } }),
    ])
    expect(people).toHaveLength(2)
    expect(people.every((person) => person.identityReviewWarning)).toBe(true)
  })

  test('view pills use HR-facing labels and hide Restricted by default', () => {
    render(<CandidateViewPills value="all" onChange={() => undefined} locale="en" />)
    for (const label of ['All', 'With a job', 'No job assigned', 'Hired', 'Archived']) {
      expect(screen.getByRole('tab', { name: label })).toBeInTheDocument()
    }
    expect(screen.queryByRole('tab', { name: 'Restricted' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Talent Pool' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Restricted' })).not.toBeInTheDocument()
  })

  test('Restricted pill appears only when authorized', () => {
    render(<CandidateViewPills value="all" onChange={() => undefined} locale="en" showRestricted />)
    expect(screen.getByRole('tab', { name: 'Restricted' })).toBeInTheDocument()
  })

  test('received source labels normalize backend variants', () => {
    expect(candidateListReceivedLabel(heldApp({ intake_source: 'bulk_import', ingested_at: new Date().toISOString() }), 'en')).toMatch(/^Manual upload ·/)
    expect(candidateListReceivedLabel(heldApp({ intake_source: 'dashboard', ingested_at: new Date().toISOString() }), 'en')).toMatch(/^Manual upload ·/)
    expect(candidateListReceivedLabel(heldApp({ intake_source: '', data_source: '', ingested_at: new Date().toISOString() }), 'en')).toMatch(/^Unknown source ·/)
  })

  test('legacy helpers remain available for profile surfaces', () => {
    expect(candidateJobLabel(heldApp(), 'en')).toBe('No job assigned')
    expect(candidateStatusLabel(liveApp(), 'en')).toBe('Ready for review')
  })

  test('missing facts are not shown as negative facts and Link to Job is hidden until shipped', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/profile')) {
        return new Response(
          JSON.stringify({
            company_code: 'WATHEFNI',
            application: heldApp(),
            held_reason: 'This CV arrived without a confirmed Job link and is held in Talent Pool until HR links it.',
            facts: {
              completeness: heldApp().completeness,
              missing_policy: 'Missing facts are Not extracted or Unknown — never a negative fact',
              events: [],
            },
            privacy: heldApp().privacy,
            held_applications: [{ app_key: 'imp-wathefni-noor-HELD', status: 'needs_role' }],
            live_applications: [],
            processing_timeline: [{ label: 'Received', at: '2026-07-25' }],
            link_to_job: heldApp().link_to_job,
            files: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify({ detail: 'unexpected' }), { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ConfirmProvider>
        <CandidateGovernedProfile
          access={{ token: 't', companyCode: 'WATHEFNI', hrPhone: '', email: '' }}
          application={heldApp()}
          locale="en"
          onClose={() => undefined}
        />
      </ConfirmProvider>,
    )

    expect(await screen.findByText('Skills not extracted')).toBeInTheDocument()
    expect(screen.getByText('Languages not extracted')).toBeInTheDocument()
    expect(screen.getByText(/never a negative fact/i)).toBeInTheDocument()
    expect(screen.getByText('Privacy and retention policy not configured')).toBeInTheDocument()
    expect(screen.getByText(/do not expose recruiting lifecycle/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Link to Job' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Not implemented in this phase/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/imp-wathefni-hidden/)).not.toBeInTheDocument()
  })
})
