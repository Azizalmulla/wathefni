import { useCallback } from 'react'
import { usePathname, useRouter } from 'expo-router'

import { performHrSafeBack } from '@hr/navigation'

/**
 * Shared HR Back contract:
 * history exists → back(); else → replace(canonical parent).
 */
export function useHrSafeBack(parentOverride?: string | null) {
  const router = useRouter()
  const pathname = usePathname()
  return useCallback(() => {
    performHrSafeBack(router, pathname || '/hr', parentOverride)
  }, [router, pathname, parentOverride])
}
