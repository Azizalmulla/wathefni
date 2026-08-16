import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { colors, font, spacing, typeScaling } from '@/theme'

type Objective = {
  objective_id: string
  title_en?: string
  title_ar?: string
  status?: string
  rollup?: { progress_pct?: number | null }
}

export default function PerformanceGoalsScreen() {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const { hasFeature } = useAuth()
  const enabled = hasFeature('performance')
  const query = useAppQuery<{ objectives?: Objective[] }>(['performance', 'goals'], '/app/performance/objectives', {
    enabled,
  })
  const cycleQuery = useAppQuery<{ cycle?: { name_en?: string; name_ar?: string } | null }>(
    ['performance', 'okr-cycle'],
    '/app/performance/okr-cycles/current',
    { enabled },
  )
  const align = readingEdgeAlign(isRTL)
  const cycle = cycleQuery.data?.cycle

  if (!enabled) return <FeatureUnavailableState feature="performance" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const rows = query.data?.objectives || []
  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('performance.goals')}</EditorialHeading>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.progress, align]}>
          {cycle
            ? `${t('performance.okrCycle')}: ${isRTL ? cycle.name_ar || cycle.name_en || '' : cycle.name_en || ''}`
            : t('performance.noOkrCycle')}
        </Text>
        {rows.length === 0 ? (
          <QuietEmpty title={t('performance.emptyGoals')} />
        ) : (
          rows.map((row) => (
            <View key={row.objective_id}>
              <Pressable onPress={() => router.push(`/performance/goals/${row.objective_id}`)}>
              <ListRow
                title={isRTL ? row.title_ar || row.title_en || '' : row.title_en || ''}
                subtitle={row.status}
                icon="flag-outline"
                showChevron
              />
              </Pressable>
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.progress, align]}>
                {row.rollup?.progress_pct == null
                  ? t('performance.progressUnknown')
                  : `${t('performance.progress')} ${row.rollup.progress_pct}%`}
              </Text>
            </View>
          ))
        )}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  progress: {
    marginTop: -spacing.sm,
    marginBottom: spacing.md,
    color: colors.textSecondary,
    fontSize: font.caption,
  },
})
