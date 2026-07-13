import { ScrollView, StyleSheet, Text, View } from 'react-native'

import { useI18n } from '@/i18n'
import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { Card, StatusChip } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { formatDate, statusLabel, statusTone } from '@/lib/format'
import { colors, font, spacing } from '@/theme'
import type { AttendanceResponse, AttendanceRow } from '@/api/types'

export default function AttendanceScreen() {
  const { t, locale } = useI18n()
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('attendance')
  const query = useAppQuery<AttendanceResponse>(['attendance'], '/app/attendance', { enabled })

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />

  const data = query.data
  const records = data?.records ?? []

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {data ? (
        <Card>
          <View style={styles.summary}>
            <Summary label={t('attendance.present')} value={data.summary.present} tone={colors.success} />
            <Summary label={t('attendance.late')} value={data.summary.late} tone={colors.warning} />
            <Summary label={t('attendance.absent')} value={data.summary.absent} tone={colors.danger} />
          </View>
        </Card>
      ) : null}

      {records.length ? (
        records.map((r: AttendanceRow, idx: number) => (
          <Card key={`${r.attendance_date}-${idx}`}>
            <View style={styles.row}>
              <Text style={styles.date}>{formatDate(r.attendance_date, locale)}</Text>
              <StatusChip label={statusLabel(r.status, t)} tone={statusTone(r.status)} />
            </View>
          </Card>
        ))
      ) : (
        <EmptyState message={t('attendance.empty')} />
      )}
    </ScrollView>
  )
}

function Summary({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <View style={styles.summaryItem}>
      <Text style={[styles.summaryValue, { color: tone }]}>{value}</Text>
      <Text style={styles.summaryLabel}>{label}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  summary: { flexDirection: 'row', justifyContent: 'space-around' },
  summaryItem: { alignItems: 'center', gap: spacing.xs },
  summaryValue: { fontSize: font.h1, fontWeight: '800' },
  summaryLabel: { fontSize: font.small, color: colors.subtle },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  date: { fontSize: font.body, color: colors.text, fontWeight: '500' },
})
