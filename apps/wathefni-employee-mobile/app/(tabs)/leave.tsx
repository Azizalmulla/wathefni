import { useCallback } from 'react'
import { Alert } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { LeaveView } from '@/features/remaining/RemainingViews'
import type { LeaveResponse } from '@/api/types'

export default function LeaveScreen() {
  const { t, locale } = useI18n()
  const { request, hasFeature, can, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const enabled = hasFeature('leave')
  const query = useAppQuery<LeaveResponse>(['leave'], '/app/leave', { enabled })

  const onCancel = useCallback(
    (leaveId: string) => {
      Alert.alert(t('leave.cancel'), undefined, [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('leave.cancel'),
          style: 'destructive',
          onPress: async () => {
            try {
              await request(`/app/leave/${leaveId}/cancel`, { method: 'POST' })
              await queryClient.invalidateQueries({ queryKey: ['leave'] })
            } catch (err) {
              Alert.alert(t('common.error'), approvedErrorMessage(err, t))
            }
          },
        },
      ])
    },
    [request, queryClient, t],
  )

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />

  return (
    <LeaveView
      data={query.data ?? { ok: true, balances_enabled: false, types: [], balances: [], requests: [] }}
      canRequest={can('leave', 'request')}
      canCancel={can('leave', 'cancel')}
      onRequest={() => router.push('/leave/request')}
      onCancel={onCancel}
    />
  )
}
