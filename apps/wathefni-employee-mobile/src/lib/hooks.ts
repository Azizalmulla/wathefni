import { useQuery, type UseQueryOptions } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'

// Thin wrapper so screens get a typed GET tied to the authenticated request
// (token injection + 401 refresh) with loading/error/empty handled by callers.
export function useAppQuery<T>(key: unknown[], path: string, options?: Partial<UseQueryOptions<T>>) {
  const { request } = useAuth()
  return useQuery<T>({
    queryKey: key,
    queryFn: () => request<T>(path),
    ...options,
  })
}
