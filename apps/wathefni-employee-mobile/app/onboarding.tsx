import { useCallback, useState } from 'react'
import { Alert } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { buildUploadForm, pickDocument } from '@/lib/uploadDocument'
import {
  OnboardingErrorView,
  OnboardingLoadingView,
  OnboardingView,
} from '@/features/onboarding/OnboardingView'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'

export default function OnboardingScreen() {
  const { t } = useI18n()
  const { request, hasFeature, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const enabled = hasFeature('onboarding')
  const query = useAppQuery<OnboardingResponse>(['onboarding'], '/app/onboarding', { enabled })
  const [uploadingId, setUploadingId] = useState<string | null>(null)

  const onUpload = useCallback(
    async (item: OnboardingItem) => {
      const itemId = item.item_id
      if (!itemId) return
      const file = await pickDocument()
      if (!file) return
      setUploadingId(itemId)
      try {
        await request('/app/onboarding/documents', {
          method: 'POST',
          body: buildUploadForm(file, itemId),
        })
        await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
        await queryClient.invalidateQueries({ queryKey: ['documents'] })
      } catch (err) {
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        setUploadingId(null)
      }
    },
    [request, queryClient, t],
  )

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <OnboardingLoadingView />
  if (query.isError || !query.data) return <OnboardingErrorView onRetry={() => void query.refetch()} />

  return (
    <OnboardingView
      data={query.data}
      uploadingId={uploadingId}
      onUpload={(item) => void onUpload(item)}
      onBack={() => router.back()}
    />
  )
}
