import { useCallback, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import { PageBackButton } from '@/components/navigation/PageBackButton'
import { colors, font, spacing, typeScaling } from '@/theme'

type ProbationResponse = {
  empty?: boolean
  case?: {
    status?: string
    probation_start?: string
    probation_end?: string
    progress_percent?: number
  }
  milestones?: Array<{
    milestone_key: string
    title_en?: string
    title_ar?: string
    status?: string
    due_on?: string
    overdue?: boolean
    row_version?: number
  }>
  employee_actions?: Array<{ milestone_key: string }>
  outcome?: { status?: string; decided_at?: string } | null
  confidential_stripped?: boolean
}

/** Employee self-service probation — no confidential manager/HR notes. */
export default function ProbationScreen() {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const onBack = useEmployeeSafeBack()
  const { hasFeature, can, request } = useAuth()
  const enabled = hasFeature('probation')
  const canComplete = can('probation', 'complete_item')
  const query = useAppQuery<ProbationResponse>(['probation'], '/app/probation', {
    enabled,
    staleTime: 0,
  })
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const complete = useCallback(
    async (itemKey: string, rowVersion?: number) => {
      if (!canComplete) return
      setBusyKey(itemKey)
      try {
        await request(`/app/probation/milestones/${encodeURIComponent(itemKey)}`, {
          method: 'POST',
          json: { to_status: 'completed', expected_row_version: rowVersion },
        })
        await query.refetch()
      } finally {
        setBusyKey(null)
      }
    },
    [canComplete, query, request],
  )

  if (!enabled) {
    return <FeatureUnavailableState feature="probation" onBack={onBack} />
  }

  const data = query.data
  const milestones = data?.milestones || []
  const actionKeys = new Set((data?.employee_actions || []).map((a) => a.milestone_key))

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={query.isFetching}
        onRefresh={() => void query.refetch()}
      >
        <View style={styles.nav}>
          <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} />
        </View>
        <FadeIn>
          <EditorialHeading>{t('employeeProbation.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('employeeProbation.subtitle')}
          </Text>
          {data?.case?.probation_end ? (
            <Text style={[styles.meta, align]}>
              {t('employeeProbation.endDate')}: {String(data.case.probation_end).slice(0, 10)}
            </Text>
          ) : null}
          {data?.case?.status ? (
            <Text style={[styles.meta, align]}>
              {t('employeeProbation.status')}: {data.case.status}
            </Text>
          ) : null}
          <Text style={[styles.meta, align]}>
            {t('employeeProbation.progress')}: {Number(data?.case?.progress_percent || 0)}%
          </Text>
          {data?.outcome?.status ? (
            <Text style={[styles.outcome, align]}>
              {t('employeeProbation.outcome')}: {data.outcome.status}
            </Text>
          ) : null}
        </FadeIn>

        {query.isLoading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}
        {query.error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={() => void query.refetch()}
          />
        ) : null}

        {data?.empty ? <ListRow title={t('employeeProbation.empty')} icon="checkmark-circle-outline" /> : null}

        {!data?.empty ? (
          <>
            <SectionHeader title={t('employeeProbation.milestones')} />
            {milestones.map((m) => {
              const owned = actionKeys.size === 0 || actionKeys.has(m.milestone_key)
              const open = m.status === 'pending' || m.status === 'overdue'
              return (
                <View key={m.milestone_key} style={styles.card}>
                  <Text style={[styles.itemTitle, align]}>
                    {locale === 'ar' ? m.title_ar || m.title_en : m.title_en || m.milestone_key}
                  </Text>
                  <View style={styles.row}>
                    <StatusChip label={String(m.status || 'pending')} tone={m.overdue ? 'warning' : 'neutral'} />
                    <Text style={styles.meta}>{m.due_on}</Text>
                  </View>
                  {owned && open && canComplete ? (
                    <Pressable onPress={() => void complete(m.milestone_key, m.row_version)}>
                      <StatusChip
                        label={busyKey === m.milestone_key ? '…' : t('employeeProbation.complete')}
                        tone="info"
                      />
                    </Pressable>
                  ) : null}
                </View>
              )
            })}
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  nav: { marginBottom: spacing.sm },
  subtitle: { ...font.body, color: colors.textSecondary, marginTop: spacing.xs },
  meta: { ...font.caption, color: colors.textSecondary, marginTop: spacing.xs },
  outcome: { ...font.bodyStrong, color: colors.textPrimary, marginTop: spacing.sm },
  card: {
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  itemTitle: { ...font.bodyStrong, color: colors.textPrimary },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
})
