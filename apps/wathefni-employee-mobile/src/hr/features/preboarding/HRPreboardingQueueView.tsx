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
  assignment_id: string
  employee_key: string
  employee_name?: string
  status: string
  joining_date?: string | null
  is_joining?: boolean
  items_summary?: { overdue?: number; required_open?: number }
}

/**
 * HR Mobile companion — Needs Attention + Joining Soon (no template admin).
 */
export function HRPreboardingQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'preboarding')
  const [view, setView] = useState<'attention' | 'joining_soon' | 'ready' | 'blocked'>('attention')
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = async () => {
    if (!me || !permitted) return
    setLoading(true)
    setError(false)
    try {
      const res = await request<{ assignments?: Row[] }>(
        `/dashboard/mobile/preboarding?view=${encodeURIComponent(view)}&limit=50`,
      )
      setRows(res.assignments || [])
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
          <EditorialHeading>{t('hrPreboarding.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrPreboarding.subtitle')}
          </Text>
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrPreboarding.permissionTitle')}
            subtitle={t('hrPreboarding.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted ? (
          <View style={styles.chips}>
            {(['attention', 'joining_soon', 'blocked', 'ready'] as const).map((v) => (
              <Pressable key={v} onPress={() => setView(v)}>
                <StatusChip label={t(`hrPreboarding.view.${v}`)} tone={view === v ? 'info' : 'neutral'} />
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
            <SectionHeader title={t(`hrPreboarding.view.${view}`)} />
            {rows.length === 0 ? (
              <ListRow title={t('hrPreboarding.empty')} icon="checkmark-circle-outline" />
            ) : (
              rows.map((item) => (
                <ListRow
                  key={item.assignment_id}
                  title={item.employee_name || item.employee_key}
                  subtitle={`${item.status} · ${item.joining_date || '—'} · ${t('hrPeople.chipJoining')}`}
                  icon="person-outline"
                  showChevron
                  emphasis={item.status === 'blocked' ? 'warning' : undefined}
                  onPress={() =>
                    router.push(toHrPath(`/preboarding/${encodeURIComponent(item.assignment_id)}`) as never)
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
  subtitle: { fontSize: font.body, color: colors.textSecondary, marginTop: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
})
