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
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { useI18n } from '@/i18n'

export function JobsPositionsView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t } = useI18n()
  const permitted = routeAvailable(me, 'candidates')

  const query = useQuery({
    queryKey: ['prehire-positions', 'open'],
    queryFn: ({ signal }) => mobileApi.positions(request, { status: 'open', limit: 50, signal }),
    enabled: permitted,
  })

  const items = (query.data?.items || []).map<CreamQueueItem>((row) => ({
    id: row.position_code,
    title: row.title || row.position_code,
    subtitle: [row.department, row.position_code].filter(Boolean).join(' · ') || undefined,
    meta:
      row.ready_for_review != null && row.ready_for_review > 0
        ? String(row.ready_for_review)
        : undefined,
    status: row.status || undefined,
    tone: 'neutral',
  }))

  const state = !permitted
    ? 'permission'
    : resourceState({
        loading: query.isLoading,
        error: query.error,
        empty: items.length === 0,
      })

  return (
    <CreamQueueScreen
      eyebrow={t('hrJobs.eyebrow')}
      title={t('hrJobs.title')}
      state={state}
      items={items}
      onBack={onBack}
      onRetry={() => void query.refetch()}
      emptyTitle={t('hrJobs.emptyTitle')}
      emptyBody={t('hrJobs.emptyBody')}
      onOpen={(item) =>
        router.push(
          toHrPath(`/candidates?position=${encodeURIComponent(item.id)}`) as never,
        )
      }
    />
  )
}
