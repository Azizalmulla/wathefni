import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { HR_WEB_SURFACE_REGISTRY } from '@/lib/hrWebSurfaceRegistry'
import { COMPLIANCE_FILTERS, URL_BACKED_WORKSPACE_TABS } from '@/lib/hrWebUrlTab'

const root = resolve(__dirname, '..')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')

const ALLOWED_UX = new Set([
  'migrated',
  'preserved_specialist',
  'preserved_overlay',
  'partial',
  'missed',
  'n_a',
])
const ALLOWED_INVENTORY = new Set(['live', 'alias', 'adjacent_setup', 'preauth', 'excluded'])

describe('HR Web Phase 8.5 migration completeness closure', () => {
  it('splits registry semantics and leaves no unexplained partial/missed rows', () => {
    const ux: Record<string, number> = {}
    const inventory: Record<string, number> = {}
    const unexplained = HR_WEB_SURFACE_REGISTRY.filter((row) => {
      expect(ALLOWED_INVENTORY.has(row.inventory_status), row.surface_id).toBe(true)
      expect(ALLOWED_UX.has(row.ux_migration_status), row.surface_id).toBe(true)
      ux[row.ux_migration_status] = (ux[row.ux_migration_status] || 0) + 1
      inventory[row.inventory_status] = (inventory[row.inventory_status] || 0) + 1
      return row.ux_migration_status === 'partial' || row.ux_migration_status === 'missed'
    })
    expect(unexplained.map((row) => row.surface_id)).toEqual([])
    expect({
      total: HR_WEB_SURFACE_REGISTRY.length,
      migrated: ux.migrated || 0,
      preserved_overlay: ux.preserved_overlay || 0,
      preserved_specialist: ux.preserved_specialist || 0,
      n_a: ux.n_a || 0,
      partial: ux.partial || 0,
      missed: ux.missed || 0,
      live: inventory.live || 0,
      alias: inventory.alias || 0,
      adjacent_setup: inventory.adjacent_setup || 0,
      preauth: inventory.preauth || 0,
      excluded: inventory.excluded || 0,
    }).toEqual({
      total: 209,
      migrated: 188,
      preserved_overlay: 15,
      preserved_specialist: 0,
      n_a: 6,
      partial: 0,
      missed: 0,
      live: 203,
      alias: 1,
      adjacent_setup: 3,
      preauth: 2,
      excluded: 0,
    })
  })

  it('fully migrates Compliance with URL-backed Findings/Register and buckets', () => {
    const app = read('App.tsx')
    const compliance = read('posthire/PostHire.tsx')
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))

    expect(app).toContain("page === 'compliance'")
    expect(compliance).toContain('HrSurfaceTabs')
    expect(compliance).toContain('ResourceState')
    expect(compliance).toContain("useUrlBackedTab('compliance', URL_BACKED_WORKSPACE_TABS.compliance, 'findings')")
    expect(compliance).toContain("useUrlBackedTab('compliance', COMPLIANCE_FILTERS, 'needs_review', 'status')")
    expect(compliance).toContain('getPosthireCompliance')
    expect(compliance).toContain('compliance_send_reminder')
    expect(compliance).not.toMatch(/#[cC]89445/)
    expect(compliance).not.toMatch(/#f3ebe0/)
    expect(URL_BACKED_WORKSPACE_TABS.compliance).toEqual(['findings', 'register'])
    expect([...COMPLIANCE_FILTERS]).toEqual(['needs_review', 'missing', 'expiring_soon', 'expired', 'all'])
    expect(byId['page.compliance']?.ux_migration_status).toBe('migrated')
    expect(byId['page.compliance']?.ux_phase).toBe(8.5)
    expect(byId['tab.compliance.findings']?.url_state).toBe('query')
    expect(byId['tab.compliance.register']?.url_state).toBe('query')
    expect(byId['tab.compliance.filter.needs_review']?.url_state).toBe('query')
  })

  it('closes leftover primary chrome without a second ConfirmDialog or palette swap', () => {
    const postHire = read('posthire/PostHire.tsx')
    const chrome = read('posthire/employees360/chrome.tsx')
    const jobsForm = read('components/JobsForm.tsx')
    const assistant = read('pages/AdminAIPage.tsx')
    const app = read('App.tsx')
    const byId = Object.fromEntries(HR_WEB_SURFACE_REGISTRY.map((row) => [row.surface_id, row]))

    expect(postHire).not.toContain('function ConfirmDialog(')
    expect(postHire).toContain('useConfirm')
    expect(chrome).toContain('HrSurfaceTabs')
    expect(chrome).not.toMatch(/#eee5d4/)
    expect(jobsForm).toContain('ms-auto')
    expect(jobsForm).toContain('border-s')
    expect(jobsForm).not.toContain('ml-auto')
    expect(assistant).toContain('ms-auto')
    expect(assistant).toContain('border-s')
    expect(assistant).not.toContain('ml-auto')
    expect(assistant).not.toContain('hover:-translate-y')
    expect(app).toContain('position_code: selectedJob.position_code')
    expect(byId['modal.shared.confirm']?.ux_migration_status).toBe('preserved_overlay')
    expect(byId['detail.jobs.workspace']?.notes || '').toMatch(/position_code/)
    expect(byId['fallback.analytics.legacy']?.ux_migration_status).toBe('preserved_overlay')
    expect(postHire).toContain('function AnalyticsPage(')
    expect(read('posthire/PostHireDispatcher.tsx')).toContain('LazyAnalyticsFallback')
  })
})
