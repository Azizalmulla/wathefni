import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, test } from 'vitest'

import { FRESHNESS_MS } from './query/freshness'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

describe('HR Web interaction performance audit (source + contracts, no fake mutations)', () => {
  test('page switches unmount the previous module; return visits skip the full-page skeleton', () => {
    const app = read('App.tsx')
    expect(app).toContain('fallback={<PagePaintFallback page={activePage} />}')
    expect(app).not.toContain('fallback={<PageSkeleton />}')
    expect(app).toContain("{activePage === 'jobs' && (")
    expect(app).toContain("{activePage === 'candidates' && (")
    expect(app).toContain('<LazyPostHirePage')
    expect(app).toContain('onPointerEnter={() => prefetchDestination(item.id)}')
    // No keep-alive cache of every visited page.
    expect(app).not.toContain('hidden={activePage !==')
  })

  test('PostHire dispatcher lazy-loads per workspace instead of one giant chunk', () => {
    const lazy = read('pages/lazy.tsx')
    const dispatcher = read('posthire/PostHireDispatcher.tsx')
    expect(lazy).toContain("import('@/posthire/PostHireDispatcher')")
    expect(dispatcher).toContain("import('@/posthire/LeaveWorkspace')")
    expect(dispatcher).toContain("import('@/posthire/TalentWorkspace')")
    expect(dispatcher).toContain('function PaintFallback')
    expect(dispatcher).toContain('if (pageChunkLoaded(page)) return null')
  })

  test('pre-hire query layer already soft-keeps list refetches; work-queue correctly opts out', () => {
    const hooks = read('lib/query/hooks.ts')
    const client = read('lib/query/client.ts')
    expect(client).toContain('placeholderData: keepPreviousData')
    expect(hooks).toContain('placeholderData: undefined')
    expect(hooks).toContain('useWorkQueueQuery')
    expect(FRESHNESS_MS.workQueue).toBe(60_000)
    expect(FRESHNESS_MS.applications).toBe(90_000)
  })

  test('Overview boot path still does not prefetch sibling module lists', () => {
    const server = read('lib/query/useDashboardServerState.ts')
    expect(server).toContain('const appsEnabled = ready && prehireOn && page === \'candidates\'')
    expect(server).toContain('const interviewsEnabled = ready && prehireOn && page === \'interviews\'')
    expect(server).toContain('const assessmentsEnabled = ready && prehireOn && assessmentsOn && page === \'assessments\'')
    expect(server).toContain("page === 'reports'")
    const prefetch = read('lib/hrWebNavPrefetch.ts')
    expect(prefetch).not.toContain('fetchApplications')
  })

  test('applyNavStateToUi uses the registry page gate instead of the incomplete navItems list', () => {
    const app = read('App.tsx')
    expect(app).toContain('isRegisteredDashboardPage(requested)')
    expect(app).toContain('isRegisteredDashboardPage(nav.page)')
    expect(app).not.toContain('navItems.some((item) => item.id === requested)')
    expect(app).not.toContain('navItems.some((item) => item.id === nav.page)')
  })

  test('enterprise workspace tabs and Settings sections are URL-backed', () => {
    const talent = read('posthire/TalentWorkspace.tsx')
    const settings = read('pages/SettingsPage.tsx')
    const leave = read('posthire/LeaveWorkspace.tsx')
    expect(talent).toContain("useUrlBackedTab<Tab>('talent'")
    expect(talent).not.toContain("useState<Tab>('overview')")
    expect(settings).toContain("useUrlBackedTab<SettingsSection>('settings'")
    expect(leave).toContain("useUrlBackedTab<'active' | 'history'>('leave'")
  })

  test('mutations stay backend-canonical (no optimistic payroll/leave success)', () => {
    const payroll = read('posthire/PostHire.tsx')
    expect(payroll).not.toMatch(/onMutate[\s\S]{0,200}payroll/)
    expect(payroll).not.toContain('optimistic')
    const client = read('lib/query/client.ts')
    expect(client).toContain('mutations: {')
    expect(client).toContain('retry: 0')
  })

  test('StatusPill and ResourceState empty use semantic tokens instead of one-off hex', () => {
    const chrome = read('components/ui/page-chrome.tsx')
    expect(chrome).toContain("tone === 'neutral' && 'bg-semantic-accent-soft text-semantic-ink-muted'")
    expect(chrome).not.toContain("bg-[#eee5d4]")
    const dataState = read('pages/shared/dataState.tsx')
    expect(dataState).toContain('bg-semantic-accent')
    expect(dataState).not.toContain('bg-[#c89445]')
  })

  test('operational core surfaces are URL-backed (Leave view, Shifts/Payroll tabs, Attendance dates)', () => {
    const leave = read('posthire/LeaveWorkspace.tsx')
    const shifts = read('posthire/ShiftsWorkspace.tsx')
    const payroll = read('posthire/PostHire.tsx')
    const urlTab = read('lib/hrWebUrlTab.ts')
    expect(leave).toContain("useUrlBackedTab<'active' | 'history'>('leave'")
    expect(shifts).toContain("useUrlBackedTab<SurfaceTab>('shifts'")
    expect(payroll).toContain("useUrlBackedTab<'run' | 'hours' | 'records'>")
    expect(payroll).toContain("useUrlBackedTab<'payslips' | 'close' | 'statutory'>")
    expect(payroll).toContain('useUrlBackedDateRange')
    expect(payroll).toContain('function AttendancePage(')
    expect(urlTab).toContain("shifts: ['schedule', 'requests', 'planning']")
    expect(urlTab).toContain("payroll: ['run', 'hours', 'records']")
  })

  test('People spine surfaces are URL-backed (employee, directory filters, org/onboarding/inbox tabs)', () => {
    const employees = read('posthire/PostHire.tsx')
    const workforce = read('posthire/employees360/WorkforcePage.tsx')
    const urlTab = read('lib/hrWebUrlTab.ts')
    expect(employees).toContain("useUrlBackedParam('employees', 'employee'")
    expect(employees).toContain("useUrlBackedTab('onboarding', URL_BACKED_WORKSPACE_TABS.onboarding")
    expect(employees).toContain("useUrlBackedTab('inbox', URL_BACKED_WORKSPACE_TABS.inbox")
    expect(workforce).toContain("useUrlBackedTab('workforce'")
    expect(urlTab).toContain("workforce: ['organization', 'lifecycle', 'remediation', 'migration', 'requests']")
    expect(urlTab).toContain("inbox: ['needs_action', 'due_soon', 'blocked', 'all']")
  })

  test('enterprise flagship details are URL-backed (metric, case, campaign, cycle)', () => {
    const intelligence = read('posthire/intelligence/IntelligenceWorkspace.tsx')
    const er = read('posthire/EmployeeRelationsWorkspace.tsx')
    const engagement = read('posthire/EngagementWorkspace.tsx')
    const comp = read('posthire/CompensationPlanningWorkspace.tsx')
    expect(intelligence).toContain("useUrlBackedParam('analytics', 'q'")
    expect(intelligence).toContain('evaluateIntelligenceMetric')
    expect(er).toContain("useUrlBackedParam('employee-relations', 'q'")
    expect(engagement).toContain("useUrlBackedParam('engagement', 'q'")
    expect(comp).toContain("useUrlBackedParam('compensation-planning', 'q'")
  })
})
