import { useMemo } from 'react'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'
import { Text } from 'react-native'

import { mobileApi } from '@hr/api/mobile'
import { resourceState } from '@hr/api/state'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  CreamQueueScreen,
  type CreamQueueItem,
} from '@hr/features/recruiting/CreamQueueScreen'
import {
  intakeLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@hr/features/recruiting/lifecycle'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { ListRow } from '@/components/lists'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, typeScaling } from '@/theme'
import { candidateStageTone } from '@hr/features/recruiting/candidateComposition'

function toneForStage(status: string | null | undefined) {
  return candidateStageTone(status)
}

export function CandidatesQueueView() {
  const { position: positionParam } = useLocalSearchParams<{ position?: string }>()
  const position = String(positionParam || '').trim()
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const permitted = routeAvailable(me, 'candidates')

  const query = useQuery({
    queryKey: ['candidates', position || '__none__'],
    queryFn: ({ signal }) =>
      mobileApi.candidates(request, {
        position: position || undefined,
        signal,
      }),
    enabled: permitted && Boolean(position),
  })

  const requiresPosition = !position
  const honestyNeedsPosition =
    Boolean(position) && Boolean(query.data?.requires_position) && (query.data?.items.length || 0) === 0
  const rankingUnavailable =
    Boolean(position) &&
    Boolean(query.data?.ranking_unavailable) &&
    !query.data?.requires_position &&
    (query.data?.items.length || 0) === 0

  const sorted = useMemo(
    () => [...(query.data?.items || [])].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)),
    [query.data?.items],
  )

  const items = sorted.map<CreamQueueItem>((item) => ({
    id: item.app_key,
    title: item.candidate.name,
    subtitle: item.position?.title || item.position?.code,
    meta: [
      intakeLabel(item.intake_source, appLocale),
      lifecycleCommunicationLabel(item.communication_status, appLocale),
      item.next_human_action ? workflowLabel(item.next_human_action, appLocale) : null,
    ]
      .filter(Boolean)
      .join(' · '),
    status: lifecycleStageLabel(item.canonical_stage || item.status, appLocale),
    tone: toneForStage(item.canonical_stage || item.status),
  }))

  const state = !permitted
    ? 'permission'
    : requiresPosition || honestyNeedsPosition || rankingUnavailable
      ? 'empty'
      : resourceState({
          loading: query.isLoading,
          error: query.error,
          stale: query.data?.stale,
          empty: items.length === 0,
        })

  return (
    <CreamQueueScreen
      eyebrow={t('hrCandidates.eyebrow')}
      title={
        position
          ? t('hrCandidates.titleScoped', { position })
          : t('hrCandidates.title')
      }
      state={state}
      items={items}
      onBack={onBack}
      onRetry={() => void query.refetch()}
      onOpen={(item) => router.push(toHrPath(`/candidates/${encodeURIComponent(item.id)}`) as never)}
      emptyTitle={
        requiresPosition || honestyNeedsPosition
          ? t('hrCandidates.requiresPositionTitle')
          : rankingUnavailable
            ? t('hrCandidates.rankingUnavailableTitle')
            : t('hrCandidates.emptyTitle')
      }
      emptyBody={
        requiresPosition || honestyNeedsPosition
          ? t('hrCandidates.requiresPositionBody')
          : rankingUnavailable
            ? t('hrCandidates.rankingUnavailableBody')
            : t('hrCandidates.emptyBody')
      }
      headerExtra={
        position ? (
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[{ color: colors.subtle, fontSize: font.tiny }, align]}>
            {t('hrCandidates.scopedHint', { position })}
          </Text>
        ) : null
      }
      banner={
        requiresPosition || honestyNeedsPosition ? (
          <ListRow
            title={t('hrCandidates.pickJob')}
            subtitle={t('hrCandidates.pickJobBody')}
            icon="briefcase-outline"
            showChevron
            onPress={() => router.push(toHrPath('/jobs') as never)}
            style={{ backgroundColor: colors.surface }}
          />
        ) : null
      }
    />
  )
}
