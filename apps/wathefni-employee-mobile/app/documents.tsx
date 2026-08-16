import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { EmployeePushedEscape } from '@/components/EmployeePushedEscape'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { approvedErrorMessage } from '@/api/errors'
import { openDocument } from '@/lib/documents'
import { DocumentsView } from '@/features/documents/DocumentsView'
import { pickDocument } from '@/lib/uploadDocument'
import { errorFeedback, successFeedback } from '@/native/haptics'
import type { DocumentsResponse } from '@/api/types'

export default function DocumentsScreen() {
  const { t } = useI18n()
  const { downloadFile, uploadFile, hasFeature, can, refreshMe } = useAuth()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()
  const enabled = hasFeature('documents')
  const canRenew = can('documents', 'upload_document')
  const query = useAppQuery<DocumentsResponse>(['documents'], '/app/documents', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const [renewingType, setRenewingType] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const cancelRef = useRef<(() => Promise<void>) | null>(null)
  const renewLock = useRef(false)
  /** Latest open wins — a newer tap cancels an in-flight download. */
  const openGeneration = useRef(0)

  useEffect(
    () => () => {
      void cancelRef.current?.()
    },
    [],
  )

  const onOpen = useCallback(
    async (fileId: string, filename: string | null) => {
      const generation = ++openGeneration.current
      // Cancel any prior transfer immediately so the latest tap is not queued.
      const previousCancel = cancelRef.current
      cancelRef.current = null
      if (previousCancel) void previousCancel()

      setOpeningId(fileId)
      setDownloadProgress(0)
      try {
        const transfer = await openDocument(fileId, filename, downloadFile, ({ progress }) => {
          if (generation !== openGeneration.current) return
          setDownloadProgress(progress)
        })
        if (generation !== openGeneration.current) {
          void transfer.cancel()
          return
        }
        cancelRef.current = transfer.cancel
        await transfer.completed
      } catch (err) {
        if (generation !== openGeneration.current) return
        if ((err as { code?: string })?.code === 'transfer_cancelled') return
        errorFeedback()
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        if (generation === openGeneration.current) {
          cancelRef.current = null
          setOpeningId(null)
          setDownloadProgress(0)
        }
      }
    },
    [downloadFile, t],
  )

  const onRenew = useCallback(
    async (documentType: string) => {
      if (!canRenew || renewLock.current) return
      try {
        const file = await pickDocument()
        if (!file) return
        renewLock.current = true
        setRenewingType(documentType)
        const transfer = uploadFile('/app/documents/renew', file, { document_type: documentType })
        await transfer.promise
        successFeedback()
        Alert.alert(t('documents.renewed'), t('documents.legitimacyNote'))
        // Soft invalidate after renew — never blocks navigation/open.
        void queryClient.invalidateQueries({ queryKey: ['documents'] })
        void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
        void queryClient.invalidateQueries({ queryKey: ['home'] })
      } catch (err) {
        if ((err as { code?: string })?.code === 'transfer_cancelled') return
        errorFeedback()
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        renewLock.current = false
        setRenewingType(null)
      }
    },
    [canRenew, uploadFile, queryClient, t],
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (!enabled) {
    return <FeatureUnavailableState feature="documents" onRefresh={() => void refreshMe()} />
  }
  if (query.isLoading && !query.data) {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <LoadingState />
      </EmployeePushedEscape>
    )
  }
  if (query.isError && !query.data) {
    return (
      <EmployeePushedEscape onBack={onBack}>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </EmployeePushedEscape>
    )
  }
  const documents = query.data?.documents ?? []
  const compliance = query.data?.compliance ?? []
  return (
    <DocumentsView
      documents={documents}
      compliance={compliance}
      openingId={openingId}
      downloadProgress={downloadProgress}
      renewingType={renewingType}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onOpen={(fileId, filename) => void onOpen(fileId, filename)}
      onCancel={() => void cancelRef.current?.()}
      onRenew={canRenew ? (documentType) => void onRenew(documentType) : undefined}
      onBack={onBack}
    />
  )
}
