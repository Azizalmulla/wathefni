import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { errorFeedback, successFeedback } from '@/native/haptics'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { LeaveRequestView } from '@/features/remaining/RemainingViews'
import type { LeaveDurationResponse, LeaveResponse } from '@/api/types'

type Selection = { startDate: string; endDate: string; leaveType: string }

export default function LeaveRequestScreen() {
  const { t } = useI18n()
  const { request, me, hasFeature, can, refreshMe } = useAuth()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()

  const leaveTypes = me?.leave.types ?? []
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const submitLock = useRef(false)

  const enabled = hasFeature('leave') && can('leave', 'request')

  // Same `['leave']` key the Leave tab uses, so arriving from it costs nothing
  // and the balance shown here is the balance shown there.
  const leave = useAppQuery<LeaveResponse>(['leave'], '/app/leave', { enabled })

  // The company's rest days and public holidays decide how many days a range
  // charges, and neither is on the device. Asking the server is the only way to
  // show a number that will match the request; there is no local fallback on
  // purpose, so a failed or missing answer shows nothing at all.
  const durationQuery = useAppQuery<LeaveDurationResponse>(
    ['leave', 'duration', selection?.startDate, selection?.endDate, selection?.leaveType],
    `/app/leave/duration?start_date=${encodeURIComponent(selection?.startDate ?? '')}` +
      `&end_date=${encodeURIComponent(selection?.endDate ?? '')}` +
      `&leave_type=${encodeURIComponent(selection?.leaveType ?? '')}`,
    { enabled: enabled && Boolean(selection), retry: false },
  )

  const onRangeChange = useCallback((next: Selection) => {
    setSelection((current) =>
      current &&
      current.startDate === next.startDate &&
      current.endDate === next.endDate &&
      current.leaveType === next.leaveType
        ? current
        : next,
    )
  }, [])

  const onSubmit = async ({ startDate, endDate, leaveType, reason }: Selection & { reason: string }) => {
    if (submitLock.current || busy) return
    submitLock.current = true
    setError(null)
    setBusy(true)
    try {
      await request('/app/leave/request', {
        method: 'POST',
        json: { start_date: startDate, end_date: endDate, leave_type: leaveType, reason: reason.trim() || null },
      })
      successFeedback()
      await queryClient.invalidateQueries({ queryKey: ['leave'] })
      onBack()
    } catch (err) {
      errorFeedback()
      setError(approvedErrorMessage(err, t))
    } finally {
      submitLock.current = false
      setBusy(false)
    }
  }

  if (!enabled) return <FeatureUnavailableState feature="leave" onRefresh={() => void refreshMe()} />

  return (
    <LeaveRequestView
      leaveTypes={leaveTypes}
      busy={busy}
      error={error}
      balances={leave.data ?? null}
      duration={durationQuery.data ?? null}
      onRangeChange={onRangeChange}
      onSubmit={(value) => void onSubmit(value)}
      onBack={onBack}
    />
  )
}
