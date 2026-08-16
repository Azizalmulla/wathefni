import { useMemo, useRef, useState } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '@hr/api/client'
import { openAuthenticatedFile } from '@hr/api/files'
import { resourceState } from '@hr/api/state'
import type { CandidateReview, ConfirmationMaterial, DecisionResponse } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  CandidateReviewView,
  type CandidateViewState,
} from '@hr/features/recruiting/CandidateReviewView'
import {
  candidateIsTerminal,
  localizeCandidateConsequence,
  localizeCandidateCurrentState,
  type CandidateDecideAction,
} from '@hr/features/recruiting/candidateComposition'
import { lifecycleStageLabel } from '@hr/features/recruiting/lifecycle'
import { createIdempotencyKey } from '@hr/lib/idempotency'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'

export default function CandidateRoute() {
  const { appKey } = useLocalSearchParams<{ appKey: string }>()
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, locale } = useI18n()
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const queryClient = useQueryClient()
  const [decisionState, setDecisionState] = useState<CandidateViewState>('ready')
  const permitted = routeAvailable(me, 'candidates')
  const pending = useRef<{ material: ConfirmationMaterial; action: string; key: string } | null>(null)

  const detail = useQuery({
    queryKey: ['candidate', appKey],
    queryFn: ({ signal }) =>
      request<{ ok: true; candidate: CandidateReview }>(
        `/dashboard/mobile/candidates/${encodeURIComponent(appKey || '')}`,
        { signal },
      ),
    enabled: Boolean(appKey) && permitted,
  })

  const candidate = detail.data?.candidate

  const prepare = async (action: CandidateDecideAction) => {
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
      action:
        action === 'shortlist'
          ? t('hrCandidate.shortlist')
          : action === 'reject'
            ? t('hrCandidate.reject')
            : t('hrCandidate.hire'),
      consequence: localizeCandidateConsequence(response.confirmation.consequence, action, t),
      currentState: localizeCandidateCurrentState(
        response.confirmation.current_state,
        appLocale,
        lifecycleStageLabel,
      ),
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
        queryClient.invalidateQueries({ queryKey: ['candidates'] }),
      ])
    } catch (error) {
      if (error instanceof ApiError && error.code === 'stale_decision') setDecisionState('stale')
      else if (
        error instanceof ApiError &&
        ['action_forbidden', 'out_of_scope', 'already_decided'].includes(error.code)
      ) {
        setDecisionState(error.code === 'already_decided' ? 'already_decided' : 'revoked')
      } else throw error
    }
  }

  const decidedOnServer = useMemo(() => {
    const stage = candidate?.overview?.canonical_stage || candidate?.overview?.status
    return candidateIsTerminal(stage)
  }, [candidate?.overview?.canonical_stage, candidate?.overview?.status])

  const state: CandidateViewState = !permitted
    ? 'permission'
    : decisionState !== 'ready'
      ? decisionState
      : decidedOnServer && !detail.isLoading
        ? 'already_decided'
        : resourceState({ loading: detail.isLoading, error: detail.error })

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
    offer: null,
    allowed_actions: [],
  }

  return (
    <CandidateReviewView
      review={candidate || fallback}
      state={state}
      company={me?.principal.company_code}
      onPrepareDecision={prepare}
      onConfirmDecision={confirm}
      onScheduleInterview={() => router.push('/hr/interviews' as never)}
      onOpenCV={(action) => {
        const cv = candidate?.cv
        const path = action === 'download' ? cv?.download_path : cv?.preview_path
        if (!cv || !path) return
        void openAuthenticatedFile({
          request,
          path,
          filename: cv.filename,
          mimeType: cv.mime_type,
          download: action === 'download',
        })
      }}
      onRetry={() => {
        setDecisionState('ready')
        void refreshMe()
        void detail.refetch()
      }}
      onBack={onBack}
    />
  )
}
