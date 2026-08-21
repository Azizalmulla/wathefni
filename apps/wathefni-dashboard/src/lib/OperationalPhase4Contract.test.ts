import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import { URL_BACKED_VIEW_PAGES, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

describe('HR Web Phase 4 operational core UX', () => {
  it('reuses Phase 3 primitives without forcing one list onto every workflow', () => {
    const leave = read('posthire/LeaveWorkspace.tsx')
    const attendance = read('posthire/PostHire.tsx')
    const shifts = read('posthire/ShiftsWorkspace.tsx')
    const tabs = read('components/hr/HrSurfaceTabs.tsx')
    expect(tabs).toContain('transition-colors duration-150')
    expect(tabs).not.toContain('hover:translate')
    expect(leave).toContain('HrSurfaceTabs')
    expect(leave).toContain('HrSection')
    expect(leave).toContain('ResourceState')
    expect(leave).toContain('SoftKeepSurface')
    expect(leave).toContain('data-leave-queue')
    expect(leave).toContain('data-leave-pending')
    expect(attendance).toContain('HrSection')
    expect(attendance).toContain('useUrlBackedDateRange')
    expect(attendance).toContain('attendance-board')
    expect(attendance).toContain('AttendanceOpsPanel')
    expect(shifts).toContain('HrSurfaceTabs')
    expect(shifts).toContain("useUrlBackedTab<SurfaceTab>('shifts'")
    expect(attendance).toContain("useUrlBackedTab<'run' | 'hours' | 'records'>")
  })

  it('keeps Leave and Payroll mutations backend-canonical', () => {
    const leave = read('posthire/LeaveWorkspace.tsx')
    const payroll = read('posthire/PostHire.tsx')
    expect(leave).toContain('expected_row_version')
    expect(leave).not.toContain('optimistic')
    expect(leave).toContain('enforced=false')
    expect(payroll).not.toMatch(/onMutate[\s\S]{0,200}payroll/)
    expect(payroll).not.toContain('optimistic')
  })

  it('URL-backs chrome that should survive refresh/back', () => {
    expect(URL_BACKED_VIEW_PAGES.leave).toEqual(['active', 'history'])
    expect(URL_BACKED_WORKSPACE_TABS.shifts).toEqual(['schedule', 'requests', 'planning'])
    expect(URL_BACKED_WORKSPACE_TABS.payroll).toEqual(['run', 'hours', 'records'])
    expect(URL_BACKED_VIEW_PAGES.payroll).toEqual(['payslips', 'close', 'statutory'])
    const app = read('App.tsx')
    expect(app).toContain('isOperationalCorePage')
    expect(app).toMatch(/density=\{[\s\S]{0,80}'page'/)
  })

  it('registers Phase 4 surfaces with query-backed chrome', () => {
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))
    expect(byId['page.leave']?.notes || '').toMatch(/Phase 4/)
    expect(byId['page.attendance']?.notes || '').toMatch(/Phase 4/)
    expect(byId['page.shifts']?.notes || '').toMatch(/Phase 4/)
    expect(byId['page.payroll']?.notes || '').toMatch(/Phase 4/)
    expect(byId['tab.shifts.schedule']?.url_state).toBe('query')
    expect(byId['tab.payroll.run']?.url_state).toBe('query')
    expect(byId['tab.payroll.records.payslips']?.url_state).toBe('query')
    expect(byId['tab.leave.history']?.notes || '').toMatch(/status/)
    expect(byId['tab.attendance.capture']?.url_state).toBe('query')
    expect(byId['tab.attendance.capture']?.notes || '').toMatch(/local/)
  })
})
