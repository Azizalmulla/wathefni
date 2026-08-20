/**
 * Intent prefetch for HR Web navigation.
 * Chunk prefetch is always safe. Data prefetch only uses existing query keys
 * with empty/default filters — never a guessed mutation, never another tenant.
 */

import type { QueryClient } from '@tanstack/react-query'

import { fetchJobs, fetchReports, fetchCalendarOverview, accessReady } from '@/lib/query/fetchers'
import { qk, stableFiltersKey } from '@/lib/query/keys'
import type { Page } from '@/types'
import type { DashboardAccess } from '@/types'

const loadedChunks = new Set<string>()
const inflight = new Map<string, Promise<unknown>>()

export function markPageChunkLoaded(page: string) {
  loadedChunks.add(page)
}

export function pageChunkLoaded(page: string) {
  return loadedChunks.has(page)
}

export function rememberChunkLoader(page: string, loader: () => Promise<unknown>) {
  const existing = inflight.get(page)
  if (existing) return existing
  const pending = loader()
    .then((value) => {
      markPageChunkLoaded(page)
      inflight.delete(page)
      return value
    })
    .catch((error) => {
      inflight.delete(page)
      throw error
    })
  inflight.set(page, pending)
  return pending
}

type ChunkLoader = () => Promise<unknown>

const PREHIRE_CHUNK_LOADERS: Partial<Record<Page, ChunkLoader>> = {
  jobs: () => import('@/pages/JobsPage'),
  candidates: () => import('@/pages/CandidatesPage'),
  interviews: () => import('@/pages/InterviewsPage'),
  assessments: () => import('@/pages/AssessmentsPage'),
  ranking: () => import('@/pages/RankingPage'),
  reports: () => import('@/pages/ReportsPage'),
  settings: () => import('@/pages/SettingsPage'),
  ai: () => import('@/pages/AdminAIPage'),
  notifications: () => import('@/pages/NotificationsPage'),
  calendar: () => import('@/components/CalendarShell'),
  requisitions: () => import('@/prehire/RequisitionsWorkspace'),
}

export function prefetchDashboardDestination(
  page: Page,
  access: DashboardAccess,
  client: QueryClient,
  extras?: { postHireLoader?: (page: Page) => Promise<unknown> | void },
) {
  const prehire = PREHIRE_CHUNK_LOADERS[page]
  // Prefetch uses a raw dynamic import so it never shares an inflight promise with
  // React.lazy's `{ default: Component }` wrapper.
  if (prehire) void prehire().then(() => markPageChunkLoaded(page))
  if (extras?.postHireLoader) void extras.postHireLoader(page)

  if (!accessReady(access)) return

  if (page === 'jobs') {
    const opts = {}
    void client.prefetchQuery({
      queryKey: qk.jobs(access, stableFiltersKey(opts)),
      queryFn: ({ signal }) => fetchJobs(access, opts, signal),
    })
  }
  if (page === 'reports') {
    void client.prefetchQuery({
      queryKey: qk.reports(access, 'en'),
      queryFn: ({ signal }) => fetchReports(access, signal, 'en'),
    })
  }
  if (page === 'calendar') {
    void client.prefetchQuery({
      queryKey: qk.calendarOverview(access, 'mine'),
      queryFn: ({ signal }) => fetchCalendarOverview(access, 'mine', signal),
    })
  }
}
