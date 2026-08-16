import { useCallback, useMemo } from 'react'
import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query'

import { useRefetchOnScreenFocus } from '@hr/lib/hrRefresh'

/**
 * Server page shape shared by the HR mobile queue endpoints.
 * `total` is the company-wide count, never the length of this page.
 */
export type HrQueuePage<TItem> = {
  items: TItem[]
  total?: number
  has_more?: boolean
  offset?: number
  limit?: number
}

export const HR_QUEUE_PAGE_SIZE = 30

type UseHrQueueArgs<TItem, TPage extends HrQueuePage<TItem>> = {
  queryKey: QueryKey
  enabled?: boolean
  pageSize?: number
  fetchPage: (args: { offset: number; limit: number; signal: AbortSignal }) => Promise<TPage>
}

/**
 * One pagination contract for every actionable HR queue.
 *
 * A queue that renders fewer rows than the server holds must say so, so this
 * always reports the server `total` alongside what is loaded — a capped page
 * can never make a queue look cleared.
 */
export function useHrQueue<TItem, TPage extends HrQueuePage<TItem> = HrQueuePage<TItem>>({
  queryKey,
  enabled = true,
  pageSize = HR_QUEUE_PAGE_SIZE,
  fetchPage,
}: UseHrQueueArgs<TItem, TPage>) {
  const query = useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      fetchPage({ offset: pageParam as number, limit: pageSize, signal }),
    getNextPageParam: (last: TPage) => {
      if (!last.has_more) return undefined
      const offset = typeof last.offset === 'number' ? last.offset : 0
      const limit = typeof last.limit === 'number' ? last.limit : pageSize
      return offset + limit
    },
  })

  // Returning to a screen that stayed mounted must not show a queue that another
  // surface already changed.
  const refetch = useCallback(() => {
    void query.refetch()
  }, [query])
  useRefetchOnScreenFocus(refetch, enabled)

  const pages = useMemo(() => query.data?.pages || [], [query.data])
  const items = useMemo(() => pages.flatMap((page) => page.items), [pages])
  const total = pages.length
    ? Math.max(Number(pages[0]?.total ?? items.length) || 0, items.length)
    : 0

  return {
    query,
    items,
    total,
    loaded: items.length,
    hasMore: query.hasNextPage === true,
    loadingMore: query.isFetchingNextPage,
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage()
    },
    // Pull-to-refresh must not look like a page load.
    refreshing: query.isRefetching && !query.isFetchingNextPage,
    refetch,
    loading: query.isLoading && !query.data,
    error: query.error && !query.data,
  }
}
