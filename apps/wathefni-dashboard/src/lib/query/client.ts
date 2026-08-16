import { QueryClient, keepPreviousData } from '@tanstack/react-query'

/**
 * Shared dashboard QueryClient — one permanent server-state authority.
 *
 * Rendering Stability Wave 2: default `placeholderData: keepPreviousData` so
 * filter/date/pagination refetches soft-keep prior content. Opt out explicitly
 * with `placeholderData: undefined` when showing the previous key's rows would
 * be wrong-scope (e.g. Overview My/Company work queue).
 */
export function createDashboardQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
        placeholderData: keepPreviousData,
      },
      mutations: {
        retry: 0,
      },
    },
  })
}

export const dashboardQueryClient = createDashboardQueryClient()
