import { ScrollView, StyleSheet, Text, View } from 'react-native'

import { useI18n } from '@/i18n'
import { useAuth } from '@/auth/AuthProvider'
import { useAppQuery } from '@/lib/hooks'
import { Card, SectionTitle, StatusChip } from '@/components/ui'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { formatDate, formatTimeRange, statusLabel, statusTone } from '@/lib/format'
import { colors, font, spacing } from '@/theme'
import type { ShiftRow } from '@/api/types'

function ShiftCard({ shift, locale, statusLabel }: { shift: ShiftRow; locale: string; statusLabel: string }) {
  return (
    <Card>
      <View style={styles.cardHead}>
        <Text style={styles.date}>{formatDate(shift.shift_date, locale)}</Text>
        <StatusChip label={statusLabel} tone={statusTone(shift.status)} />
      </View>
      <Text style={styles.time}>{formatTimeRange(shift.start_time, shift.end_time)}</Text>
      {shift.role ? <Text style={styles.muted}>{shift.role}</Text> : null}
      {shift.location ? <Text style={styles.muted}>{shift.location}</Text> : null}
    </Card>
  )
}

export default function ShiftsScreen() {
  const { t, locale } = useI18n()
  const { hasFeature, refreshMe } = useAuth()
  const enabled = hasFeature('shifts')
  const today = useAppQuery<{ shifts: ShiftRow[] }>(['shifts', 'today'], '/app/shifts/today', { enabled })
  const upcoming = useAppQuery<{ shifts: ShiftRow[] }>(['shifts', 'upcoming'], '/app/shifts/upcoming', { enabled })

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />
  if (today.isLoading || upcoming.isLoading) return <LoadingState />
  if (today.isError) return <ErrorState error={today.error} onRetry={() => today.refetch()} />
  if (upcoming.isError) return <ErrorState error={upcoming.error} onRetry={() => upcoming.refetch()} />

  const todays = today.data?.shifts ?? []
  const next = upcoming.data?.shifts ?? []
  const labelForStatus = (s: string) => statusLabel(s, t)

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <SectionTitle>{t('shifts.today')}</SectionTitle>
      {todays.length ? (
        todays.map((s: ShiftRow) => <ShiftCard key={s.shift_id} shift={s} locale={locale} statusLabel={labelForStatus(s.status)} />)
      ) : (
        <Card>
          <Text style={styles.muted}>{t('home.noShiftToday')}</Text>
        </Card>
      )}

      <SectionTitle>{t('shifts.upcoming')}</SectionTitle>
      {next.length ? (
        next.map((s: ShiftRow) => <ShiftCard key={s.shift_id} shift={s} locale={locale} statusLabel={labelForStatus(s.status)} />)
      ) : (
        <EmptyState message={t('shifts.empty')} />
      )}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  date: { fontSize: font.small, color: colors.subtle, fontWeight: '600' },
  time: { fontSize: font.h2, fontWeight: '700', color: colors.text },
  muted: { fontSize: font.body, color: colors.subtle },
})
