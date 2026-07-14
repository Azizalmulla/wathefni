import { useCallback, useEffect, useRef, useState } from 'react'
import { ActionSheetIOS, Alert, Linking, Platform } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth, type CancellableTransfer } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import {
  pickDocument,
  pickImageFromLibrary,
  takePhoto,
  UploadPickError,
  type PickedFile,
} from '@/lib/uploadDocument'
import { successHaptic } from '@/native/haptics'
import {
  OnboardingErrorView,
  OnboardingLoadingView,
  OnboardingView,
} from '@/features/onboarding/OnboardingView'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'

export default function OnboardingScreen() {
  const { t } = useI18n()
  const { uploadFile, hasFeature, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const enabled = hasFeature('onboarding')
  const query = useAppQuery<OnboardingResponse>(['onboarding'], '/app/onboarding', { enabled })
  const [uploadingId, setUploadingId] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [failedUpload, setFailedUpload] = useState<{ item: OnboardingItem; file: PickedFile } | null>(null)
  const transferRef = useRef<CancellableTransfer<void> | null>(null)

  useEffect(() => () => {
    void transferRef.current?.cancel()
  }, [])

  const performUpload = useCallback(
    async (item: OnboardingItem, file: PickedFile) => {
      const itemId = item.item_id
      if (!itemId) return
      setUploadingId(itemId)
      setUploadProgress(0)
      setFailedUpload(null)
      try {
        const transfer = uploadFile(
          '/app/onboarding/documents',
          file,
          { item_id: itemId },
          ({ progress }) => setUploadProgress(progress),
        )
        transferRef.current = transfer
        await transfer.promise
        successHaptic()
        await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
        await queryClient.invalidateQueries({ queryKey: ['documents'] })
      } catch (err) {
        if ((err as { code?: string })?.code === 'transfer_cancelled') return
        setFailedUpload({ item, file })
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        transferRef.current = null
        setUploadingId(null)
        setUploadProgress(0)
      }
    },
    [uploadFile, queryClient, t],
  )

  const onUpload = useCallback(async (item: OnboardingItem) => {
    try {
      const source = await chooseUploadSource(t)
      const file =
        source === 'camera'
          ? await takePhoto()
          : source === 'library'
            ? await pickImageFromLibrary()
            : source === 'files'
              ? await pickDocument()
              : null
      if (file) await performUpload(item, file)
    } catch (error) {
      if (error instanceof UploadPickError) {
        Alert.alert(t('onboarding.permissionTitle'), t('onboarding.permissionMessage'), [
          { text: t('common.cancel'), style: 'cancel' },
          { text: t('onboarding.openSettings'), onPress: () => void Linking.openSettings() },
        ])
        return
      }
      Alert.alert(t('common.error'), approvedErrorMessage(error, t))
    }
  }, [performUpload, t])

  const cancelUpload = useCallback(() => {
    void transferRef.current?.cancel()
  }, [])

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <OnboardingLoadingView />
  if (query.isError || !query.data) return <OnboardingErrorView onRetry={() => void query.refetch()} />

  return (
    <OnboardingView
      data={query.data}
      uploadingId={uploadingId}
      uploadProgress={uploadProgress}
      failedUploadId={failedUpload?.item.item_id ?? null}
      onUpload={(item) => void onUpload(item)}
      onCancelUpload={cancelUpload}
      onRetryUpload={() => {
        if (failedUpload) void performUpload(failedUpload.item, failedUpload.file)
      }}
      onBack={() => router.back()}
    />
  )
}

type UploadSource = 'camera' | 'library' | 'files'

function chooseUploadSource(t: (key: string) => string): Promise<UploadSource | null> {
  const labels = [
    t('onboarding.takePhoto'),
    t('onboarding.photoLibrary'),
    t('onboarding.browseFiles'),
    t('common.cancel'),
  ]
  if (Platform.OS === 'ios') {
    return new Promise((resolve) => {
      ActionSheetIOS.showActionSheetWithOptions(
        { options: labels, cancelButtonIndex: 3, title: t('onboarding.uploadSource') },
        (index) => resolve(index === 0 ? 'camera' : index === 1 ? 'library' : index === 2 ? 'files' : null),
      )
    })
  }
  return new Promise((resolve) => {
    Alert.alert(t('onboarding.uploadSource'), undefined, [
      { text: labels[0], onPress: () => resolve('camera') },
      { text: labels[1], onPress: () => resolve('library') },
      { text: labels[2], onPress: () => resolve('files') },
      { text: labels[3], style: 'cancel', onPress: () => resolve(null) },
    ], { cancelable: true, onDismiss: () => resolve(null) })
  })
}
