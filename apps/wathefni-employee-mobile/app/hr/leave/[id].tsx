import { useMemo, useRef, useState } from 'react'
import { useLocalSearchParams } from 'expo-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@hr/api/client'
import { resourceState } from '@hr/api/state'
import type { ConfirmationMaterial, DecisionResponse, LeaveRequest } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { hasCapability } from '@hr/capabilities'
import { LeaveApprovalView, type LeaveViewState } from '@hr/features/leave/LeaveApprovalView'
import {
  localizeLeaveConsequence,
  localizeLeaveCurrentState,
} from '@hr/features/leave/leaveComposition'
import { createIdempotencyKey } from '@hr/lib/idempotency'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'

function paramId(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return String(value[0] || '')
  return String(value || '')
}

export default function LeaveRoute() {
  const params = useLocalSearchParams<{ id: string | string[] }>()
  const id = paramId(params.id)
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [decisionState, setDecisionState] = useState<LeaveViewState>('ready')
  const permitted = hasCapability(me, 'hr', 'leave_approvals')
  const pending = useRef<{
    material: ConfirmationMaterial
    action: 'approve' | 'reject'
    reason?: string
    key: string
  } | null>(null)

  const detail = useQuery({
    queryKey: ['leave', id],
    queryFn: ({ signal }) =>
      request<{ ok: true; request: LeaveRequest }>(
        `/dashboard/mobile/leave/${encodeURIComponent(id || '')}`,
        { signal },
      ),
    enabled: Boolean(id) && permitted,
  })

  const leaveRequest = detail.data?.request

  const prepare = async (action: 'approve' | 'reject', reason?: string) => {
    const key = createIdempotencyKey(`leave-${action}`)
    const response = await request<DecisionResponse>(
      `/dashboard/mobile/leave/${encodeURIComponent(id || '')}/decision`,
      {
        method: 'POST',
        json: { action, reason, idempotency_key: key, confirm: false },
      },
    )
    if (!response?.confirmation?.confirmation_id || !response.confirmation.confirmation_hash) {
      throw new ApiError(409, 'confirmation_unavailable', t('confirm.errorGeneric'))
    }
    pending.current = { material: response.confirmation, action, reason, key }
    return {
      target: response.confirmation.summary,
      action: action === 'approve' ? t('hrLeave.approve') : t('hrLeave.reject'),
      consequence: localizeLeaveConsequence(response.confirmation.consequence, action, t),
      currentState: localizeLeaveCurrentState(response.confirmation.current_state, t),
      reason,
    }
  }

  const confirm = async () => {
    const value = pending.current
    if (!value) {
      throw new ApiError(409, 'confirmation_unavailable', t('confirm.errorMissing'))
    }
    try {
      const response = await request<DecisionResponse>(
        `/dashboard/mobile/leave/${encodeURIComponent(id || '')}/decision`,
        {
          method: 'POST',
          json: {
            action: value.action,
            reason: value.reason,
            idempotency_key: value.key,
            confirm: true,
            confirmation_id: value.material.confirmation_id,
            confirmation_hash: value.material.confirmation_hash,
          },
        },
      )
      if (!response.ok) {
        throw new ApiError(
          409,
          String(response.status || 'decision_failed'),
          t('confirm.errorGeneric'),
        )
      }
      setDecisionState('success')
      pending.current = null
      // Refresh after dismiss path — never block Confirm on post-success fan-out.
      void Promise.all([
        refreshMe(),
        queryClient.invalidateQueries({ queryKey: ['mobile-priorities'] }),
        queryClient.invalidateQueries({ queryKey: ['leave', id] }),
      ]).catch(() => undefined)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'stale_decision') {
        setDecisionState('stale')
        pending.current = null
        return
      }
      if (
        error instanceof ApiError &&
        ['action_forbidden', 'out_of_scope'].includes(error.code)
      ) {
        setDecisionState('revoked')
        pending.current = null
        return
      }
      throw error
    }
  }

  const decidedOnServer = useMemo(() => {
    const status = String(leaveRequest?.status || '').toLowerCase()
    return Boolean(status && status !== 'requested')
  }, [leaveRequest?.status])

  const state: LeaveViewState = !permitted
    ? 'permission'
    : decisionState !== 'ready'
      ? decisionState
      : decidedOnServer && !detail.isLoading
        ? 'already_decided'
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
      request={leaveRequest || fallback}
      state={state}
      company={me?.principal.company_code}
      onPrepareDecision={prepare}
      onConfirmDecision={confirm}
      onRetry={() => {
        setDecisionState('ready')
        void refreshMe()
        void detail.refetch()
      }}
      onBack={onBack}
    />
  )
}
