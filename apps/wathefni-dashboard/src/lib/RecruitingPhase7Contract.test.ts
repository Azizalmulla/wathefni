import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import { URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

const RECRUITING_PAGES = [
  'ai',
  'jobs',
  'requisitions',
  'candidates',
  'interviews',
  'calendar',
  'assessments',
  'ranking',
  'reports',
] as const

describe('HR Web Phase 7 recruiting / pre-hiring UX', () => {
  it('reuses shared chrome without flattening recruiting personalities', () => {
    const app = read('App.tsx')
    const jobs = read('pages/JobsPage.tsx')
    const requisitions = read('prehire/RequisitionsWorkspace.tsx')
    const candidates = read('components/candidates/CandidatesTable.tsx')
    const interviews = read('pages/InterviewsPage.tsx')
    const assessments = read('pages/AssessmentsPage.tsx')
    const calendar = read('components/CalendarShell.tsx')
    const ranking = read('pages/RankingPage.tsx')
    const reports = read('pages/ReportsPage.tsx')
    const assistant = read('pages/AdminAIPage.tsx')

    expect(app).toContain('isRecruitingPrehirePage')
    expect(app).toContain('usesCanonicalPageHeader')
    expect(app).toContain("'Recruiting'")
    expect(app).toContain("pagePersonality === 'spatial' ? 'h-8 w-8 px-0")
    expect(app).toContain("activePage === 'ai' ? undefined : pageSubtitle")

    expect(jobs).toContain('HrSection')
    expect(jobs).toContain('jobs-status-tiles')
    expect(jobs).toContain('bg-wf-accent-priority-soft')
    expect(jobs).not.toContain('HrSurfaceTabs')

    expect(requisitions).toContain('HrSurfaceTabs')
    expect(requisitions).toContain('useUrlBackedTab')
    expect(requisitions).toContain('paintedRef')
    expect(requisitions).toContain('postRequisitionTransition')
    expect(requisitions).not.toContain('<h1')

    expect(candidates).toContain('HrSurfaceTabs')
    expect(candidates).toContain('candidate-view-pills')
    expect(candidates).toContain("'talent_pool'")
    expect(candidates).toContain("'restricted'")

    expect(interviews).toContain('HrSurfaceTabs')
    expect(interviews).toContain('interview-status-tiles')
    expect(interviews).toContain('interviewTabUpcoming')
    expect(interviews).toContain('video_interviews')

    expect(assessments).toContain('HrSurfaceTabs')
    expect(assessments).toContain('fetchAssessmentReport')
    expect(assessments).toContain('cachedPayload')

    expect(calendar).toContain('useUrlBackedTab')
    expect(calendar).toContain('useUrlBackedParam')
    expect(calendar).toContain('data-calendar-wave1c')
    expect(calendar).toContain('Managed through Interviews')

    expect(ranking).toContain('rankingComponentRows')
    expect(ranking).toContain('rankingCopy(locale, \'cv_evidence\')')
    expect(ranking).not.toMatch(/score\s*=\s*[^=]/)
    expect(ranking).not.toContain('HrSurfaceTabs')

    expect(reports).toContain('bg-semantic-ink px-2 text-[11px] font-semibold text-white')
    expect(reports).toContain('interview_debt')
    expect(reports).not.toContain('HrSurfaceTabs')

    expect(assistant).toContain('emptyState')
    expect(assistant).toContain('assistant-empty-chips')
    expect(read('lib/api.ts')).toContain('/dashboard/prehire/assistant/capabilities')
    expect(assistant).not.toContain('function assistantPromptChips')
    expect(assistant).not.toMatch(/assistant-empty-chips[\s\S]{0,800}wf-accent-/)
    expect(assistant).not.toMatch(/assistant-empty-chips[\s\S]{0,400}hover:-translate-y/)
  })

  it('URL-backs recruiting chrome that should survive refresh', () => {
    expect(URL_BACKED_WORKSPACE_TABS.requisitions).toEqual([
      'attention',
      'draft',
      'pending_approval',
      'approved',
      'open',
      'filled',
    ])
    expect(URL_BACKED_WORKSPACE_TABS.calendar).toEqual(['day', 'week', 'month'])
    const nav = read('lib/dashboardNavigation.ts')
    expect(nav).toContain("state.page === 'jobs' || state.page === 'requisitions'")
    expect(nav).toContain("state.page === 'attendance' || state.page === 'calendar'")
    const app = read('App.tsx')
    expect(app).toContain('jobsStatusFilter')
    expect(app).toContain('interviewQuery.trim()')
  })

  it('keeps ranking and assistant as consumers of backend authority', () => {
    const ranking = read('pages/RankingPage.tsx')
    const presentation = read('lib/rankingPresentation.ts')
    const assistant = read('pages/AdminAIPage.tsx')
    const app = read('App.tsx')
    expect(ranking).toContain('ranking?.needs_run')
    expect(ranking).toContain('rankingEligibilityLabel')
    expect(presentation).toContain("group: 'cv'")
    expect(assistant).toContain('emptyState')
    expect(app).toContain('getAssistantCapabilities')
    expect(read('lib/api.ts')).toContain('/dashboard/prehire/assistant/capabilities')
    expect(app).not.toContain('rankCandidatesLocally')
  })

  it('registers Phase 7 surfaces as canonical', () => {
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
    for (const page of RECRUITING_PAGES) {
      expect(byId[`page.${page}`]?.migration_status).toBe('canonical')
      expect(byId[`page.${page}`]?.notes || '').toMatch(/Phase 7/)
    }
    expect(byId['tab.requisitions.attention']?.url_state).toBe('query')
    expect(byId['tab.calendar.week']?.url_state).toBe('query')
    expect(byId['tab.candidates.view.talent_pool']?.url_state).toBe('query')
    expect(byId['tab.interviews.upcoming']?.url_state).toBe('query')
    expect(byId['tab.assessments.send']?.url_state).toBe('query')
  })
})
