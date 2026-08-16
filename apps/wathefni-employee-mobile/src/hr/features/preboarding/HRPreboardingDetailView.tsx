import { useEffect, useState } from 'react'
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

type Item = {
  item_key: string
  title_en?: string
  title_ar?: string
  owner_role?: string
  status?: string
  required?: boolean
  overdue?: boolean
  row_version?: number
}

/**
 * HR Mobile detail — review / waive only (canonical actions).
 */
export function HRPreboardingDetailView() {
  const { assignmentId } = useLocalSearchParams<{ assignmentId: string }>()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'preboarding')
  const [assignment, setAssignment] = useState<Record<string, unknown> | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const load = async () => {
    if (!assignmentId || !permitted) return
    setLoading(true)
    try {
      const res = await request<{
        assignment?: Record<string, unknown>
        items?: Item[]
      }>(`/dashboard/mobile/preboarding/${encodeURIComponent(String(assignmentId))}`)
      setAssignment(res.assignment || null)
      setItems(res.items || [])
    } catch {
      setAssignment(null)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignmentId, permitted])

  const waive = async (itemKey: string) => {
    setBusyKey(itemKey)
    try {
      await request(`/dashboard/mobile/preboarding/${encodeURIComponent(String(assignmentId))}/items/${encodeURIComponent(itemKey)}/waive`, {
        method: 'POST',
        json: { waive_reason: 'hr_mobile_waive' },
      })
      await load()
    } finally {
      setBusyKey(null)
    }
  }

  const markDone = async (itemKey: string, rowVersion?: number) => {
    setBusyKey(itemKey)
    try {
      await request(`/dashboard/mobile/preboarding/${encodeURIComponent(String(assignmentId))}/items/${encodeURIComponent(itemKey)}`, {
        method: 'POST',
        json: { to_status: 'done', expected_row_version: rowVersion },
      })
      await load()
    } finally {
      setBusyKey(null)
    }
  }

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
          <EditorialHeading>
            {String(assignment?.employee_name || assignment?.employee_key || t('hrPreboarding.title'))}
          </EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {String(assignment?.status || '')} · {String(assignment?.joining_date || '—')} · {t('hrPeople.chipJoining')}
          </Text>
        </FadeIn>

        {!permitted ? (
          <ListRow title={t('hrPreboarding.permissionTitle')} icon="lock-closed-outline" />
        ) : null}

        {permitted ? (
          <View>
            <SectionHeader title={t('hrPreboarding.items')} />
            {items.map((item) => (
              <View key={item.item_key} style={styles.itemCard}>
                <Text style={[styles.itemTitle, align]}>
                  {locale === 'ar' ? item.title_ar || item.title_en : item.title_en || item.item_key}
                </Text>
                <View style={styles.row}>
                  <StatusChip label={String(item.status || 'pending')} tone={item.status === 'blocked' ? 'warning' : 'neutral'} />
                  <Text style={styles.meta}>
                    {item.owner_role}
                    {item.required ? ` · ${t('hrPreboarding.required')}` : ''}
                    {item.overdue ? ` · ${t('hrPreboarding.overdue')}` : ''}
                  </Text>
                </View>
                {item.status !== 'done' && item.status !== 'waived' ? (
                  <View style={styles.actions}>
                    <Pressable onPress={() => void markDone(item.item_key, item.row_version)}>
                      <StatusChip
                        label={busyKey === item.item_key ? '…' : t('hrPreboarding.markDone')}
                        tone="info"
                      />
                    </Pressable>
                    <Pressable onPress={() => void waive(item.item_key)}>
                      <StatusChip label={t('hrPreboarding.waive')} tone="neutral" />
                    </Pressable>
                  </View>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  subtitle: { ...font.body, color: colors.textSecondary, marginTop: spacing.sm },
  itemCard: {
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  itemTitle: { ...font.bodyStrong, color: colors.textPrimary },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.sm },
  meta: { ...font.caption, color: colors.textSecondary },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
})
