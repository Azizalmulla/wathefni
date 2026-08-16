import { useCallback } from 'react'
import { usePathname, useRouter } from 'expo-router'

import { HOME_ROUTE } from '@/composition/employeeAppComposition'
import { performEmployeeSafeBack } from '@/navigation/employeeSafeBack'

/**
 * Shared Employee Back contract:
 * history exists → back(); else → replace(canonical parent).
 */
export function useEmployeeSafeBack(parentOverride?: string | null) {
  const router = useRouter()
  const pathname = usePathname()
  return useCallback(() => {
    performEmployeeSafeBack(router, pathname || HOME_ROUTE, parentOverride)
  }, [router, pathname, parentOverride])
}
