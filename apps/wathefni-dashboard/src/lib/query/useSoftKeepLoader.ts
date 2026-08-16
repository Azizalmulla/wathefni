import { useCallback, useEffect, useRef, useState } from 'react'

import { accessIssueFromError, type AccessIssue } from '@/lib/access'

type SoftKeepLoaderOptions = {
  onAccessIssue?: (issue: AccessIssue) => void
  fallbackError?: string
}

/**
 * Shared soft-keep loader for non-TanStack module fetches.
 * - Cold `loading` only when `data === null`
 * - `refreshing` while a request is in flight (keeps prior data)
 * - Latest request wins via requestId
 */
export function useSoftKeepLoader<T>(
  loader: () => Promise<T>,
  options: SoftKeepLoaderOptions = {},
) {
  const { onAccessIssue, fallbackError = 'We couldn’t load this section right now.' } = options
  const [data, setData] = useState<T | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current
    setRefreshing(true)
    setError(null)
    try {
      const next = await loader()
      if (requestId !== requestIdRef.current) return
      setData(next)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      const issue = accessIssueFromError(err)
      if (issue) {
        onAccessIssue?.(issue)
        return
      }
      setError(err instanceof Error && err.message ? err.message : fallbackError)
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false)
    }
  }, [fallbackError, loader, onAccessIssue])

  useEffect(() => {
    setError(null)
    void reload()
  }, [reload])

  const loading = refreshing && data === null
  return { data, setData, loading, refreshing, error, setError, reload }
}
