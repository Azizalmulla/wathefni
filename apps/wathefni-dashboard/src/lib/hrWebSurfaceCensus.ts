/**
 * Static HR Web surface discovery.
 *
 * Walks dashboard source (not screenshots) and returns destinations that must
 * be represented in HR_WEB_SURFACE_REGISTRY or HR_WEB_SURFACE_EXCLUSIONS.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

const SRC = resolve(__dirname, '..')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (['node_modules', 'dist', 'coverage'].includes(name)) continue
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) walk(full, out)
    else if (/\.(tsx?|jsx?)$/.test(name) && !/\.(test|spec)\./.test(name)) out.push(full)
  }
  return out
}

function read(relOrAbs: string) {
  const full = relOrAbs.startsWith('/') ? relOrAbs : resolve(SRC, relOrAbs)
  return readFileSync(full, 'utf8')
}

export function parsePageUnion(source = read('types.ts')): string[] {
  const start = source.indexOf('export type Page =')
  const end = source.indexOf('export type ChatMessage')
  if (start < 0 || end < 0) return []
  return Array.from(source.slice(start, end).matchAll(/'([a-z0-9-]+)'/g)).map((m) => m[1])
}

export function parseAppNavItemIds(source = read('lib/hrWebNavCatalog.ts')): string[] {
  const start = source.indexOf('const PAGE_ICONS')
  const end = source.indexOf('export const DASHBOARD_NAV_CATALOG')
  if (start < 0 || end < 0) return []
  return Array.from(source.slice(start, end).matchAll(/^\s+'?([a-z0-9-]+)'?: /gm)).map((m) => m[1])
}

export function parsePostHireCases(source = read('posthire/PostHireDispatcher.tsx')): string[] {
  const start = source.indexOf('switch (page)')
  if (start < 0) return []
  const block = source.slice(start, start + 8000)
  return Array.from(block.matchAll(/case '([a-z0-9-]+)':/g)).map((m) => m[1])
}

export function parseCapabilityNavPages(source = read('lib/workspaceCapability.ts')): string[] {
  const pages = new Set<string>()
  const navBlocks = source.split('kind: \'nav\'')
  for (const block of navBlocks.slice(1)) {
    const match = block.match(/page: '([a-z0-9-]+)'/)
    if (match) pages.add(match[1])
  }
  return [...pages]
}

export function parsePageQueryDestinations(files = walk(SRC)): string[] {
  const found = new Set<string>()
  for (const file of files) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(/[?&]page=([a-z0-9-]+)/g)) found.add(match[1])
    for (const match of text.matchAll(/page=([a-z0-9-]+)/g)) found.add(match[1])
    for (const match of text.matchAll(/opsHref: '\/dashboard\?page=([a-z0-9-]+)/g)) found.add(match[1])
  }
  return [...found].sort()
}

export function parseWorkspaceTabUnions(files = walk(join(SRC, 'posthire'))): Array<{ file: string; tabs: string[] }> {
  const out: Array<{ file: string; tabs: string[] }> = []
  for (const file of files) {
    if (!file.endsWith('Workspace.tsx')) continue
    const text = readFileSync(file, 'utf8')
    const match = text.match(/type Tab = ([^\n]+)/)
    if (!match) continue
    const tabs = Array.from(match[1].matchAll(/'([a-z0-9-]+)'/g)).map((m) => m[1])
    if (tabs.length) out.push({ file: relative(SRC, file), tabs })
  }
  return out
}

export function parseSettingsSections(source = read('pages/SettingsPage.tsx')): string[] {
  const match = source.match(/type SettingsSection = ([^\n]+)/)
  if (!match) return []
  return Array.from(match[1].matchAll(/'([a-z0-9-]+)'/g)).map((m) => m[1])
}

export function parseOverlayNames(files = walk(SRC)): string[] {
  const names = new Set<string>()
  for (const file of files) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(/function ([A-Z][A-Za-z0-9]*(?:Modal|Drawer|Dialog))\b/g)) {
      names.add(match[1])
    }
    for (const match of text.matchAll(/export function ([A-Z][A-Za-z0-9]*(?:Modal|Drawer|Dialog))\b/g)) {
      names.add(match[1])
    }
  }
  return [...names].sort()
}

export function parseNavItemsSomeGate(source = read('App.tsx')): { initialState: boolean; applyNavState: boolean; registryPageGate: boolean } {
  return {
    initialState: /navItems\.some\(\(item\) => item\.id === requested\)/.test(source),
    applyNavState: /navItems\.some\(\(item\) => item\.id === nav\.page\)/.test(source),
    registryPageGate: /isRegisteredDashboardPage\(requested\)/.test(source) && /isRegisteredDashboardPage\(nav\.page\)/.test(source),
  }
}

export type StaticCensus = {
  pageUnion: string[]
  navItems: string[]
  postHireCases: string[]
  capabilityNav: string[]
  pageQueryDestinations: string[]
  workspaceTabs: Array<{ file: string; tabs: string[] }>
  settingsSections: string[]
  overlays: string[]
  navItemsSomeGate: { initialState: boolean; applyNavState: boolean; registryPageGate: boolean }
}

export function runStaticCensus(): StaticCensus {
  return {
    pageUnion: parsePageUnion(),
    navItems: parseAppNavItemIds(),
    postHireCases: parsePostHireCases(),
    capabilityNav: parseCapabilityNavPages(),
    pageQueryDestinations: parsePageQueryDestinations(),
    workspaceTabs: parseWorkspaceTabUnions(),
    settingsSections: parseSettingsSections(),
    overlays: parseOverlayNames(),
    navItemsSomeGate: parseNavItemsSomeGate(),
  }
}

export function knownPageKeysFromRegistry(routes: string[]): Set<string> {
  const keys = new Set<string>()
  for (const route of routes) {
    for (const match of route.matchAll(/[?&]page=([a-z0-9-]+)/g)) keys.add(match[1])
  }
  return keys
}

export function diffCensusAgainstRegistry(args: {
  census: StaticCensus
  registryPageIds: string[]
  registrySurfaceIds: string[]
  registryRoutes: string[]
  exclusions: Array<{ id: string; pattern: string }>
}): {
  pagesMissingFromRegistry: string[]
  queryDestinationsMissingFromRegistry: string[]
  postHireMissingFromRegistry: string[]
  capabilityMissingFromRegistry: string[]
  settingsMissingFromRegistry: string[]
  workspaceTabsMissingFromRegistry: string[]
  sidebarGaps: string[]
  capabilityNotInSidebar: string[]
} {
  const pageSet = new Set(args.registryPageIds)
  const routePages = knownPageKeysFromRegistry(args.registryRoutes)
  const covered = (id: string) => pageSet.has(id) || routePages.has(id)
  const excluded = (value: string) => args.exclusions.some((row) => value.includes(row.pattern) || row.pattern === value)
  const missingPages = (list: string[]) => list.filter((id) => !covered(id) && !excluded(id))
  const tabMissing = args.census.workspaceTabs.flatMap((row) => {
    const pageId = guessPageId(row.file)
    return row.tabs
      .filter((tab) => !args.registrySurfaceIds.includes(`tab.${pageId}.${tab}`))
      .map((tab) => `${pageId}:${tab}`)
  })
  return {
    pagesMissingFromRegistry: missingPages(args.census.pageUnion),
    queryDestinationsMissingFromRegistry: missingPages(args.census.pageQueryDestinations),
    postHireMissingFromRegistry: missingPages(args.census.postHireCases),
    capabilityMissingFromRegistry: missingPages(args.census.capabilityNav),
    settingsMissingFromRegistry: args.census.settingsSections.filter(
      (id) => !args.registrySurfaceIds.includes(`settings.${id}`) && !excluded(id),
    ),
    workspaceTabsMissingFromRegistry: tabMissing,
    sidebarGaps: args.census.pageUnion.filter((id) => !args.census.navItems.includes(id)),
    capabilityNotInSidebar: args.census.capabilityNav.filter((id) => !args.census.navItems.includes(id)),
  }
}

function guessPageId(file: string): string {
  const base = file.replace(/^posthire\//, '').replace(/Workspace\.tsx$/, '')
  const map: Record<string, string> = {
    Talent: 'talent',
    Learning: 'learning',
    Benefits: 'benefits',
    EmployeeRelations: 'employee-relations',
    Engagement: 'engagement',
    CompensationPlanning: 'compensation-planning',
    WorkforcePlanning: 'workforce-planning',
    JobArchitecture: 'job-architecture',
    Performance: 'performance',
  }
  return map[base] || base.replace(/([a-z])([A-Z])/g, '$1-$2').toLowerCase()
}
