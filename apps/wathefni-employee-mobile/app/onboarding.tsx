import { useCallback, useState } from 'react'
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { Button, Card, ProgressBar, SectionTitle, StatusChip } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { buildUploadForm, pickDocument } from '@/lib/uploadDocument'
import { statusLabel, statusTone } from '@/lib/format'
import { colors, font, spacing } from '@/theme'
import type { OnboardingItem, OnboardingResponse } from '@/api/types'

export default function OnboardingScreen() {
  const { t } = useI18n()
  const { request, hasFeature, refreshMe } = useAuth()
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
        await request('/app/onboarding/documents', { method: 'POST', body: buildUploadForm(file, itemId) })
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
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />

  const data = query.data
  const pending = data?.pending ?? []
  const received = data?.received ?? []
  const canUpload = Boolean(data?.can_upload)

  const renderItem = (item: OnboardingItem, allowUpload: boolean) => {
    const key = item.item_id || item.document_type || item.label || Math.random().toString()
    const isDoc = (item.item_type || '').toLowerCase() === 'document' || Boolean(item.document_type)
    return (
      <Card key={key}>
        <View style={styles.itemHead}>
          <Text style={styles.itemLabel}>{item.label || item.document_type || item.item_id}</Text>
          <StatusChip label={statusLabel(item.status || 'pending', t)} tone={statusTone(item.status)} />
        </View>
        {allowUpload && canUpload && isDoc && item.item_id ? (
          <Button
            label={item.file_id ? t('onboarding.replace') : t('onboarding.upload')}
            variant="secondary"
            busy={uploadingId === item.item_id}
            onPress={() => onUpload(item)}
          />
        ) : null}
      </Card>
    )
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {data ? (
        <Card tone="accent" style={styles.progressCard}>
          <Text style={styles.progress}>
            {t('onboarding.progress', { done: data.received_count, total: data.required_total })}
          </Text>
          <ProgressBar value={data.required_total ? data.received_count / data.required_total : 1} />
        </Card>
      ) : null}

      {pending.length ? (
        <>
          <SectionTitle>{t('onboarding.pending')}</SectionTitle>
          {pending.map((item: OnboardingItem) => renderItem(item, true))}
        </>
      ) : (
        <EmptyState message={t('onboarding.empty')} />
      )}

      {received.length ? (
        <>
          <SectionTitle>{t('onboarding.received')}</SectionTitle>
          {received.map((item: OnboardingItem) => renderItem(item, true))}
        </>
      ) : null}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  progressCard: { padding: spacing.lg, gap: spacing.md },
  progress: { fontSize: font.body, color: colors.primary, fontWeight: '700' },
  itemHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  itemLabel: { fontSize: font.body, fontWeight: '600', color: colors.text, flexShrink: 1 },
})
