import { useCallback, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { approvedErrorMessage } from '@/api/errors'
import { errorFeedback, successFeedback, warningFeedback } from '@/native/haptics'
import { LeaveHistoryView } from '@/features/leave/LeaveHistoryView'

/**
 * Dedicated leave-request history beyond the Leave root ~50-row window.
 * Uses `/app/leave/history`; does not redesign Leave root.
 */
export default function LeaveHistoryScreen() {
  const { t } = useI18n()
  const { request, can } = useAuth()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()
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
              await queryClient.invalidateQueries({ queryKey: ['leave-history'] })
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
    [queryClient, request, t],
  )

  return (
    <LeaveHistoryView
      canCancel={can('leave', 'cancel')}
      cancelingId={cancelingId}
      onCancel={onCancel}
      onBack={onBack}
    />
  )
}
