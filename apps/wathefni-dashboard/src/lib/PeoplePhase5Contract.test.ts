import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import {
  EMPLOYEE_ONBOARDING_FILTERS,
  EMPLOYEE_STATUS_FILTERS,
  URL_BACKED_VIEW_PAGES,
  URL_BACKED_WORKSPACE_TABS,
} from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

describe('HR Web Phase 5 People spine UX', () => {
  it('reuses Phase 3/4 chrome without collapsing People workflows', () => {
    const employees = read('posthire/PostHire.tsx')
    const workforce = read('posthire/employees360/WorkforcePage.tsx')
    const preboarding = read('posthire/PreboardingWorkspace.tsx')
    const probation = read('posthire/ProbationWorkspace.tsx')
    const header = read('components/hr/HrPageHeader.tsx')
    const anchors = read('components/hr/HrAnchorNav.tsx')
    expect(header).toContain("density?: 'hero' | 'page'")
    expect(anchors).toContain('scrollIntoView')
    expect(employees).toContain('function EmployeesPage(')
    expect(employees).toContain('HrSection')
    expect(employees).toContain('SoftKeepSurface')
    expect(employees).toContain('employees-directory-board')
    expect(employees).toContain('data-testid="employee-profile"')
    expect(employees).toContain('HrAnchorNav')
    expect(employees).toContain('id="emp360-section-onboarding"')
    expect(employees).toContain('needs-attention-board')
    expect(workforce).toContain("useUrlBackedTab('workforce'")
    expect(workforce).toContain('organization-structure-board')
    expect(preboarding).toContain('HrSurfaceTabs')
    expect(probation).toContain('HrSurfaceTabs')
    expect(employees).toContain('OnboardingDetailDrawer')
  })

  it('URL-backs People chrome that should survive refresh/back', () => {
    expect(URL_BACKED_VIEW_PAGES.employees).toEqual(['', 'migration'])
    expect(EMPLOYEE_STATUS_FILTERS).toEqual(['active', 'left', 'all'])
    expect(EMPLOYEE_ONBOARDING_FILTERS).toEqual(['any', 'open', 'complete', 'not_started'])
    expect(URL_BACKED_WORKSPACE_TABS.workforce).toEqual([
      'organization',
      'lifecycle',
      'remediation',
      'migration',
      'requests',
    ])
    expect(URL_BACKED_WORKSPACE_TABS.onboarding).toEqual([
      'needs_attention',
      'in_progress',
      'not_started',
      'completed',
      'all',
    ])
    expect(URL_BACKED_WORKSPACE_TABS.inbox).toEqual(['needs_action', 'due_soon', 'blocked', 'all'])
    const employees = read('posthire/PostHire.tsx')
    expect(employees).toContain("useUrlBackedParam('employees', 'employee'")
    expect(employees).toContain("useUrlBackedParam('employees', 'q'")
    expect(employees).toContain("useUrlBackedTab('employees', EMPLOYEE_STATUS_FILTERS")
    expect(employees).toContain("useUrlBackedTab('onboarding', URL_BACKED_WORKSPACE_TABS.onboarding")
    expect(employees).toContain("useUrlBackedTab('inbox', URL_BACKED_WORKSPACE_TABS.inbox")
    const app = read('App.tsx')
    expect(app).toContain('isPeopleSpinePage')
    expect(app).toContain('usesCanonicalPageHeader')
  })

  it('keeps Employee 360 as a record, not a second source of truth', () => {
    const employees = read('posthire/PostHire.tsx')
    const profileStart = employees.indexOf('function EmployeeProfile(')
    const profileEnd = employees.indexOf('// --- Onboarding')
    const profile = employees.slice(profileStart, profileEnd)
    expect(profile).toContain('Open in Onboarding')
    expect(profile).not.toContain('onboarding_mark_item')
    expect(profile).toContain('Open in Payroll')
    expect(profile).not.toContain('run_payroll')
    expect(profile).toContain('next_actions')
  })

  it('keeps Action Inbox as a routing surface with published totals', () => {
    const employees = read('posthire/PostHire.tsx')
    const inboxStart = employees.indexOf('function ActionInboxPage(')
    const inbox = employees.slice(inboxStart, employees.indexOf('function AnalyticsPage(', inboxStart))
    expect(inbox).toContain('summary?.total')
    expect(inbox).toContain('honorsEmployee')
    expect(inbox).not.toContain('groupByEmployee')
    expect(inbox).not.toContain('optimistic')
  })

  it('registers Phase 5 People surfaces as canonical', () => {
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
    for (const id of [
      'page.employees',
      'page.workforce',
      'page.onboarding',
      'page.preboarding',
      'page.probation',
      'page.inbox',
      'detail.employees.profile',
    ]) {
      expect(byId[id]?.migration_status).toBe('canonical')
      expect(byId[id]?.notes || '').toMatch(/Phase 5/)
    }
    expect(byId['tab.workforce.organization']?.url_state).toBe('query')
    expect(byId['tab.onboarding.needs_attention']?.url_state).toBe('query')
    expect(byId['tab.inbox.needs_action']?.url_state).toBe('query')
  })
})
