import { useState } from 'react'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { LeaveRequestView } from '@/features/remaining/RemainingViews'

export default function LeaveRequestScreen() {
  const { t } = useI18n()
  const { request, me, hasFeature, can, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  const leaveTypes = me?.leave.types ?? []
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enabled = hasFeature('leave') && can('leave', 'request')

  const onSubmit = async ({ startDate, endDate, leaveType, reason }: { startDate: string; endDate: string; leaveType: string; reason: string }) => {
    setError(null)
    setBusy(true)
    try {
      await request('/app/leave/request', {
        method: 'POST',
        json: { start_date: startDate, end_date: endDate, leave_type: leaveType, reason: reason.trim() || null },
      })
      await queryClient.invalidateQueries({ queryKey: ['leave'] })
      router.back()
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />

  return (
    <LeaveRequestView
      leaveTypes={leaveTypes}
      busy={busy}
      error={error}
      onSubmit={(value) => void onSubmit(value)}
      onBack={() => router.back()}
    />
  )
}
