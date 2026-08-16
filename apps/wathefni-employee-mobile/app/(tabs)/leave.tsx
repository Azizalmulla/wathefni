import { useCallback, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { errorFeedback, successFeedback, warningFeedback } from '@/native/haptics'
import { LeaveView } from '@/features/remaining/RemainingViews'
import type { LeaveResponse } from '@/api/types'

export default function LeaveScreen() {
  const { t } = useI18n()
  const { request, hasFeature, can, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const enabled = hasFeature('leave')
  const query = useAppQuery<LeaveResponse>(['leave'], '/app/leave', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [refreshing, setRefreshing] = useState(false)
  const [cancelingId, setCancelingId] = useState<string | null>(null)
  const cancelLocks = useRef(new Set<string>())

  const onCancel = useCallback(
    (leaveId: string) => {
      if (cancelLocks.current.has(leaveId)) return
      warningFeedback()
      Alert.alert(t('leave.cancel'), undefined, [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('leave.cancel'),
          style: 'destructive',
          onPress: async () => {
            if (cancelLocks.current.has(leaveId)) return
            cancelLocks.current.add(leaveId)
            setCancelingId(leaveId)
            try {
              await request(`/app/leave/${leaveId}/cancel`, { method: 'POST' })
              successFeedback()
              await queryClient.invalidateQueries({ queryKey: ['leave'] })
            } catch (err) {
              errorFeedback()
              Alert.alert(t('common.error'), approvedErrorMessage(err, t))
            } finally {
              cancelLocks.current.delete(leaveId)
              setCancelingId(null)
            }
          },
        },
      ])
    },
    [request, queryClient, t],
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (!enabled) return <FeatureUnavailableState feature="leave" onRefresh={() => void refreshMe()} />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />

  return (
    <LeaveView
      data={query.data ?? { ok: true, balances_enabled: false, types: [], balances: [], requests: [] }}
      canRequest={can('leave', 'request')}
      canCancel={can('leave', 'cancel')}
      cancelingId={cancelingId}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onRequest={() => router.push('/leave/request')}
      onViewAllHistory={() => router.push('/leave/history')}
      onCancel={onCancel}
    />
  )
}
