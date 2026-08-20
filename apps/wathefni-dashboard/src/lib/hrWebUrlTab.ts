import { useCallback, useEffect, useState } from 'react'

import { readDashboardNavState, writeDashboardNavUrl } from '@/lib/dashboardNavigation'

export const SETTINGS_SECTIONS = [
  'account',
  'team',
  'company',
  'communications',
  'integrations',
  'advanced',
] as const

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number]

export const URL_BACKED_WORKSPACE_TABS = {
  settings: SETTINGS_SECTIONS,
  performance: ['overview', 'goals', 'reviews', 'calibration', 'development'],
  talent: ['overview', 'people', 'reviews', 'succession', 'mobility', 'ninebox', 'models', 'rolefit', 'map'],
  learning: ['overview', 'catalog', 'assignments', 'sessions', 'certifications', 'requests', 'history'],
  benefits: ['overview', 'plans', 'enrollment', 'coverage', 'contributions', 'history'],
  'employee-relations': ['overview', 'cases', 'detail', 'my-work', 'history'],
  engagement: ['overview', 'surveys', 'results', 'actions', 'history'],
  'compensation-planning': ['overview', 'worksheet', 'calibration', 'approvals', 'finalized', 'history'],
  'workforce-planning': ['overview', 'plan', 'scenarios', 'demand', 'cost', 'approvals', 'execution', 'history'],
  'job-architecture': ['overview', 'catalog', 'grades', 'paths', 'mappings'],
} as const

export const URL_BACKED_VIEW_PAGES = {
  leave: ['active', 'history'],
} as const

export function isUrlBackedTabPage(page: string): boolean {
  return Object.prototype.hasOwnProperty.call(URL_BACKED_WORKSPACE_TABS, page)
}

export function isUrlBackedViewPage(page: string): boolean {
  return Object.prototype.hasOwnProperty.call(URL_BACKED_VIEW_PAGES, page)
}

/**
 * URL-backed workspace tab/view. Refresh, back, and forward restore the same surface.
 * Does not invent backend truth — it only records operator chrome state.
 */
export function useUrlBackedTab<T extends string>(
  pageId: string,
  allowed: readonly T[],
  fallback: T,
  queryKey: 'tab' | 'view' = 'tab',
): [T, (next: T) => void] {
  const allowedSet = allowed
  const readTab = useCallback((): T => {
    const nav = readDashboardNavState()
    if (nav.page !== pageId) return fallback
    const raw = String((queryKey === 'view' ? nav.filters.view : nav.filters.tab) || '').trim()
    return allowedSet.includes(raw as T) ? (raw as T) : fallback
  }, [pageId, fallback, queryKey, allowedSet])

  const [tab, setTabState] = useState<T>(readTab)

  useEffect(() => {
    const sync = () => setTabState(readTab())
    sync()
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [readTab])

  const setTab = useCallback(
    (next: T) => {
      setTabState(next)
      const nav = readDashboardNavState()
      const filters = { ...nav.filters }
      if (queryKey === 'view') filters.view = next
      else filters.tab = next
      writeDashboardNavUrl(
        {
          page: pageId,
          candidate: nav.candidate,
          filters,
          overviewScrollY: nav.overviewScrollY,
        },
        'push',
      )
    },
    [pageId, queryKey],
  )

  return [tab, setTab]
}
