import { useRouter, type Href } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { ErrorState, LoadingState } from '@/components/States'
import { HomeView } from '@/features/home/HomeView'
import type {
  AttendanceResponse,
  LeaveResponse,
  NotificationsResponse,
  OnboardingResponse,
  ShiftRow,
} from '@/api/types'

export default function HomeScreen() {
  const { profile, hasFeature, can } = useAuth()
  const router = useRouter()

  const features = {
    shifts: hasFeature('shifts'),
    attendance: hasFeature('attendance'),
    leave: hasFeature('leave'),
    onboarding: hasFeature('onboarding'),
    documents: hasFeature('documents'),
  }
  const today = useAppQuery<{ shifts: ShiftRow[] }>(
    ['shifts', 'today'],
    '/app/shifts/today',
    { enabled: features.shifts },
  )
  const attendance = useAppQuery<AttendanceResponse>(
    ['attendance'],
    '/app/attendance',
    { enabled: features.attendance },
  )
  const leave = useAppQuery<LeaveResponse>(
    ['leave'],
    '/app/leave',
    { enabled: features.leave },
  )
  const onboarding = useAppQuery<OnboardingResponse>(
    ['onboarding'],
    '/app/onboarding',
    { enabled: features.onboarding },
  )
  const notifications = useAppQuery<NotificationsResponse>(
    ['notifications'],
    '/app/notifications',
  )

  const optionalQueries = [
    features.shifts ? today : null,
    features.attendance ? attendance : null,
    features.leave ? leave : null,
    features.onboarding ? onboarding : null,
  ].filter(Boolean)
  if (notifications.isLoading || optionalQueries.some((query) => query?.isLoading)) {
    return <LoadingState />
  }
  const failed = notifications.isError
    ? notifications
    : optionalQueries.find((query) => query?.isError)
  if (failed?.isError) {
    return <ErrorState error={failed.error} onRetry={() => void failed.refetch()} />
  }

  return (
    <HomeView
      profile={profile}
      features={features}
      shift={today.data?.shifts?.[0]}
      attendance={attendance.data}
      leave={leave.data}
      notifications={notifications.data}
      onboarding={onboarding.data}
      canRequestLeave={can('leave', 'request')}
      onNavigate={(path) => router.push(path as Href)}
    />
  )
}
