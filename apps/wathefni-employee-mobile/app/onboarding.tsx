import { useCallback, useEffect, useRef, useState } from 'react'
import { ActionSheetIOS, Alert, Linking, Platform } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth, type CancellableTransfer, type DocumentUploadResult } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { approvedErrorMessage, documentValidationSuccessMessage } from '@/api/errors'
import {
  pickDocument,
  pickImageFromLibrary,
  takePhoto,
  UploadPickError,
  type PickedFile,
} from '@/lib/uploadDocument'
import { openDocument } from '@/lib/documents'
import { errorFeedback, successFeedback, warningFeedback } from '@/native/haptics'
import {
  OnboardingErrorView,
  OnboardingLoadingView,
  OnboardingView,
  type VersionRow,
} from '@/features/onboarding/OnboardingView'
import { projectOnboardingLifecycle } from '@/features/onboarding/lifecycleProjection'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'

export default function OnboardingScreen() {
  const { t } = useI18n()
  const { uploadFile, downloadFile, hasFeature, can, refreshMe, request } = useAuth()
  const router = useRouter()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()
  const enabled = hasFeature('onboarding')
  const canUploadDocuments = can('onboarding', 'upload_document')
  const query = useAppQuery<OnboardingResponse>(['onboarding'], '/app/onboarding', {
    enabled,
    // Always refetch when opening checklist so Wave 2A groups are authoritative.
    staleTime: 0,
  })

  useEffect(() => {
    if (query.data) {
      // Contract log is inside projectOnboardingLifecycle / logOnboardingContract.
      projectOnboardingLifecycle(query.data)
    }
  }, [query.data])
  const [uploadingId, setUploadingId] = useState<string | null>(null)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [failedUploadItemId, setFailedUploadItemId] = useState<string | null>(null)
  const [versionsByItem, setVersionsByItem] = useState<Record<string, VersionRow[]>>({})
  const [versionsLoadingId, setVersionsLoadingId] = useState<string | null>(null)
  const transferRef = useRef<CancellableTransfer<DocumentUploadResult> | null>(null)
  const uploadLock = useRef(false)
  const versionsLock = useRef(false)
  const onUploadRef = useRef<(item: OnboardingItem, part?: 'front' | 'back') => void>(() => {})
  const cancelPreviewRef = useRef<(() => Promise<void>) | null>(null)
  /** Latest preview wins — a newer tap cancels an in-flight download. */
  const openGeneration = useRef(0)

  useEffect(
    () => () => {
      void transferRef.current?.cancel()
      void cancelPreviewRef.current?.()
    },
    [],
  )

  const softRefreshOnboarding = useCallback(() => {
    // Soft invalidate — never await before continuing UI work / navigation.
    void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    void queryClient.invalidateQueries({ queryKey: ['documents'] })
    void queryClient.invalidateQueries({ queryKey: ['home'] })
  }, [queryClient])

  const performUpload = useCallback(
    async (item: OnboardingItem, file: PickedFile, part?: 'front' | 'back') => {
      const itemId = item.item_id
      if (!canUploadDocuments || !itemId || uploadLock.current) return
      uploadLock.current = true
      setUploadingId(part ? `${itemId}:${part}` : itemId)
      setUploadProgress(0)
      setFailedUploadItemId(null)
      try {
        const parameters: Record<string, string> = { item_id: itemId }
        if (part) parameters.part = part
        const transfer = uploadFile(
          '/app/onboarding/documents',
          file,
          parameters,
          ({ progress }) => setUploadProgress(progress),
        )
        transferRef.current = transfer
        const uploaded = await transfer.promise
        successFeedback()
        setVersionsByItem((prev) => {
          const next = { ...prev }
          delete next[itemId]
          return next
        })
        const uncertainCopy = documentValidationSuccessMessage(uploaded?.validation, t)
        if (uncertainCopy) {
          Alert.alert(t('onboarding.uploaded'), uncertainCopy)
        } else if (part && uploaded && (uploaded as { parts_complete?: boolean }).parts_complete === false) {
          Alert.alert(t('onboarding.uploaded'), t('onboarding.civilId.bothRequired'))
        }
        softRefreshOnboarding()
      } catch (err) {
        if ((err as { code?: string })?.code === 'transfer_cancelled') return
        // Never auto-resend a rejected file — mark the item and reopen picker on Try again.
        setFailedUploadItemId(part ? `${itemId}:${part}` : itemId)
        const code = String((err as { code?: string })?.code || '')
        const isValidation = code.startsWith('document_validation_')
        const title = isValidation ? t('onboarding.validationTitle') : t('common.error')
        if (isValidation) warningFeedback()
        else errorFeedback()
        Alert.alert(title, approvedErrorMessage(err, t), [
          { text: t('common.cancel'), style: 'cancel' },
          {
            text: t('common.retry'),
            onPress: () => {
              void onUploadRef.current?.(item, part)
            },
          },
        ])
      } finally {
        transferRef.current = null
        uploadLock.current = false
        setUploadingId(null)
        setUploadProgress(0)
      }
    },
    [canUploadDocuments, softRefreshOnboarding, t, uploadFile],
  )

  const onUpload = useCallback(async (item: OnboardingItem, part?: 'front' | 'back') => {
    if (!canUploadDocuments || uploadLock.current || uploadingId) return
    const actions = item.actions || []
    const dual =
      Boolean(item.civil_id_parts) &&
      !item.civil_id_parts?.legacy_single &&
      actions.some((a) =>
        a === 'upload_front' ||
        a === 'upload_back' ||
        a === 'replace_front' ||
        a === 'replace_back',
      )
    if (dual) {
      if (!part) return
      const allowed =
        (part === 'front' && (actions.includes('upload_front') || actions.includes('replace_front'))) ||
        (part === 'back' && (actions.includes('upload_back') || actions.includes('replace_back')))
      if (!allowed) return
    } else if (!actions.some((a) => a === 'upload' || a === 'replace' || a === 'resubmit')) {
      return
    }
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
      if (file) await performUpload(item, file, part)
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
  }, [canUploadDocuments, performUpload, t, uploadingId])

  useEffect(() => {
    onUploadRef.current = (item, part) => {
      void onUpload(item, part)
    }
  }, [onUpload])

  const onPreview = useCallback(
    async (item: OnboardingItem, part?: 'front' | 'back') => {
      const fileId = part
        ? item.civil_id_parts?.[part]?.file_id || null
        : item.file_id
      if (!fileId) return
      const generation = ++openGeneration.current
      const previousCancel = cancelPreviewRef.current
      cancelPreviewRef.current = null
      if (previousCancel) void previousCancel()

      setOpeningId(item.item_id || fileId)
      try {
        const handle = await openDocument(
          fileId,
          part
            ? `${item.label || item.item_id || 'civil_id'}-${part}`
            : item.version_filename || item.label || item.item_id || 'document',
          downloadFile,
        )
        if (generation !== openGeneration.current) {
          void handle.cancel?.()
          return
        }
        cancelPreviewRef.current = handle.cancel || null
        await handle.completed
      } catch (error) {
        if (generation !== openGeneration.current) return
        if ((error as { code?: string })?.code === 'transfer_cancelled') return
        Alert.alert(t('common.error'), approvedErrorMessage(error, t))
      } finally {
        if (generation === openGeneration.current) {
          cancelPreviewRef.current = null
          setOpeningId(null)
        }
      }
    },
    [downloadFile, t],
  )

  const onViewVersions = useCallback(
    async (item: OnboardingItem) => {
      const itemId = item.item_id
      if (!itemId || versionsLock.current) return
      if (versionsByItem[itemId]?.length) return
      versionsLock.current = true
      setVersionsLoadingId(itemId)
      try {
        const res = await request<{ ok: boolean; versions?: VersionRow[] }>(
          `/app/onboarding/items/${encodeURIComponent(itemId)}/versions`,
        )
        setVersionsByItem((prev) => ({ ...prev, [itemId]: res.versions || [] }))
      } catch (error) {
        Alert.alert(t('common.error'), approvedErrorMessage(error, t))
      } finally {
        versionsLock.current = false
        setVersionsLoadingId(null)
      }
    },
    [request, t, versionsByItem],
  )

  const cancelUpload = useCallback(() => {
    void transferRef.current?.cancel()
  }, [])

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  const onOpenBank = useCallback(() => {
    // Immediate navigation — never await a checklist refresh first.
    router.push('/bank')
  }, [router])

  if (!enabled) {
    return <FeatureUnavailableState feature="onboarding" onRefresh={() => void refreshMe()} />
  }
  if (query.isLoading && !query.data) return <OnboardingLoadingView onBack={onBack} />
  if ((query.isError || !query.data) && !query.data) {
    return <OnboardingErrorView onRetry={() => void query.refetch()} onBack={onBack} />
  }
  if (!query.data) return <OnboardingLoadingView onBack={onBack} />

  return (
    <OnboardingView
      data={query.data}
      canUploadDocuments={canUploadDocuments}
      uploadingId={uploadingId}
      uploadProgress={uploadProgress}
      failedUploadId={failedUploadItemId}
      openingId={openingId}
      versionsByItem={versionsByItem}
      versionsLoadingId={versionsLoadingId}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onUpload={(item, part) => void onUpload(item, part)}
      onPreview={(item, part) => void onPreview(item, part)}
      onViewVersions={(item) => void onViewVersions(item)}
      onCancelUpload={cancelUpload}
      onRetryUpload={(item, part) => {
        // Try again always reopens picker for a new file — never resends a rejected upload.
        setFailedUploadItemId(null)
        void onUpload(item, part)
      }}
      onOpenBank={hasFeature('bank') ? onOpenBank : undefined}
      onBack={onBack}
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
