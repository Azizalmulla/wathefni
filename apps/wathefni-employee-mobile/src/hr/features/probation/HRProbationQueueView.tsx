import { useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Row = {
  case_id: string
  employee_key: string
  employee_name?: string
  status: string
  probation_end?: string | null
  decision_required?: boolean
  needs_attention?: boolean
  milestones_summary?: { overdue?: number; open?: number }
  next_milestone?: { title_en?: string; due_on?: string } | null
}

/** HR Mobile companion — Needs Attention / Reviews Due / Upcoming (no admin). */
export function HRProbationQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'probation')
  const [view, setView] = useState<'attention' | 'reviews_due' | 'upcoming' | 'active'>('attention')
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = async () => {
    if (!me || !permitted) return
    setLoading(true)
    setError(false)
    try {
      const res = await request<{ cases?: Row[] }>(
        `/dashboard/mobile/probation?view=${encodeURIComponent(view)}&limit=50`,
      )
      setRows(res.cases || [])
    } catch {
      setError(true)
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, me?.principal.user_id, permitted])

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={loading}
        onRefresh={() => {
          void refreshMe()
          void load()
        }}
      >
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn>
          <EditorialHeading>{t('hrProbation.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrProbation.subtitle')}
          </Text>
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrProbation.permissionTitle')}
            subtitle={t('hrProbation.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted ? (
          <View style={styles.chips}>
            {(['attention', 'reviews_due', 'upcoming', 'active'] as const).map((v) => (
              <Pressable key={v} onPress={() => setView(v)}>
                <StatusChip label={t(`hrProbation.view.${v}`)} tone={view === v ? 'info' : 'neutral'} />
              </Pressable>
            ))}
          </View>
        ) : null}

        {permitted && loading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}
        {permitted && error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={() => void load()}
          />
        ) : null}

        {permitted && !loading && !error ? (
          <View>
            <SectionHeader title={t(`hrProbation.view.${view}`)} />
            {rows.length === 0 ? (
              <ListRow title={t('hrProbation.empty')} icon="checkmark-circle-outline" />
            ) : (
              rows.map((item) => (
                <ListRow
                  key={item.case_id}
                  title={String(item.employee_name || item.employee_key)}
                  subtitle={`${item.status}${item.probation_end ? ` · ${String(item.probation_end).slice(0, 10)}` : ''}${
                    item.decision_required ? ` · ${t('hrProbation.decisionRequired')}` : ''
                  }`}
                  icon="timer-outline"
                  showChevron
                  emphasis={item.needs_attention ? 'warning' : undefined}
                  onPress={() => router.push(toHrPath(`/probation/${item.case_id}`))}
                />
              ))
            )}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  subtitle: { ...font.body, color: colors.textSecondary, marginTop: spacing.xs },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
})
