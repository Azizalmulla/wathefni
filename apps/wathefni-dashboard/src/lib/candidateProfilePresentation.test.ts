import { describe, expect, it } from 'vitest'

import type { ApplicationSummary, CandidatePersonProfileResponse } from '@/types'
import {
  applicationNextActionLabel,
  candidateJobHeaderLabel,
  candidateStageHeaderLabel,
  cvVersionsFromProfile,
  hasDuplicateJobApplication,
  headerMetaParts,
  humanActivityItems,
  offerEligible,
  openAssignableJobs,
  overviewFromProfile,
  profileOverviewDetails,
} from '@/lib/candidateProfilePresentation'

function app(partial: Partial<ApplicationSummary>): ApplicationSummary {
  return {
    app_key: partial.app_key || 'app-1',
    company_code: 'DEMO',
    phone: partial.phone || '96550000000',
    ...partial,
  }
}

describe('candidateProfilePresentation', () => {
  it('shows No job assigned and non-technical stage for general candidates', () => {
    const general = app({
      status: 'needs_role',
      record_state: 'talent_pool',
      is_held: true,
      status_display: 'Talent Pool',
      job_display: 'Not linked',
    })
    expect(candidateJobHeaderLabel(general, 'en')).toBe('No job assigned')
    // Talent Pool / needs_role uses quiet em dash — never technical "New".
    expect(candidateStageHeaderLabel(general, 'en')).toBe('—')
    expect(applicationNextActionLabel(general, 'en', { assessmentEnabled: true, videoInterviewsEnabled: true })).toBe('Add to job')
  })

  it('renders canonical profile_facts strings only', () => {
    const person = {
      company_code: 'DEMO',
      application: app({ intake_source: 'email', ingested_at: new Date().toISOString() }),
      applications: [],
      profile_facts: {
        schema: 'candidate-profile-facts-v1',
        skills: ['Python', 'React'],
        education: ['BSc Computer Science'],
        employment: ['Intern · Acme'],
        languages: ['English'],
        location: 'Kuwait',
        professional_summary: 'Results-oriented Computer Science undergraduate.',
        primary_expertise: 'Computer Science',
        experience_years: null,
      },
      person: { display_name: 'yasser al dossary' },
    } as CandidatePersonProfileResponse

    const overview = overviewFromProfile(person.application, person, 'en')
    expect(overview.name).toBe('Yasser Al Dossary')
    expect(overview.summary).toContain('Computer Science')
    expect(overview.skills).toEqual(['Python', 'React'])
    expect(overview.education).toEqual(['BSc Computer Science'])
    expect(overview.location).toBe('Kuwait')
    expect(overview.expertise).toBe('Computer Science')
    expect(overview.experienceYears).toBe('')
    expect(headerMetaParts(person.application, person, 'en')).toEqual(['Computer Science', 'Kuwait'])
  })

  it('omits Not identified placeholders from header meta', () => {
    const person = {
      company_code: 'DEMO',
      application: app({ status: 'needs_role', is_held: true }),
      applications: [],
      profile_facts: {
        skills: [],
        education: [],
        employment: ['One role blob'],
        languages: [],
        location: null,
        professional_summary: null,
        primary_expertise: null,
        experience_years: null,
      },
    } as CandidatePersonProfileResponse
    expect(headerMetaParts(person.application, person, 'en')).toEqual([])
  })

  it('presents structured experience and education without flattened CV rows', () => {
    const person = {
      company_code: 'DEMO',
      application: app({}),
      applications: [],
      profile_facts: {
        schema: 'candidate-profile-facts-v2',
        skills: ['Python'],
        education: ['BSc · Gulf University · Kuwait · 2022 – 2026 · GPA: 3.7/4.0 · Honors'],
        employment: ['Developer · Acme · 2024 – Present'],
        languages: ['Arabic', 'English'],
        structured: {
          employment: [{
            title: 'Developer',
            company: 'Acme',
            location: 'Kuwait',
            start_date: '2024',
            end_date: 'Present',
            description: 'Built internal systems.',
            achievements: ['Reduced processing time'],
          }],
          education: [{
            degree: 'BSc Computer Science',
            institution: 'Gulf University',
            location: 'Kuwait',
            start_date: '2022',
            end_date: '2026',
            gpa: '3.7/4.0',
            honors: 'Graduated with Honors; Activities: Robotics Club',
          }],
        },
      },
    } as CandidatePersonProfileResponse

    const details = profileOverviewDetails(person)
    expect(details.experience[0]).toMatchObject({
      title: 'Developer',
      company: 'Acme',
      period: '2024 – Present',
    })
    expect(details.education[0]).toMatchObject({
      degree: 'BSc Computer Science',
      institution: 'Gulf University',
      gpa: '3.7/4.0',
      details: ['Graduated with Honors', 'Activities: Robotics Club'],
    })
  })

  it('decomposes flattened education rows when structured V2 details are unavailable', () => {
    const person = {
      company_code: 'DEMO',
      application: app({}),
      applications: [],
      profile_facts: {
        skills: [],
        education: ['BSc Computer Science · Gulf University · Kuwait · 2022 – 2026 · GPA: 3.7/4.0 · Member of the Technology Club'],
        employment: [],
        languages: [],
      },
    } as CandidatePersonProfileResponse

    const education = profileOverviewDetails(person).education[0]
    expect(education.degree).toBe('BSc Computer Science')
    expect(education.institution).toBe('Gulf University')
    expect(education.period).toBe('2022 – 2026')
    expect(education.gpa).toBe('3.7/4.0')
    expect(education.details).toEqual(['Member of the Technology Club'])
  })

  it('detects duplicate job applications and filters open jobs', () => {
    const related = [
      app({ app_key: 'held', status: 'needs_role', record_state: 'talent_pool', is_held: true }),
      app({ app_key: 'live', status: 'shortlisted', canonical_stage: 'shortlisted', position: { code: 'WELDER', title: 'Welder' } }),
    ]
    expect(hasDuplicateJobApplication(related, 'WELDER')).toBe(true)
    expect(hasDuplicateJobApplication(related, 'DRIVER')).toBe(false)
    const jobs = openAssignableJobs(
      [
        { position_code: 'WELDER', position_title: 'Welder', title: 'Welder', status: 'open', application_count: 0, active_count: 0 },
        { position_code: 'DRIVER', position_title: 'Driver', title: 'Driver', status: 'open', application_count: 0, active_count: 0 },
        { position_code: 'CLOSED', position_title: 'Closed', title: 'Closed', status: 'closed', application_count: 0, active_count: 0 },
      ],
      related,
    )
    expect(jobs.map((job) => job.position_code)).toEqual(['DRIVER'])
  })

  it('filters technical activity wording and gates offers', () => {
    const live = app({
      status: 'shortlisted',
      canonical_stage: 'shortlisted',
      position: { code: 'DRIVER', title: 'Driver' },
      automatic_activity: ['CV received', 'review_held_intake', 'Talent Pool sync'],
      waiting_for_hr: ['needs_role'],
      allowed_actions: ['hire'],
    })
    expect(humanActivityItems(live, 'en').join(' ')).toContain('CV received')
    expect(humanActivityItems(live, 'en').join(' ')).not.toMatch(/held|Talent Pool|needs_role/i)
    expect(offerEligible(live, true)).toBe(true)
    expect(offerEligible(app({ status: 'needs_role', record_state: 'talent_pool', is_held: true }), true)).toBe(false)
  })

  it('does not repeat current CV under previous versions', () => {
    const versions = cvVersionsFromProfile({
      company_code: 'DEMO',
      application: app({}),
      applications: [],
      cv_versions: {
        current: { id: 'doc-1', filename: 'cv.pdf', created_at: '2026-07-01', latest: true },
        previous: [
          { id: 'doc-1', filename: 'cv.pdf', created_at: '2026-07-01', latest: true },
          { id: 'doc-0', filename: 'old.pdf', created_at: '2026-06-01', latest: false },
        ],
      },
    } as CandidatePersonProfileResponse)
    expect(versions.current?.filename).toBe('cv.pdf')
    expect(versions.previous.map((item) => item.id)).toEqual(['doc-0'])
  })
})
