import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { AttendanceView } from '@/features/remaining/RemainingViews'
import type { AttendanceResponse } from '@/api/types'

export default function AttendanceScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('attendance')
  const query = useAppQuery<AttendanceResponse>(['attendance'], '/app/attendance', { enabled })

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />

  return (
    <AttendanceView
      data={query.data ?? { ok: true, window_days: 30, summary: { present: 0, late: 0, absent: 0 }, records: [] }}
    />
  )
}
