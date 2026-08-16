import { useCallback, useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { can, routeAvailable } from '@hr/capabilities'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Req = {
  requisition_id: string
  title_en?: string
  title_ar?: string
  status: string
  headcount?: number
  department?: string | null
  target_hire_date?: string | null
  row_version?: number
  decision_required?: boolean
}

/** HR Mobile requisition detail — approve/reject only when capability permits (SoD on server). */
export function HRRequisitionDetailView() {
  const { requisitionId } = useLocalSearchParams<{ requisitionId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'requisitions')
  const canApprove = can(me, 'recruiting', 'requisitions_review', 'approve')
  const canManage = can(me, 'recruiting', 'requisitions_review', 'manage')
  const [req, setReq] = useState<Req | null>(null)
  const [events, setEvents] = useState<Array<{ event_type?: string; created_at?: string }>>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    if (!me || !permitted || !requisitionId) return
    setError(false)
    try {
      const res = await request<{
        requisition?: Req
        events?: Array<{ event_type?: string; created_at?: string }>
      }>(`/dashboard/mobile/requisitions/${encodeURIComponent(String(requisitionId))}`)
      setReq(res.requisition || null)
      setEvents(res.events || [])
    } catch {
      setError(true)
    }
  }, [me, permitted, request, requisitionId])

  useEffect(() => {
    void load()
  }, [load])

  const transition = async (to_status: string) => {
    if (!requisitionId || !req) return
    setBusy(to_status)
    try {
      await request(`/dashboard/mobile/requisitions/${encodeURIComponent(String(requisitionId))}/transition`, {
        method: 'POST',
        json: { to_status, expected_row_version: req.row_version },
      })
      await load()
    } finally {
      setBusy(null)
    }
  }

  if (!me) return null

  const title =
    locale === 'ar' ? req?.title_ar || req?.title_en : req?.title_en || req?.title_ar

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={false} onRefresh={() => void load()}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn>
          <EditorialHeading>{title || t('hrRequisitions.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
            {String(req?.status || '')} · {t('hrRequisitions.headcount')}: {req?.headcount ?? '—'}
          </Text>
          {req?.decision_required ? (
            <Text style={[styles.warn, align]}>{t('hrRequisitions.decisionRequired')}</Text>
          ) : null}
          <Text style={[styles.note, align]}>{t('hrRequisitions.sodNote')}</Text>
        </FadeIn>

        {!permitted ? <ListRow title={t('hrRequisitions.permissionTitle')} icon="lock-closed-outline" /> : null}
        {error ? <ListRow title={t('home.dataUnavailable')} icon="cloud-offline-outline" emphasis="warning" /> : null}

        {permitted && req ? (
          <>
            <SectionHeader title={t('hrRequisitions.actions')} />
            {canManage && req.status === 'draft' ? (
              <Pressable onPress={() => void transition('pending_approval')}>
                <StatusChip
                  label={busy === 'pending_approval' ? '…' : t('hrRequisitions.submit')}
                  tone="info"
                />
              </Pressable>
            ) : null}
            {canApprove && req.status === 'pending_approval' ? (
              <View style={styles.actions}>
                <Pressable onPress={() => void transition('approved')}>
                  <StatusChip
                    label={busy === 'approved' ? '…' : t('hrRequisitions.approve')}
                    tone="info"
                  />
                </Pressable>
                <Pressable onPress={() => void transition('rejected')}>
                  <StatusChip
                    label={busy === 'rejected' ? '…' : t('hrRequisitions.reject')}
                    tone="warning"
                  />
                </Pressable>
              </View>
            ) : null}
            {canManage && req.status === 'approved' ? (
              <Pressable onPress={() => void transition('open')}>
                <StatusChip label={busy === 'open' ? '…' : t('hrRequisitions.open')} tone="info" />
              </Pressable>
            ) : null}

            <SectionHeader title={t('hrRequisitions.history')} />
            {events.length === 0 ? (
              <ListRow title={t('hrRequisitions.emptyHistory')} icon="time-outline" />
            ) : (
              events.slice(0, 12).map((e, i) => (
                <ListRow
                  key={`${e.created_at}-${i}`}
                  title={String(e.event_type || 'event')}
                  subtitle={String(e.created_at || '').slice(0, 19)}
                  icon="git-commit-outline"
                />
              ))
            )}
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: { fontSize: font.body, color: colors.textSecondary, marginTop: spacing.xs },
  warn: { fontSize: font.body, color: colors.warning, marginTop: spacing.sm },
  note: { fontSize: font.small, color: colors.textSecondary, marginTop: spacing.sm },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
})
