import { useCallback } from 'react'
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { Button, Card, SectionTitle, StatusChip } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { formatDate, statusLabel, statusTone } from '@/lib/format'
import { colors, font, spacing } from '@/theme'
import type { LeaveBalance, LeaveRequestRow, LeaveResponse } from '@/api/types'

export default function LeaveScreen() {
  const { t, locale } = useI18n()
  const { request, hasFeature, can, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const enabled = hasFeature('leave')
  const query = useAppQuery<LeaveResponse>(['leave'], '/app/leave', { enabled })

  const onCancel = useCallback(
    (leaveId: string) => {
      Alert.alert(t('leave.cancel'), undefined, [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('leave.cancel'),
          style: 'destructive',
          onPress: async () => {
            try {
              await request(`/app/leave/${leaveId}/cancel`, { method: 'POST' })
              await queryClient.invalidateQueries({ queryKey: ['leave'] })
            } catch (err) {
              Alert.alert(t('common.error'), approvedErrorMessage(err, t))
            }
          },
        },
      ])
    },
    [request, queryClient, t],
  )

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />

  const data = query.data
  const requests = data?.requests ?? []
  const labelForStatus = (s: string) => statusLabel(s, t)

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {can('leave', 'request') ? <Button label={t('leave.request')} onPress={() => router.push('/leave/request')} /> : null}

      {data?.balances_enabled && data.balances.length ? (
        <Card>
          <SectionTitle>{t('leave.balance')}</SectionTitle>
          {data.balances.map((b: LeaveBalance) => (
            <View key={`${b.leave_type}-${b.period_year ?? ''}`} style={styles.balanceRow}>
              <Text style={styles.balanceType}>{cap(b.leave_type)}</Text>
              <Text style={styles.balanceDays}>{fmtDays(b.balance_days)}</Text>
            </View>
          ))}
          <Text style={styles.notEnforced}>{t('leave.notEnforced')}</Text>
        </Card>
      ) : null}

      <SectionTitle>{t('leave.requests')}</SectionTitle>
      {requests.length ? (
        requests.map((r: LeaveRequestRow) => (
          <Card key={r.leave_id}>
            <View style={styles.cardHead}>
              <Text style={styles.range}>
                {formatDate(r.start_date, locale)} – {formatDate(r.end_date, locale)}
              </Text>
              <StatusChip label={labelForStatus(r.status)} tone={statusTone(r.status)} />
            </View>
            {r.leave_type ? <Text style={styles.muted}>{r.leave_type}</Text> : null}
            {can('leave', 'cancel') && ['requested', 'approved'].includes((r.status || '').toLowerCase()) ? (
              <Button label={t('leave.cancel')} variant="secondary" onPress={() => onCancel(r.leave_id)} />
            ) : null}
          </Card>
        ))
      ) : (
        <EmptyState message={t('leave.empty')} />
      )}
    </ScrollView>
  )
}

function cap(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : ''
}

function fmtDays(value: number | undefined): string {
  if (value === undefined || value === null) return '—'
  return `${value}`
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  balanceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.xs },
  balanceType: { fontSize: font.body, color: colors.text, fontWeight: '500' },
  balanceDays: { fontSize: font.h3, color: colors.text, fontWeight: '700' },
  notEnforced: { fontSize: font.tiny, color: colors.subtle, marginTop: spacing.xs },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  range: { fontSize: font.body, fontWeight: '600', color: colors.text, flexShrink: 1 },
  muted: { fontSize: font.small, color: colors.subtle },
})
