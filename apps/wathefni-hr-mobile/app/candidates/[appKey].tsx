import { useRef, useState } from 'react'
import { useLocalSearchParams } from 'expo-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/client'
import type { CandidateReview, ConfirmationMaterial, DecisionResponse } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { CandidateReviewView, type CandidateViewState } from '@/features/recruiting/CandidateReviewView'
import { useLocale } from '@/i18n'
import { createIdempotencyKey } from '@/lib/idempotency'

export default function CandidateRoute() {
  const { appKey } = useLocalSearchParams<{ appKey: string }>()
  const { me, request, refreshMe } = useAuth()
  const { locale, setLocale } = useLocale()
  const queryClient = useQueryClient()
  const [decisionState, setDecisionState] = useState<CandidateViewState>('ready')
  const pending = useRef<{ material: ConfirmationMaterial; action: string; key: string } | null>(null)
  const detail = useQuery({
    queryKey: ['candidate', appKey],
    queryFn: ({ signal }) =>
      request<{ ok: true; candidate: CandidateReview }>(
        `/dashboard/mobile/candidates/${encodeURIComponent(appKey || '')}`,
        { signal },
      ),
    enabled: Boolean(appKey),
  })

  const prepare = async (action: 'shortlist' | 'reject' | 'hire') => {
    const key = createIdempotencyKey(`candidate-${action}`)
    const response = await request<DecisionResponse>(
      `/dashboard/mobile/candidates/${encodeURIComponent(appKey || '')}/decision`,
      {
        method: 'POST',
        json: { action, idempotency_key: key, confirm: false },
      },
    )
    pending.current = { material: response.confirmation, action, key }
    return {
      target: response.confirmation.summary,
      action,
      consequence: response.confirmation.consequence,
      currentState: response.confirmation.current_state,
    }
  }

  const confirm = async () => {
    const value = pending.current
    if (!value) return
    try {
      const response = await request<DecisionResponse>(
        `/dashboard/mobile/candidates/${encodeURIComponent(appKey || '')}/decision`,
        {
          method: 'POST',
          json: {
            action: value.action,
            idempotency_key: value.key,
            confirm: true,
            confirmation_id: value.material.confirmation_id,
            confirmation_hash: value.material.confirmation_hash,
          },
        },
      )
      if (!response.ok) throw new ApiError(409, response.status, 'The decision was not completed.')
      setDecisionState('success')
      pending.current = null
      await Promise.all([
        refreshMe(),
        queryClient.invalidateQueries({ queryKey: ['mobile-priorities'] }),
        queryClient.invalidateQueries({ queryKey: ['candidate', appKey] }),
      ])
    } catch (error) {
      if (error instanceof ApiError && error.code === 'stale_decision') setDecisionState('stale')
      else if (error instanceof ApiError && error.code === 'action_forbidden') setDecisionState('revoked')
      else throw error
    }
  }

  const state: CandidateViewState = detail.isLoading
    ? 'loading'
    : detail.isError
      ? detail.error instanceof ApiError && detail.error.code === 'action_forbidden'
        ? 'revoked'
        : 'error'
      : decisionState

  const fallback: CandidateReview = {
    app_key: appKey || '',
    overview: {},
    ranking: {
      score: null,
      confidence: null,
      reasons: [],
      evidence: [],
      concerns: [],
      missing_evidence: [],
      ai_advisory: true,
    },
    cv: {
      available: false,
      filename: null,
      mime_type: null,
      size_bytes: null,
      preview_path: null,
      download_path: null,
    },
    interview: null,
    communication_status: [],
    allowed_actions: [],
  }
  return (
    <CandidateReviewView
      review={detail.data?.candidate || fallback}
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
