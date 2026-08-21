import { useCallback, useEffect, useState } from 'react'

import {
  readDashboardNavState,
  writeDashboardNavUrl,
  type DashboardNavFilters,
} from '@/lib/dashboardNavigation'

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
  shifts: ['schedule', 'requests', 'planning'],
  payroll: ['run', 'hours', 'records'],
  workforce: ['organization', 'lifecycle', 'remediation', 'migration', 'requests'],
  onboarding: ['needs_attention', 'in_progress', 'not_started', 'completed', 'all'],
  preboarding: ['all', 'blocked', 'ready', 'in_progress', 'not_started'],
  probation: ['attention', 'active', 'under_review', 'confirmed', 'extended', 'failed'],
  inbox: ['needs_action', 'due_soon', 'blocked', 'all'],
  requisitions: ['attention', 'draft', 'pending_approval', 'approved', 'open', 'filled'],
  calendar: ['day', 'week', 'month'],
  notifications: ['needs_follow_up', 'failed', 'retrying', 'resolved', 'all'],
} as const

export const URL_BACKED_VIEW_PAGES = {
  leave: ['active', 'history'],
  payroll: ['payslips', 'close', 'statutory'],
  employees: ['', 'migration'],
} as const

export const EMPLOYEE_STATUS_FILTERS = ['active', 'left', 'all'] as const
export const EMPLOYEE_ONBOARDING_FILTERS = ['any', 'open', 'complete', 'not_started'] as const

export const LEAVE_HISTORY_STATUSES = ['', 'approved', 'rejected', 'cancelled', 'withdrawn', 'requested'] as const

export type UrlBackedQueryKey =
  | 'tab'
  | 'view'
  | 'status'
  | 'date'
  | 'date_end'
  | 'q'
  | 'department'
  | 'onboarding'
  | 'employee'

export function isUrlBackedTabPage(page: string): boolean {
  return Object.prototype.hasOwnProperty.call(URL_BACKED_WORKSPACE_TABS, page)
}

export function isUrlBackedViewPage(page: string): boolean {
  return Object.prototype.hasOwnProperty.call(URL_BACKED_VIEW_PAGES, page)
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function isIsoDate(value: string): boolean {
  return ISO_DATE.test(value)
}

/** Patch operator chrome into the dashboard URL in one history write. */
export function patchDashboardNavFilters(
  pageId: string,
  patch: Partial<DashboardNavFilters>,
  mode: 'push' | 'replace' = 'push',
) {
  const nav = readDashboardNavState()
  const filters: DashboardNavFilters = { ...nav.filters }
  for (const [key, value] of Object.entries(patch) as Array<[keyof DashboardNavFilters, string | undefined]>) {
    const next = String(value || '').trim()
    if (next) filters[key] = next
    else delete filters[key]
  }
  writeDashboardNavUrl(
    {
      page: pageId,
      candidate: nav.candidate,
      filters,
      overviewScrollY: nav.overviewScrollY,
    },
    mode,
  )
}

/**
 * URL-backed workspace tab/view. Refresh, back, and forward restore the same surface.
 * Does not invent backend truth — it only records operator chrome state.
 */
export function useUrlBackedTab<T extends string>(
  pageId: string,
  allowed: readonly T[],
  fallback: T,
  queryKey: UrlBackedQueryKey = 'tab',
): [T, (next: T) => void] {
  const allowedSet = allowed
  const readTab = useCallback((): T => {
    const nav = readDashboardNavState()
    if (nav.page !== pageId) return fallback
    const raw = String(nav.filters[queryKey] || '').trim()
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
      patchDashboardNavFilters(pageId, { [queryKey]: next } as Partial<DashboardNavFilters>, 'push')
    },
    [pageId, queryKey],
  )

  return [tab, setTab]
}

/**
 * Free-form URL chrome (search, department, employee key). Empty clears the param.
 */
export function useUrlBackedParam(
  pageId: string,
  queryKey: UrlBackedQueryKey,
  fallback = '',
  historyMode: 'push' | 'replace' = 'push',
): [string, (next: string, mode?: 'push' | 'replace') => void] {
  const readValue = useCallback((): string => {
    const nav = readDashboardNavState()
    if (nav.page !== pageId) return fallback
    return String(nav.filters[queryKey] || '').trim() || fallback
  }, [pageId, queryKey, fallback])

  const [value, setValueState] = useState<string>(readValue)

  useEffect(() => {
    const sync = () => setValueState(readValue())
    sync()
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [readValue])

  const setValue = useCallback(
    (next: string, mode: 'push' | 'replace' = historyMode) => {
      const trimmed = String(next || '').trim()
      setValueState(trimmed || fallback)
      patchDashboardNavFilters(pageId, { [queryKey]: trimmed } as Partial<DashboardNavFilters>, mode)
    },
    [pageId, queryKey, fallback, historyMode],
  )

  return [value, setValue]
}

export type DateRangeValue = { start: string; end: string }

/**
 * Attendance board range. `null` means the backend default (today).
 * Refresh/back restore the same start/end when they were chosen.
 */
export function useUrlBackedDateRange(pageId: string): [DateRangeValue | null, (next: DateRangeValue | null) => void] {
  const readRange = useCallback((): DateRangeValue | null => {
    const nav = readDashboardNavState()
    if (nav.page !== pageId) return null
    const start = String(nav.filters.date || '').trim()
    const end = String(nav.filters.date_end || '').trim()
    if (isIsoDate(start) && isIsoDate(end)) return { start, end }
    if (isIsoDate(start)) return { start, end: start }
    return null
  }, [pageId])

  const [range, setRangeState] = useState<DateRangeValue | null>(readRange)

  useEffect(() => {
    const sync = () => setRangeState(readRange())
    sync()
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [readRange])

  const setRange = useCallback(
    (next: DateRangeValue | null) => {
      setRangeState(next)
      patchDashboardNavFilters(
        pageId,
        {
          date: next?.start || '',
          date_end: next?.end || '',
        },
        'push',
      )
    },
    [pageId],
  )

  return [range, setRange]
}
