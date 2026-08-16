import { describe, expect, it } from 'vitest'

import {
  aggregateCandidatesForList,
  candidateExpertiseLabel,
  candidateListFooterLabel,
  candidateListJobLabel,
  candidateListJobPresentation,
  candidateListStageBucket,
  candidateListStageFilterStatuses,
  candidateListStageLabel,
  CANDIDATE_LIST_STAGE_FILTER_STATUSES,
  CANDIDATE_LIST_STAGE_FILTERS,
  formatCandidateDisplayName,
  normalizeListSourceKey,
} from '@/lib/candidatesListPresentation'
import type { ApplicationSummary } from '@/types'

function app(overrides: Partial<ApplicationSummary> = {}): ApplicationSummary {
  return {
    app_key: 'A1',
    company_code: 'WATHEFNI',
    phone: '96550001111',
    status: 'ready_for_review',
    canonical_stage: 'ready_for_review',
    candidate: { name: 'Amina Saleh', email: 'amina@example.com' },
    grounded_contacts: { email: 'amina@example.com', phone: '96550001111' },
    position: { code: 'HR', title: 'HR Officer' },
    intake_source: 'email',
    ...overrides,
  }
}

describe('candidatesListPresentation', () => {
  it('cleans expertise chips to a single professional field', () => {
    expect(candidateExpertiseLabel(app({ classification_chip: 'Advisory: Technology · Software Engineering' }), 'en')).toBe('Software Engineering')
    expect(candidateExpertiseLabel(app({ classification_chip: null }), 'en')).toBe('Not identified')
    expect(candidateExpertiseLabel(app({ classification_chip: '' }), 'ar')).toBe('غير محدد')
  })

  it('keeps Talent Pool off Stage New and maps legacy offer to Shortlisted', () => {
    expect(candidateListStageLabel(app({ status: 'offer_sent', canonical_stage: null }), 'en')).toBe('Shortlisted')
    expect(candidateListStageLabel(app({ status: 'offered', canonical_stage: null }), 'en')).toBe('Shortlisted')
    expect(candidateListStageLabel(app({
      status: 'needs_role',
      record_state: 'talent_pool',
      is_held: true,
      status_display: 'Talent Pool',
    }), 'en')).toBe('—')
    expect(candidateListStageBucket(app({
      status: 'import_review',
      record_state: 'talent_pool',
      is_held: true,
    }))).toBe('none')
    expect(candidateListStageLabel(app({ status: 'mystery_legacy', canonical_stage: null }), 'en')).toBe('Unknown')
  })

  it('maps every canonical Stage bucket and legacy aliases for display + filter', () => {
    const cases: Array<{ status: string; bucket: string; filterValue: string }> = [
      { status: 'awaiting_cv', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'cv_processing', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'cv_received', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'screening', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'cv_request', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'cv_upload', bucket: 'new', filterValue: 'awaiting_cv' },
      { status: 'ready_for_review', bucket: 'ready_for_review', filterValue: 'ready_for_review' },
      { status: 'screening_complete', bucket: 'ready_for_review', filterValue: 'ready_for_review' },
      { status: 'review_pending', bucket: 'ready_for_review', filterValue: 'ready_for_review' },
      { status: 'shortlisted', bucket: 'shortlisted', filterValue: 'shortlisted' },
      { status: 'offered', bucket: 'shortlisted', filterValue: 'shortlisted' },
      { status: 'offer_sent', bucket: 'shortlisted', filterValue: 'shortlisted' },
      { status: 'interview', bucket: 'interview', filterValue: 'interview' },
      { status: 'scheduled', bucket: 'interview', filterValue: 'interview' },
      { status: 'hired', bucket: 'hired', filterValue: 'hired' },
      { status: 'rejected', bucket: 'rejected', filterValue: 'rejected' },
      { status: 'withdrawn', bucket: 'withdrawn', filterValue: 'withdrawn' },
    ]

    for (const item of cases) {
      expect(candidateListStageBucket(app({ status: item.status, canonical_stage: null }))).toBe(item.bucket)
      const expanded = candidateListStageFilterStatuses(item.filterValue)
      expect(expanded).toContain(item.status)
      expect(expanded).toEqual([...CANDIDATE_LIST_STAGE_FILTER_STATUSES[item.filterValue]])
    }

    // Toolbar "New" must not include Talent Pool intake statuses.
    expect(candidateListStageFilterStatuses('awaiting_cv')).toEqual([
      'awaiting_cv',
      'cv_processing',
      'cv_received',
      'screening',
      'cv_request',
      'cv_upload',
    ])
    expect(candidateListStageFilterStatuses('awaiting_cv')).not.toContain('needs_role')
    expect(candidateListStageFilterStatuses('awaiting_cv')).not.toContain('import_review')
    expect(candidateListStageFilterStatuses('shortlisted')).toEqual(['shortlisted', 'offered', 'offer_sent'])
    expect(CANDIDATE_LIST_STAGE_FILTERS.find((item) => item.en === 'New')?.value).toBe('awaiting_cv')
  })

  it('expands raw legacy aliases to the same Stage filter set', () => {
    expect(candidateListStageFilterStatuses('screening')).toEqual(candidateListStageFilterStatuses('awaiting_cv'))
    expect(candidateListStageFilterStatuses('screening_complete')).toEqual(
      candidateListStageFilterStatuses('ready_for_review'),
    )
    expect(candidateListStageFilterStatuses('scheduled')).toEqual(candidateListStageFilterStatuses('interview'))
    expect(candidateListStageFilterStatuses('offer_sent')).toEqual(candidateListStageFilterStatuses('shortlisted'))
    expect(candidateListStageFilterStatuses('offered')).toEqual(candidateListStageFilterStatuses('shortlisted'))
  })

  it('normalizes source variants for list display', () => {
    expect(normalizeListSourceKey(app({ intake_source: 'bulk' }))).toBe('manual')
    expect(normalizeListSourceKey(app({ intake_source: 'recruiting_email' }))).toBe('email')
    expect(normalizeListSourceKey(app({ intake_source: 'octopus_whatsapp' }))).toBe('whatsapp')
  })

  it('shows No job assigned for general candidates', () => {
    expect(candidateListJobLabel(app({
      is_held: true,
      record_state: 'talent_pool',
      status: 'needs_role',
      job_display: 'Not linked',
      position: {},
    }), 'en')).toBe('No job assigned')
  })

  it('does not merge people without confirmed contact identity', () => {
    const people = aggregateCandidatesForList([
      app({ app_key: '1', grounded_contacts: {}, phone: 'imp-1', candidate: { name: 'Same Name' } }),
      app({ app_key: '2', grounded_contacts: {}, phone: 'imp-2', candidate: { name: 'Same Name' } }),
    ])
    expect(people).toHaveLength(2)
    expect(people[0].identityReviewWarning).toBe(true)
  })

  it('formats Latin casing conservatively and preserves Arabic / mixed case', () => {
    expect(formatCandidateDisplayName('yasser al dossary')).toBe('Yasser Al Dossary')
    expect(formatCandidateDisplayName('HAMAD ALMULLA')).toBe('Hamad Almulla')
    expect(formatCandidateDisplayName('Aziz Almulla')).toBe('Aziz Almulla')
    expect(formatCandidateDisplayName('محمد أحمد')).toBe('محمد أحمد')
  })

  it('shows application-count only for multi-app people', () => {
    const one = candidateListJobPresentation(app({ position: { code: 'HR', title: 'HR' } }), 'en', 0)
    expect(one.title).toBe('HR')
    expect(one.activeApplications).toBe(1)

    const multi = candidateListJobPresentation(app({ position: { code: 'HR', title: 'HR' } }), 'en', 3)
    expect(multi.title).toBe('4 applications')
    expect(multi.activeApplications).toBe(4)
    expect(candidateListJobLabel(app({ position: { code: 'HR', title: 'HR' } }), 'en', 3)).toBe('4 applications')
    expect(candidateListJobLabel(app({ position: { code: 'HR', title: 'HR' } }), 'ar', 1)).toBe('طلبان')
    expect(candidateListJobLabel(app({ position: { code: 'HR', title: 'HR' } }), 'ar', 2)).toBe('3 طلبات')
  })

  it('uses person-level footer copy only', () => {
    expect(candidateListFooterLabel(7, 0, 25, 'en')).toBe('Showing 1–7 of 7 candidates')
    expect(candidateListFooterLabel(1, 0, 25, 'en')).toBe('1 candidate')
    expect(candidateListFooterLabel(0, 0, 25, 'en')).toBe('No candidates to show')
  })
})
