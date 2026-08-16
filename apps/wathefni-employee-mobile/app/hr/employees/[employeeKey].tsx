import { useLocalSearchParams } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import { ApiError } from '@hr/api/client'
import { mobileApi } from '@hr/api/mobile'
import { resourceState } from '@hr/api/state'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  EmployeeProfileView,
  type EmployeeProfileViewState,
} from '@hr/features/people/EmployeeProfileView'
import { useHrSafeBack } from '@hr/useHrSafeBack'

function isNotFound(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 ||
      error.code === 'employee_not_found' ||
      error.code === 'not_found')
  )
}

export default function EmployeeProfileRoute() {
  const { employeeKey = '' } = useLocalSearchParams<{ employeeKey: string }>()
  const key = String(employeeKey || '').trim()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const permitted = routeAvailable(me, 'employees')

  const query = useQuery({
    queryKey: ['employee', key],
    queryFn: ({ signal }) => mobileApi.employeeDetail(request, key, signal),
    enabled: permitted && Boolean(key),
  })

  const state: EmployeeProfileViewState = !permitted
    ? 'permission'
    : !key
      ? 'unavailable'
      : isNotFound(query.error)
        ? 'not_found'
        : resourceState({
            loading: query.isLoading,
            error: query.error,
            stale: query.data?.stale,
            empty: Boolean(query.data) && !query.data?.item?.employee_key,
          })

  // Map empty success to not_found — never a blank ready card.
  const viewState: EmployeeProfileViewState =
    state === 'empty' ? 'not_found' : state === 'ready' && !query.data?.item ? 'not_found' : state

  return (
    <EmployeeProfileView
      employee={query.data?.item || null}
      state={viewState}
      onRetry={() => void query.refetch()}
      onBack={onBack}
    />
  )
}
