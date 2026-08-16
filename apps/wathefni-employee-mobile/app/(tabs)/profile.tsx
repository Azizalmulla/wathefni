import { useCallback, useState } from 'react'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { LoadingState } from '@/components/States'
import { ProfileView } from '@/features/profile/ProfileView'
import type { ProfileResponse } from '@/api/types'

export default function ProfileScreen() {
  const { profile: meProfile, signOut, hasFeature, refreshMe } = useAuth()
  const router = useRouter()
  const [refreshing, setRefreshing] = useState(false)

  // Richer Profile uses /app/profile — /app/me stays the compact auth/entitlement contract.
  const query = useAppQuery<ProfileResponse>(['profile'], '/app/profile', {
    staleTime: HIGH_CHURN_STALE_MS,
  })

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await Promise.all([refreshMe(), query.refetch()])
    } finally {
      setRefreshing(false)
    }
  }, [refreshMe, query])

  if (!query.data && query.isLoading && !meProfile) return <LoadingState />

  return (
    <ProfileView
      profile={query.data ?? null}
      fallbackName={meProfile?.name}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      profileError={query.isError && !query.data}
      onRetryProfile={() => void query.refetch()}
      onSettings={() => router.push('/settings')}
      onBank={hasFeature('bank') ? () => router.push('/bank') : undefined}
      onPreboarding={hasFeature('preboarding') ? () => router.push('/preboarding') : undefined}
      onProbation={hasFeature('probation') ? () => router.push('/probation') : undefined}
      onPrivacySupport={() => router.push('/privacy-support')}
      onSignOut={() => void signOut()}
    />
  )
}
