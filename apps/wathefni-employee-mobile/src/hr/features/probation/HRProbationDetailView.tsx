import { useCallback, useEffect, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Milestone = {
  milestone_key: string
  title_en?: string
  title_ar?: string
  due_on?: string
  status?: string
  overdue?: boolean
  row_version?: number
}

/** HR Mobile probation detail — milestones + recommend; finalize only with decide. */
export function HRProbationDetailView() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'probation')
  const [caseRow, setCaseRow] = useState<Record<string, unknown> | null>(null)
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [perms, setPerms] = useState<{ decide?: boolean; recommend?: boolean }>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    if (!me || !permitted || !caseId) return
    setError(false)
    try {
      const res = await request<{
        case?: Record<string, unknown>
        milestones?: Milestone[]
        permissions?: { decide?: boolean; recommend?: boolean }
      }>(`/dashboard/mobile/probation/${encodeURIComponent(String(caseId))}`)
      setCaseRow(res.case || null)
      setMilestones(res.milestones || [])
      setPerms(res.permissions || {})
    } catch {
      setError(true)
    }
  }, [caseId, me, permitted, request])

  useEffect(() => {
    void load()
  }, [load])

  const recommend = async (recommendation: 'confirm' | 'extend' | 'fail') => {
    if (!caseId) return
    setBusy(recommendation)
    try {
      await request(`/dashboard/mobile/probation/${encodeURIComponent(String(caseId))}/recommend`, {
        method: 'POST',
        json: { recommendation, notes: `mobile:${recommendation}` },
      })
      await load()
    } finally {
      setBusy(null)
    }
  }

  const decide = async (to_status: 'confirmed' | 'failed') => {
    if (!caseId || !perms.decide) return
    setBusy(to_status)
    try {
      await request(`/dashboard/mobile/probation/${encodeURIComponent(String(caseId))}/transition`, {
        method: 'POST',
        json: { to_status, decision_reason: `mobile_${to_status}` },
      })
      await load()
    } finally {
      setBusy(null)
    }
  }

  const completeMs = async (key: string, rowVersion?: number) => {
    if (!caseId) return
    setBusy(key)
    try {
      await request(
        `/dashboard/mobile/probation/${encodeURIComponent(String(caseId))}/milestones/${encodeURIComponent(key)}`,
        { method: 'POST', json: { to_status: 'completed', expected_row_version: rowVersion } },
      )
      await load()
    } finally {
      setBusy(null)
    }
  }

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={false} onRefresh={() => void load()}>
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn>
          <EditorialHeading>
            {String(caseRow?.employee_name || caseRow?.employee_key || t('hrProbation.title'))}
          </EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.meta, align]}>
            {String(caseRow?.status || '')} · {t('hrProbation.end')}:{' '}
            {String(caseRow?.probation_end || '').slice(0, 10)}
          </Text>
          {caseRow?.decision_required ? (
            <Text style={[styles.warn, align]}>{t('hrProbation.decisionRequired')}</Text>
          ) : null}
          <Text style={[styles.note, align]}>{t('hrProbation.managerNote')}</Text>
        </FadeIn>

        {!permitted ? <ListRow title={t('hrProbation.permissionTitle')} icon="lock-closed-outline" /> : null}
        {error ? <ListRow title={t('home.dataUnavailable')} icon="cloud-offline-outline" emphasis="warning" /> : null}

        {permitted ? (
          <>
            <SectionHeader title={t('hrProbation.milestones')} />
            {milestones.map((m) => (
              <View key={m.milestone_key} style={styles.card}>
                <Text style={[styles.itemTitle, align]}>
                  {locale === 'ar' ? m.title_ar || m.title_en : m.title_en || m.milestone_key}
                </Text>
                <View style={styles.row}>
                  <StatusChip
                    label={String(m.status || 'pending')}
                    tone={m.overdue || m.status === 'overdue' ? 'warning' : 'neutral'}
                  />
                  <Text style={styles.meta}>
                    {m.due_on}
                    {m.overdue ? ` · ${t('hrProbation.overdue')}` : ''}
                  </Text>
                </View>
                {m.status === 'pending' || m.status === 'overdue' ? (
                  <Pressable onPress={() => void completeMs(m.milestone_key, m.row_version)}>
                    <StatusChip
                      label={busy === m.milestone_key ? '…' : t('hrProbation.complete')}
                      tone="info"
                    />
                  </Pressable>
                ) : null}
              </View>
            ))}

            <SectionHeader title={t('hrProbation.actions')} />
            {perms.recommend !== false ? (
              <View style={styles.actions}>
                <Pressable onPress={() => void recommend('confirm')}>
                  <StatusChip
                    label={busy === 'confirm' ? '…' : t('hrProbation.recommendConfirm')}
                    tone="info"
                  />
                </Pressable>
                <Pressable onPress={() => void recommend('extend')}>
                  <StatusChip
                    label={busy === 'extend' ? '…' : t('hrProbation.recommendExtend')}
                    tone="neutral"
                  />
                </Pressable>
                <Pressable onPress={() => void recommend('fail')}>
                  <StatusChip
                    label={busy === 'fail' ? '…' : t('hrProbation.recommendFail')}
                    tone="warning"
                  />
                </Pressable>
              </View>
            ) : null}
            {perms.decide ? (
              <View style={styles.actions}>
                <Pressable onPress={() => void decide('confirmed')}>
                  <StatusChip
                    label={busy === 'confirmed' ? '…' : t('hrProbation.confirm')}
                    tone="info"
                  />
                </Pressable>
                <Pressable onPress={() => void decide('failed')}>
                  <StatusChip label={busy === 'failed' ? '…' : t('hrProbation.fail')} tone="warning" />
                </Pressable>
              </View>
            ) : null}
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  meta: { ...font.body, color: colors.textSecondary, marginTop: spacing.xs },
  warn: { ...font.body, color: colors.warning, marginTop: spacing.sm },
  note: { ...font.caption, color: colors.textSecondary, marginTop: spacing.sm },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
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
