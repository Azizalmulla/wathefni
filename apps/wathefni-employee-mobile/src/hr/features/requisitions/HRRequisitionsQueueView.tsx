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
  requisition_id: string
  title_en?: string
  title_ar?: string
  status: string
  headcount?: number
  department?: string | null
  decision_required?: boolean
  needs_attention?: boolean
}

/** HR Mobile companion — Needs Approval / Open to fill (no heavy admin). */
export function HRRequisitionsQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'requisitions')
  const [view, setView] = useState<'attention' | 'pending_approval' | 'approved' | 'open' | 'draft'>(
    'attention',
  )
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = async () => {
    if (!me || !permitted) return
    setLoading(true)
    setError(false)
    try {
      const res = await request<{ requisitions?: Row[] }>(
        `/dashboard/mobile/requisitions?view=${encodeURIComponent(view)}&limit=50`,
      )
      setRows(res.requisitions || [])
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
          <EditorialHeading>{t('hrRequisitions.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrRequisitions.subtitle')}
          </Text>
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrRequisitions.permissionTitle')}
            subtitle={t('hrRequisitions.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted ? (
          <View style={styles.chips}>
            {(['attention', 'pending_approval', 'approved', 'open', 'draft'] as const).map((v) => (
              <Pressable key={v} onPress={() => setView(v)}>
                <StatusChip label={t(`hrRequisitions.view.${v}`)} tone={view === v ? 'info' : 'neutral'} />
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
            <SectionHeader title={t(`hrRequisitions.view.${view}`)} />
            {rows.length === 0 ? (
              <ListRow title={t('hrRequisitions.empty')} icon="checkmark-circle-outline" />
            ) : (
              rows.map((item) => (
                <ListRow
                  key={item.requisition_id}
                  title={
                    locale === 'ar'
                      ? item.title_ar || item.title_en || item.requisition_id
                      : item.title_en || item.requisition_id
                  }
                  subtitle={`${t('hrRequisitions.headcount')}: ${item.headcount ?? '—'}${
                    item.department ? ` · ${item.department}` : ''
                  }${item.decision_required ? ` · ${t('hrRequisitions.decisionRequired')}` : ''}`}
                  icon="briefcase-outline"
                  showChevron
                  onPress={() =>
                    router.push(toHrPath(`/hr/requisitions/${encodeURIComponent(item.requisition_id)}`))
                  }
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
