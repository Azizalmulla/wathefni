import { DASHBOARD_NAV_CATALOG } from './hrWebNavCatalog'
import { describe, expect, test } from 'vitest'

import { diffCensusAgainstRegistry, runStaticCensus } from './hrWebSurfaceCensus'
import {
  HR_WEB_SIDEBAR_COVERAGE_GAPS,
  HR_WEB_SURFACE_EXCLUSIONS,
  HR_WEB_SURFACE_REGISTRY,
  capabilityNavPages,
  registryPageIds,
} from './hrWebSurfaceRegistry'
import { HR_WEB_UX_INVENTORY } from './hrWebUxInventory'

const census = runStaticCensus()
const diff = diffCensusAgainstRegistry({
  census,
  registryPageIds: registryPageIds(),
  registrySurfaceIds: HR_WEB_SURFACE_REGISTRY.map((row) => row.surface_id),
  registryRoutes: HR_WEB_SURFACE_REGISTRY.map((row) => row.route),
  exclusions: HR_WEB_SURFACE_EXCLUSIONS,
})

describe('HR Web Surface Registry coverage contract', () => {
  test('every Page union member is a registry page', () => {
    expect(diff.pagesMissingFromRegistry).toEqual([])
    expect(census.pageUnion.length).toBeGreaterThanOrEqual(30)
  })

  test('every App.tsx nav item is a registry page', () => {
    const missing = census.navItems.filter((id) => !registryPageIds().includes(id))
    expect(missing).toEqual([])
  })

  test('every PostHire switch case is a registry page', () => {
    expect(diff.postHireMissingFromRegistry).toEqual([])
  })

  test('every workspaceCapability nav page is a registry page', () => {
    expect(diff.capabilityMissingFromRegistry).toEqual([])
    expect(capabilityNavPages().sort()).toEqual([...census.capabilityNav].sort())
  })

  test('every discovered ?page= / opsHref destination is registered or aliased', () => {
    expect(diff.queryDestinationsMissingFromRegistry).toEqual([])
  })

  test('every Settings section is registered', () => {
    expect(diff.settingsMissingFromRegistry).toEqual([])
  })

  test('every post-hire workspace Tab union is registered', () => {
    expect(diff.workspaceTabsMissingFromRegistry).toEqual([])
  })

  test('every named Modal/Drawer/Dialog is represented in the registry', () => {
    const missing = census.overlays.filter(
      (name) =>
        !HR_WEB_SURFACE_REGISTRY.some(
          (row) => row.component.includes(name) || (row.notes || '').includes(name),
        ),
    )
    expect(missing).toEqual([])
  })

  test('registry surface_ids are unique and cover every Page', () => {
    const ids = HR_WEB_SURFACE_REGISTRY.map((row) => row.surface_id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(HR_WEB_SURFACE_REGISTRY.filter((row) => row.kind === 'page')).toHaveLength(census.pageUnion.length)
    expect(HR_WEB_SURFACE_REGISTRY.length).toBeGreaterThanOrEqual(140)
  })

  test('sidebar lockstep: catalog matches capability and the navItems.some gate is gone', () => {
    expect(diff.capabilityNotInSidebar).toEqual([])
    expect(HR_WEB_SIDEBAR_COVERAGE_GAPS).toEqual([])
    expect(census.navItemsSomeGate.initialState).toBe(false)
    expect(census.navItemsSomeGate.applyNavState).toBe(false)
    expect(census.navItemsSomeGate.registryPageGate).toBe(true)
    expect([...census.navItems].sort()).toEqual([...census.capabilityNav].sort())
    expect(DASHBOARD_NAV_CATALOG.map((item) => item.id).sort()).toEqual(capabilityNavPages().sort())
  })

  test('employee_app remains excluded from HR nav', () => {
    expect(census.navItems).not.toContain('employee_app')
    expect(HR_WEB_SURFACE_EXCLUSIONS.some((row) => row.id === 'employee_app')).toBe(true)
  })

  test('UX inventory covers the required families', () => {
    const families = new Set(HR_WEB_UX_INVENTORY.map((row) => row.family))
    for (const family of [
      'app shell/sidebar',
      'headers/page intros',
      'actions',
      'tabs',
      'search/filters',
      'tables/lists',
      'cards',
      'forms',
      'drawers/modals',
      'status indicators',
      'loading/error/empty/unavailable',
    ]) {
      expect(families.has(family), family).toBe(true)
    }
  })

  test('every surface has split inventory/ux fields and no unexplained leftover chrome', () => {
    for (const row of HR_WEB_SURFACE_REGISTRY) {
      expect(row.inventory_status, row.surface_id).toBeTruthy()
      expect(row.ux_migration_status, row.surface_id).toBeTruthy()
      expect(row).toHaveProperty('ux_phase')
      expect(['partial', 'missed']).not.toContain(row.ux_migration_status)
    }
  })
})
