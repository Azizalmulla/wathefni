import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import type { PrioritiesResponse } from '@/api/types'
import { useAuth } from '@/auth/AuthProvider'
import { HRHomeView } from '@/features/home/HRHomeView'
import { useLocale } from '@/i18n'

export default function HomeRoute() {
  const router = useRouter()
  const { me, request, refreshMe } = useAuth()
  const { locale, setLocale } = useLocale()
  const priorities = useQuery({
    queryKey: ['mobile-priorities', me?.principal.user_id],
    queryFn: ({ signal }) => request<PrioritiesResponse>('/dashboard/mobile/priorities', { signal }),
    enabled: Boolean(me),
  })

  if (!me) return null
  return (
    <HRHomeView
      me={me}
      priorities={
        priorities.data || {
          ok: true,
          generated_at: '',
          ranking_policy: 'separated_authoritative_sections_no_invented_urgency',
          sections: [],
        }
      }
      state={priorities.isLoading ? 'loading' : priorities.isError ? 'error' : priorities.data?.sections.every((section) => !section.items.length) ? 'empty' : 'ready'}
      onRetry={() => {
        void refreshMe()
        void priorities.refetch()
      }}
      onLocale={() => void setLocale(locale === 'ar' ? 'en' : 'ar')}
      onOpen={(destination) => router.push(destination as never)}
    />
  )
}
