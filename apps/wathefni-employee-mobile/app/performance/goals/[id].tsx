import { useState } from 'react'
import { StyleSheet, Text, TextInput, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { colors, font, spacing, typeScaling } from '@/theme'

type Detail = {
  objective?: { title_en?: string; title_ar?: string; status?: string }
  key_results?: Array<{
    key_result_id: string
    title_en?: string
    title_ar?: string
    unit?: string
    target?: number
  }>
  rollup?: { progress_pct?: number | null }
  history?: unknown[]
  updates?: Array<{ update_id?: string; update_text?: string; confidence?: string | null }>
  operating_history?: { alignment_events?: unknown[]; target_versions?: unknown[] }
}

export default function PerformanceGoalDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const { t, isRTL } = useI18n()
  const { hasFeature, can, request } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<Detail>(['performance', 'goal', id], `/app/performance/objectives/${id}`, {
    enabled: enabled && Boolean(id),
  })
  const align = readingEdgeAlign(isRTL)
  const [value, setValue] = useState('')
  const [updateText, setUpdateText] = useState('')
  const [busy, setBusy] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const objective = query.data?.objective
  const krs = query.data?.key_results || []
  const pct = query.data?.rollup?.progress_pct
  const updates = query.data?.updates || []
  const history = query.data?.operating_history

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>
          {isRTL ? objective?.title_ar || objective?.title_en || '' : objective?.title_en || ''}
        </EditorialHeading>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
          {pct == null ? t('performance.progressUnknown') : `${t('performance.progress')} ${pct}%`}
        </Text>
        {krs.length === 0 ? <QuietEmpty title={t('performance.emptyGoals')} /> : null}
        {krs.map((kr) => (
          <View key={kr.key_result_id}>
            <ListRow
              title={isRTL ? kr.title_ar || kr.title_en || '' : kr.title_en || ''}
              subtitle={`${kr.unit || ''} · ${t('performance.progress')}`}
              icon="analytics-outline"
            />
            {can('performance', 'update') ? (
              <View style={styles.update}>
                <TextInput
                  value={value}
                  onChangeText={setValue}
                  keyboardType="numeric"
                  placeholder={t('performance.currentValue')}
                  placeholderTextColor={colors.navMuted}
                  style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
                />
                <PremiumButton
                  label={t('performance.updateProgress')}
                  disabled={busy || !value.trim()}
                  busy={busy}
                  onPress={async () => {
                    setBusy(true)
                    try {
                      await request('/app/performance/progress', {
                        method: 'POST',
                        json: {
                          subject_type: 'key_result',
                          subject_id: kr.key_result_id,
                          current_value: Number(value),
                        },
                      })
                      setValue('')
                      await query.refetch()
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              </View>
            ) : null}
          </View>
        ))}
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
          {t('performance.updateText')}
        </Text>
        <Text maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
          {t('performance.checkInNotProgress')}
        </Text>
        {updates.map((item) => (
          <Text key={String(item.update_id || item.update_text)} maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
            {item.update_text || ''}
            {item.confidence ? ` · ${t('performance.confidence')}: ${item.confidence}` : ''}
          </Text>
        ))}
        {can('performance', 'update') ? (
          <View style={styles.update}>
            <TextInput
              value={updateText}
              onChangeText={setUpdateText}
              placeholder={t('performance.addUpdate')}
              placeholderTextColor={colors.navMuted}
              style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
            />
            <PremiumButton
              label={t('performance.addUpdate')}
              disabled={busy || !updateText.trim()}
              busy={busy}
              onPress={async () => {
                if (!id) return
                setBusy(true)
                try {
                  await request(`/app/performance/objectives/${id}/updates`, {
                    method: 'POST',
                    json: {
                      subject_type: 'objective',
                      subject_id: id,
                      update_text: updateText.trim(),
                      reason: 'okr update',
                    },
                  })
                  setUpdateText('')
                  await query.refetch()
                } finally {
                  setBusy(false)
                }
              }}
            />
          </View>
        ) : null}
        {history?.alignment_events && history.alignment_events.length > 0 ? (
          <Text maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
            {t('performance.alignmentHint')}
          </Text>
        ) : null}
        <Text maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
          {t('performance.historyReady')}
          {history?.target_versions ? ` · ${history.target_versions.length}` : ''}
        </Text>
        <Text maxFontSizeMultiplier={typeScaling.caption} style={[styles.meta, align]}>
          {t('performance.talentOff')}
        </Text>
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: {
    color: colors.textSecondary,
    fontSize: font.body,
  },
  update: {
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  input: {
    minHeight: 48,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    color: colors.text,
    fontSize: font.body,
  },
})
