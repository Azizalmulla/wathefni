import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ShiftsView } from '@/features/remaining/RemainingViews'
import type { ShiftRow } from '@/api/types'

export default function ShiftsScreen() {
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('shifts')
  const today = useAppQuery<{ shifts: ShiftRow[] }>(['shifts', 'today'], '/app/shifts/today', { enabled })
  const upcoming = useAppQuery<{ shifts: ShiftRow[] }>(['shifts', 'upcoming'], '/app/shifts/upcoming', { enabled })

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (today.isLoading || upcoming.isLoading) return <LoadingState />
  if (today.isError) return <ErrorState error={today.error} onRetry={() => today.refetch()} />
  if (upcoming.isError) return <ErrorState error={upcoming.error} onRetry={() => upcoming.refetch()} />

  return <ShiftsView today={today.data?.shifts ?? []} upcoming={upcoming.data?.shifts ?? []} />
}
