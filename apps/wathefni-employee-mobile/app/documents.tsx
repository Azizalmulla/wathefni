import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { openDocument } from '@/lib/documents'
import { DocumentsView } from '@/features/remaining/RemainingViews'
import type { DocumentsResponse } from '@/api/types'

export default function DocumentsScreen() {
  const { t } = useI18n()
  const { downloadFile, hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('documents')
  const query = useAppQuery<DocumentsResponse>(['documents'], '/app/documents', { enabled })
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const cancelRef = useRef<(() => Promise<void>) | null>(null)

  useEffect(() => () => {
    void cancelRef.current?.()
  }, [])

  // Document bytes use AuthProvider's refresh-aware authenticated download path;
  // the bearer token is never embedded in the URL.
  const onOpen = useCallback(
    async (fileId: string, filename: string | null) => {
      setOpeningId(fileId)
      setDownloadProgress(0)
      try {
        const transfer = await openDocument(fileId, filename, downloadFile, ({ progress }) => {
          setDownloadProgress(progress)
        })
        cancelRef.current = transfer.cancel
        await transfer.completed
      } catch (err) {
        if ((err as { code?: string })?.code === 'transfer_cancelled') return
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        cancelRef.current = null
        setOpeningId(null)
        setDownloadProgress(0)
      }
    },
    [downloadFile, t],
  )

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const documents = query.data?.documents ?? []
  return (
    <DocumentsView
      documents={documents}
      openingId={openingId}
      downloadProgress={downloadProgress}
      onOpen={(fileId, filename) => void onOpen(fileId, filename)}
      onCancel={() => void cancelRef.current?.()}
    />
  )
}
