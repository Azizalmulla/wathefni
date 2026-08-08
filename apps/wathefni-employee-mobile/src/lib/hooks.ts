import { useQuery, type UseQueryOptions } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'

// Thin wrapper so screens get a typed GET tied to the authenticated request
// (token injection + 401 refresh) with loading/error/empty handled by callers.
// Foreground refetch is owned by ForegroundQueryRefresh; keep staleTime short
// enough that pull-to-refresh / foreground stay useful without full remounts.
export function useAppQuery<T>(key: unknown[], path: string, options?: Partial<UseQueryOptions<T>>) {
  const { request } = useAuth()
  return useQuery<T>({
    queryKey: key,
    queryFn: ({ signal }) => request<T>(path, { signal }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    ...options,
  })
}
