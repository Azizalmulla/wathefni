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
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Row = {
  case_id: string
  status?: string
  summary_en?: string
  summary_ar?: string
  destination?: string
}

export function HREmployeeRelationsQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'employee-relations')
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = async () => {
    if (!me || !permitted) return
    setLoading(true)
    setError(false)
    try {
      const res = await request<{ items?: Row[] }>('/dashboard/mobile/employee-relations?limit=50')
      setRows(res.items || [])
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
  }, [me?.principal.user_id, permitted])

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
          <EditorialHeading>{t('hrEmployeeRelations.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrEmployeeRelations.subtitle')}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrEmployeeRelations.privacy')}
          </Text>
        </FadeIn>
        {!permitted ? (
          <ListRow
            title={t('hrEmployeeRelations.permissionTitle')}
            subtitle={t('hrEmployeeRelations.permissionBody')}
            icon="lock-closed-outline"
          />
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
            <SectionHeader title={t('hrEmployeeRelations.queue')} />
            {rows.length === 0 ? (
              <ListRow title={t('hrEmployeeRelations.empty')} icon="checkmark-circle-outline" />
            ) : (
              rows.map((item) => (
                <Pressable
                  key={item.case_id}
                  onPress={() => router.push(toHrPath(item.destination || `/employee-relations/${item.case_id}`))}
                >
                  <ListRow
                    title={isRTL ? item.summary_ar || item.summary_en || '' : item.summary_en || ''}
                    subtitle={item.status || ''}
                    icon="shield-checkmark-outline"
                    showChevron
                  />
                </Pressable>
              ))
            )}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  subtitle: {
    marginTop: spacing.sm,
    color: colors.textSecondary,
    fontSize: font.body,
  },
})
