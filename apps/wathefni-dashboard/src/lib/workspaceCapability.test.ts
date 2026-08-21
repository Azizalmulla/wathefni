import { describe, expect, test } from 'vitest'

import {
  COMPOSITION_MATRIX,
  ROLE_PERMISSIONS_FIXTURE,
  authorityForMatrixRow,
  filterTabsByAuthority,
  overviewActionGridClass,
  resolveWorkspaceAuthority,
} from './workspaceCapability'
import type { ModuleWorkspaceCatalog } from './moduleWorkspace'

const catalog: ModuleWorkspaceCatalog[] = [
  { key: 'pre_hiring', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'assessments', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'interviews', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'video_interviews', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'calendar', suite: 'pre_hire', people_surface: false, effective: true, configured: true, platform_available: true },
  { key: 'onboarding', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'attendance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'leave', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'payroll', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'shifts', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'compliance', suite: 'post_hire', people_surface: true, effective: true, configured: true, platform_available: true },
  { key: 'analytics', suite: 'post_hire', people_surface: false, effective: true, configured: true, platform_available: true },
]

describe('workspaceCapability composition matrix', () => {
  for (const row of COMPOSITION_MATRIX) {
    test(row.label, () => {
      const authority = authorityForMatrixRow(row, catalog)
      expect(authority.navGroups.map((g) => g.group)).toEqual(row.expectNavGroups)
      for (const id of row.expectNavIncludes) {
        expect(authority.pageAllowed(id), `expected nav ${id}`).toBe(true)
      }
      for (const id of row.expectNavExcludes) {
        expect(authority.pageAllowed(id), `did not expect nav ${id}`).toBe(false)
      }
      expect(authority.overview.layout).toBe(row.expectOverviewLayout)
      // Empty groups never emitted
      expect(authority.navGroups.every((g) => g.ids.length > 0)).toBe(true)
    })
  }

  test('deep-link allowlist matches nav offerable pages', () => {
    const authority = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'assessments'],
      access: { role: 'owner', permissions: ['candidate.manage', 'candidates.read', 'jobs.read', 'jobs.create', 'assessment.manage', 'report.export', 'settings.manage', 'audit.read'] },
      catalog,
    })
    expect(authority.pageAllowed('overview')).toBe(true)
    expect(authority.pageAllowed('assessments')).toBe(true)
    expect(authority.pageAllowed('payroll')).toBe(false)
  })

  test('video interviews tab hides when module off and collapses when one tab', () => {
    const withVideo = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'interviews', 'video_interviews'],
      access: { role: 'owner', permissions: ['interview.manage', 'prehire.read'] },
      catalog,
    })
    const withoutVideo = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'interviews'],
      access: { role: 'owner', permissions: ['interview.manage', 'prehire.read'] },
      catalog,
    })
    expect(withVideo.offerable('tab.interviews.video')).toBe(true)
    expect(withoutVideo.offerable('tab.interviews.video')).toBe(false)

    const tabs = [
      { id: 'upcoming' },
      { id: 'video_interviews' },
      { id: 'completed' },
    ]
    const filtered = filterTabsByAuthority(tabs, withoutVideo, { video_interviews: 'tab.interviews.video' })
    expect(filtered.tabs.map((t) => t.id)).toEqual(['upcoming', 'completed'])
    expect(filtered.hideTabBar).toBe(false)

    const single = filterTabsByAuthority([{ id: 'upcoming' }], withoutVideo, {})
    expect(single.hideTabBar).toBe(true)
  })

  test('overview action grid classes adapt to card count', () => {
    expect(overviewActionGridClass('one', 1)).toContain('grid-cols-1')
    expect(overviewActionGridClass('two', 2)).toContain('md:grid-cols-2')
    expect(overviewActionGridClass('three', 3)).toContain('md:grid-cols-3')
    expect(overviewActionGridClass('grid', 4)).toContain('xl:grid-cols-4')
  })

  test('recruiter vs owner permission regression', () => {
    const owner = authorityForMatrixRow(
      COMPOSITION_MATRIX.find((r) => r.id === 'full_prehiring')!,
      catalog,
    )
    const recruiter = authorityForMatrixRow(
      COMPOSITION_MATRIX.find((r) => r.id === 'restricted_recruiter')!,
      catalog,
    )
    expect(owner.pageAllowed('overview')).toBe(true)
    expect(recruiter.pageAllowed('overview')).toBe(false)
    expect(recruiter.pageAllowed('jobs')).toBe(true)
    expect(recruiter.pageAllowed('payroll')).toBe(false)
    expect(recruiter.pageAllowed('assessments')).toBe(false)
  })

  test('compliance-only owner does not get Employees without employees.read', () => {
    const authority = resolveWorkspaceAuthority({
      enabledModules: ['compliance'],
      access: {
        role: 'owner',
        permissions: ['compliance.read', 'compliance.manage', 'users.manage', 'settings.manage'],
      },
      catalog,
    })
    expect(authority.pageAllowed('employees')).toBe(false)
    expect(authority.pageAllowed('compliance')).toBe(true)
    expect(authority.pageAllowed('overview')).toBe(true)
    expect(authority.overview.showWorkQueue).toBe(true)
    expect(authority.navGroups.map((g) => g.group)).toEqual(['posthire', 'settings'])
  })

  test('compliance-only actor with employees.read can open Employees', () => {
    const authority = resolveWorkspaceAuthority({
      enabledModules: ['compliance'],
      access: {
        role: 'owner',
        permissions: ['compliance.read', 'employees.read', 'users.manage', 'settings.manage'],
      },
      catalog,
    })
    expect(authority.pageAllowed('employees')).toBe(true)
  })

  test('empty permissions fail closed for Employees', () => {
    const authority = resolveWorkspaceAuthority({
      enabledModules: ['compliance'],
      access: { role: 'viewer', permissions: [] },
      catalog,
    })
    expect(authority.pageAllowed('employees')).toBe(false)
  })

  test('owner composition fixture includes candidate decision authority', () => {
    expect(ROLE_PERMISSIONS_FIXTURE.owner).toContain('candidate.decide')
  })

  test('Interviews nav requires interviews or video_interviews — not bare pre_hiring', () => {
    const prehireOnly = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    const videoOnly = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'video_interviews'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    const liveOnly = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'interviews'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    expect(prehireOnly.pageAllowed('interviews')).toBe(false)
    expect(prehireOnly.pageAllowed('assessments')).toBe(false)
    expect(videoOnly.pageAllowed('interviews')).toBe(true)
    expect(liveOnly.pageAllowed('interviews')).toBe(true)
  })

  test('Assessments nav and direct-URL allowlist follow assessments module (EN/AR labels exist)', async () => {
    const off = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'interviews'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    const on = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'assessments'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    expect(off.pageAllowed('assessments')).toBe(false)
    expect(on.pageAllowed('assessments')).toBe(true)
    // Direct-URL contract: pageAllowed is the allowlist used by App remapping.
    expect(off.navIds.includes('assessments')).toBe(false)
    expect(on.navIds.includes('assessments')).toBe(true)
  })

  test('Alerts & Delivery nav requires manage permission, not module relevance alone', () => {
    const owner = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'leave'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    const recruiter = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring', 'leave'],
      access: { role: 'recruiter', permissions: ROLE_PERMISSIONS_FIXTURE.recruiter },
      catalog,
    })
    expect(owner.pageAllowed('notifications')).toBe(true)
    expect(recruiter.pageAllowed('notifications')).toBe(false)
  })

  test('overview work queue and role priority follow offerable surfaces', () => {
    const owner = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring'],
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    const viewer = resolveWorkspaceAuthority({
      enabledModules: ['pre_hiring'],
      access: { role: 'viewer', permissions: ['prehire.read'] },
      catalog,
    })
    expect(owner.overview.showWorkQueue).toBe(true)
    expect(owner.overview.showRolePriority).toBe(true)
    expect(viewer.overview.showWorkQueue).toBe(false)
    expect(viewer.overview.showRolePriority).toBe(false)
  })

  test('post-hire only owner still gets Overview as company home without recruiting bands', () => {
    const authority = authorityForMatrixRow(
      COMPOSITION_MATRIX.find((r) => r.id === 'posthire_only')!,
      catalog,
    )
    expect(authority.pageAllowed('overview')).toBe(true)
    expect(authority.pageAllowed('jobs')).toBe(false)
    expect(authority.overview.showWorkQueue).toBe(true)
    expect(authority.overview.showRolePriority).toBe(false)
    expect(authority.overview.showHiringMetrics).toBe(false)
    expect(authority.overview.headlineMode).toBe('team')
    expect(authority.navGroups.find((g) => g.group === 'posthire')?.ids).toContain('overview')
  })

  test('missing enabled_modules fails closed instead of enabling prehire', () => {
    const authority = resolveWorkspaceAuthority({
      enabledModules: undefined,
      access: { role: 'owner', permissions: ROLE_PERMISSIONS_FIXTURE.owner },
      catalog,
    })
    expect(authority.pageAllowed('overview')).toBe(false)
    expect(authority.pageAllowed('jobs')).toBe(false)
    expect(authority.pageAllowed('payroll')).toBe(false)
    expect(authority.pageAllowed('employees')).toBe(false)
  })
})
