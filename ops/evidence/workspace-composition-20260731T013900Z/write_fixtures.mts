/**
 * Visual composition fixtures for each entitlement matrix row.
 * Generated from COMPOSITION_MATRIX / resolveWorkspaceAuthority.
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  COMPOSITION_MATRIX,
  authorityForMatrixRow,
} from '../../apps/wathefni-dashboard/src/lib/workspaceCapability'
import type { ModuleWorkspaceCatalog } from '../../apps/wathefni-dashboard/src/lib/moduleWorkspace'

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

const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(here, 'fixtures')
mkdirSync(outDir, { recursive: true })

const rows = COMPOSITION_MATRIX.map((row) => {
  const authority = authorityForMatrixRow(row, catalog)
  return {
    id: row.id,
    label: row.label,
    modules: row.modules,
    role: row.role,
    nav_groups: authority.navGroups.map((g) => g.group),
    nav_group_detail: authority.navGroups,
    nav_ids: authority.navIds,
    overview_layout: authority.overview.layout,
    overview_priority_surfaces: authority.overview.prioritySurfaces,
    headline_mode: authority.overview.headlineMode,
    offerable_tabs: {
      video_interviews: authority.offerable('tab.interviews.video'),
    },
    settings: {
      team: authority.offerable('settings.team'),
      integrations: authority.offerable('settings.integrations'),
    },
  }
})

writeFileSync(resolve(outDir, 'composition-matrix.json'), `${JSON.stringify(rows, null, 2)}\n`)
for (const row of rows) {
  writeFileSync(resolve(outDir, `${row.id}.json`), `${JSON.stringify(row, null, 2)}\n`)
}
console.log(`wrote ${rows.length} visual fixtures to ${outDir}`)
