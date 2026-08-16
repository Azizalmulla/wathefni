import { useEffect, useState } from 'react'
import { StyleSheet, Text } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Summary = {
  case_id?: string
  status?: string
  status_label_en?: string
  status_label_ar?: string
  summary_en?: string
  summary_ar?: string
  web_deep_link?: string
}

export function HREmployeeRelationsCaseView() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>()
  const onBack = useHrSafeBack()
  const { request } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const [detail, setDetail] = useState<Summary | null>(null)
  const [error, setError] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    if (!caseId) return
    setError(false)
    setForbidden(false)
    try {
      setDetail(await request<Summary>(`/dashboard/mobile/employee-relations/cases/${caseId}`))
    } catch (err) {
      const status = Number((err as { status?: number })?.status || 0)
      setForbidden(status === 403)
      setError(status !== 403)
      setDetail(null)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} onRefresh={() => void load()}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <EditorialHeading>{t('hrEmployeeRelations.detail')}</EditorialHeading>
        {forbidden ? (
          <ListRow title={t('hrEmployeeRelations.permissionTitle')} subtitle={t('hrEmployeeRelations.permissionBody')} icon="lock-closed-outline" />
        ) : null}
        {error ? (
          <ListRow title={t('home.dataUnavailable')} icon="cloud-offline-outline" emphasis="warning" onPress={() => void load()} />
        ) : null}
        {detail ? (
          <>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {isRTL ? detail.status_label_ar || detail.status : detail.status_label_en || detail.status}
            </Text>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {isRTL ? detail.summary_ar || detail.summary_en : detail.summary_en || ''}
            </Text>
            <PremiumButton
              label={t('hrEmployeeRelations.acknowledge')}
              loading={saving}
              onPress={() => {
                void (async () => {
                  setSaving(true)
                  try {
                    await request(`/dashboard/mobile/employee-relations/cases/${caseId}/acknowledge`, {
                      method: 'POST',
                    })
                    await load()
                  } catch {
                    setError(true)
                  } finally {
                    setSaving(false)
                  }
                })()
              }}
            />
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
              {t('hrEmployeeRelations.openWeb')}
            </Text>
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: {
    color: colors.textSecondary,
    fontSize: font.body,
  },
})
