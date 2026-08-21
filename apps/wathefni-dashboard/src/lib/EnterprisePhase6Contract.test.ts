import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import { URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

const ENTERPRISE_PAGES = [
  'performance',
  'talent',
  'learning',
  'benefits',
  'employee-relations',
  'engagement',
  'compensation-planning',
  'workforce-planning',
  'job-architecture',
  'analytics',
] as const

describe('HR Web Phase 6 enterprise flagship UX', () => {
  it('reuses shared chrome without collapsing flagship workflows into admin tables', () => {
    const performance = read('posthire/PerformanceWorkspace.tsx')
    const talent = read('posthire/TalentWorkspace.tsx')
    const intelligence = read('posthire/intelligence/IntelligenceWorkspace.tsx')
    expect(performance).toContain('HrSurfaceTabs')
    expect(performance).toContain('getPerformanceWorkspace')
    expect(performance).toContain('postPerformanceJson')
    expect(performance).toContain('9-box vocabulary is forbidden')
    expect(performance).not.toContain('hipo')
    expect(talent).toContain('HrSurfaceTabs')
    expect(talent).toContain("id: 'ninebox'")
    expect(talent).toContain('There is no universal Talent score.')
    expect(talent).toContain('getTalentMap')
    expect(intelligence).toContain('evaluateIntelligenceMetric')
    expect(intelligence).toContain('drillIntelligenceMetric')
    expect(intelligence).toContain('Ops Attention is separate from Intelligence')
    expect(intelligence).not.toContain('hover:-translate-y')
    expect(intelligence).not.toContain('#fffdf8')
    expect(intelligence).not.toMatch(/turnover\s*=/i)
  })

  it('URL-backs enterprise chrome that should survive refresh/back', () => {
    expect(URL_BACKED_WORKSPACE_TABS.performance).toContain('goals')
    expect(URL_BACKED_WORKSPACE_TABS.talent).toEqual([
      'overview',
      'people',
      'reviews',
      'succession',
      'mobility',
      'ninebox',
      'models',
      'rolefit',
      'map',
    ])
    expect(URL_BACKED_WORKSPACE_TABS.learning).toContain('assignments')
    expect(URL_BACKED_WORKSPACE_TABS['employee-relations']).toContain('detail')
    const app = read('App.tsx')
    expect(app).toContain('isEnterpriseFlagshipPage')
    expect(app).toContain("page === 'analytics'")
    expect(read('posthire/LearningWorkspace.tsx')).toContain('HrSurfaceTabs')
    expect(read('posthire/BenefitsWorkspace.tsx')).toContain('HrSurfaceTabs')
    expect(read('posthire/EmployeeRelationsWorkspace.tsx')).toContain("useUrlBackedParam('employee-relations', 'q'")
    expect(read('posthire/EngagementWorkspace.tsx')).toContain("useUrlBackedParam('engagement', 'q'")
    expect(read('posthire/CompensationPlanningWorkspace.tsx')).toContain(
      "useUrlBackedParam('compensation-planning', 'q'",
    )
    expect(read('posthire/WorkforcePlanningWorkspace.tsx')).toContain('HrSurfaceTabs')
    expect(read('posthire/JobArchitectureWorkspace.tsx')).toContain('HrSurfaceTabs')
    expect(read('posthire/intelligence/IntelligenceWorkspace.tsx')).toContain("useUrlBackedParam('analytics', 'q'")
  })

  it('keeps mutations and KPI methodology backend-canonical', () => {
    const performance = read('posthire/PerformanceWorkspace.tsx')
    const talent = read('posthire/TalentWorkspace.tsx')
    const intelligence = read('posthire/intelligence/IntelligenceWorkspace.tsx')
    expect(performance).toContain('postPerformanceJson')
    expect(performance).not.toContain('optimistic')
    expect(talent).toContain('postTalentJson')
    expect(talent).not.toContain('optimistic')
    expect(intelligence).toContain('evaluateIntelligenceMetric')
    expect(intelligence).toContain('getIntelligenceTrend')
    expect(intelligence).toContain('segmentIntelligenceMetric')
    expect(intelligence).toContain('status === \'suppressed\'')
    expect(intelligence).not.toContain('optimistic')
  })

  it('registers Phase 6 surfaces as canonical with query-backed chrome', () => {
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
    for (const page of ENTERPRISE_PAGES) {
      expect(byId[`page.${page}`]?.migration_status).toBe('canonical')
      expect(byId[`page.${page}`]?.notes || '').toMatch(/Phase 6/)
    }
    expect(byId['tab.performance.goals']?.url_state).toBe('query')
    expect(byId['tab.talent.succession']?.url_state).toBe('query')
    expect(byId['tab.talent.ninebox']?.notes || '').toMatch(/Phase 6/)
    expect(byId['drawer.analytics.metric']?.url_state).toBe('query')
    expect(byId['drawer.analytics.metric']?.notes || '').toMatch(/Phase 6/)
  })
})
