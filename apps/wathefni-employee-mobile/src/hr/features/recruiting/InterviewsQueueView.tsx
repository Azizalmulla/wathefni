import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import { resourceState } from '@hr/api/state'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  CreamQueueScreen,
  type CreamQueueItem,
} from '@hr/features/recruiting/CreamQueueScreen'
import {
  facetStatusLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@hr/features/recruiting/lifecycle'
import { formatDateTime } from '@hr/i18n/date'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'
import type { StatusTone } from '@/components/ui'

function interviewTone(status: string): StatusTone {
  const value = status.toLowerCase()
  if (value.includes('complete')) return 'success'
  if (value.includes('cancel') || value.includes('no_show')) return 'danger'
  if (value.includes('schedul') || value.includes('pending')) return 'warning'
  return 'neutral'
}

export function InterviewsQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, locale } = useI18n()
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const permitted = routeAvailable(me, 'interviews')

  const query = useQuery({
    queryKey: ['interviews'],
    queryFn: ({ signal }) => mobileApi.interviews(request, signal),
    enabled: permitted,
  })

  const items = (query.data?.items || []).map<CreamQueueItem>((item) => ({
    id: item.interview_id,
    title: item.candidate.name,
    subtitle: item.position?.title || item.position?.code,
    meta: [
      facetStatusLabel(item.status, appLocale),
      item.scheduled_at ? formatDateTime(item.scheduled_at, appLocale) : null,
      item.next_human_action ? workflowLabel(item.next_human_action, appLocale) : null,
    ]
      .filter(Boolean)
      .join(' · '),
    status: lifecycleStageLabel(item.application_stage, appLocale),
    tone: interviewTone(item.status),
  }))

  const state = !permitted
    ? 'permission'
    : resourceState({
        loading: query.isLoading,
        error: query.error,
        stale: query.data?.stale,
        empty: items.length === 0,
      })

  return (
    <CreamQueueScreen
      eyebrow={t('hrInterviews.eyebrow')}
      title={t('hrInterviews.title')}
      state={state}
      items={items}
      onBack={onBack}
      onRetry={() => void query.refetch()}
      emptyTitle={t('hrInterviews.emptyTitle')}
      emptyBody={t('hrInterviews.emptyBody')}
      onOpen={(item) =>
        router.push(toHrPath(`/interviews/${encodeURIComponent(item.id)}`) as never)
      }
    />
  )
}
