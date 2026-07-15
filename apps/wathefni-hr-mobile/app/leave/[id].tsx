import { useRef, useState } from 'react'
import { useLocalSearchParams } from 'expo-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/client'
import { resourceState } from '@/api/state'
import type { ConfirmationMaterial, DecisionResponse, LeaveRequest } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { hasCapability } from '@/capabilities'
import { LeaveApprovalView, type LeaveViewState } from '@/features/leave/LeaveApprovalView'
import { useLocale } from '@/i18n'
import { createIdempotencyKey } from '@/lib/idempotency'

export default function LeaveRoute() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const { me, request, refreshMe } = useAuth()
  const { locale, setLocale } = useLocale()
  const queryClient = useQueryClient()
  const [decisionState, setDecisionState] = useState<LeaveViewState>('ready')
  const permitted = hasCapability(me, 'hr', 'leave_approvals')
  const pending = useRef<{ material: ConfirmationMaterial; action: string; reason?: string; key: string } | null>(null)

  const detail = useQuery({
    queryKey: ['leave', id],
    queryFn: ({ signal }) =>
      request<{ ok: true; request: LeaveRequest }>(`/dashboard/mobile/leave/${encodeURIComponent(id || '')}`, { signal }),
    enabled: Boolean(id) && permitted,
  })

  const prepare = async (action: 'approve' | 'reject', reason?: string) => {
    const key = createIdempotencyKey(`leave-${action}`)
    const response = await request<DecisionResponse>(`/dashboard/mobile/leave/${encodeURIComponent(id || '')}/decision`, {
      method: 'POST',
      json: { action, reason, idempotency_key: key, confirm: false },
    })
    pending.current = { material: response.confirmation, action, reason, key }
    return {
      target: response.confirmation.summary,
      action,
      consequence: response.confirmation.consequence,
      currentState: response.confirmation.current_state,
      reason,
    }
  }

  const confirm = async () => {
    const value = pending.current
    if (!value) return
    try {
      const response = await request<DecisionResponse>(`/dashboard/mobile/leave/${encodeURIComponent(id || '')}/decision`, {
        method: 'POST',
        json: {
          action: value.action,
          reason: value.reason,
          idempotency_key: value.key,
          confirm: true,
          confirmation_id: value.material.confirmation_id,
          confirmation_hash: value.material.confirmation_hash,
        },
      })
      if (!response.ok) throw new ApiError(409, response.status, 'The decision was not completed.')
      setDecisionState('success')
      pending.current = null
      await Promise.all([refreshMe(), queryClient.invalidateQueries({ queryKey: ['mobile-priorities'] })])
    } catch (error) {
      if (error instanceof ApiError && error.code === 'stale_decision') setDecisionState('stale')
      else if (error instanceof ApiError && ['action_forbidden', 'out_of_scope'].includes(error.code)) setDecisionState('revoked')
      else throw error
    }
  }

  const state: LeaveViewState =
    !permitted
      ? 'permission'
      : decisionState !== 'ready'
      ? decisionState
      : resourceState({ loading: detail.isLoading, error: detail.error })
  const fallback: LeaveRequest = {
    leave_id: id || '',
    employee: { name: 'Employee' },
    leave_type: null,
    start_date: '',
    end_date: '',
    duration_days: null,
    reason: null,
    status: '',
    decision_note: null,
    requested_at: null,
    updated_at: null,
    shift_conflict_count: 0,
    balance: null,
    allowed_actions: [],
    destination: '',
  }
  return (
    <LeaveApprovalView
      request={detail.data?.request || fallback}
      state={state}
      company={me?.principal.company_code}
      onPrepareDecision={prepare}
      onConfirmDecision={confirm}
      onRetry={() => {
        setDecisionState('ready')
        void refreshMe()
        void detail.refetch()
      }}
      onLocale={() => void setLocale(locale === 'ar' ? 'en' : 'ar')}
    />
  )
}
