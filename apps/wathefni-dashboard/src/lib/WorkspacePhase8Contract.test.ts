import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import { URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

const WORKSPACE_PAGES = ['settings', 'notifications', 'activity'] as const

describe('HR Web Phase 8 Settings / Alerts / Activity UX', () => {
  it('reuses shared chrome without changing configuration, delivery, or audit authority', () => {
    const app = read('App.tsx')
    const settings = read('pages/SettingsPage.tsx')
    const alerts = read('pages/NotificationsPage.tsx')
    const activity = read('components/ActivityLog.tsx')

    expect(app).toContain('isWorkspaceOpsPage')
    expect(app).toContain('usesCanonicalPageHeader')
    expect(app).toContain("'Workspace'")
    expect(app).toContain('isWorkspaceOpsPage(activePage)')

    expect(settings).toContain('HrSurfaceTabs')
    expect(settings).toContain("useUrlBackedTab<SettingsSection>('settings'")
    expect(settings).toContain('data-settings-section="account"')
    expect(settings).toContain('data-settings-section="advanced"')
    expect(settings).toContain('variant="integrations"')
    expect(settings).toContain('variant="advanced"')
    expect(settings).not.toContain('<h1')
    expect(settings).not.toMatch(/#[cC]89445/)
    expect(settings).not.toMatch(/#fff7e6/)

    expect(alerts).toContain('HrSurfaceTabs')
    expect(alerts).toContain("useUrlBackedTab<IssueFilter>('notifications'")
    expect(alerts).toContain('canManageAlertsAndDelivery')
    expect(alerts).toContain("resolveHrTask(access, taskId, 'done', expectedStatus)")
    expect(alerts).toContain('alertsPaintedRef')
    expect(alerts).not.toContain('<h1')
    expect(alerts).not.toMatch(/#[cC]89445/)

    expect(activity).toContain('getCompanyActivity')
    expect(activity).toContain('downloadCompanyActivityCsv')
    expect(activity).toContain('useUrlBackedParam')
    expect(activity).toContain("useUrlBackedParam('activity', 'q'")
    expect(activity).toContain('humanizeActionType')
    expect(activity).toContain('Read-only audit record')
    expect(activity).not.toMatch(/method:\s*'POST'/)
    expect(activity).not.toContain('HrSurfaceTabs')
    expect(activity).not.toMatch(/#[cC]89445/)
    expect(activity).not.toMatch(/#fffaf0/)
  })

  it('URL-backs Settings sections, Alerts filters, and Activity chrome', () => {
    expect(URL_BACKED_WORKSPACE_TABS.settings).toEqual([
      'account',
      'team',
      'company',
      'communications',
      'integrations',
      'advanced',
    ])
    expect(URL_BACKED_WORKSPACE_TABS.notifications).toEqual([
      'needs_follow_up',
      'failed',
      'retrying',
      'resolved',
      'all',
    ])
    const nav = read('lib/dashboardNavigation.ts')
    expect(nav).toContain("state.page === 'activity'")
    expect(nav).toContain("params.set('date_end', dateEnd)")
  })

  it('keeps Settings configuration-oriented and Alerts/Activity backend-canonical', () => {
    const settings = read('pages/SettingsPage.tsx')
    const alerts = read('pages/NotificationsPage.tsx')
    const activity = read('components/ActivityLog.tsx')
    expect(settings).toContain('Setup Console')
    expect(settings).toContain('without changing role permissions or delivery ownership')
    expect(settings).toContain('putPrehireVisibilityPolicy')
    expect(alerts).toContain('getOutboundNeedsFollowUp')
    expect(alerts).toContain('moduleScopedNotificationRows')
    expect(activity).toContain('getCompanyActivity')
    expect(activity).not.toMatch(/resolveHrTask|runPosthireAction/)
    expect(read('lib/api.ts')).toContain("request<ActivityResponse>(`/dashboard/activity")
  })

  it('registers Phase 8 surfaces as canonical', () => {
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
    for (const page of WORKSPACE_PAGES) {
      expect(byId[`page.${page}`]?.migration_status).toBe('canonical')
      expect(byId[`page.${page}`]?.notes || '').toMatch(/Phase 8/)
    }
    expect(byId['settings.account']?.url_state).toBe('query')
    expect(byId['settings.advanced']?.migration_status).toBe('consolidate')
    expect(byId['tab.notifications.needs_follow_up']?.url_state).toBe('query')
    expect(byId['tab.notifications.needs_follow_up']?.notes || '').toMatch(/Phase 8/)
  })

  it('does not restyle already-migrated product modules', () => {
    expect(read('pages/JobsPage.tsx')).toContain('jobs-status-tiles')
    expect(read('pages/JobsPage.tsx')).not.toContain('HrSurfaceTabs')
    expect(read('posthire/LeaveWorkspace.tsx')).toContain('HrSurfaceTabs')
    expect(read('pages/RankingPage.tsx')).not.toContain('HrSurfaceTabs')
  })
})
