import { useCallback, useState } from 'react'
import { Alert, FlatList, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { Button } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { openDocument } from '@/lib/documents'
import { formatDate } from '@/lib/format'
import { colors, font, radius, spacing } from '@/theme'
import type { DocumentsResponse } from '@/api/types'

export default function DocumentsScreen() {
  const { t, locale } = useI18n()
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
  if (!documents.length) return <EmptyState message={t('documents.empty')} />

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={documents}
      keyExtractor={(d) => d.file_id}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.label}>{item.label || item.document_type || item.filename}</Text>
            <Text style={styles.meta}>{formatDate(item.stored_at, locale)}</Text>
          </View>
          {item.has_file ? (
            <Button label={t('documents.view')} variant="secondary" busy={openingId === item.file_id} onPress={() => onOpen(item.file_id, item.filename)} />
          ) : null}
        </View>
      )}
    />
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  flex: { flex: 1, gap: 2 },
  label: { fontSize: font.body, fontWeight: '600', color: colors.text },
  meta: { fontSize: font.tiny, color: colors.subtle },
})
