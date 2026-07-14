import { useCallback, useState } from 'react'
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
  const { download, hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('documents')
  const query = useAppQuery<DocumentsResponse>(['documents'], '/app/documents', { enabled })
  const [openingId, setOpeningId] = useState<string | null>(null)

  // Document bytes use AuthProvider's refresh-aware authenticated download path;
  // the bearer token is never embedded in the URL.
  const onOpen = useCallback(
    async (fileId: string, filename: string | null) => {
      setOpeningId(fileId)
      try {
        await openDocument(fileId, filename, download)
      } catch (err) {
        Alert.alert(t('common.error'), approvedErrorMessage(err, t))
      } finally {
        setOpeningId(null)
      }
    },
    [download, t],
  )

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const documents = query.data?.documents ?? []
  return (
    <DocumentsView
      documents={documents}
      openingId={openingId}
      onOpen={(fileId, filename) => void onOpen(fileId, filename)}
    />
  )
}
